#!/usr/bin/env python3
"""WGS real-data loader: sr-malaria `sample` table export -> per-admin-2 units -> data_wgs.json.

Reuses gen_reports.assemble_report for all aggregation / Wilson-CI / stoplight /
export assembly; the loader only does intake + the minimal analytics.

Real schema (broad-firecloud-dsde-methods/sr-malaria `sample` table, 164 cols):
  id            entity:sample_id
  admin-2       District  (+ Region, Site, Latitude, Longitude)  -- direct columns
  time          Year  (also date_of_collection = YYYYMMDD)
  QC            qc_status = Pass/Fail  (fallback qc_status_original = passed/failed)
  markers       per-AA columns  pf<gene>_<Aaa>_<pos>_<Aaa>  with genotype call
                {hom_ref | hom_var | het | missing | ''}  -- ALL drug-res info is here
  hrp2/hrp3     '+' present(not deleted) / '-' deleted / '' not assessed
  barcode       24-SNP string ('N' = mixed) ; mono_poly_genomic_barcode_estimate is empty

Analytics kept minimal this iteration (per request):
  markers   = carriage prevalence = (hom_var + het) / (hom_ref + hom_var + het)
  hrp2/hrp3 = deletion fraction  ('-' / ('+'|'-'))
  COI/poly  = from barcode ('N' count); poly if any 'N'; COI proxy = 1 + #N
  RH / cotx = NOT computed (null; pending hmmIBD relatedness run)
  CNV       = NOT parsed (null)

Usage:  ./load_wgs.py [sample.tsv] [out.json]
"""
import sys, os, csv, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_reports as G

csv.field_size_limit(10**7)

# gene token in the table column  ->  MK marker token
GENE2TOK = {'kelch13':'k13','crt':'crt','mdr1':'mdr1','mdr2':'mdr2','dhfr':'dhfr','dhps':'dhps',
            'coronin':'coronin','ubp1':'ubp1','ap2_mu':'ap2mu','cytb':'cytb',
            'arps10':'arps10','exo':'exo','aat1':'aat1','carl':'carl','atg18':'atg18','fd':'fd'}
AA3 = {'A':'Ala','R':'Arg','N':'Asn','D':'Asp','C':'Cys','Q':'Gln','E':'Glu','G':'Gly','H':'His',
       'I':'Ile','L':'Leu','K':'Lys','M':'Met','F':'Phe','P':'Pro','S':'Ser','T':'Thr','W':'Trp',
       'Y':'Tyr','V':'Val'}
def _codon(aa): return int(re.findall(r'\d+', aa)[0])
# MK key -> (tok, codon, ref3, alt3): the mutant AA disambiguates columns that share a codon
# (e.g. pfdhps_Ala_613_Ser vs _Thr) and tolerates a mis-annotated reference AA in the export
# (e.g. pfdhps_Lys_437_Gly for the A437G marker — flagged upstream, still the right column).
MK_POS = {k: (G.MK[k]['tok'], _codon(G.MK[k]['aa']),
              AA3.get(G.MK[k]['aa'][0], ''), AA3.get(G.MK[k]['aa'][-1], '')) for k in G.MK}
MARKER_COL_RE = re.compile(r'^pf(?P<gene>.+?)_(?P<ref>[A-Z][a-z]{2})_(?P<pos>\d+)_(?P<alt>[A-Z][a-z]{2})$')

# health-district / alt spelling -> geoBoundaries department
HEALTH2DEPT = {'RICHARD TOLL':'Dagana','DIOULOULOU':'Bignona','NDOFFANE':'Kaolack',
               'TOUBA':'Mbacke','MAKACOULIBANTANG':'Koumpentoum','MBAO':'Pikine',
               'MADIYANA 2':'Mbacke'}
DEPT_BY_NA = {G._na(d['name']): d['name'] for d in G.DEPTS}

def marker_columns(header):
    """Map each report marker key -> its genotype column in this export (if present).
    Prefers an exact ref+codon+alt AA match, then falls back to codon+alt (mis-annotated
    reference AA), then codon alone."""
    exact = {}; by_alt = {}; by_pos = {}
    for col in header:
        m = MARKER_COL_RE.match(col)
        if not m: continue
        tok = GENE2TOK.get(m.group('gene').lower())
        if not tok: continue
        pos, ref, alt = int(m.group('pos')), m.group('ref'), m.group('alt')
        exact[(tok, pos, ref, alt)] = col
        by_alt.setdefault((tok, pos, alt), col)
        by_pos.setdefault((tok, pos), col)
    out = {}
    for k, (tok, pos, ref, alt) in MK_POS.items():
        col = exact.get((tok, pos, ref, alt)) or by_alt.get((tok, pos, alt)) or by_pos.get((tok, pos))
        if col: out[k] = col
    return out

def dept_of(row):
    d = (row.get('District') or '').strip()
    return DEPT_BY_NA.get(G._na(HEALTH2DEPT.get(d.upper(), d)))

def qc_pass(row):
    s = (row.get('qc_status') or '').strip().lower()
    if s in ('pass','passed','true'): return True
    if s in ('fail','failed','false'): return False
    return (row.get('qc_status_original') or '').strip().lower() == 'passed'   # fallback

def year_of(row):
    d = (row.get('date_of_collection') or '').strip()
    if len(d) >= 4 and d[:4].isdigit(): return d[:4]
    y = (row.get('Year') or '').strip()
    return y if y.isdigit() else None

def coi_from_barcode(bc):
    bc = (bc or '').strip().upper()
    if not re.search('[ACGT]', bc): return None, None      # no real call
    hets = bc.count('N')
    return 1 + hets, hets > 0

