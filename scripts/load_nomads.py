#!/usr/bin/env python3
"""NOMADS (ONT amplicon) loader -> per-admin-2 units -> report DATA blob.

NOMADS has no production workspace yet, so rather than guess at nomadic's native file
layout this loader consumes a documented, assay-agnostic **marker-calls table**: one row
per sample x marker. Whoever runs the pipeline maps the nomadic outputs onto it, which
keeps the WDL interface stable if nomadic's own format changes.

Required columns (matched case-insensitively, with the aliases listed in ALIASES):
  sample_id   sample | sample_id | SampleID | specimen_id
  gene        gene | Gene | gene_name        (k13 / crt / ... or Pfk13 / Pfcrt / kelch13)
  aa_change   aa | aa_change | mutation | alteration          e.g. "K76T"
              (or codon + alt_aa instead: codon | CodonID , alt_aa | alt | AA)
  call        call | genotype | gt | status
                ref | wt | hom_ref | 0      -> typed, mutant absent
                alt | mut | hom_var | 1     -> typed, mutant present
                het | mixed | 0/1           -> typed, mutant present (carriage)
                missing | nocall | . | ""   -> not typed (excluded from the denominator)
              (or read counts instead: mutant_reads/alt_reads + wildtype_reads/ref_reads)

Location, at least one of:
  district    district | admin2 | dept | department      admin-2 name
  lat + lon   lat | latitude , lon | long | longitude    resolved by point-in-polygon
  site        site | facility | location                 optional, drives the site map

Time, at least one of:
  year        year | collection_year
  date        date | collection_date | date_of_collection
              (YYYY-MM-DD / YYYYMMDD / YYYY, or day-first 28.07.2025 / 28-07-2025)

Prevalence is carriage: samples whose call is alt or het, over samples typed at that marker.
"""
import csv, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_reports as G
import terra_samples
import geoloc
import panels
dept_of_coords = lambda lat, lon: G.dept_of_point(lat, lon)   # projected-space PIP, any country

csv.field_size_limit(10**7)

# the location audit from the most recent load, picked up by make_report.py
LAST_AUDIT = {}
DECLARED_PANEL = None   # set by make_report when --assay named a panel

ALIASES = {
    'sample_id': ('sample_id', 'sample', 'sampleid', 'specimen_id', 'specimen'),
    'gene':      ('gene', 'gene_name', 'gene_symbol', 'genesymbol'),
    'aa_change': ('aa_change', 'aa', 'aachange', 'mutation', 'alteration', 'variant'),
    'codon':     ('codon', 'codonid', 'codon_id', 'position', 'pos'),
    'alt_aa':    ('alt_aa', 'alt', 'aa_alt', 'mutant_aa'),
    'call':      ('call', 'genotype', 'gt', 'status', 'result'),
    'mut_reads': ('mutant_reads', 'alt_reads', 'mut_reads', 'mutant_count', 'alt_count'),
    'wt_reads':  ('wildtype_reads', 'ref_reads', 'wt_reads', 'wildtype_count', 'ref_count'),
    'district':  ('district', 'admin2', 'adm2', 'dept', 'department', 'admin_2'),
    'region':    ('region', 'admin1', 'adm1', 'admin_1', 'province', 'state'),
    'country':   ('country', 'admin0', 'adm0', 'country_name'),
    'site':      ('site', 'facility', 'location', 'facility_name'),
    'lat':       ('lat', 'latitude'),
    'lon':       ('lon', 'long', 'longitude'),
    'year':      ('year', 'collection_year'),
    # QC written back onto the per-sample table by 02_AmpliconPanelQcReport
    'qc_status': ('library_sample_qc_status', 'qc_status', 'sample_qc_status'),
    'batch_pass': ('batch_pass', 'batchpass'),
    'sample_type': ('sample_type', 'sampletype'),
    'date':      ('date', 'collection_date', 'date_of_collection'),
}
# The amplicon QC workflow grades each library pass / repool / reprep, worst-across-
# reactions, from the proportion of good loci (reprep below 0.5, repool below 0.75). Only
# "pass" is a clean library, so only "pass" counts by default; the others are reported, not
# dropped silently. Set qc_statuses in the render config to widen it.
QC_OK = {'pass', 'passed', 'true', 'yes', ''}
CONTROL_TYPES = {'negative', 'positive', 'control', 'ntc', 'blank'}
QC_STATUSES = None      # overridable: a set of acceptable library_sample_qc_status values

