#!/usr/bin/env python3
"""Build a Senegal malaria molecular-surveillance report from real assay outputs.

This is the single entrypoint the WDL tasks call, for all three assays. It is the
*stable contract*: the flags below are the interface, and changing how the report looks
must not change them. Rendering evolves through three escape hatches instead:

  --template     supply a different report template (the HTML/JS that draws everything)
  --reference    supply updated reference data (boundaries, WHO compendium, schemas)
  --config       a JSON file of settings; unknown keys are passed through to the report's
                 metadata, so a new template can read new settings with no WDL change

Usage:
  make_report.py --assay WGS        --sample-table sample.tsv ...
  make_report.py --assay MAD4HATTER --resmarker-table r1.txt r2.txt --site-metadata m.csv
                                    [--allele-table a1.txt ...]
  make_report.py --assay NOMADS     --marker-calls calls.tsv [--site-metadata m.csv]

Always:
  --out-html report.html --out-data-json data.json [--out-csv-dir csv/]
"""
import argparse, base64, csv, gzip, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Settings that belong to the report model rather than the template. Anything else in the
# config file is merged into DATA.meta untouched, which is what lets a new template take
# new settings without a new WDL input.
MODEL_SETTINGS = {
    'min_samples':        ('MIN_SAMPLES', int),
    'marker_action_pct':  ('MARKER_PCT', float),
    'min_frame_n':        ('MIN_FRAME_N', int),
}
META_PASSTHROUGH_SKIP = set(MODEL_SETTINGS)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Build a malaria molecular-surveillance report.')
    # AMPLICON detects the panel from the loci in the input. MAD4HATTER and PFPHAST still
    # work and are treated as declarations: they are honoured, and a disagreement with the
    # detected panel is reported rather than silently accepted.
    p.add_argument('--assay', required=True,
                   choices=['WGS', 'AMPLICON', 'MAD4HATTER', 'PFPHAST', 'NOMADS'],
                   help='AMPLICON detects which amplicon panel produced the input from its '
                        'loci; MAD4HATTER and PFPHAST declare it explicitly')

    # WGS
    p.add_argument('--sample-table', help='WGS: Terra export of the sample table (TSV)')
    # MAD4HATTER
    p.add_argument('--resmarker-table', nargs='*', default=[],
                   help='MAD4HATTER: resmarker_table.txt files, one per sequencing run')
    p.add_argument('--allele-table', nargs='*', default=[],
                   help='MAD4HATTER: allele_data.txt files (optional)')
    # NOMADS
    p.add_argument('--marker-calls', nargs='*', default=[],
                   help='NOMADS: marker-calls tables (see load_nomads.py for the schema)')
    # shared
    p.add_argument('--site-metadata', help='Per-sample site/coordinate table (MAD4HATTER, NOMADS)')

    # sample selection
    p.add_argument('--sample-ids', default=None,
                   help='Restrict the report to these samples: a file with one sample id per '
                        'line (# comments allowed) or a comma-separated list. Omit to use every '
                        'sample in the inputs.')
    p.add_argument('--selection-label', default=None,
                   help='Human-readable name for the selection, shown in the report '
                        '(e.g. a Terra sample_set name)')

    # country / geography
    p.add_argument('--country-iso3', default=None,
                   help='ISO3 country code selecting the admin-2 boundary set '
                        '(reference/adm2/<ISO3>_adm2_map.json.gz). Default SEN.')
    p.add_argument('--country-name', default=None, help='Country name shown in the report')

    # stable knobs
    p.add_argument('--version-label', default=None, help='Version string stamped on the report')
    p.add_argument('--data-source', default=None, help='Provenance line shown in the report banner')
    p.add_argument('--config', default=None, help='JSON settings file (see module docstring)')
    p.add_argument('--template', default=None, help='Report template override (HTML)')
    p.add_argument('--reference', default=None, help='Reference data directory override')
    p.add_argument('--schemas', default=None, help='Export-schema directory override')

    # outputs
    p.add_argument('--out-html', required=True)
    p.add_argument('--out-data-json', required=True)
    p.add_argument('--out-csv-dir', default=None, help='Write each export view out as CSV')
    p.add_argument('--out-location-audit', default=None,
                   help='Write the location-resolution audit as TSV: how each sample was '
                        'placed, every unplaced name with spelling suggestions, and every '
                        'coordinate/name disagreement')
    return p.parse_args(argv)


