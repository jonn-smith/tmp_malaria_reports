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
dept_of_coords = lambda lat, lon: G.dept_of_point(lat, lon)   # projected-space PIP, any country

csv.field_size_limit(10**7)

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
    'site':      ('site', 'facility', 'location', 'facility_name'),
    'lat':       ('lat', 'latitude'),
    'lon':       ('lon', 'long', 'longitude'),
    'year':      ('year', 'collection_year'),
    'date':      ('date', 'collection_date', 'date_of_collection'),
}
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


def _dept(name, lat, lon):
    if name:
        d = _dept_by_na().get(G._na(HEALTH2DEPT.get(name.upper(), name)))
        if d: return d
    if lat is not None and lon is not None:
        return dept_of_coords(lat, lon)
    return None


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
                                  'year': _year_of(r, cm)}

    samples = {}
    drop = {'rows': 0, 'no_marker': 0, 'not_typed': 0, 'no_location': 0, 'not_selected': 0}
    for path in call_tables:
        with open(path, newline='') as fh:
            delim = '\t' if path.lower().endswith(('.tsv', '.txt')) else ','
            rd = csv.DictReader(fh, delimiter=delim)
            cm = _colmap(rd.fieldnames)
            if 'sample_id' not in cm:
                sys.stderr.write(f'[load_nomads] skipping {path}: no sample_id column\n')
                continue
            for row in rd:
                drop['rows'] += 1
                sid = _get(row, cm, 'sample_id')
                if not sid: continue
                if selection is not None and not selection.keep(sid):
                    drop['not_selected'] = drop.get('not_selected', 0) + 1
                    continue
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
                    'date': _year_of(row, cm) or sm.get('year') or '',
                    'calls': {},
                })
                # carriage wins: one alt call at a marker makes the sample a carrier
                prev = rec['calls'].get(key)
                rec['calls'][key] = (0, 1) if (state == 'alt' or (prev and prev[1])) else (1, 0)

    # resolve admin-2 and drop samples we cannot place
    placed = []
    for rec in samples.values():
        d = _dept(rec.pop('district_raw', ''), rec.get('lat'), rec.get('lon'))
        if not d:
            drop['no_location'] += 1
            continue
        rec['district'] = d
        rec['region'] = (G.SEN_REGION.get(d) if G.COUNTRY_ISO == 'SEN' else None) or G.region_of(d) or '—'
        placed.append(rec)

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
