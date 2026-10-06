#!/usr/bin/env python3
"""Generate DATA JSON for the v0.5 single-country (Senegal) malaria molecular-surveillance
mock-ups: WGS, MAD4HATTER, NOMADS (ONT), COMBINED.

v0.5 redesign (colleague feedback):
  - Prevalence only (NO incidence).
  - NO drug-resistance phenotype prediction. Show gene + AA change + associated drug +
    the WHO compendium class + criterion only. Class names are WHO's own (Validated /
    Candidate / Potential marker); the word "validated" is used only inside those terms.
  - Include NON-WHO (research) markers, clearly labelled.
  - 3 nav categories: Resistance markers / Diagnostics (HRP2/3) / Transmission (+ Summary, Export, Panel, Methods).
  - Diagnostics (HRP2/3) data is KEPT but rendered greyed-out + "not validated" (template).
  - Small-sample masking: suppress region prevalence when n < min_samples (default 5; user slider).
  - Action thresholds: resistance marker >=10% (WHO TES / treatment-failure trigger),
    pfhrp2/3 >=5% (WHO RDT-switch). Flags on native sections + Summary stoplight.
  - Transmission: THE REAL McCOIL COI, polygenomic fraction, monogenomic-clone fraction,
    RH (intra-host relatedness, Wong et al.), cotx (co-transmission) fraction -- PER admin unit.
  - Export views: WHO Malaria Threats Map, Africa CDC, DHIS2 (DHIS2 schema real; others representative).
Synthetic data throughout.
"""
import json, math, random, re, sys, unicodedata, gzip, base64, zlib

def fmt_years(ys):
    """Compress a set of years to a compact string: contiguous runs use en-dashes,
    non-contiguous entries are comma-separated. e.g. {2005,2010,2011,2012,2020..23}
    -> '2005, 2010–2012, 2020–2023'."""
    ys = sorted({int(y) for y in ys if str(y).isdigit()})
    if not ys: return ''
    runs = []; s = p = ys[0]
    for y in ys[1:]:
        if y == p + 1: p = y; continue
        runs.append((s, p)); s = p = y
    runs.append((s, p))
    return ', '.join(f"{a}" if a == b else f"{a}–{b}" for a, b in runs)
random.seed(505)
def _na(x):  # accent- & case-insensitive key for name lookups (geoBoundaries names are un-accented)
    return ''.join(c for c in unicodedata.normalize('NFD', str(x)) if unicodedata.category(c) != 'Mn').lower().strip()
# Version label stamped into every report. Importers set it with set_version(); the CLI
# below takes it as argv[1]. Not read from argv at import time so that this module can be
# imported as a library (make_report.py) without inheriting the caller's arguments.
VERSION = 'v0.12'
def set_version(v):
    global VERSION
    if v: VERSION = v

def set_country(iso, name=None):
    """Point the report model at another country's admin-2 geometry. Must be called
    before a loader runs, because DEPTS/EPI and the point-in-polygon index derive from it."""
    global COUNTRY_ISO, COUNTRY_NAME, MAP, DEPTS, latMin, latMax, EPI, _PIP_RINGS
    COUNTRY_ISO = (iso or COUNTRY_ISO).upper()
    MAP = load_country_map(COUNTRY_ISO)
    COUNTRY_NAME = name or MAP.get('country') or COUNTRY_NAME or COUNTRY_ISO
    DEPTS = MAP['depts']
    latMin = min(d['lat'] for d in DEPTS); latMax = max(d['lat'] for d in DEPTS)
    EPI = {d['name']: {'s': southness(d['lat']), 'pop': base_pop(d['name'], southness(d['lat']))}
           for d in DEPTS}
    _PIP_RINGS = None

Z = 1.959963985
def wilson(x, n):
    if n == 0: return (0.0, 0.0, 0.0)
    p = x/n; d = 1+Z*Z/n
    c = (p+Z*Z/(2*n))/d
    h = (Z*math.sqrt(p*(1-p)/n + Z*Z/(4*n*n)))/d
    return (round(100*p,1), round(100*max(0,c-h),1), round(100*min(1,c+h),1))
def cnt(p, n): return int(round(p/100.0*n))

import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repo root (this file lives in scripts/)
# Reference/schema locations are overridable so a deployment can supply updated boundaries
# or an updated WHO compendium without rebuilding the container (see docs/WDL_INTERFACE.md).
REF_DIR    = _os.environ.get('MALARIA_REPORTS_REF_DIR')    or _os.path.join(ROOT, 'reference')
SCHEMA_DIR = _os.environ.get('MALARIA_REPORTS_SCHEMA_DIR') or _os.path.join(ROOT, 'schemas')
import gzip as _gzip, math as _math, re as _re2

COUNTRY_ISO = (_os.environ.get('MALARIA_REPORTS_COUNTRY') or 'SEN').upper()
COUNTRY_NAME = _os.environ.get('MALARIA_REPORTS_COUNTRY_NAME') or ''

def load_country_map(iso=None):
    """Projected admin-2 map for a country: reference/adm2/<ISO3>_adm2_map.json[.gz],
    falling back to the committed Senegal artefact."""
    iso = (iso or COUNTRY_ISO).upper()
    for cand in (_os.path.join(REF_DIR, 'adm2', f'{iso}_adm2_map.json.gz'),
                 _os.path.join(REF_DIR, 'adm2', f'{iso}_adm2_map.json')):
        if _os.path.exists(cand):
            if cand.endswith('.gz'):
                with _gzip.open(cand, 'rt', encoding='utf-8') as fh: return json.load(fh)
            with open(cand, encoding='utf-8') as fh: return json.load(fh)
    if iso == 'SEN':
        return json.load(open(_os.path.join(REF_DIR, 'sen_admin2_map.json')))
    raise SystemExit(f'no admin-2 map for {iso}: expected reference/adm2/{iso}_adm2_map.json(.gz). '
                     'Build one with scripts/build_maps.py --geojson <file> --iso ' + iso)

MAP = load_country_map()
PHA4GE_FIELDS = json.load(open(_os.path.join(SCHEMA_DIR, 'pha4ge_fields.json')))
DEPTS = MAP['depts']
latMin = min(d['lat'] for d in DEPTS); latMax = max(d['lat'] for d in DEPTS)
def southness(lat): return (latMax - lat)/(latMax - latMin)

POP_BASE = {'Dakar':1250000,'Pikine':1200000,'Guédiawaye':330000,'Rufisque':560000,'Thiès':820000,'Mbour':750000}
def base_pop(name,s): return POP_BASE.get(name, int(120000+380000*random.random()+200000*(1-s)))
EPI = {d['name']:{'s':southness(d['lat']),'pop':base_pop(d['name'],southness(d['lat']))} for d in DEPTS}