def load_config(path):
    if not path:
        return {}
    with open(path) as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        raise SystemExit(f'--config must contain a JSON object, got {type(cfg).__name__}')
    return cfg


def main(argv=None):
    a = parse_args(argv)
    cfg = load_config(a.config)

    # reference/schema overrides have to be in place before gen_reports is imported,
    # because it loads the projected map and the PHA4GE field order at import time
    if a.reference:
        os.environ['MALARIA_REPORTS_REF_DIR'] = a.reference
    if a.schemas:
        os.environ['MALARIA_REPORTS_SCHEMA_DIR'] = a.schemas

    sys.path.insert(0, HERE)
    import gen_reports as G

    # model-level settings from the config file
    for key, (const, cast) in MODEL_SETTINGS.items():
        if key in cfg:
            setattr(G, const, cast(cfg[key]))

    # geography first: the model's districts, point-in-polygon index and map all derive
    # from the selected country, and the loaders read them at import time
    iso = a.country_iso3 or cfg.get('country_iso3')
    cname = a.country_name or cfg.get('country_name')
    country_note = None

    # No country given? Read it out of the data rather than defaulting to Senegal and
    # dropping every sample. A country column is already required-ish for a surveillance
    # table, and this is the failure the default caused in the first real Terra run.
    if not iso:
        import countries as C
        tables = ([a.sample_table] if a.sample_table else []) + \
                 list(a.resmarker_table or []) + list(a.marker_calls or []) + \
                 ([a.site_metadata] if a.site_metadata else [])
        raw, counts = C.sniff(tables)
        if raw:
            hit = C.resolve(raw)
            if hit and hit['has_map']:
                iso, cname = hit['iso3'], cname or hit['name']
                how = hit['how'] + ('' if hit['score'] == 1.0 else f" {hit['score']}")
                country_note = (f"country taken from the data: {raw!r} -> {hit['iso3']} "
                                f"({hit['name']}) via {how}")
                if hit['how'] == 'fuzzy':
                    country_note += '  -- a spelling guess; check it'
                if len(counts) > 1:
                    others = ', '.join(f'{k!r} x{v}' for k, v in
                                       sorted(counts.items(), key=lambda kv: -kv[1])[1:4])
                    country_note += f'; the table also names {others}'
                sys.stderr.write(f'[make_report] {country_note}\n')
            elif hit:
                raise SystemExit(
                    f'the data says country {raw!r} ({hit["iso3"]} {hit["name"]}), but no '
                    f'admin boundary map is shipped for it. Add one with '
                    f'scripts/build_maps.py and supply it through reference_bundle_tar, '
                    f'or pass --country-iso3 for a country that does have a map.')
            else:
                # Sniffing is a convenience, so an unreadable value must not become a new
                # way for the run to die. Some tables have a column named "country" that
                # holds something else entirely - mad_meta.csv names sites in it. Say so
                # and carry on with the default; a genuinely wrong country still fails
                # later, when every sample lands outside it, with a message that says so.
                sys.stderr.write(
                    f'[make_report] the column named country holds {raw!r}, which matches '
                    f'no country even approximately; ignoring it and using '
                    f'{G.COUNTRY_ISO}. Pass --country-iso3 to be explicit.\n')

    if iso or cname:
        G.set_country(iso or G.COUNTRY_ISO, cname)

    version = a.version_label or cfg.get('version') or G.VERSION
    G.set_version(version)

    # A selection changes every denominator in the report, so it is carried through to the
    # metadata and rendered, rather than quietly narrowing the cohort.
    selection = G.Selection.from_arg(a.sample_ids, a.selection_label or cfg.get('selection_label'))

    if a.assay == 'WGS':
        if not a.sample_table:
            raise SystemExit('--assay WGS requires --sample-table')
        import load_wgs
        rep = load_wgs.load(a.sample_table, selection)
    elif a.assay in ('AMPLICON', 'MAD4HATTER', 'PFPHAST'):
        if not a.resmarker_table:
            raise SystemExit(f'--assay {a.assay} requires --resmarker-table')
        declared = None if a.assay == 'AMPLICON' else a.assay
        wide = [f for f in a.resmarker_table if _is_wide_terra_table(f)]
        if wide:
            # The per-sample Terra table is the amplicon input shape for short reads: the
            # 01 workflow's resmarker calls and the 02 workflow's QC both land on it as
            # columns, so the geography, the QC verdicts and the marker calls arrive in one
            # file. It carries its own site metadata, hence the fallback below.
            if len(wide) != len(a.resmarker_table):
                raise SystemExit('mixing wide Terra sample tables with long resmarker '
                                 'tables in one run is not supported; pass one shape')
            import load_nomads
            load_nomads.DECLARED_PANEL = declared
            if cfg.get('qc_statuses'):
                load_nomads.QC_STATUSES = {str(x).lower() for x in cfg['qc_statuses']}
            rep = load_nomads.load(a.resmarker_table,
                                   a.site_metadata or a.resmarker_table[0],
                                   selection=selection)
            # That loader is shared, so it stamps its own assay and provenance. This is a
            # short-read amplicon run, and the report header, the assay chip and the
            # export files all read meta['assay'] - leaving it as NOMADS would label
            # Illumina PfPHAST data as nanopore.
            det = (rep.get('meta') or {}).get('panel_detection') or {}
            rep['meta']['assay'] = det.get('panel') or ('AMPLICON' if declared is None
                                                        else declared)
            G.ASSAY_NAME.setdefault(rep['meta']['assay'], 'Amplicon sequencing')
            if not a.data_source:
                label = (rep['meta'].get('panel_label')
                         or rep['meta']['assay'].replace('_', ' '))
                rep['meta']['data_source'] = (f'{label} amplicon \u00b7 per-sample Terra '
                                              f'table')
        else:
            if not a.site_metadata:
                raise SystemExit(f'--assay {a.assay} with long resmarker tables requires '
                                 f'--site-metadata')
            import load_mad
            # a declared panel is a cross-check for the detector, not an instruction
            load_mad.DECLARED_PANEL = declared
            # load_mad takes directories; stage the listed files into one
            rm_dir = _stage('resmarker', a.resmarker_table)
            ad_dir = _stage('allele', a.allele_table) if a.allele_table else None
            rep = load_mad.load(rm_dir, a.site_metadata, ad_dir, selection)
    else:
        if not a.marker_calls:
            raise SystemExit('--assay NOMADS requires --marker-calls')
        import load_nomads
        rep = load_nomads.load(a.marker_calls, a.site_metadata, selection=selection)

    # metadata overrides: explicit flags win over the config file
    rep['meta']['version'] = version
    if country_note:
        rep['meta']['country_resolution'] = country_note
    if a.data_source:
        rep['meta']['data_source'] = a.data_source
    for k, v in cfg.items():
        if k in META_PASSTHROUGH_SKIP:
            continue
        rep['meta'][k] = v          # includes keys this template does not know about yet

    os.makedirs(os.path.dirname(os.path.abspath(a.out_data_json)) or '.', exist_ok=True)
    with open(a.out_data_json, 'w') as fh:
        json.dump(rep, fh, separators=(',', ':'))

    tpl_path = a.template or os.path.join(ROOT, 'templates', 'report_v05.template.html')
    with open(tpl_path, encoding='utf-8') as fh:
        tpl = fh.read()
    html = (tpl.replace('/*DATA_HERE*/', 'const DATA = ' + json.dumps(rep, separators=(',', ':')) + ';')
               .replace('__ASSAY__', a.assay)
               .replace('__VERSION__', version))
    os.makedirs(os.path.dirname(os.path.abspath(a.out_html)) or '.', exist_ok=True)
    with open(a.out_html, 'w', encoding='utf-8') as fh:
        fh.write(html)

    if a.out_csv_dir:
        write_export_csvs(rep, a.out_csv_dir)

    # The audit is written whether or not it found anything, so a clean run is positive
    # evidence rather than an absent file.
    audit = (rep.get('meta') or {}).get('location_audit') or {}
    _warn_location.__globals__['G_ISO'] = [G.COUNTRY_ISO]
    if a.out_location_audit:
        _write_audit(audit, a.out_location_audit)
        sys.stderr.write(f'[make_report] location audit -> {a.out_location_audit}\n')
    _warn_location(audit)

    m = rep['meta']
    if selection:
        sys.stderr.write(f"[make_report] selection '{m.get('sample_selection')}': "
                         f"{m.get('n_matched')} of {m.get('n_requested')} requested samples matched"
                         + (f", {m['n_requested_missing']} not found (e.g. "
                            f"{', '.join(m['requested_missing_examples'][:3])})"
                            if m.get('n_requested_missing') else '') + '\n')
        if not m.get('n_matched'):
            raise SystemExit('no samples matched --sample-ids; refusing to build an empty report')
    sys.stderr.write(f"[make_report] {G.COUNTRY_ISO} ({m.get('country')}) "
                     f"{a.assay} {version}: {m['n_qc']} QC pass samples, "
                     f"{m['n_units_sampled']}/{m['n_units_total']} admin-2 units, period {m['period']}\n")
    # A report with no samples is not a result, it is a failed run that looks like a
    # successful one: the task exits 0, Terra shows green, and the HTML renders empty.
    # Every way of getting here is a misconfiguration worth stopping on - an unreadable
    # table, a column the loader did not recognise, or site metadata that places nobody.
    if not m['n_qc']:
        raise SystemExit(
            f'no samples made it into the report. Check the loader warnings above. The '
            f'usual causes, in order of likelihood: the wrong country '
            f'(country_iso3 was {G.COUNTRY_ISO}, so every sample outside it was dropped); '
            f'an unrecognised sample-id column; or site metadata with no district and no '
            f'lat/lon. See docs/TERRA_TABLES.md for the six required fields.')
    sys.stderr.write(f"[make_report] wrote {a.out_html} and {a.out_data_json}\n")
    return 0


