#!/usr/bin/env python3
"""MAD4HATTER real-data loader — UCSF mad4hatter outputs -> per-admin-2 units -> data_mad4hatter.json.

The Terra AmpSeq run on the full 993-sample set failed (22 samples had blank FASTQ paths ->
the cutadapt scatter fails the workflow). But UCSF already processed every sequencing run and
deposited the mad4hatter outputs at
  gs://fc-dab15d04-.../cigass_mad4hatter/ucsf_outputs/out_run*/
so we load those directly (full multi-site cohort, no re-run needed).

Inputs (downloaded to a local dir):
  resmarker_table.txt per run  — columns: SampleID, [Locus,] GeneID, Gene, CodonID, RefCodon,
       Codon, [CodonStart,] CodonRefAlt, RefAA, AA, AARefAlt(REF/ALT), Reads   (2 schema variants)
  site metadata CSV (mad_meta.csv = All_2023_runs_metadata1.csv): Sample_id, Country(=site), Latitude, Longitude

Per marker (MK): genotyped if the sample has any resmarker row at (Gene, CodonID); mutant carriage if
any row has AA == the marker's alt AA with AARefAlt == ALT. Samples unioned across runs/repeats by
base SampleID (strip _S##_L001). Site -> admin-2 by point-in-polygon on sen_adm2.geojson.
COI/poly, hrp2/3, RH/cotx: not computed here (need allele_data / coverage / relatedness) -> null.

Usage:  ./load_mad.py [resmarker_dir=/workspace/fiss_downloads/rm] [meta_csv] [-o out.json]
"""
import sys, os, csv, re, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_reports as G

csv.field_size_limit(10**7)
HERE = os.path.dirname(os.path.abspath(__file__))

def _codon(aa): return int(re.findall(r'\d+', aa)[0])
# MK key -> (gene token, codon, alt single-letter AA)
MK_TGT = {k: (G.MK[k]['tok'], _codon(G.MK[k]['aa']), G.MK[k]['aa'][-1])
          for k in G.MK if G.MK[k]['tok'] in ('k13','crt','mdr1','dhfr','dhps','cytb')}

def load_meta(path):
    m = {}
    for r in csv.DictReader(open(path)):
        def f(v):
            try: return float(v)
            except (TypeError, ValueError): return None
        m[r['Sample_id']] = (r.get('Country', ''), f(r.get('Latitude')), f(r.get('Longitude')))
    return m

# --- point-in-polygon dept assignment (sen ADM2) ---
_FEATS = json.load(open(os.path.join(os.path.dirname(HERE), 'reference', 'sen_adm2.geojson')))['features']
def _rings(g): return g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
def _pip(lon, lat, poly):
    pts = poly[0]; n = len(pts); ins = False; j = n-1
    for i in range(n):
        xi, yi = pts[i][0], pts[i][1]; xj, yj = pts[j][0], pts[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj-xi)*(lat-yi)/(yj-yi)+xi): ins = not ins
        j = i
    return ins
_DEPT_CACHE = {}
def dept_of(lat, lon):
    if lat is None or lon is None: return None
    key = (round(lat, 4), round(lon, 4))
    if key in _DEPT_CACHE: return _DEPT_CACHE[key]
    d = None
    for ft in _FEATS:
        if any(_pip(lon, lat, poly) for poly in _rings(ft['geometry'])): d = ft['properties']['shapeName']; break
    _DEPT_CACHE[key] = d; return d

base = lambda s: re.sub(r'_S\d+_L001$', '', s)