def load(sample_tsv):
    with open(sample_tsv, newline='') as f:
        rdr = csv.DictReader(f, delimiter='\t')
        mcols = marker_columns(rdr.fieldnames)
        sys.stderr.write(f"[load_wgs] mapped {len(mcols)}/{len(G.MK)} report markers to columns: "
                         f"{sorted(mcols)}\n")
        by_dept = {}; drop = {'not_sen':0,'no_dept':0}; unmatched = set(); samples = []
        for row in rdr:
            sid = (row.get('entity:sample_id') or '').strip()
            if not sid.startswith('SEN_'):            # drop controls / non-Senegal (3D7, Dd2, ...)
                drop['not_sen'] += 1; continue
            dept = dept_of(row)
            if not dept:
                drop['no_dept'] += 1; unmatched.add((row.get('District') or '').strip()); continue
            a = by_dept.setdefault(dept, {'n_col':0,'n':0,'years':set(),'mkx':{},'mkn':{},
                                          'h2x':0,'h3x':0,'hrpn':0,'coi':[],'poly':0,'poly_n':0})
            a['n_col'] += 1
            if not qc_pass(row): continue
            a['n'] += 1
            y = year_of(row)
            if y: a['years'].add(y)
            def _f(v):
                try: return float(v)
                except (TypeError, ValueError): return None
            srec = {'id': sid, 'district': dept, 'region': (row.get('Region') or '—'),
                    'site': (row.get('Site') or ''), 'lat': _f(row.get('Latitude')), 'lon': _f(row.get('Longitude')),
                    'date': (row.get('date_of_collection') or y or ''), 'calls': {}}
            for k, col in mcols.items():
                g = (row.get(col) or '').strip().lower()
                if g in ('hom_ref','hom_var','het'):
                    a['mkn'][k] = a['mkn'].get(k, 0) + 1
                    if g in ('hom_var','het'):                      # carriage of the mutant
                        a['mkx'][k] = a['mkx'].get(k, 0) + 1
                    srec['calls'][k] = (1,0) if g=='hom_ref' else (0,1) if g=='hom_var' else (1,1)
            h2 = (row.get('hrp2') or '').strip(); h3 = (row.get('hrp3') or '').strip()
            if h2 in ('+','-') or h3 in ('+','-'):
                a['hrpn'] += 1
                a['h2x'] += 1 if h2 == '-' else 0
                a['h3x'] += 1 if h3 == '-' else 0
            coi, poly = coi_from_barcode(row.get('barcode'))
            if coi is not None:
                a['coi'].append(coi); a['poly_n'] += 1; a['poly'] += 1 if poly else 0
            srec.update(coi=coi, poly=poly, hrp2del=(h2=='-'), hrp3del=(h3=='-'),
                        hrp_called=(h2 in ('+','-') or h3 in ('+','-')))
            samples.append(srec)

    units = []
    for d in G.DEPTS:
        name = d['name']; a = by_dept.get(name)
        if not a or a['n'] == 0:
            units.append({'name': name, 'sampled': False, 'n': 0}); continue
        yrs = sorted(a['years'])
        poly_pct = round(100*a['poly']/a['poly_n']) if a['poly_n'] else None
        rec = {'name': name, 'sampled': True, 'n': a['n'], 'n_col': a['n_col'],
               'date_min': (yrs[0] if yrs else None), 'date_max': (yrs[-1] if yrs else None), 'years': yrs,
               'mk': {k: round(100*a['mkx'].get(k,0)/a['mkn'][k], 1) for k in a['mkn'] if a['mkn'][k]},
               'mkx': a['mkx'], 'mkn': a['mkn'],
               'div': {'coi': round(sum(a['coi'])/len(a['coi']), 2) if a['coi'] else None,
                       'poly': poly_pct, 'mono': (100-poly_pct) if poly_pct is not None else None,
                       'rh': None, 'cotx': None}}       # rh/cotx pending hmmIBD
        if a['hrpn']:
            rec['hrp2'] = round(100*a['h2x']/a['hrpn'], 1); rec['hrp3'] = round(100*a['h3x']/a['hrpn'], 1)
            rec['hrp2x'] = a['h2x']; rec['hrp3x'] = a['h3x']; rec['hrpn'] = a['hrpn']
        units.append(rec)

    ns = sum(1 for u in units if u.get('sampled'))
    sys.stderr.write(f"[load_wgs] depts sampled={ns}/{len(units)} qc_samples={sum(u.get('n',0) for u in units)} "
                     f"dropped: non-SEN={drop['not_sen']} no_dept={drop['no_dept']}"
                     + (f" (unmatched districts: {sorted(x for x in unmatched if x)})" if unmatched else "") + "\n")
    rep = G.assemble_report('WGS', G.ASSAYS['WGS'], units)
    rep['meta']['real'] = True
    rep['meta']['version'] = 'v0.9-real'   # gen_reports reads sys.argv on import; set explicitly
    rep['meta']['data_source'] = 'Illumina WGS · broad-firecloud-dsde-methods/sr-malaria (Senegal joint call)'
    G.real_export(rep, samples, 'Whole genome sequencing')   # real-only export (no fabrication)
    rep['sites'] = G.sites_from_samples(samples)             # site-level points (finer than admin-2)
    sys.stderr.write(f"[load_wgs] sites={len(rep['sites'])}\n")
    return rep

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else '/workspace/sample.tsv'
    out = sys.argv[2] if len(sys.argv) > 2 else 'build/data_wgs.json'
    json.dump(load(src), open(out, 'w'))
    sys.stderr.write(f"[load_wgs] wrote {out}\n")