def _is_wide_terra_table(path):
    """Does this file carry one column per marker, rather than one row per marker call?"""
    sys.path.insert(0, HERE)
    import terra_samples
    delim = '\t' if path.lower().endswith(('.tsv', '.txt')) else ','
    try:
        with open(path, newline='', encoding='utf-8-sig') as fh:
            header = next(csv.reader(fh, delimiter=delim), []) or []
    except OSError:
        return False
    return any(terra_samples.AA_COL.match(c) or terra_samples.RES_COL.match(c) for c in header)


def _write_audit(audit, path):
    """The audit as TSV, so a pipeline can gate on it instead of reading a log."""
    rows = [('finding', 'value', 'n_samples', 'detail')]
    for how, n in sorted((audit.get('placed_by') or {}).items()):
        rows.append(('placed', how, n, ''))
    for u in audit.get('unplaced') or []:
        detail = u.get('reason', '')
        if u.get('suggest'):
            detail += '; suggest ' + ', '.join(u['suggest'])
        rows.append(('unplaced_district', u.get('name', ''), u.get('n', 0), detail))
    if audit.get('coords_outside_country'):
        rows.append(('unplaced_coords_outside_country', '', audit['coords_outside_country'],
                     'check lat/lon order and sign'))
    for d in audit.get('coords_vs_name') or []:
        rows.append(('coords_disagree_with_district', f"{d['given']} / {d['from_coords']}",
                     d['n'], 'coordinates used'))
    for d in audit.get('district_not_in_boundaries') or []:
        rows.append(('district_not_in_boundary_file', f"{d['given']} / {d['from_coords']}",
                     d['n'], 'coordinates used'))
    for d in audit.get('region_mismatch') or []:
        rows.append(('region_mismatch', f"{d['district']} / {d['given']}", d['n'],
                     f"boundary file says {d['expected']}"))
    for c, n in sorted((audit.get('other_country') or {}).items()):
        rows.append(('country_not_report_country', c, n, ''))
    for raw, unit in sorted((audit.get('aliases_used') or {}).items()):
        rows.append(('health_district_alias', raw, 0, f'resolved to {unit}'))

    os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        for r in rows:
            fh.write('\t'.join(str(c) for c in r) + '\n')
    return path


