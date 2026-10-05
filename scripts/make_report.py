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
    p.add_argument('--assay', required=True, choices=['WGS', 'MAD4HATTER', 'NOMADS'])

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
    elif a.assay == 'MAD4HATTER':
        if not a.resmarker_table or not a.site_metadata:
            raise SystemExit('--assay MAD4HATTER requires --resmarker-table and --site-metadata')
        import load_mad
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

    m = rep['meta']
    if selection:
        sys.stderr.write(f"[make_report] selection '{m.get('sample_selection')}': "
                         f"{m.get('n_matched')} of {m.get('n_requested')} requested samples matched"
                         + (f", {m['n_requested_missing']} not found (e.g. "
                            f"{', '.join(m['requested_missing_examples'][:3])})"
                            if m.get('n_requested_missing') else '') + '\n')
        if not m.get('n_matched'):
            raise SystemExit('no samples matched --sample-ids; refusing to build an empty report')
    sys.stderr.write(f"[make_report] {a.assay} {version}: {m['n_qc']} QC pass samples, "
                     f"{m['n_units_sampled']}/{m['n_units_total']} admin-2 units, period {m['period']}\n")
    sys.stderr.write(f"[make_report] wrote {a.out_html} and {a.out_data_json}\n")
    return 0


def _stage(kind, files):
    """load_mad globs a directory; link the explicitly listed files into one."""
    d = os.path.abspath(f'_staged_{kind}')
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