def coi_from_alleles(ad_dir):
    """base sample -> (COI, is_poly). Naive COI = max distinct microhaplotype alleles at any single
    locus; poly if >=2 loci carry >1 allele. Within-run diversity (max across runs, no cross-run union)."""
    perloc = {}   # base -> {locus: max distinct alleles seen in one run}
    for fp in sorted(glob.glob(os.path.join(ad_dir, '*.txt'))):
        rd = csv.DictReader(open(fp), delimiter='\t')
        if not rd.fieldnames or 'SampleID' not in rd.fieldnames or 'Locus' not in rd.fieldnames: continue
        f = {}
        for row in rd:
            b = base(row['SampleID'])
            f.setdefault(b, {}).setdefault(row['Locus'], set()).add(row.get('Allele') or row.get('ASV'))
        for b, loci in f.items():
            d = perloc.setdefault(b, {})
            for loc, al in loci.items(): d[loc] = max(d.get(loc, 0), len(al))
    out = {}
    for b, loci in perloc.items():
        cnts = list(loci.values())
        if cnts: out[b] = (max(cnts), sum(1 for c in cnts if c > 1) >= 2)
    return out
isctrl = lambda b: b.upper().startswith(('DC', 'DD', '3D7', 'NTC')) or b == 'Undetermined'
def year_of(b):
    m = re.search(r'(?:SEN|SNG?)[-_]?(\d{2})', b)  # SNG23.. / SN23.. / SEN-2020-..
    if re.search(r'SEN[-_]20\d{2}', b): return re.search(r'(20\d{2})', b).group(1)
    return '20'+m.group(1) if m else None