def _warn_location(audit):
    """Repeat the headline location problems at the very end of the log.

    The loaders already print the detail, but that scrolls past; a run that dropped
    samples or placed them against a disagreeing name should say so as the last thing
    anyone reads, because both failures are invisible in the rendered numbers.
    """
    n_unplaced = sum(u.get('n', 0) for u in audit.get('unplaced') or [])
    n_unplaced += audit.get('coords_outside_country') or 0
    n_dis = sum(d['n'] for d in (audit.get('coords_vs_name') or []))
    n_notin = sum(d['n'] for d in (audit.get('district_not_in_boundaries') or []))
    n_reg = sum(d['n'] for d in (audit.get('region_mismatch') or []))
    if not (n_unplaced or n_dis or n_notin or n_reg):
        return
    sys.stderr.write('[make_report] LOCATION WARNINGS\n')
    if n_unplaced:
        sys.stderr.write(f'[make_report]   {n_unplaced} sample(s) could not be placed and are '
                         f'absent from every denominator in this report\n')
    # Every sample outside the country is almost never bad coordinates - it is the wrong
    # country selected, which is a one-flag fix and worth saying outright.
    outside = audit.get('coords_outside_country') or 0
    if outside and outside == n_unplaced:
        sys.stderr.write(f'[make_report]   all {outside} are outside '
                         f'{G_ISO[0]}: country_iso3 is the first thing to check\n')
    if n_dis:
        sys.stderr.write(f'[make_report]   {n_dis} sample(s) have a district name that '
                         f'disagrees with their coordinates\n')
    if n_notin:
        sys.stderr.write(f'[make_report]   {n_notin} sample(s) name a district that is not a '
                         f'unit in this boundary file - the file may be the wrong admin '
                         f'level for this data\n')
    if n_reg:
        sys.stderr.write(f'[make_report]   {n_reg} sample(s) give a region that disagrees '
                         f'with the boundary file\n')
    sys.stderr.write('[make_report]   full detail: --out-location-audit, and the '
                     'location_audit block in the data JSON\n')