REF_WORDS = {'ref', 'wt', 'wildtype', 'wild_type', 'hom_ref', 'homref', '0', '0/0', 'absent', 'negative'}
ALT_WORDS = {'alt', 'mut', 'mutant', 'hom_var', 'homvar', '1', '1/1', 'present', 'positive'}
HET_WORDS = {'het', 'mixed', 'heterozygous', '0/1', '1/0'}
NO_WORDS  = {'missing', 'nocall', 'no_call', '.', '', 'na', 'n/a', 'null', 'fail', 'failed'}

# admin-2 name lookup + the health-district spellings the other loaders already handle
def _dept_by_na(): return {G._na(d['name']): d['name'] for d in G.DEPTS}
HEALTH2DEPT = {'RICHARD TOLL': 'Dagana', 'DIOULOULOU': 'Bignona', 'NDOFFANE': 'Kaolack',
               'TOUBA': 'Mbacke', 'MAKACOULIBANTANG': 'Koumpentoum', 'MBAO': 'Pikine',
               'MADIYANA 2': 'Mbacke'}

# (gene token, codon, alt AA) -> report marker key
MK_BY_POS = {}
for _k, _m in G.MK.items():
    _mo = re.match(r'^([A-Z])(\d+)([A-Za-z*])$', _m['aa'])
    if _mo:
        MK_BY_POS[(_m['tok'], int(_mo.group(2)), _mo.group(3).upper())] = _k


def _colmap(fieldnames):
    have = {(h or '').strip().lower().replace(' ', '_'): h for h in (fieldnames or [])}
    out = {}
    # Terra names its id column after the table (entity:pfphast_sample_id), so it never
    # matches a fixed alias list.
    for h in (fieldnames or []):
        if terra_samples.ENTITY_ID.match((h or '').strip()):
            out['sample_id'] = h
            break
    for canon, alts in ALIASES.items():
        for a in alts:
            if a in have:
                out[canon] = have[a]
                break
    return out


def _get(row, cm, key):
    col = cm.get(key)
    return (row.get(col) or '').strip() if col else ''


def _gene_tok(g):
    g = re.sub(r'^pf', '', (g or '').strip().lower())
    return {'kelch13': 'k13', 'ap2_mu': 'ap2mu', 'ap2-mu': 'ap2mu'}.get(g, g)


def _marker_key(row, cm):
    tok = _gene_tok(_get(row, cm, 'gene'))
    mo = re.match(r'^([A-Za-z])(\d+)([A-Za-z*])$', _get(row, cm, 'aa_change'))
    if mo:
        pos, alt = int(mo.group(2)), mo.group(3).upper()
        key = MK_BY_POS.get((tok, pos, alt))
        if key:
            return key
        # A panel locus the compendium does not list. Keep it, labelled by class, rather
        # than dropping a column the programme paid to generate; see G.register_marker.
        aa = f'{mo.group(1).upper()}{pos}{alt}'
        key = G.register_marker(tok, aa)
        MK_BY_POS[(tok, pos, alt)] = key
        return key
    try:
        codon = int(_get(row, cm, 'codon'))
    except ValueError:
        return None
    alt = _get(row, cm, 'alt_aa').upper()
    return MK_BY_POS.get((tok, codon, alt[:1])) if alt else None