# ---- marker catalogue --------------------------------------------------------
# (key, gene, gene_id, aa, drug, class, gene_token, synthetic_mean%, criterion)
# class: 'confirmed'  = WHO compendium highest evidence class (Epi.+Lab.+Clin.)
#        'candidate'  = WHO compendium candidate marker
#        'potential'  = WHO compendium potential marker / listed haplotype component
#        'background' = assay-panel background / partner-drug locus, absent from the compendium
#        'research'   = published research association, absent from the compendium
# Sources: WHO "Compendium of molecular markers for antimalarial drug resistance"
# (reference/who_combined.json, 117 entries) for the WHO classes; the codons actually
# typed come from the sr-malaria `sample` genotype columns (WGS) and the MAD4HATTER v4
# resmarker tables (reference/mad_resmarker.tsv + the UCSF resmarker outputs).
MARKERS = [
 # --- Pfk13, artemisinin partial resistance (WHO-confirmed propeller markers) ---
 ('k13_F446I','Pfk13','PF3D7_1343700','F446I','Artemisinin (ACT)','confirmed','k13',0.3,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_N458Y','Pfk13','PF3D7_1343700','N458Y','Artemisinin (ACT)','confirmed','k13',0.2,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_C469Y','Pfk13','PF3D7_1343700','C469Y','Artemisinin (ACT)','confirmed','k13',0.2,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_M476I','Pfk13','PF3D7_1343700','M476I','Artemisinin (ACT)','confirmed','k13',0.2,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_Y493H','Pfk13','PF3D7_1343700','Y493H','Artemisinin (ACT)','confirmed','k13',0.2,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_G533S','Pfk13','PF3D7_1343700','G533S','Artemisinin (ACT)','confirmed','k13',0.1,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_R539T','Pfk13','PF3D7_1343700','R539T','Artemisinin (ACT)','confirmed','k13',0.3,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_I543T','Pfk13','PF3D7_1343700','I543T','Artemisinin (ACT)','confirmed','k13',0.2,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_P553L','Pfk13','PF3D7_1343700','P553L','Artemisinin (ACT)','confirmed','k13',0.3,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_R561H','Pfk13','PF3D7_1343700','R561H','Artemisinin (ACT)','confirmed','k13',0.3,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_P574L','Pfk13','PF3D7_1343700','P574L','Artemisinin (ACT)','confirmed','k13',0.3,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_C580Y','Pfk13','PF3D7_1343700','C580Y','Artemisinin (ACT)','confirmed','k13',0.4,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_R622I','Pfk13','PF3D7_1343700','R622I','Artemisinin (ACT)','confirmed','k13',0.6,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 ('k13_A675V','Pfk13','PF3D7_1343700','A675V','Artemisinin (ACT)','confirmed','k13',0.5,'WHO-confirmed artemisinin partial-resistance marker (K13 propeller)'),
 # --- Pfk13 candidate / potential ---
 ('k13_P441L','Pfk13','PF3D7_1343700','P441L','Artemisinin (ACT)','candidate','k13',0.2,'WHO candidate artemisinin partial-resistance marker'),
 ('k13_C469F','Pfk13','PF3D7_1343700','C469F','Artemisinin (ACT)','candidate','k13',0.2,'WHO candidate artemisinin partial-resistance marker'),
 ('k13_N537I','Pfk13','PF3D7_1343700','N537I','Artemisinin (ACT)','candidate','k13',0.1,'WHO candidate artemisinin partial-resistance marker'),
 ('k13_G538V','Pfk13','PF3D7_1343700','G538V','Artemisinin (ACT)','candidate','k13',0.1,'WHO candidate artemisinin partial-resistance marker'),
 ('k13_V568G','Pfk13','PF3D7_1343700','V568G','Artemisinin (ACT)','candidate','k13',0.2,'WHO candidate artemisinin partial-resistance marker'),
 ('k13_E252Q','Pfk13','PF3D7_1343700','E252Q','Artemisinin (ACT)','candidate','k13',0.2,'WHO candidate artemisinin partial-resistance marker (non-propeller)'),
 ('k13_R515K','Pfk13','PF3D7_1343700','R515K','Artemisinin (ACT)','potential','k13',0.2,'WHO potential artemisinin partial-resistance marker'),
 ('k13_P527H','Pfk13','PF3D7_1343700','P527H','Artemisinin (ACT)','potential','k13',0.1,'WHO potential artemisinin partial-resistance marker'),
 ('k13_G449A','Pfk13','PF3D7_1343700','G449A','Artemisinin (ACT)','potential','k13',0.2,'WHO potential artemisinin partial-resistance marker'),
 ('k13_M579I','Pfk13','PF3D7_1343700','M579I','Artemisinin (ACT)','potential','k13',0.1,'WHO potential artemisinin partial-resistance marker'),
 ('k13_D584V','Pfk13','PF3D7_1343700','D584V','Artemisinin (ACT)','potential','k13',0.2,'WHO potential artemisinin partial-resistance marker'),
 ('k13_Q613E','Pfk13','PF3D7_1343700','Q613E','Artemisinin (ACT)','potential','k13',0.2,'WHO potential artemisinin partial-resistance marker'),
 # --- Pfcrt: chloroquine / amodiaquine and piperaquine ---
 ('crt_K76T','Pfcrt','PF3D7_0709000','K76T','Chloroquine / amodiaquine','confirmed','crt',11.0,'WHO-confirmed chloroquine-resistance transporter marker'),
 ('crt_T93S','Pfcrt','PF3D7_0709000','T93S','Piperaquine','confirmed','crt',0.4,'WHO-confirmed Pfcrt piperaquine-resistance marker'),
 ('crt_H97Y','Pfcrt','PF3D7_0709000','H97Y','Piperaquine','confirmed','crt',0.3,'WHO-confirmed Pfcrt piperaquine-resistance marker'),
 ('crt_F145I','Pfcrt','PF3D7_0709000','F145I','Piperaquine','confirmed','crt',0.2,'WHO-confirmed Pfcrt piperaquine-resistance marker'),
 ('crt_I218F','Pfcrt','PF3D7_0709000','I218F','Piperaquine','confirmed','crt',0.2,'WHO-confirmed Pfcrt piperaquine-resistance marker'),
 ('crt_C350R','Pfcrt','PF3D7_0709000','C350R','Piperaquine / chloroquine','confirmed','crt',0.5,'WHO-confirmed Pfcrt marker (piperaquine; reverts chloroquine resistance)'),
 ('crt_M343L','Pfcrt','PF3D7_0709000','M343L','Piperaquine','candidate','crt',0.3,'WHO candidate Pfcrt piperaquine-resistance marker'),
 ('crt_G353V','Pfcrt','PF3D7_0709000','G353V','Piperaquine','candidate','crt',0.3,'WHO candidate Pfcrt piperaquine-resistance marker'),
 ('crt_C101F','Pfcrt','PF3D7_0709000','C101F','Piperaquine','potential','crt',0.2,'WHO potential Pfcrt piperaquine-resistance marker'),
 ('crt_C72S','Pfcrt','PF3D7_0709000','C72S','Chloroquine / amodiaquine','candidate','crt',6.0,'Component of the WHO-listed Pfcrt chloroquine/amodiaquine-resistance haplotype'),
 ('crt_M74I','Pfcrt','PF3D7_0709000','M74I','Chloroquine / amodiaquine','candidate','crt',7.0,'Component of the WHO-listed Pfcrt chloroquine/amodiaquine-resistance haplotype'),
 ('crt_N75E','Pfcrt','PF3D7_0709000','N75E','Chloroquine / amodiaquine','candidate','crt',7.0,'Component of the WHO-listed Pfcrt chloroquine/amodiaquine-resistance haplotype'),
 ('crt_A220S','Pfcrt','PF3D7_0709000','A220S','Chloroquine / amodiaquine','candidate','crt',8.0,'Component of the WHO-listed Pfcrt chloroquine/amodiaquine-resistance haplotype'),
 ('crt_I356T','Pfcrt','PF3D7_0709000','I356T','Chloroquine / amodiaquine','candidate','crt',5.0,'Component of the WHO-listed Pfcrt chloroquine/amodiaquine-resistance haplotype'),
 # --- Pfmdr1: partner drugs ---
 ('mdr1_N86Y','Pfmdr1','PF3D7_0523000','N86Y','Amodiaquine / lumefantrine','confirmed','mdr1',8.0,'WHO-confirmed multidrug-resistance transporter marker'),
 ('mdr1_S1034C','Pfmdr1','PF3D7_0523000','S1034C','Amodiaquine / lumefantrine','potential','mdr1',0.6,'Component of the WHO-listed Pfmdr1 potential haplotype (S1034C + N1042D + D1246Y)'),
 ('mdr1_N1042D','Pfmdr1','PF3D7_0523000','N1042D','Amodiaquine / lumefantrine','potential','mdr1',0.6,'Component of the WHO-listed Pfmdr1 potential haplotype (S1034C + N1042D + D1246Y)'),
 ('mdr1_D1246Y','Pfmdr1','PF3D7_0523000','D1246Y','Amodiaquine / lumefantrine','potential','mdr1',1.5,'Component of the WHO-listed Pfmdr1 potential haplotype (S1034C + N1042D + D1246Y)'),
 ('mdr1_Y184F','Pfmdr1','PF3D7_0523000','Y184F','Lumefantrine / amodiaquine','background','mdr1',35.0,'Partner-drug response modulator on the assay panel; not listed in the WHO compendium'),
 # --- Pfdhfr / Pfdhps: antifolates (SP, IPTp / SMC / PMC) ---
 ('dhfr_N51I','Pfdhfr','PF3D7_0417200','N51I','Pyrimethamine / SP','potential','dhfr',58.0,'WHO-listed antifolate (pyrimethamine) marker'),
 ('dhfr_C59R','Pfdhfr','PF3D7_0417200','C59R','Pyrimethamine / SP','potential','dhfr',55.0,'WHO-listed antifolate (pyrimethamine) marker'),
 ('dhfr_S108N','Pfdhfr','PF3D7_0417200','S108N','Pyrimethamine / SP','candidate','dhfr',66.0,'WHO candidate antifolate (pyrimethamine) marker'),
 ('dhfr_I164L','Pfdhfr','PF3D7_0417200','I164L','Pyrimethamine / SP','potential','dhfr',0.5,'WHO-listed antifolate (pyrimethamine) marker; high-level antifolate resistance'),
 ('dhfr_A16V','Pfdhfr','PF3D7_0417200','A16V','Cycloguanil / SP','potential','dhfr',0.4,'Component of the WHO-listed Pfdhfr potential haplotype (A16V + S108T)'),
 ('dhps_S436A','Pfdhps','PF3D7_0810800','S436A','Sulfadoxine / SP','potential','dhps',30.0,'WHO-listed antifolate (sulfadoxine) marker / haplotype component'),
 ('dhps_A437G','Pfdhps','PF3D7_0810800','A437G','Sulfadoxine / SP','potential','dhps',42.0,'WHO-listed antifolate (sulfadoxine) marker'),
 ('dhps_K540E','Pfdhps','PF3D7_0810800','K540E','Sulfadoxine / SP','potential','dhps',4.0,'WHO-listed antifolate (sulfadoxine) marker; sextuple-haplotype component'),
 ('dhps_A581G','Pfdhps','PF3D7_0810800','A581G','Sulfadoxine / SP','potential','dhps',0.8,'WHO-listed antifolate (sulfadoxine) marker; sextuple-haplotype component'),
 ('dhps_A613S','Pfdhps','PF3D7_0810800','A613S','Sulfadoxine / SP','potential','dhps',0.6,'WHO-listed antifolate (sulfadoxine) marker / haplotype component'),
 ('dhps_A613T','Pfdhps','PF3D7_0810800','A613T','Sulfadoxine / SP','potential','dhps',0.4,'WHO-listed antifolate (sulfadoxine) marker / haplotype component'),
 ('dhps_I431V','Pfdhps','PF3D7_0810800','I431V','Sulfadoxine / SP','candidate','dhps',0.5,'Component of the WHO-listed Pfdhps candidate haplotype (I431V + S436A + A437G + A581G + A613S)'),
 # --- Pfcytb: atovaquone ---
 ('cytb_Y268S','Pfcytb','mal_mito_3','Y268S','Atovaquone','confirmed','cytb',0.3,'WHO-confirmed atovaquone (cytochrome b) marker'),
 ('cytb_Y268C','Pfcytb','mal_mito_3','Y268C','Atovaquone','potential','cytb',0.2,'WHO potential atovaquone (cytochrome b) marker'),
 # --- Pfcoronin: WHO potential (laboratory) artemisinin markers ---
 ('coronin_G50E','Pfcoronin','PF3D7_1251200','G50E','Artemisinin (ACT)','potential','coronin',1.2,'WHO potential artemisinin marker (laboratory evidence)'),
 ('coronin_R100K','Pfcoronin','PF3D7_1251200','R100K','Artemisinin (ACT)','potential','coronin',1.0,'WHO potential artemisinin marker (laboratory evidence)'),
 ('coronin_E107V','Pfcoronin','PF3D7_1251200','E107V','Artemisinin (ACT)','potential','coronin',0.9,'WHO potential artemisinin marker (laboratory evidence)'),
 ('coronin_P76S','Pfcoronin','PF3D7_1251200','P76S','Artemisinin (research)','research','coronin',0.8,'Research association; not listed in the WHO compendium'),
 # --- assay-panel background / partner loci (counted; labelled as absent from the compendium) ---
 ('arps10_V127M','Pfarps10','PF3D7_1460900','V127M','Artemisinin (genetic background)','background','arps10',4.0,'Panel background locus: artemisinin-resistance genetic background; not listed in the WHO compendium'),
 ('arps10_D128H','Pfarps10','PF3D7_1460900','D128H','Artemisinin (genetic background)','background','arps10',3.0,'Panel background locus: artemisinin-resistance genetic background; not listed in the WHO compendium'),
 ('fd_D193Y','Pffd','PF3D7_1318100','D193Y','Artemisinin (genetic background)','background','fd',3.5,'Panel background locus (ferredoxin): artemisinin-resistance genetic background; not listed in the WHO compendium'),
 ('mdr2_T484I','Pfmdr2','PF3D7_1447900','T484I','Artemisinin (genetic background)','background','mdr2',5.0,'Panel background locus: artemisinin-resistance genetic background; not listed in the WHO compendium'),
 ('exo_E415G','Pfexo','PF3D7_1362500','E415G','Piperaquine (background)','background','exo',2.5,'Panel background locus (exonuclease): piperaquine-resistance background; not listed in the WHO compendium'),
 ('atg18_T38I','Pfatg18','PF3D7_1012900','T38I','Artemisinin (research)','research','atg18',2.0,'Research association; not listed in the WHO compendium'),
 ('aat1_S258L','Pfaat1','PF3D7_0629500','S258L','Chloroquine (research)','research','aat1',9.0,'Research association (amino-acid transporter 1, chloroquine); not listed in the WHO compendium'),
 ('aat1_F313S','Pfaat1','PF3D7_0629500','F313S','Chloroquine (research)','research','aat1',3.0,'Research association (amino-acid transporter 1, chloroquine); not listed in the WHO compendium'),
 ('aat1_Q454E','Pfaat1','PF3D7_0629500','Q454E','Chloroquine (research)','research','aat1',2.0,'Research association (amino-acid transporter 1, chloroquine); not listed in the WHO compendium'),
 ('aat1_K541N','Pfaat1','PF3D7_0629500','K541N','Chloroquine (research)','research','aat1',1.5,'Research association (amino-acid transporter 1, chloroquine); not listed in the WHO compendium'),
 ('carl_I1139K','Pfcarl','PF3D7_0321900','I1139K','Ganaplacide / KAF156 (research)','research','carl',0.5,'Research association (cyclic-amine resistance locus, investigational drug); not listed in the WHO compendium'),
 ('carl_L830V','Pfcarl','PF3D7_0321900','L830V','Ganaplacide / KAF156 (research)','research','carl',0.4,'Research association (cyclic-amine resistance locus, investigational drug); not listed in the WHO compendium'),
 ('carl_S1076N','Pfcarl','PF3D7_0321900','S1076N','Ganaplacide / KAF156 (research)','research','carl',0.4,'Research association (cyclic-amine resistance locus, investigational drug); not listed in the WHO compendium'),
 ('carl_V1103L','Pfcarl','PF3D7_0321900','V1103L','Ganaplacide / KAF156 (research)','research','carl',0.3,'Research association (cyclic-amine resistance locus, investigational drug); not listed in the WHO compendium'),
 ('ubp1_D1525E','Pfubp1','PF3D7_0104300','D1525E','ACT (research)','research','ubp1',0.9,'Research association; not listed in the WHO compendium'),
 ('ubp1_V3275F','Pfubp1','PF3D7_0104300','V3275F','ACT (research)','research','ubp1',0.7,'Research association; not listed in the WHO compendium'),
 ('ap2mu_I592T','Pfap2-mu','PF3D7_1218300','I592T','ACT (research)','research','ap2mu',1.5,'Research association; not listed in the WHO compendium'),
]
CLS_LABEL = {'validated':'Validated marker','candidate':'Candidate marker','potential':'Potential marker',
             'haplotype':'Haplotype component','background':'Not in WHO compendium (panel locus)',
             'research':'Not in WHO compendium (research)'}
MK = {m[0]:dict(gene=m[1],gene_id=m[2],aa=m[3],drug=m[4],cls=m[5],who=(m[5] in ('confirmed','candidate','potential')),
                tok=m[6],mean=m[7],crit=m[8]) for m in MARKERS}

# synthetic-only: fixed per-marker drift so the mock-up trend charts show something
# (sign and magnitude are arbitrary illustration, not an epidemiological claim)
TREND_SLOPE={k:((zlib.crc32(k.encode())%13)-5)/8.0 for k in MK}

_PIP_RINGS = None

def _pip_rings():
    """Parse each unit's SVG path back into projected rings, once."""
    global _PIP_RINGS
    if _PIP_RINGS is None:
        rings = []
        for d in DEPTS:
            polys = []
            for seg in d['path'].split('M'):
                seg = seg.strip()
                if not seg: continue
                pts = []
                for tok in seg.rstrip('Z').split('L'):
                    tok = tok.strip()
                    if not tok: continue
                    x, _, y = tok.partition(',')
                    try: pts.append((float(x), float(y)))
                    except ValueError: pass
                if len(pts) >= 3: polys.append(pts)
            rings.append((d['name'], polys))
        _PIP_RINGS = rings
    return _PIP_RINGS

def project_point(lat, lon):
    """lon/lat -> the same projected x,y that build_maps.py emitted."""
    pad = MAP.get('pad', 10)
    cosLat = _math.cos(_math.radians((MAP['latMin'] + MAP['latMax']) / 2))
    scale = (MAP['W'] - 2 * pad) / ((MAP['lonMax'] - MAP['lonMin']) * cosLat)
    return ((lon - MAP['lonMin']) * cosLat * scale + pad,
            (MAP['latMax'] - lat) * scale + pad)

def dept_of_point(lat, lon):
    """Admin-2 unit containing a coordinate, or None. Works in projected space, so the
    paths that draw the choropleth are also what assigns samples to districts. Paths are
    rounded to 0.1 px (~100 m for a country the size of Senegal), so a point essentially
    on a boundary may fall either side."""
    if lat is None or lon is None: return None
    x, y = project_point(lat, lon)
    for name, polys in _pip_rings():
        for pts in polys:
            inside = False; n = len(pts); j = n - 1
            for i in range(n):
                xi, yi = pts[i]; xj, yj = pts[j]
                if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
                    inside = not inside
                j = i
            if inside: return name
    return None

def region_of(dept_name):
    """Admin-1 name for a unit, when the boundary source carried a parent name."""
    for d in DEPTS:
        if d['name'] == dept_name: return d.get('region') or ''
    return ''

def dept_prev(key,s):
    m=MK[key]['mean']
    if MK[key]['tok'] in ('dhfr','dhps','crt','mdr1') and key not in ('dhps_K540E','dhps_A581G'):
        p=m*(0.55+0.9*s)*(0.75+0.5*random.random())
    else:
        p=m*(0.4+1.3*random.random())
    return max(0.0,min(100.0,p))
def hrp_dept(s):
    h2=max(0.0,min(15.0,2.0+4.0*random.random()+3.5*(1-s)*random.random()))
    return round(h2,1), round(h2+3+6*random.random(),1)

# Capability model — what each platform can actually measure. Cross-checked against
# real data (2026-09): WGS = broad-firecloud-dsde-methods/sr-malaria; MAD4HATTER =
# CIGASS-testing v4 panel, pools 1A+1B+2 (marker table MAD4HAtTer_v4_MarkersTable.csv,
# 276 amplicons). cnv/hrp/species flags are capability, not just diversity.
#   - WGS: genome-wide -> all SNP markers + research loci; CNV via gCNV (cnv_intervals,
#     cnv_contig_ploidy_priors); hrp2/3 by coverage; barcode COI + hmmIBD relatedness.
#   - MAD4HATTER v4: SNP resmarkers (k13/crt/mdr1/dhfr/dhps/cytb + partners); hrp2
#     (PF3D7_0831800) AND hrp3 (PF3D7_1372200) deletion amplicons CONFIRMED in panel;
#     pfpm2/pfpm3 (PF3D7_1408000/1408100) amplicons present -> coverage-based CNV;
#     165 microhaplotypes -> COI + relatedness (RH / co-transmission via Dcifer/hmmIBD);
#     non-falciparum species (Pv/Pm/Poc/Pk ldh). CORRECTION (2026-09-29, from the deployed
#     UCSF resmarker outputs): the shipped panel DOES type coronin (50/100/107) and ubp1
#     (1525) plus background loci arps10, fd, exo, mdr2 and mdr1 Y184F; it does not type
#     ap2-mu, aat1, carl or atg18. CNV/hrp are coverage-based => panel/pool-dependent.
#   - NOMADS (nomads16, not yet a live workspace): core crt/k13/dhfr/dhps/mdr1 only
#     (+ hrp2/3 deletions, pm2/3 CNV, msp2/ama1/csp diversity — none shown in v0.8).
ASSAYS = {
 'WGS': dict(full='Whole-genome sequencing (Illumina)', platform='Illumina NovaSeq (deep WGS)',
   turnaround='3–6 weeks', color='#4a3aa7', n_range=(15,60), years=[str(y) for y in range(2017,2025)], n_depts=11, qc=0.82,
   genes={'k13','crt','mdr1','mdr2','dhfr','dhps','coronin','ubp1','ap2mu','arps10','exo','aat1','carl','atg18'},
   cnv=True, hrp=True, species=False,
   div=dict(coi=True,poly=True,mono=True,rh=True,cotx=True,coi_method='24-SNP barcode heterozygosity'),
   note='Whole-genome short-read sequencing; this report shows the prevalence of drug-resistance markers from the WHO compendium, plus panel background and research loci, called from per-sample genotypes.'),
 'MAD4HATTER': dict(full='MAD4HATTER v4 amplicon panel (Illumina)', platform='Illumina (v4, pools 1A+1B+2)',
   turnaround='1–2 weeks', color='#1baf7a', n_range=(30,260), years=[str(y) for y in range(2020,2025)], n_depts=38, qc=0.87,
   genes={'k13','crt','mdr1','mdr2','dhfr','dhps','cytb','coronin','ubp1','arps10','fd','exo'},
   cnv=True, hrp=True, species=True,
   div=dict(coi=True,poly=True,mono=True,rh=True,cotx=True,coi_method='naive COI (max distinct microhaplotype alleles per locus)'),
   note='v4 amplicon panel (resistance pools); this report shows the prevalence of drug-resistance markers from the WHO compendium, called from resistance-marker (resmarker) output. Also types Pfcoronin, Pfubp1, and the panel background loci (Pfarps10, Pffd, Pfmdr2, and Pfexo); it does not type Pfap2-mu, Pfaat1, Pfcarl or Pfatg18.'),
 'NOMADS': dict(full='NOMADS targeted panel (Oxford Nanopore)', platform='ONT MinION (nomads16)',
   turnaround='1–3 days', color='#2a78d6', n_range=(40,160), years=[str(y) for y in range(2022,2025)], n_depts=19, qc=0.84,
   genes={'k13','crt','mdr1','dhfr','dhps'},
   cnv=False, hrp=True, species=False,
   div=dict(coi=True,poly=True,mono=True,rh=False,cotx=False,coi_method='msp2 allele counting (coarse)'),
   note='Targeted ONT amplicon panel (nomads16); this report shows the prevalence of the core Pfcrt / Pfk13 / Pfdhfr / Pfdhps / Pfmdr1 markers listed in the WHO compendium. The panel carries no atovaquone or Pfcoronin markers and none of the dedicated background loci (Pfarps10, Pffd, Pfmdr2, Pfexo), though Pfmdr1 Y184F is typed.'),
}
PIPELINE_LINKS = {
 'WGS':[('Malaria Plasmodium Illumina Whole Genome — featured workspace (Terra)','https://app.terra.bio/#workspaces/malaria-featured-workspaces/Malaria_Plasmodium_Illumina_Whole_Genome'),
        ('MalariaGEN Pf7 Data Resource (Terra)','https://app.terra.bio/#workspaces/malaria-featured-workspaces/MalariaGEN_Pf7_Data_Resource'),
        ('MalariaGEN Pf8 Data Resource (Terra)','https://app.terra.bio/#workspaces/gates-malaria/MalariaGEN_Pf8_Data_Resource'),
        ('PlasmoDB (Pf3D7 reference)','https://plasmodb.org/')],
 'MAD4HATTER':[('MAD4HATTER pipeline — EPPIcenter (GitHub)','https://github.com/EPPIcenter/mad4hatter'),
        ('MAD4HATTER documentation','https://eppicenter.github.io/mad4hatter/'),
        ('Copy-number / deletion estimation (EPPIcenter)','https://github.com/EPPIcenter/copy-number-variation'),
        ('Malaria Plasmodium Illumina Amplicon Mad4Hatter — featured workspace (Terra)','https://app.terra.bio/#workspaces/gates-malaria/Malaria_Plasmodium_Illumina_Amplicon_Mad4Hatter')],
 'NOMADS':[('NOMADS community (GitHub)','https://github.com/nomads-community'),
        ('nomadic analysis toolkit','https://github.com/nomads-community/nomadic'),
        ('nomadic workflow demo — featured workspace (Terra)','https://app.terra.bio/#workspaces/gates-malaria/nomadic-workflow-demo')],
 'COMBINED':[('MAD4HATTER — EPPIcenter (GitHub)','https://github.com/EPPIcenter/mad4hatter'),
        ('Malaria Plasmodium Illumina Whole Genome — featured workspace (Terra)','https://app.terra.bio/#workspaces/malaria-featured-workspaces/Malaria_Plasmodium_Illumina_Whole_Genome'),
        ('MalariaGEN Pf7 Data Resource (Terra)','https://app.terra.bio/#workspaces/malaria-featured-workspaces/MalariaGEN_Pf7_Data_Resource'),
        ('MalariaGEN Pf8 Data Resource (Terra)','https://app.terra.bio/#workspaces/gates-malaria/MalariaGEN_Pf8_Data_Resource')],
}

# ---- WHO compendium classification (derived from the source file, not hand-typed) ----
WHO_URL = 'https://www.who.int/publications/m/item/compendium-of-molecular-markers-for-antimalarial-drug-resistance'
_WHO_GENE_TOK = {'pfk13':'k13','pfcrt':'crt','pfdhfr':'dhfr','pfdhps':'dhps','pfcytb':'cytb',
                 'pfmdr1':'mdr1','pfcoronin':'coronin','pfpm2/3':'pm23','pfgch1':'gch1'}
_WHO_RANK = {'Validated':3,'Candidate':2,'Potential':1}

def _alt_components(alt):
    """Split a compendium alteration cell into individual amino-acid changes.
    Handles '+' haplotypes, parenthesised wild-type runs, and slash forms
    ('S108N/T' -> S108N, S108T)."""
    out = []
    for part in re.split(r'[+&]', alt.replace('(', ' ').replace(')', ' ')):
        t = part.strip()
        if not t: continue
        m = re.match(r'^([A-Z]?)(\d+)([A-Za-z*](?:/[A-Za-z*])*)$', t)
        if not m: continue
        ref, pos, alts = m.groups()
        for a in alts.split('/'):
            out.append((int(pos), a.upper()))
    return out

def _who_index():
    """gene token -> list of (components, who_class_string, raw_alt). A
    'Pfdhfr & Pfdhps' row is split so each gene gets only its own alterations."""
    idx = {}
    for r in json.load(open(_os.path.join(REF_DIR, 'who_combined.json'))):
        genes = [g.strip() for g in r['gene'].split('&')]
        alts  = [a.strip() for a in r['alt'].split('&')]
        if len(genes) > 1 and len(alts) != len(genes): continue
        total = len(_alt_components(r['alt']))          # components across the whole entry
        for gi, g in enumerate(genes):
            tok = _WHO_GENE_TOK.get(g.lower())
            if not tok: continue
            a = alts[gi] if len(genes) > 1 else r['alt']
            comps = _alt_components(a)
            if comps: idx.setdefault(tok, []).append((comps, r['cls'], r['alt'].strip(), total))
    return idx

WHO_IDX = _who_index()

def who_classify(tok, aa):
    """Return (class_key, who_class_string, how) for a gene token + AA change.
    A marker WHO lists on its own gets WHO's class for that entry. A marker that
    only ever appears inside a listed multi-codon haplotype is reported as a
    haplotype component -- inheriting the haplotype's class would claim a WHO
    status for the single codon that WHO does not give it."""
    m = re.match(r'^([A-Z])(\d+)([A-Za-z*])$', aa)
    if not m: return (None, None, None)
    pos, alt = int(m.group(2)), m.group(3).upper()
    best_single = best_hap = None
    for comps, cls, raw, total in WHO_IDX.get(tok, []):
        if (pos, alt) not in comps: continue
        rank = _WHO_RANK.get(cls.split()[0], 0)
        if total == 1:
            if not best_single or rank > best_single[0]: best_single = (rank, cls, raw)
        else:
            if not best_hap or rank > best_hap[0]: best_hap = (rank, cls, raw)
    if best_single:
        return (best_single[1].split()[0].lower(), best_single[1], 'listed individually')
    if best_hap:
        return ('haplotype', best_hap[1], 'component of the WHO-listed haplotype ' + best_hap[2])
    return (None, None, None)

# Classes come from the WHO compendium, not from the table above: who_classify() reads
# reference/who_combined.json, so the labels in the report are WHO's own and traceable.
# The catalogue's own class field is only a fallback for loci WHO does not list.
_CLS_PREFIX = re.compile(r'^(WHO-confirmed|WHO candidate|WHO potential|WHO-listed|Component of the WHO-listed)\s*')
for _k, _m in MK.items():
    _cls, _who, _how = who_classify(_m['tok'], _m['aa'])
    _desc = _CLS_PREFIX.sub('', _m['crit']).strip()
    if _cls:
        _m['cls'] = _cls; _m['who_cls'] = _who; _m['who_how'] = _how; _m['who'] = True
        _m['crit'] = f"WHO Compendium: {_who} \u2014 {_how}" + (f". {_desc[0].upper()}{_desc[1:]}" if _desc else '')
    else:
        assert _m['cls'] in ('background', 'research'), f"{_k}: claimed a WHO class but is not in the compendium"
        _m['who_cls'] = None; _m['who_how'] = None; _m['who'] = False
        _m['crit'] = _desc
del _k, _m, _cls, _who, _how, _desc

MARKER_PCT = 10.0
MIN_FRAME_N = 100     # a year with >= this many QC pass samples becomes its own trend frame

class Selection:
    """An optional sample allow-list. Report prevalence is a proportion, so a filtered
    cohort has to be visible in the report rather than silently changing the denominators:
    this tracks what was asked for, what matched and what was never seen, and
    assemble_report() stamps all of it into the report metadata."""

    def __init__(self, ids=None, label=None):
        self.label = label or ''
        self.requested = [i for i in (ids or []) if i]
        self._want = set(self.requested)
        self.matched = set()

    def __bool__(self):
        return bool(self._want)

    def keep(self, *candidate_ids):
        """True when the sample should be included. Several id forms may be offered
        (e.g. a run-suffixed MAD4HATTER id and its base id); any match keeps the sample."""
        if not self._want:
            return True
        for cid in candidate_ids:
            if cid and cid in self._want:
                self.matched.add(cid)
                return True
        return False

    def meta(self):
        if not self._want:
            return {}
        missing = sorted(self._want - self.matched)
        return {'sample_selection': self.label or 'explicit sample list',
                'n_requested': len(self.requested),
                'n_matched': len(self.matched),
                'n_requested_missing': len(missing),
                'requested_missing_examples': missing[:20]}

    @staticmethod
    def from_arg(arg, label=None):
        """arg is a path to a file of ids (one per line) or a comma-separated list."""
        if not arg:
            return Selection()
        if _os.path.exists(arg):
            with open(arg) as fh:
                ids = [ln.strip() for ln in fh if ln.strip() and not ln.startswith('#')]
        else:
            ids = [t.strip() for t in arg.split(',') if t.strip()]
        return Selection(ids, label)

HRP_PCT    = 5.0
MIN_SAMPLES = 5
MONTHS = [f'2024-{m:02d}' for m in range(1,13)]

def make_frames(year_counts, min_n=MIN_FRAME_N):
    """Group consecutive years into display frames with a usable denominator.
    A year that reaches min_n on its own stands alone; sparse runs are merged until
    they reach min_n; a trailing remainder joins the previous frame. Real cohorts are
    very uneven (the Senegal WGS set has 1-32 samples/year before 2019, then 614/542/
    115/674), so fixed 5-year bins would bury the dense years inside sparse ones."""
    ys = sorted(year_counts)
    frames = []; pend = []; pn = 0
    for y in ys:
        n = year_counts[y]
        if n >= min_n:
            if pend: frames.append(pend); pend = []; pn = 0
            frames.append([y]); continue
        pend.append(y); pn += n
        if pn >= min_n: frames.append(pend); pend = []; pn = 0
    if pend:
        if frames: frames[-1] = frames[-1] + pend
        else: frames.append(pend)
    return [{'key': f[0] if len(f) == 1 else f[0] + '-' + f[-1],
             'label': fmt_years(f), 'years': f} for f in frames]

def build_trends(covered, units):
    """Per-unit, per-year marker atoms (the only time-resolved store; frames and
    national totals are summed from these, client-side and in the self-checks, so a
    frame can never disagree with the years it contains).
    Each unit may carry by_year = {year: {'n':int, 'x':{mk:ct}, 'd':{mk:ct}}}."""
    has = any(u.get('by_year') for u in units)
    if not has: return None
    mk = list(covered)
    year_counts = {}
    uout = {}
    for u in units:
        by = u.get('by_year') or {}
        if not by: continue
        rec = {}
        for y, v in sorted(by.items()):
            n = int(v.get('n', 0))
            if n <= 0: continue
            rec[y] = {'n': n,
                      'x': [int((v.get('x') or {}).get(k, 0)) for k in mk],
                      'd': [int((v.get('d') or {}).get(k, 0)) for k in mk]}
            year_counts[y] = year_counts.get(y, 0) + n
        if rec: uout[u['name']] = rec
    if not uout: return None
    years = sorted(year_counts)
    nat = {}
    for y in years:
        xs = [0]*len(mk); ds = [0]*len(mk)
        for rec in uout.values():
            if y not in rec: continue
            for i in range(len(mk)):
                xs[i] += rec[y]['x'][i]; ds[i] += rec[y]['d'][i]
        nat[y] = {'n': year_counts[y], 'x': xs, 'd': ds}
    return {'mk': mk, 'years': years, 'year_n': year_counts,
            'frames': make_frames(year_counts), 'nat': nat, 'units': uout,
            'min_frame_n': MIN_FRAME_N}

def assemble_report(name, spec, units, selection=None):
    """Assemble the template DATA blob from per-admin-2 unit records.
    Shared by the synthetic generator (build_assay) and real-data loaders
    (load_wgs.py, ...). Each unit dict: name, sampled(bool), n(QC pass denom),
    n_col?(collected), date_min?/date_max?, mk{k:pct}, mkx{k:mutant_ct},
    mkn{k:genotyped_ct}, hrp2/hrp3(pct) + hrp2x/hrp3x/hrpn(cts), div{coi,poly,mono,rh,cotx}."""
    covered=[k for k in MK if MK[k]['tok'] in spec['genes']]
    sampled=[u for u in units if u.get('sampled')]
    chosen_names={u['name'] for u in sampled}
    tot_col=sum(u.get('n_col',u.get('n',0)) for u in sampled); tot_qc=sum(u.get('n',0) for u in sampled)
    natx={k:0 for k in MK}; natn={k:0 for k in MK}
    for u in sampled:
        for k in covered:
            natx[k]+=(u.get('mkx') or {}).get(k,0); natn[k]+=(u.get('mkn') or {}).get(k,0)
    natmarkers=[]
    for k,m in MK.items():
        base=dict(key=k,gene=m['gene'],gene_id=m['gene_id'],aa=m['aa'],drug=m['drug'],who=m['who'],
                  cls=m['cls'],category=CLS_LABEL[m['cls']],crit=m['crit'],
                  who_cls=m.get('who_cls'),who_how=m.get('who_how'))
        if m['tok'] not in spec['genes'] or natn.get(k,0)==0: base['assessed']=False; natmarkers.append(base); continue
        est,lo,hi=wilson(natx[k],natn[k])
        base.update(assessed=True,x=natx[k],n=natn[k],est=est,lo=lo,hi=hi,action=(m['cls']=='validated' and est>=MARKER_PCT))
        natmarkers.append(base)
    res_hits=[m for m in natmarkers if m.get('assessed') and m.get('cls')=='validated' and m['est']>=MARKER_PCT]
    res_watch=[m for m in natmarkers if m.get('assessed') and m.get('cls')=='validated' and 5.0<=m['est']<MARKER_PCT]
    stoplight=[
      dict(cat='Resistance Markers',status=('red' if res_hits else 'amber' if res_watch else 'green'),
           findings=([f"{m['gene']} {m['aa']} = {m['est']}% (≥{int(MARKER_PCT)}%)" for m in res_hits]
                     +[f"{m['gene']} {m['aa']} = {m['est']}% (watch, 5–10%)" for m in res_watch]) or ['No WHO Validated marker at or above the action threshold']),
    ]
    trends=build_trends(covered, units)
    tabs=['summary','resistance']+(['trends'] if trends else [])+['export','methods']
    for u in sampled:
        if not u.get('years'):
            u['years']=sorted({str(d)[:4] for d in (u.get('date_min'),u.get('date_max')) if d and str(d)[:4].isdigit()})
    allyears=set()
    for u in sampled: allyears|=set(u.get('years') or [])
    period=fmt_years(allyears) or 'n/a'
    meta=dict(assay=name,assay_full=spec['full'],platform=spec['platform'],
              color=spec['color'],note=spec['note'],country=(COUNTRY_NAME or 'Senegal'),admin=(MAP.get('admin_label') or 'Admin-2 (district)'),
              admin_available=True,dates_available=bool(allyears),period=period,years=sorted(allyears),
              links=PIPELINE_LINKS.get(name,[]),
              generated='2026-09-23',version=VERSION,real=False,data_source='Synthetic design mock-up (illustrative values)',
              marker_action_pct=MARKER_PCT,min_samples=MIN_SAMPLES,who_url=WHO_URL,
              n_units_sampled=len(chosen_names),n_units_total=len(DEPTS),n_collected=tot_col,n_qc=tot_qc,
              n_called=tot_qc,   # loaders override: QC pass samples with >=1 marker genotype call
              qc_rate=round(100*tot_qc/tot_col,1) if tot_col else 0)
    if selection is not None:
        meta.update(selection.meta())
    caps=dict(tabs=tabs,genes=sorted(spec['genes']),covered_markers=covered)
    # v0.8: COI (transmission) and HRP2/3 (diagnostics) sections removed from the report;
    # per-unit hrp/div inputs are accepted from loaders but not emitted.
    drop=('hrp2','hrp3','hrp2x','hrp3x','hrpn','div','coi','poly','mono','by_year')
    units=[{k:v for k,v in u.items() if k not in drop} for u in units]
    rep_=dict(meta=meta,capabilities=caps,map=MAP,units=units,markers=natmarkers,
              stoplight=stoplight,marker_defs={k:MK[k] for k in MK})
    if trends:
        rep_['trends']=trends
        # pooled numbers must equal the sum over years, or the pooled view and the
        # trend view would tell different stories for the same cohort.
        for i,k in enumerate(trends['mk']):
            sx=sum(v['x'][i] for v in trends['nat'].values()); sd=sum(v['d'][i] for v in trends['nat'].values())
            assert sx==natx[k] and sd==natn[k], f'{name} {k}: pooled {natx[k]}/{natn[k]} != per-year {sx}/{sd}'
        assert sum(v['n'] for v in trends['nat'].values())==tot_qc, f'{name}: per-year n != pooled n_qc'
    return rep_

def build_assay(name, spec):
    random.seed(zlib.crc32(name.encode()))   # stable across runs (hash() is PYTHONHASHSEED-salted)
    order=sorted(DEPTS,key=lambda d:(-EPI[d['name']]['pop']-random.random()*400000))
    chosen=(random.sample([d for d in DEPTS if EPI[d['name']]['pop']>250000],spec['n_depts'])
            if name=='WGS' else order[:spec['n_depts']])
    chosen_names={d['name'] for d in chosen}
    covered=[k for k in MK if MK[k]['tok'] in spec['genes']]
    units=[]
    for d in DEPTS:
        s=EPI[d['name']]['s']; rec={'name':d['name']}
        if d['name'] in chosen_names:
            lo,hi=spec['n_range']; n=int(lo+(hi-lo)*(0.3+0.7*random.random())); nqc=int(n*spec['qc']*(0.94+0.06*random.random()))
            rec.update(n=nqc,n_col=n,sampled=True)
            mi=random.randint(0,10); rec['date_min']=MONTHS[mi]; rec['date_max']=MONTHS[min(11,mi+random.randint(0,2))]
            # time-resolved synthetic draws: each unit samples a recent run of years,
            # markers drift linearly over the span (sign fixed per marker), and the
            # pooled counts below are summed from the years so the two always agree.
            yrs_all=spec['years']; start=random.randint(0,max(0,len(yrs_all)-2))
            uyears=yrs_all[start:]
            w=[0.4+random.random() for _ in uyears]; tw=sum(w)
            alloc=[max(1,int(round(nqc*x/tw))) for x in w]
            alloc[-1]+=nqc-sum(alloc)
            if alloc[-1]<1: alloc[-1]=1
            nqc=sum(alloc)
            rec['n']=nqc; rec['n_col']=int(round(nqc/spec['qc']))
            rec['date_min']=uyears[0]; rec['date_max']=uyears[-1]; rec['years']=list(uyears)
            rec['by_year']={}
            rec['mkx']={k:0 for k in covered}; rec['mkn']={k:0 for k in covered}
            for yi,(yy,ny) in enumerate(zip(uyears,alloc)):
                t=(yi/(len(uyears)-1)) if len(uyears)>1 else 1.0
                xs={}; ds={}
                for k in covered:
                    slope=TREND_SLOPE[k]
                    p=max(0.0,min(100.0,dept_prev(k,s)*(1+slope*(t-0.5))))
                    xs[k]=cnt(p,ny); ds[k]=ny
                    rec['mkx'][k]+=xs[k]; rec['mkn'][k]+=ny
                rec['by_year'][yy]={'n':ny,'x':xs,'d':ds}
            rec['mk']={k:(round(100*rec['mkx'][k]/rec['mkn'][k],1) if rec['mkn'][k] else 0.0) for k in covered}
            h2,h3=hrp_dept(s); rec['hrp2']=h2; rec['hrp3']=h3
            rec['hrp2x']=cnt(h2,nqc); rec['hrp3x']=cnt(h3,nqc); rec['hrpn']=nqc
            coi=round(1.3+1.6*s+0.25*random.random(),2)
            poly=int(round(min(95,100*(0.15+0.7*s)*(0.85+0.3*random.random()))))
            div={'coi':coi,'poly':poly,'mono':100-poly}
            div['rh']=round(0.15+0.6*s*(0.7+0.6*random.random()),2) if spec['div']['rh'] else None
            div['cotx']=int(round(min(90,100*(0.2+0.55*s)*(0.8+0.4*random.random())))) if spec['div']['cotx'] else None
            rec['div']=div
        else:
            rec.update(sampled=False,n=0)
        units.append(rec)
    return assemble_report(name, spec, units)

def build_combined(reports):
    units=[]
    for d in DEPTS:
        recs={a:next(u for u in reports[a]['units'] if u['name']==d['name']) for a in ASSAYS}
        samp=[recs[a] for a in ASSAYS if recs[a].get('sampled')]
        rec={'name':d['name'],'sampled':bool(samp),'assays':[a for a in ASSAYS if recs[a].get('sampled')]}
        rec['n']=sum(r['n'] for r in samp)
        if samp:
            rec['date_min']=min(r['date_min'] for r in samp); rec['date_max']=max(r['date_max'] for r in samp)
            rec['years']=sorted(set().union(*[set(r.get('years',[])) for r in samp]))
            mk={}
            for r in samp:
                for k,v in r.get('mk',{}).items(): mk.setdefault(k,[]).append(v)
            rec['mk']={k:round(sum(v)/len(v),1) for k,v in mk.items()}
            # per-year atoms: sum the contributing assays' own trend atoms for this unit
            by={}
            for a in ASSAYS:
                tr=reports[a].get('trends')
                if not tr or d['name'] not in tr['units']: continue
                for yy,v in tr['units'][d['name']].items():
                    slot=by.setdefault(yy,{'n':0,'x':{},'d':{}})
                    slot['n']+=v['n']
                    for i,k in enumerate(tr['mk']):
                        slot['x'][k]=slot['x'].get(k,0)+v['x'][i]
                        slot['d'][k]=slot['d'].get(k,0)+v['d'][i]
            if by: rec['by_year']=by
        units.append(rec)
    genes=set().union(*[ASSAYS[a]['genes'] for a in ASSAYS]); covered=[k for k in MK if MK[k]['tok'] in genes]
    natmarkers=[]
    for k,m in MK.items():
        contrib=[a for a in ASSAYS if m['tok'] in ASSAYS[a]['genes']]
        base=dict(key=k,gene=m['gene'],gene_id=m['gene_id'],aa=m['aa'],drug=m['drug'],who=m['who'],
                  cls=m['cls'],category=CLS_LABEL[m['cls']],crit=m['crit'],
                  who_cls=m.get('who_cls'),who_how=m.get('who_how'))
        if not contrib: base['assessed']=False; natmarkers.append(base); continue
        x=sum(next((mm['x'] for mm in reports[a]['markers'] if mm['key']==k and mm.get('assessed')),0) for a in contrib)
        n=sum(next((mm['n'] for mm in reports[a]['markers'] if mm['key']==k and mm.get('assessed')),0) for a in contrib)
        est,lo,hi=wilson(x,n); base.update(assessed=True,x=x,n=n,est=est,lo=lo,hi=hi,action=(m['cls']=='validated' and est>=MARKER_PCT),assays=contrib)
        natmarkers.append(base)
    res_hits=[m for m in natmarkers if m.get('assessed') and m.get('cls')=='validated' and m['est']>=MARKER_PCT]
    res_watch=[m for m in natmarkers if m.get('assessed') and m.get('cls')=='validated' and 5.0<=m['est']<MARKER_PCT]
    stoplight=[dict(cat='Resistance Markers',status=('red' if res_hits else 'amber' if res_watch else 'green'),
                    findings=([f"{m['gene']} {m['aa']} = {m['est']}% (≥{int(MARKER_PCT)}%)" for m in res_hits]
                              +[f"{m['gene']} {m['aa']} = {m['est']}% (watch)" for m in res_watch]) or ['No WHO Validated marker at or above the action threshold'])]
    tot_qc=sum(reports[a]['meta']['n_qc'] for a in ASSAYS); tot_col=sum(reports[a]['meta']['n_collected'] for a in ASSAYS)
    meta=dict(assay='COMBINED',assay_full='Combined multi-assay (WGS + MAD4HATTER + NOMADS)',
              platform='Illumina WGS + Illumina amplicon + ONT',color='#006dae',
              note='Harmonised view; markers pooled across assays that type each locus.',country=(COUNTRY_NAME or 'Senegal'),
              admin='Admin-2 (department)',admin_available=True,dates_available=True,
              period=(fmt_years(set().union(*([set(u.get('years',[])) for u in units if u.get('sampled')] or [set()]))) or 'n/a'),
              years=sorted(set().union(*([set(u.get('years',[])) for u in units if u.get('sampled')] or [set()]))),
              links=PIPELINE_LINKS.get('COMBINED',[]),
              generated='2026-09-23',version=VERSION,real=False,data_source='Synthetic design mock-up (illustrative values)',
              marker_action_pct=MARKER_PCT,min_samples=MIN_SAMPLES,who_url=WHO_URL,
              n_units_sampled=sum(1 for u in units if u['sampled']),n_units_total=len(DEPTS),
              n_collected=tot_col,n_qc=tot_qc,qc_rate=round(100*tot_qc/tot_col,1),by_assay={a:reports[a]['meta']['n_qc'] for a in ASSAYS})
    ctrends=build_trends(covered, units)
    caps=dict(tabs=['summary','resistance']+(['trends'] if ctrends else [])+['export','methods'],
              genes=sorted(genes),covered_markers=covered,
              assays=list(ASSAYS.keys()),assay_colors={a:ASSAYS[a]['color'] for a in ASSAYS})
    out=dict(meta=meta,capabilities=caps,map=MAP,units=[{k:v for k,v in u.items() if k!='by_year'} for u in units],
             markers=natmarkers,stoplight=stoplight,marker_defs={k:MK[k] for k in MK})
    if ctrends: out['trends']=ctrends
    return out

def build_synthetic_reports():
    """Build the four synthetic mock-up reports (design review only)."""
    reports = {name: build_assay(name, spec) for name, spec in ASSAYS.items()}
    reports['COMBINED'] = build_combined(reports)
    for a in reports: add_export(reports[a])
    return reports

# Senegal admin-2 (department) -> admin-1 (region), best-effort for the Africa CDC "Region" column.
SEN_REGION = {
 'Dakar':'Dakar','Pikine':'Dakar','Guédiawaye':'Dakar','Rufisque':'Dakar','Keur Massar':'Dakar',
 'Thiès':'Thiès','Mbour':'Thiès','Tivaouane':'Thiès',
 'Diourbel':'Diourbel','Bambey':'Diourbel','Mbacké':'Diourbel',
 'Fatick':'Fatick','Foundiougne':'Fatick','Gossas':'Fatick',
 'Kaffrine':'Kaffrine','Birkelane':'Kaffrine','Koungheul':'Kaffrine','Malem Hodar':'Kaffrine',
 'Kaolack':'Kaolack','Guinguinéo':'Kaolack','Nioro du Rip':'Kaolack',
 'Kédougou':'Kédougou','Salémata':'Kédougou','Saraya':'Kédougou',
 'Kolda':'Kolda','Médina Yoro Foulah':'Kolda','Vélingara':'Kolda',
 'Louga':'Louga','Kébémer':'Louga','Linguère':'Louga',
 'Matam':'Matam','Kanel':'Matam','Ranérou':'Matam',
 'Saint-Louis':'Saint-Louis','Dagana':'Saint-Louis','Podor':'Saint-Louis',
 'Sédhiou':'Sédhiou','Bounkiling':'Sédhiou','Goudomp':'Sédhiou',
 'Tambacounda':'Tambacounda','Bakel':'Tambacounda','Goudiry':'Tambacounda','Koumpentoum':'Tambacounda',
 'Ziguinchor':'Ziguinchor','Bignona':'Ziguinchor','Oussouye':'Ziguinchor',
}
ASSAY_NAME = {'WGS':'Whole genome sequencing','MAD4HATTER':'Amplicon sequencing',
              'NOMADS':'Amplicon sequencing (Nanopore)','COMBINED':'Mixed (WGS + amplicon)'}

_MON = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
def _mmm_yyyy(d):
    """Collection date -> 'MMM-YYYY' when month known (YYYYMMDD), else the bare year."""
    d = str(d or '')
    if len(d) >= 6 and d[:6].isdigit():
        mo = int(d[4:6]); return f"{_MON[mo-1]}-{d[:4]}" if 1 <= mo <= 12 else d[:4]
    if len(d) >= 4 and d[:4].isdigit(): return d[:4]
    return ''
# export view metadata: key -> (button label, csv filename, on-screen title)
VIEW_META = {
 'who':      ('WHO Threat Maps', 'who_threat_map.csv', 'WHO Malaria Threats Map',
             'WHO Malaria Threats Map layout: one row per admin-2 × marker (samples tested, mutant present, percent, and WHO class). Representative of the schema.'),
 'afcdc':    ('Africa CDC', 'afcdc_mutation_haplotype.csv', 'Africa CDC — Mutation / Haplotype data sheet',
             'Africa CDC Mutation/Haplotype data sheet: one row per sample × observed mutant alteration (Gene symbol · Gene Alteration · Haplotype). Columns not captured in the sequencing data (host subject ID, haplotype, travel history, destinations, endemicity, and study type) are left blank.'),
 'pha4ge':   ('PHA4GE', 'pha4ge_malaria_standard.csv', 'PHA4GE Malaria Community Standard (human sample) — one row per sample × observed alteration',
             'PHA4GE Malaria Community Standard (human sample): the 210-field per-specimen schema, one row per sample × observed alteration. Only fields the genomic data supports are populated (sample ID, geography, collection date, organism/host, assay/instrument, MOI, and gene/alteration); all other fields (accessions, host demographics, sequencing kit, etc.) are left blank.'),
 'dhis2':    ('DHIS2', 'dhis2_datavalueset.csv', 'DHIS2 dataValueSet',
             'DHIS2 dataValueSet import schema: dataElement · period · orgUnit · categoryOptionCombo · value — one row per admin-2 × marker (value = prevalence %).'),
}
def _iso_date(d):
    d = str(d or '')
    if len(d) >= 8 and d[:8].isdigit(): return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    if len(d) >= 4 and d[:4].isdigit(): return d[:4]
    return ''
def build_pha4ge(samples, mkdefs, assay_name, platform):
    """PHA4GE Malaria Community Standard rows (per sample × observed mutant alteration).
    Fills the fields our genomic data supports; everything else (host demographics, accessions,
    sequencing kit, etc.) is left blank per the real-only rule."""
    rows = []
    for s in samples:
        muts = [mkdefs[k] for k, (wt, mut) in (s.get('calls') or {}).items()
                if mut > 0 and mkdefs.get(k) and mkdefs[k].get('assessed')]
        if not muts: continue
        base = {f: '' for f in PHA4GE_FIELDS}
        d = str(s.get('date') or ''); iso = _iso_date(d)
        base.update({'specimen_collector_sample_ID': s['id'], 'organism': 'Plasmodium falciparum',
                     'host_taxid': '9606', 'host(common_name)': 'Human', 'host(scientific_name)': 'Homo sapiens',
                     'geo_loc_name(country)': 'Senegal', 'geo_loc_name(state/province/territory)': s.get('region') or '',
                     'geo_loc_name(county/region)': s.get('district') or '', 'geo_loc_name(city)': s.get('site') or '',
                     'sample_collection_date': iso,
                     'sample_collection_date_precision': ('day' if len(d) >= 8 and d[:8].isdigit() else 'year' if iso else ''),
                     'sequencing_assay_type': assay_name, 'sequencing_instrument': platform or ''})
        if s.get('lat') is not None: base['geo_loc_latitude'] = s['lat']
        if s.get('lon') is not None: base['geo_loc_longitude'] = s['lon']
        for m in muts:
            r = dict(base); g = _afgene(m['gene'])
            r['gene_name'] = g; r['gene_symbol'] = g; r['gene_alteration'] = m['aa']
            rows.append(r)
    return rows
def _csv_cell(v):
    s = str(v)
    return '"'+s.replace('"', '""')+'"' if any(c in s for c in ',"\n\r') else s
def _csv_text(rows):
    if not rows: return ''
    cols = list(rows[0].keys())
    out = [','.join(cols)]
    for r in rows: out.append(','.join(_csv_cell(r.get(c, '')) for c in cols))
    return '\n'.join(out)
def _pack_export(rep, rows_by_key, note, order, preview_n=50):
    """Store FULL export tables gzip+base64 (decompressed/downloaded client-side) plus a small
    on-screen preview + row count. Avoids embedding the full uncompressed tables in the page.
    rows_by_key: {view_key: [row dicts]}; order: display order of view keys."""
    views = {}
    for key in order:
        rows = rows_by_key.get(key, [])
        label, name, title, vnote = VIEW_META[key]
        views[key] = dict(label=label, name=name, title=title, note=vnote,
                          cols=(list(rows[0].keys()) if rows else []), count=len(rows),
                          preview=rows[:preview_n],
                          gz=base64.b64encode(gzip.compress(_csv_text(rows).encode(), mtime=0)).decode())
    rep['export'] = dict(views=views, order=order, note=note)

def add_export(rep):
    ctry=rep['meta']['country']; assay=rep['meta']['assay']; assay_name=ASSAY_NAME.get(assay,'Sequencing')
    markers=[m for m in rep['markers'] if m.get('assessed')]
    who=[]; dhis=[]
    for m in markers:
        who.append(dict(country=ctry,admin1='(national)',admin2='(pooled)',year=2024,gene=m['gene'],mutation=m['aa'],
                        tested=m['n'],present=m['x'],percent=m['est'],who_tracked=('Yes' if m['who'] else 'No — research')))
        dhis.append(dict(dataElement=("MAL_RES_"+m['gene']+"_"+m['aa']).replace(' ',''),period='2024',
                         orgUnit=ctry,categoryOptionCombo='default',value=m['est']))
    # Africa CDC: one row per (sample, gene, codon) with wildtype/mutation read counts (real schema).
    random.seed(zlib.crc32(('afcdc_'+assay).encode())); afc=[]; sid=0
    def afgene(g): g=g[2:] if g.startswith('Pf') else g; return 'kelch13' if g=='k13' else g
    def afdate(dm):
        if not dm: return ''
        p=str(dm).split('-'); y=p[0]; mo=int(p[1]) if len(p)>1 else random.randint(1,12)
        return f"{mo}/{random.randint(1,28)}/{y[2:] if len(y)>=4 else y}"
    region_n={_na(k):v for k,v in SEN_REGION.items()}
    for u in sorted([u for u in rep['units'] if u.get('sampled')],key=lambda u:-u['n'])[:6]:
        reg=region_n.get(_na(u['name']),'—'); ab=''.join(c for c in u['name'].upper() if c.isalpha())[:3]
        for si in range(1, 2+(1 if u['n']>100 else 0)):
            sid+=1; sample_id=f"SEN-{ab}-{sid:03d}-2024-MSMT-{si}"; date=afdate(u.get('date_min'))
            trav='yes' if random.random()<0.12 else 'no'; tloc=(random.choice(['Mali','Guinea','Mauritania']) if trav=='yes' else '')
            en=''
            for m in markers:
                tot=random.randint(12,60); mut=tot if random.random()<(m['est']/100.0) else 0
                afc.append({'Sample ID':sample_id,'Date of sample collection':date,'Facility name':f"{u['name']} HC",
                    'District':u['name'],'Region':reg,'Country name':ctry,'Study type':'cross_sectional_survey',
                    'Gene name':afgene(m['gene']),'Codon':m['aa'],'Wildtype count':tot-mut,'Mutation count':mut,
                    'Travel_history':trav,'Travel location (if Y)':tloc,'Endemicity':en,'Assay used':assay_name})
    afc_mut = [{'Sample ID': r['Sample ID'], 'Host subject ID': '',
                'Date of sample collection': r['Date of sample collection'], 'Facility name': r['Facility name'],
                'Country': r['Country name'], 'Region/Province (Admin Level 1)': r['Region'],
                'District (Admin Level 2)': r['District'], 'Study type': r['Study type'], 'Gene symbol': r['Gene name'],
                'Gene Alteration': r['Codon'], 'Haplotype': '', 'Travel history [Y/N]': r['Travel_history'],
                'Destination of most recent travel(city)': r['Travel location (if Y)'],
                'Destination of most recent travel(state/province/territory)': '',
                'Destination of most recent travel(country)': '', 'Endemicity': r['Endemicity'],
                'Assay used': r['Assay used']} for r in afc if r['Mutation count'] > 0]
    pha4ge = [{**{f: '' for f in PHA4GE_FIELDS},
               'specimen_collector_sample_ID': r['Sample ID'], 'organism': 'Plasmodium falciparum',
               'host_taxid': '9606', 'host(common_name)': 'Human', 'host(scientific_name)': 'Homo sapiens',
               'geo_loc_name(country)': r['Country name'], 'geo_loc_name(state/province/territory)': r['Region'],
               'geo_loc_name(county/region)': r['District'], 'geo_loc_name(city)': r['Facility name'],
               'sequencing_assay_type': r['Assay used'], 'gene_name': r['Gene name'], 'gene_symbol': r['Gene name'],
               'gene_alteration': r['Codon']} for r in afc if r['Mutation count'] > 0]
    _pack_export(rep, {'who': who, 'afcdc': afc_mut, 'pha4ge': pha4ge, 'dhis2': dhis},
        order=['who', 'dhis2', 'afcdc', 'pha4ge'],
        note='Africa CDC (Mutation/Haplotype) lists one row per sample × observed mutant alteration; AF-CDC Marker-Centric gives per sample × codon wildtype/mutation counts; PHA4GE follows the Malaria Community Standard (human sample); DHIS2 follows the dataValueSet schema. Values are synthetic; WHO Malaria Threats Map layout is representative.')

def project(lon, lat):
    """lon/lat -> SVG x,y using the SAME equirectangular projection as build_maps.py (via MAP bounds)."""
    m = MAP; pad = 10.0
    cosLat = math.cos(math.radians((m['latMin']+m['latMax'])/2))
    scale = (m['W']-2*pad)/((m['lonMax']-m['lonMin'])*cosLat)
    return (round((lon-m['lonMin'])*cosLat*scale+pad, 1), round((m['latMax']-lat)*scale+pad, 1))

def sites_from_samples(samples):
    """Aggregate per-sample records to site-level points (real lat/long) — finer than admin-2.
    Each sample: site, district, lat, lon, calls{k:(wt,mut)}, coi?, poly?, hrp2del?/hrp3del?/hrp_called?."""
    agg = {}
    for s in samples:
        if s.get('lat') is None or s.get('lon') is None: continue
        key = (s.get('site') or s.get('district') or '', round(s['lat'], 4), round(s['lon'], 4))
        a = agg.setdefault(key, {'name': s.get('site') or s.get('district'), 'district': s.get('district'),
                                 'lat': s['lat'], 'lon': s['lon'], 'n': 0, 'mkx': {}, 'mkn': {}})
        a['n'] += 1
        for k, (wt, mut) in (s.get('calls') or {}).items():
            a['mkn'][k] = a['mkn'].get(k, 0) + 1
            if mut: a['mkx'][k] = a['mkx'].get(k, 0) + 1
    sites = []
    for a in agg.values():
        x, y = project(a['lon'], a['lat'])
        sites.append({'name': a['name'], 'district': a['district'], 'lat': a['lat'], 'lon': a['lon'], 'x': x, 'y': y,
                      'n': a['n'], 'mk': {k: round(100*a['mkx'].get(k, 0)/a['mkn'][k], 1) for k in a['mkn'] if a['mkn'][k]},
                      'mkn': a['mkn']})
    return sorted(sites, key=lambda t: -t['n'])

def _afgene(g):
    g = g[2:] if g.startswith('Pf') else g
    return 'kelch13' if g == 'k13' else g

def real_export(rep, samples, assay_name, max_afcdc=500):
    """Export views built ONLY from real measurements + derived fields (no random, no fabrication).
    WHO Threats-Map & DHIS2 = per admin-2 x marker real prevalence. Africa CDC = per sample x codon
    (wildtype/mutation = allele calls from genotypes). Unmeasured columns are left blank.
    samples = [{id, district, region, site, date, calls:{mk_key:(wt,mut)}}]."""
    ctry = rep['meta']['country']
    mkdefs = {m['key']: m for m in rep['markers']}
    reg_by_dept = {}
    for s in samples: reg_by_dept.setdefault(s['district'], s.get('region') or '—')
    who = []; dhis = []
    for u in rep['units']:
        if not u.get('sampled'): continue
        yr = fmt_years(u.get('years') or [str(u.get('date_min') or '')[:4], str(u.get('date_max') or '')[:4]])
        reg = reg_by_dept.get(u['name'], '—')
        for k, n in (u.get('mkn') or {}).items():
            m = mkdefs.get(k)
            if not m or not m.get('assessed') or not n: continue
            x = u['mkx'].get(k, 0); p = round(100*x/n, 1)
            who.append(dict(country=ctry, region=reg, admin2=u['name'], year=yr, gene=m['gene'], mutation=m['aa'],
                            tested=n, present=x, percent=p, who_tracked=('Yes' if m['who'] else 'No — research')))
            dhis.append(dict(dataElement=('MAL_RES_'+m['gene']+'_'+m['aa']).replace(' ', ''), period=yr,
                             orgUnit=u['name'], categoryOptionCombo='default', value=p))
    afc_mc = []   # marker-centric: one row per sample × codon (wildtype/mutation counts)
    afc_mut = []  # mutation/haplotype: one row per sample × mutant alteration (Africa CDC main sheet)
    for s in samples:
        for k, (wt, mut) in (s.get('calls') or {}).items():
            m = mkdefs.get(k)
            if not m or not m.get('assessed'): continue
            afc_mc.append({'Sample ID': s['id'], 'Date of sample collection': s.get('date', ''),
                        'Facility name': s.get('site', ''), 'District': s['district'], 'Region': s.get('region') or '—',
                        'Country name': ctry, 'Study type': '', 'Gene name': _afgene(m['gene']), 'Codon': m['aa'],
                        'Wildtype count': wt, 'Mutation count': mut, 'Travel_history': '', 'Travel location (if Y)': '',
                        'Endemicity': '', 'Assay used': assay_name})
            if mut > 0:   # mutation-centric lists observed alterations only
                afc_mut.append({'Sample ID': s['id'], 'Host subject ID': '',
                        'Date of sample collection': _mmm_yyyy(s.get('date', '')), 'Facility name': s.get('site', ''),
                        'Country': ctry, 'Region/Province (Admin Level 1)': s.get('region') or '—',
                        'District (Admin Level 2)': s['district'], 'Study type': '', 'Gene symbol': _afgene(m['gene']),
                        'Gene Alteration': m['aa'], 'Haplotype': '', 'Travel history [Y/N]': '',
                        'Destination of most recent travel(city)': '',
                        'Destination of most recent travel(state/province/territory)': '',
                        'Destination of most recent travel(country)': '', 'Endemicity': '', 'Assay used': assay_name})
    pha4ge = build_pha4ge(samples, mkdefs, assay_name, rep['meta'].get('platform', ''))
    _pack_export(rep, {'who': who, 'afcdc': afc_mut, 'pha4ge': pha4ge, 'dhis2': dhis},
        order=['who', 'dhis2', 'afcdc', 'pha4ge'],
        note=('All values are real measurements or fields derived from them (prevalence = carriers ÷ typed; '
              '95% Wilson CIs). WHO Threats-Map and DHIS2 rows are per admin-2 × marker. Africa CDC (Mutation/Haplotype) '
              'lists one row per sample × observed mutant alteration; AF-CDC Marker-Centric gives per sample × codon '
              'wildtype/mutation counts (includes wild-type, so it carries the denominator). Full tables are embedded '
              'compressed and rebuilt on download; the table shows a preview. Blank columns (travel, destination, '
              'endemicity, study type, host subject ID, haplotype) are not captured in the sequencing data.'))
    return rep

if __name__ == '__main__':
    # CLI: build the synthetic mock-up data blobs + run the self-checks.
    #   python3 gen_reports.py <version-label>
    set_version(sys.argv[1] if len(sys.argv) > 1 else VERSION)
    reports = build_synthetic_reports()
    _os.makedirs(_os.path.join(ROOT,'build'), exist_ok=True)
    for a,rep in reports.items():
        json.dump(rep,open(_os.path.join(ROOT,'build',f'data_{a.lower()}.json'),'w'),separators=(',',':'))

    # ---- self-checks -----------------------------------------------------------
    assert abs(wilson(10,100)[1]-5.52)<0.05
    for name in ('WGS','MAD4HATTER','NOMADS','COMBINED'):
        r=reports[name]; m=r['meta']
        assert 'incidence' not in json.dumps(r).lower(), f'{name}: incidence leaked'
        # "validated" may appear only inside WHO's defined class name. Walk display strings
        # (the internal 'cls' key is a machine value, never rendered).
        def _walk(o, key=None):
            if isinstance(o, dict):
                for k, v in o.items(): _walk(v, k)
            elif isinstance(o, list):
                for v in o: _walk(v)
            elif isinstance(o, str) and key != 'cls':
                for mo in re.finditer(r'validated', o, re.I):
                    assert o[mo.start():mo.start()+len('Validated marker')] == 'Validated marker', \
                        f'{name}: "validated" outside WHO\'s defined term, in {key!r}: {o[:120]!r}'
        _walk(r)
        assert 'diagnostics' not in r['capabilities']['tabs'] and 'transmission' not in r['capabilities']['tabs']
        assert 'diagnostics' not in r and 'transmission' not in r
        assert m['marker_action_pct']==10.0
        nonwho=[mk for mk in r['markers'] if mk.get('assessed') and not mk['who']]
        print(f"{name:11s} units={m['n_units_sampled']:2d}/{m['n_units_total']} n={m['n_qc']:5d} "
              f"markers={sum(1 for mk in r['markers'] if mk.get('assessed'))} (nonWHO={len(nonwho)}) "
              f"tabs={','.join(r['capabilities']['tabs'])}")
    for name in ('WGS','MAD4HATTER','NOMADS','COMBINED'):
        tr=reports[name].get('trends')
        assert tr, f'{name}: no trends block'
        assert [y for f in tr['frames'] for y in f['years']]==tr['years'], f'{name}: frames do not partition years in order'
        for f in tr['frames']:
            assert sum(tr['year_n'][y] for y in f['years'])>0, f'{name} {f["key"]}: empty frame'
        print(f"{name:11s} trends: {len(tr['years'])} years -> {len(tr['frames'])} frames "
              f"[{', '.join(f['label']+'(n='+str(sum(tr['year_n'][y] for y in f['years']))+')' for f in tr['frames'])}]")
    print("stoplight (WGS):", [(s['cat'],s['status']) for s in reports['WGS']['stoplight']])
    print("ALL CHECKS PASS")