def _stage(kind, files):
    """load_mad globs a directory; link the explicitly listed files into one.

    The directory is emptied first. It is a fixed path in the working directory, so a
    second run in the same directory would otherwise glob the previous run's files as
    well, silently reporting on a cohort nobody asked for. A WDL task gets a fresh
    directory and never saw this; running twice by hand does.
    """
    d = os.path.abspath(f'_staged_{kind}')
    if os.path.isdir(d):
        for old in os.listdir(d):
            op = os.path.join(d, old)
            if os.path.islink(op) or os.path.isfile(op):
                os.unlink(op)
    os.makedirs(d, exist_ok=True)
    for i, f in enumerate(files):
        # keep the original basename when unique so run-specific names survive in logs
        base = os.path.basename(f)
        dest = os.path.join(d, base if base.endswith('.txt') else f'{i:03d}_{base}.txt')
        if os.path.exists(dest):
            dest = os.path.join(d, f'{i:03d}_{base}')
        if not os.path.exists(dest):
            os.symlink(os.path.abspath(f), dest)
    return d


def write_export_csvs(rep, outdir):
    """Decode the embedded (gzip+base64) export tables back out as plain CSV files."""
    os.makedirs(outdir, exist_ok=True)
    views = (rep.get('export') or {}).get('views') or {}
    for key in (rep.get('export') or {}).get('order') or list(views):
        v = views.get(key) or {}
        blob = v.get('gz')
        if not blob:
            continue
        name = v.get('name') or f'{key}.csv'
        with open(os.path.join(outdir, name), 'w', encoding='utf-8') as fh:
            fh.write(gzip.decompress(base64.b64decode(blob)).decode())


if __name__ == '__main__':
    sys.exit(main())