def _call_state(row, cm):
    """'ref' | 'alt' | None (not typed)."""
    raw = _get(row, cm, 'call').lower()
    if raw:
        if raw in NO_WORDS: return None
        if raw in ALT_WORDS or raw in HET_WORDS: return 'alt'
        if raw in REF_WORDS: return 'ref'
    if 'mut_reads' in cm or 'wt_reads' in cm:
        def _i(k):
            try: return int(float(_get(row, cm, k) or 0))
            except ValueError: return 0
        mut, wt = _i('mut_reads'), _i('wt_reads')
        if mut + wt <= 0: return None
        return 'alt' if mut > 0 else 'ref'
    return None


def _year_of(row, cm):
    y = _get(row, cm, 'year')
    if y[:4].isdigit(): return y[:4]
    d = _get(row, cm, 'date')
    if d[:4].isdigit(): return d[:4]
    # day-first forms (28.07.2025, 28/07/2025) - what the Nomadic experiment metadata
    # CSVs use. Only the year is taken, so day/month order never has to be guessed.
    m = re.match(r'^\d{1,2}[./-]\d{1,2}[./-](\d{4})$', d.strip())
    return m.group(1) if m else None


def _f(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def _qc_verdict(row, cm):
    """-> (keep, reason). Uses the QC the amplicon pipeline wrote back onto the table.

    `02_AmpliconPanelQcReport` grades every library pass / repool / reprep and marks
    controls in sample_type, so the report defers to that rather than inventing its own
    thresholds. A sample excluded here is reported, never dropped quietly: it would
    otherwise vanish from a denominator with no trace.
    """
    st = _get(row, cm, 'sample_type').lower()
    if st and st in CONTROL_TYPES:
        return False, f'control ({st})'
    bp = _get(row, cm, 'batch_pass').lower()
    if bp and bp not in QC_OK:
        return False, f'batch_pass={bp}'
    qs = _get(row, cm, 'qc_status').lower()
    ok = QC_STATUSES if QC_STATUSES is not None else QC_OK
    if qs and qs not in ok:
        return False, f'library_sample_qc_status={qs}'
    return True, None




def _read_calls(path):
    """Read a marker-calls table, reshaping a wide Terra sample table if that is what it is.

    Terra workspaces publish one COLUMN per marker. Sniffing that here, rather than making
    the caller run a conversion first, means the WDL and its frozen input list work on a
    Terra export unchanged - the pipeline takes "marker calls tables" and this is one.
    """
    delim = '\t' if path.lower().endswith(('.tsv', '.txt')) else ','
    with open(path, newline='', encoding='utf-8-sig') as fh:
        rd = csv.DictReader(fh, delimiter=delim)
        rows, fields = list(rd), list(rd.fieldnames or [])
    if any(terra_samples.AA_COL.match(c) or terra_samples.RES_COL.match(c) for c in fields):
        calls, passthrough = terra_samples.reshape(rows, fields)
        sys.stderr.write(f'[load_nomads] {os.path.basename(path)} is a wide Terra sample '
                         f'table: {len(rows)} rows -> {len(calls)} marker calls\n')
        return calls, ['sample_id', 'gene', 'aa_change', 'call'] + passthrough
    return rows, fields


def load(call_tables, site_metadata=None, version=None, data_source=None, selection=None):
    # optional per-sample geography/date table, for calls tables that carry none
    smeta = {}
    if site_metadata and os.path.exists(site_metadata):
        with open(site_metadata, newline='') as fh:
            delim = '\t' if site_metadata.lower().endswith(('.tsv', '.txt')) else ','
            rd = csv.DictReader(fh, delimiter=delim)
            cm = _colmap(rd.fieldnames)
            for r in rd:
                sid = _get(r, cm, 'sample_id')
                if sid:
                    smeta[sid] = {'site': _get(r, cm, 'site'), 'lat': _f(_get(r, cm, 'lat')),
                                  'lon': _f(_get(r, cm, 'lon')), 'district': _get(r, cm, 'district'),
                                  'region': _get(r, cm, 'region'),
                                  'country': _get(r, cm, 'country'),
                                  'year': _year_of(r, cm)}

    samples = {}
    drop = {'rows': 0, 'no_marker': 0, 'not_typed': 0, 'no_location': 0, 'not_selected': 0}
    qc_seen, qc_bad, qc_reasons = set(), {}, {}
    seen_loci = set()
    for path in call_tables:
            rows, fields = _read_calls(path)
            cm = _colmap(fields)
            if 'sample_id' not in cm:
                sys.stderr.write(f'[load_nomads] skipping {path}: no sample_id column\n')
                continue
            for row in rows:
                drop['rows'] += 1
                sid = _get(row, cm, 'sample_id')
                if not sid: continue
                if selection is not None and not selection.keep(sid):
                    drop['not_selected'] = drop.get('not_selected', 0) + 1
                    continue
                if sid in qc_bad:
                    continue
                if sid not in qc_seen:
                    qc_seen.add(sid)
                    keep, why = _qc_verdict(row, cm)
                    if not keep:
                        qc_bad[sid] = why
                        qc_reasons[why] = qc_reasons.get(why, 0) + 1
                if sid in qc_bad:
                    continue
                mo_l = re.match(r'^([A-Za-z])(\d+)([A-Za-z*])$', _get(row, cm, 'aa_change'))
                if mo_l:
                    seen_loci.add(f'{_gene_tok(_get(row, cm, "gene"))}:{int(mo_l.group(2))}')
                key = _marker_key(row, cm)
                if not key:
                    drop['no_marker'] += 1
                    continue
                state = _call_state(row, cm)
                if state is None:
                    drop['not_typed'] += 1
                    continue
                sm = smeta.get(sid, {})
                rec = samples.setdefault(sid, {
                    'id': sid,
                    'site': _get(row, cm, 'site') or sm.get('site', ''),
                    'lat': _f(_get(row, cm, 'lat')) if cm.get('lat') else sm.get('lat'),
                    'lon': _f(_get(row, cm, 'lon')) if cm.get('lon') else sm.get('lon'),
                    'district_raw': _get(row, cm, 'district') or sm.get('district', ''),
                    'region_raw': _get(row, cm, 'region') or sm.get('region', ''),
                    'country_raw': _get(row, cm, 'country') or sm.get('country', ''),
                    'date': _year_of(row, cm) or sm.get('year') or '',
                    'calls': {},
                })
                # carriage wins: one alt call at a marker makes the sample a carrier
                prev = rec['calls'].get(key)
                rec['calls'][key] = (0, 1) if (state == 'alt' or (prev and prev[1])) else (1, 0)

    # resolve admin-2 and drop samples we cannot place. Precedence and every mismatch
    # finding live in geoloc, shared with the WGS and amplicon loaders.
    resolver = geoloc.Resolver()
    placed = []
    for rec in samples.values():
        given_region = rec.pop('region_raw', '')
        d, _how = resolver.resolve(district=rec.pop('district_raw', ''),
                                   lat=rec.get('lat'), lon=rec.get('lon'),
                                   region=given_region, country=rec.pop('country_raw', ''))
        if not d:
            drop['no_location'] += 1
            continue
        rec['district'] = d
        rec['region'] = ((G.SEN_REGION.get(d) if G.COUNTRY_ISO == 'SEN' else None)
                         or G.region_of(d) or given_region or '—')
        placed.append(rec)
    if qc_reasons:
        tot = sum(qc_reasons.values())
        sys.stderr.write(f'[load_nomads] QC excluded {tot} sample(s): '
                         + ', '.join(f'{k} x{v}' for k, v in sorted(qc_reasons.items())) + '\n')
    detection = panels.detect(seen_loci)
    panels.register(detection)
    for line in panels.lines(detection, declared=DECLARED_PANEL):
        sys.stderr.write(f'[load_nomads] {line}\n')
    resolver.report(tag='load_nomads')
    LAST_AUDIT['nomads'] = resolver.audit

    # aggregate to admin-2 units (same shape the other loaders emit)
    by = {}
    for s in placed:
        a = by.setdefault(s['district'], {'n': 0, 'n_col': 0, 'years': set(), 'mkx': {}, 'mkn': {},
                                          'by_year': {}})
        a['n'] += 1; a['n_col'] += 1
        if s['date']: a['years'].add(s['date'])
        yslot = a['by_year'].setdefault(s['date'], {'n': 0, 'x': {}, 'd': {}}) if s['date'] else None
        if yslot is not None: yslot['n'] += 1
        for k, (wt, mt) in s['calls'].items():
            a['mkn'][k] = a['mkn'].get(k, 0) + 1
            if yslot is not None: yslot['d'][k] = yslot['d'].get(k, 0) + 1
            if mt:
                a['mkx'][k] = a['mkx'].get(k, 0) + 1
                if yslot is not None: yslot['x'][k] = yslot['x'].get(k, 0) + 1

    units = []
    for d in G.DEPTS:
        a = by.get(d['name'])
        if not a:
            units.append({'name': d['name'], 'sampled': False, 'n': 0})
            continue
        yrs = sorted(a['years'])
        units.append({'name': d['name'], 'sampled': True, 'n': a['n'], 'n_col': a['n_col'],
                      'date_min': (yrs[0] if yrs else None), 'date_max': (yrs[-1] if yrs else None),
                      'years': yrs,
                      'mk': {k: round(100 * a['mkx'].get(k, 0) / a['mkn'][k], 1) for k in a['mkn'] if a['mkn'][k]},
                      'mkx': a['mkx'], 'mkn': a['mkn'], 'by_year': a['by_year']})

    ns = sum(1 for u in units if u.get('sampled'))
    sys.stderr.write(f"[load_nomads] tables={len(call_tables)} rows={drop['rows']} samples={len(placed)} "
                     f"depts sampled={ns}/{len(units)} dropped={{'no_marker': {drop['no_marker']}, "
                     f"'not_typed': {drop['not_typed']}, 'no_location': {drop['no_location']}}}\n")

    rep = G.assemble_report('NOMADS', G.ASSAYS['NOMADS'], units, selection)
    rep['meta']['real'] = True
    rep['meta']['version'] = version or G.VERSION
    rep['meta']['data_source'] = data_source or 'NOMADS ONT amplicon · nomadic marker calls'
    rep['meta']['n_called'] = sum(1 for s in placed if s.get('calls'))
    rep['meta']['location_audit'] = resolver.audit.meta()
    rep['meta']['panel_detection'] = detection
    if detection.get('recognised'):
        rep['meta']['panel'] = detection['panel']
        rep['meta']['panel_label'] = detection.get('label')
    rep['meta']['qc_excluded'] = dict(qc_reasons)
    rep['meta']['n_qc_excluded'] = sum(qc_reasons.values())
    G.real_export(rep, placed, 'ONT amplicon sequencing')
    rep['sites'] = G.sites_from_samples(placed)
    sys.stderr.write(f"[load_nomads] site points={len(rep['sites'])}\n")
    return rep


if __name__ == '__main__':
    args = [a for a in sys.argv[1:]]
    out = 'build/data_nomads_real.json'
    if '-o' in args:
        i = args.index('-o'); out = args[i + 1]; del args[i:i + 2]
    site_meta = None
    if '--site-metadata' in args:
        i = args.index('--site-metadata'); site_meta = args[i + 1]; del args[i:i + 2]
    json.dump(load(args, site_meta), open(out, 'w'))
    sys.stderr.write(f'[load_nomads] wrote {out}\n')