def load(rm_dir, meta_csv, ad_dir=None):
    meta = load_meta(meta_csv)
    coi_map = coi_from_alleles(ad_dir) if ad_dir and os.path.isdir(ad_dir) else {}
    # union marker calls across all runs, per base sample
    cov = {}; mut = {}      # base -> set(mk covered) / set(mk mutant)
    files = 0
    for fp in sorted(glob.glob(os.path.join(rm_dir, '*.txt'))):
        rd = csv.DictReader(open(fp), delimiter='\t')
        if not rd.fieldnames or 'SampleID' not in rd.fieldnames or 'Gene' not in rd.fieldnames: continue
        files += 1
        # index MK targets by (gene, codon) for this file
        for row in rd:
            b = base(row['SampleID'])
            g = (row.get('Gene') or '').strip();
            try: c = int(row.get('CodonID'))
            except (TypeError, ValueError): continue
            aa = (row.get('AA') or '').strip()
            for k, (tok, codon, altaa) in MK_TGT.items():
                if g == tok and c == codon:
                    cov.setdefault(b, set()).add(k)
                    # carriage = sample shows the resistance amino acid, regardless of REF/ALT polarity
                    # (the panel reference encodes the mutant at some codons, e.g. dhps 437 Ref=Gly).
                    if aa == altaa: mut.setdefault(b, set()).add(k)
    # build per-sample records (real samples joined to site + coords)
    samples = []; drop = {'ctrl': 0, 'no_meta': 0, 'no_dept': 0}
    for b in cov:
        if isctrl(b): drop['ctrl'] += 1; continue
        site, lat, lon = meta.get(b, ('', None, None))
        if lat is None: drop['no_meta'] += 1; continue
        d = dept_of(lat, lon)
        if not d: drop['no_dept'] += 1; continue
        # sorted(): cov[b] is a set, and its iteration order would otherwise leak
        # PYTHONHASHSEED into the per-sample export row order.
        calls = {k: ((0, 1) if k in mut.get(b, set()) else (1, 0)) for k in sorted(cov[b])}
        coi, poly = coi_map.get(b, (None, None))
        samples.append({'id': b, 'district': d, 'region': '—', 'site': site, 'lat': lat, 'lon': lon,
                        'coi': coi, 'poly': poly, 'date': (year_of(b) or ''), 'calls': calls})
    # region from SEN_REGION by dept
    reg_na = {G._na(k): v for k, v in G.SEN_REGION.items()}
    for s in samples: s['region'] = reg_na.get(G._na(s['district']), '—')

    # aggregate to admin-2 units
    by = {}
    for s in samples:
        a = by.setdefault(s['district'], {'n': 0, 'n_col': 0, 'years': set(), 'mkx': {}, 'mkn': {},
                                          'coi': [], 'poly': 0, 'poly_n': 0, 'by_year': {}})
        a['n'] += 1; a['n_col'] += 1
        if s['date']: a['years'].add(s['date'])
        # per-year atoms (same samples as the pooled counts). MAD years come from the
        # sample ID, so this is a two-point comparison, not a dense series.
        yslot = a['by_year'].setdefault(s['date'], {'n': 0, 'x': {}, 'd': {}}) if s['date'] else None
        if yslot is not None: yslot['n'] += 1
        for k, (wt, mt) in s['calls'].items():
            a['mkn'][k] = a['mkn'].get(k, 0) + 1
            if yslot is not None: yslot['d'][k] = yslot['d'].get(k, 0) + 1
            if mt:
                a['mkx'][k] = a['mkx'].get(k, 0) + 1
                if yslot is not None: yslot['x'][k] = yslot['x'].get(k, 0) + 1
        if s.get('coi') is not None:
            a['coi'].append(s['coi']); a['poly_n'] += 1; a['poly'] += 1 if s.get('poly') else 0
    units = []
    for d in G.DEPTS:
        a = by.get(d['name'])
        if not a: units.append({'name': d['name'], 'sampled': False, 'n': 0}); continue
        yrs = sorted(a['years'])
        poly_pct = round(100*a['poly']/a['poly_n']) if a['poly_n'] else None
        units.append({'name': d['name'], 'sampled': True, 'n': a['n'], 'n_col': a['n_col'],
                      'date_min': (yrs[0] if yrs else None), 'date_max': (yrs[-1] if yrs else None), 'years': yrs,
                      'mk': {k: round(100*a['mkx'].get(k, 0)/a['mkn'][k], 1) for k in a['mkn'] if a['mkn'][k]},
                      'mkx': a['mkx'], 'mkn': a['mkn'],
                      'div': {'coi': (round(sum(a['coi'])/len(a['coi']), 2) if a['coi'] else None),
                              'poly': poly_pct, 'mono': (100-poly_pct) if poly_pct is not None else None,
                              'rh': None, 'cotx': None},
                      'by_year': a['by_year']})
    ns = sum(1 for u in units if u.get('sampled'))
    sys.stderr.write(f"[load_mad] runs={files} samples={len(samples)} depts sampled={ns}/{len(units)} "
                     f"sites={len(set(s['site'] for s in samples))} dropped={drop}\n")
    rep = G.assemble_report('MAD4HATTER', G.ASSAYS['MAD4HATTER'], units)
    rep['meta']['real'] = True
    rep['meta']['n_called'] = sum(1 for s_ in samples if s_.get('calls'))
    rep['meta']['version'] = 'v0.11-real'   # gen_reports reads sys.argv on import; set explicitly
    rep['meta']['data_source'] = 'MAD4HATTER v4 amplicon · UCSF mad4hatter outputs (runs 1–10)'
    G.real_export(rep, samples, 'Amplicon sequencing')
    rep['sites'] = G.sites_from_samples(samples)
    sys.stderr.write(f"[load_mad] site points={len(rep['sites'])}\n")
    return rep

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '-o']
    out = 'build/data_mad4hatter.json'
    if '-o' in sys.argv: out = sys.argv[sys.argv.index('-o')+1]; args = [a for a in args if a != out]
    rm_dir = args[0] if len(args) > 0 else '/workspace/fiss_downloads/rm'
    meta_csv = args[1] if len(args) > 1 else '/workspace/fiss_downloads/mad_meta.csv'
    ad_dir = args[2] if len(args) > 2 else '/workspace/fiss_downloads/ad'
    json.dump(load(rm_dir, meta_csv, ad_dir), open(out, 'w'))
    sys.stderr.write(f"[load_mad] wrote {out}\n")
