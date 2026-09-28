#!/usr/bin/env python3
"""Generate DATA JSON for the v0.5 single-country (Senegal) malaria molecular-surveillance
mock-ups: WGS, MAD4HATTER, NOMADS (ONT), COMBINED.

v0.5 redesign (colleague feedback):
  - Prevalence only (NO incidence).
  - NO drug-resistance phenotype prediction. Show gene + AA change + associated drug +
    WHO-tracked status + the WHO criterion only. Never the word "validated" -> "WHO-tracked".
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
import json, math, random, sys, unicodedata, gzip, base64

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
VERSION = sys.argv[1] if len(sys.argv) > 1 else 'v0.8'   # single source of truth; build_reports.sh passes it

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
MAP = json.load(open(_os.path.join(ROOT, 'reference', 'sen_admin2_map.json')))
PHA4GE_FIELDS = json.load(open(_os.path.join(ROOT, 'schemas', 'pha4ge_fields.json')))
DEPTS = MAP['depts']
latMin = min(d['lat'] for d in DEPTS); latMax = max(d['lat'] for d in DEPTS)
def southness(lat): return (latMax - lat)/(latMax - latMin)

POP_BASE = {'Dakar':1250000,'Pikine':1200000,'Guédiawaye':330000,'Rufisque':560000,'Thiès':820000,'Mbour':750000}
def base_pop(name,s): return POP_BASE.get(name, int(120000+380000*random.random()+200000*(1-s)))
EPI = {d['name']:{'s':southness(d['lat']),'pop':base_pop(d['name'],southness(d['lat']))} for d in DEPTS}

# ---- marker catalogue (key, gene, gene_id, aa, drug, who_tracked, gene_token, mean%, criterion) ----
MARKERS = [
 ('k13_C580Y','Pfk13','PF3D7_1343700','C580Y','Artemisinin (ACT)',True,'k13',0.4,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_R561H','Pfk13','PF3D7_1343700','R561H','Artemisinin (ACT)',True,'k13',0.3,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_A675V','Pfk13','PF3D7_1343700','A675V','Artemisinin (ACT)',True,'k13',0.5,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_R622I','Pfk13','PF3D7_1343700','R622I','Artemisinin (ACT)',True,'k13',0.6,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_F446I','Pfk13','PF3D7_1343700','F446I','Artemisinin (ACT)',True,'k13',0.3,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_N458Y','Pfk13','PF3D7_1343700','N458Y','Artemisinin (ACT)',True,'k13',0.2,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_C469Y','Pfk13','PF3D7_1343700','C469Y','Artemisinin (ACT)',True,'k13',0.2,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_M476I','Pfk13','PF3D7_1343700','M476I','Artemisinin (ACT)',True,'k13',0.2,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_Y493H','Pfk13','PF3D7_1343700','Y493H','Artemisinin (ACT)',True,'k13',0.2,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_R539T','Pfk13','PF3D7_1343700','R539T','Artemisinin (ACT)',True,'k13',0.3,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_I543T','Pfk13','PF3D7_1343700','I543T','Artemisinin (ACT)',True,'k13',0.2,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_P553L','Pfk13','PF3D7_1343700','P553L','Artemisinin (ACT)',True,'k13',0.3,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('k13_P574L','Pfk13','PF3D7_1343700','P574L','Artemisinin (ACT)',True,'k13',0.3,'WHO-tracked artemisinin partial-resistance marker (propeller)'),
 ('crt_K76T','Pfcrt','PF3D7_0709000','K76T','Chloroquine / amodiaquine',True,'crt',11.0,'WHO-tracked chloroquine-resistance transporter marker'),
 ('mdr1_N86Y','Pfmdr1','PF3D7_0523000','N86Y','Amodiaquine / lumefantrine',True,'mdr1',8.0,'WHO-tracked multidrug-resistance transporter marker'),
 ('dhfr_N51I','Pfdhfr','PF3D7_0417200','N51I','Pyrimethamine / SP',True,'dhfr',58.0,'WHO-tracked antifolate (pyrimethamine) marker'),
 ('dhfr_C59R','Pfdhfr','PF3D7_0417200','C59R','Pyrimethamine / SP',True,'dhfr',55.0,'WHO-tracked antifolate (pyrimethamine) marker'),
 ('dhfr_S108N','Pfdhfr','PF3D7_0417200','S108N','Pyrimethamine / SP',True,'dhfr',66.0,'WHO-tracked antifolate (pyrimethamine) marker'),
 ('dhfr_I164L','Pfdhfr','PF3D7_0417200','I164L','Pyrimethamine / SP',True,'dhfr',0.5,'WHO-tracked antifolate (pyrimethamine) marker'),
 ('dhps_A437G','Pfdhps','PF3D7_0810800','A437G','Sulfadoxine / SP',True,'dhps',42.0,'WHO-tracked antifolate (sulfadoxine) marker'),
 ('dhps_K540E','Pfdhps','PF3D7_0810800','K540E','Sulfadoxine / SP',True,'dhps',4.0,'WHO-tracked antifolate (sulfadoxine) marker'),
 ('dhps_A581G','Pfdhps','PF3D7_0810800','A581G','Sulfadoxine / SP',True,'dhps',0.8,'WHO-tracked antifolate (sulfadoxine) marker'),
 ('dhps_A613S','Pfdhps','PF3D7_0810800','A613S','Sulfadoxine / SP',True,'dhps',0.6,'WHO-tracked antifolate (sulfadoxine) marker'),
 ('cytb_Y268S','Pfcytb','mal_mito_3','Y268S','Atovaquone',True,'cytb',0.3,'WHO-tracked atovaquone (cytochrome b) marker'),
 ('coronin_G50E','Pfcoronin','PF3D7_1251200','G50E','Artemisinin (research)',False,'coronin',1.2,'Research candidate; not WHO-tracked'),
 ('ubp1_D1525E','Pfubp1','PF3D7_0104300','D1525E','ACT (research)',False,'ubp1',0.9,'Research association; not WHO-tracked'),
 ('ap2mu_S160N','Pfap2-mu','PF3D7_1218300','S160N','ACT (research)',False,'ap2mu',1.5,'Research association; not WHO-tracked'),
]
MK = {m[0]:dict(gene=m[1],gene_id=m[2],aa=m[3],drug=m[4],who=m[5],tok=m[6],mean=m[7],crit=m[8]) for m in MARKERS}

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
#     non-falciparum species (Pv/Pm/Poc/Pk ldh). Does NOT type coronin/ubp1/ap2mu
#     (absent from the resmarker table). CNV/hrp are coverage-based => panel/pool-dependent.
#   - NOMADS (nomads16, not yet a live workspace): SNP core + hrp2/3 deletions + msp2 COI.
ASSAYS = {
 'WGS': dict(full='Whole-genome sequencing (Illumina)', platform='Illumina NovaSeq (deep WGS)',
   turnaround='3–6 weeks', color='#4a3aa7', n_range=(15,60), n_depts=11, qc=0.82,
   genes={'k13','crt','mdr1','dhfr','dhps','cytb','coronin','ubp1','ap2mu'},
   cnv=True, hrp=True, species=False,
   div=dict(coi=True,poly=True,mono=True,rh=True,cotx=True,coi_method='24-SNP barcode heterozygosity'),
   note='Whole-genome short-read sequencing; this report shows the prevalence of WHO-tracked and research drug-resistance markers from per-sample genotype calls.'),
 'MAD4HATTER': dict(full='MAD4HATTER v4 amplicon panel (Illumina)', platform='Illumina (v4, pools 1A+1B+2)',
   turnaround='1–2 weeks', color='#1baf7a', n_range=(30,260), n_depts=38, qc=0.87,
   genes={'k13','crt','mdr1','dhfr','dhps','cytb'},
   cnv=True, hrp=True, species=True,
   div=dict(coi=True,poly=True,mono=True,rh=True,cotx=True,coi_method='naive COI (max distinct microhaplotype alleles per locus)'),
   note='v4 amplicon panel (resistance pools); this report shows the prevalence of WHO-tracked drug-resistance markers from resistance-marker (resmarker) calls. Does not type the research markers coronin/ubp1/ap2mu.'),
 'NOMADS': dict(full='NOMADS targeted panel (Oxford Nanopore)', platform='ONT MinION (nomads16)',
   turnaround='1–3 days', color='#2a78d6', n_range=(40,160), n_depts=19, qc=0.84,
   genes={'k13','crt','mdr1','dhfr','dhps'},
   cnv=False, hrp=True, species=False,
   div=dict(coi=True,poly=True,mono=True,rh=False,cotx=False,coi_method='msp2 allele counting (coarse)'),
   note='Targeted ONT amplicon panel; this report shows the prevalence of the core WHO-tracked drug-resistance markers. No atovaquone or research markers.'),
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
MARKER_PCT = 10.0
HRP_PCT    = 5.0
MIN_SAMPLES = 5
MONTHS = [f'2024-{m:02d}' for m in range(1,13)]

def assemble_report(name, spec, units):
    """Assemble the template DATA blob from per-admin-2 unit records.
    Shared by the synthetic generator (build_assay) and real-data loaders
    (load_wgs.py, ...). Each unit dict: name, sampled(bool), n(QC-pass denom),
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
                  category=('WHO-tracked' if m['who'] else 'Research (not WHO-tracked)'),crit=m['crit'])
        if m['tok'] not in spec['genes'] or natn.get(k,0)==0: base['assessed']=False; natmarkers.append(base); continue
        est,lo,hi=wilson(natx[k],natn[k])
        base.update(assessed=True,x=natx[k],n=natn[k],est=est,lo=lo,hi=hi,action=(m['who'] and est>=MARKER_PCT))
        natmarkers.append(base)
    res_hits=[m for m in natmarkers if m.get('assessed') and m['who'] and m['est']>=MARKER_PCT]
    res_watch=[m for m in natmarkers if m.get('assessed') and m['who'] and 5.0<=m['est']<MARKER_PCT]
    stoplight=[
      dict(cat='Resistance Markers',status=('red' if res_hits else 'amber' if res_watch else 'green'),
           findings=([f"{m['gene']} {m['aa']} = {m['est']}% (≥{int(MARKER_PCT)}% — WHO criteria indicates TES)" for m in res_hits]
                     +[f"{m['gene']} {m['aa']} = {m['est']}% (watch, 5–10%)" for m in res_watch]) or ['No WHO-tracked marker ≥ threshold']),
    ]
    tabs=['summary','resistance','export','methods']
    for u in sampled:
        if not u.get('years'):
            u['years']=sorted({str(d)[:4] for d in (u.get('date_min'),u.get('date_max')) if d and str(d)[:4].isdigit()})
    allyears=set()
    for u in sampled: allyears|=set(u.get('years') or [])
    period=fmt_years(allyears) or 'n/a'
    meta=dict(assay=name,assay_full=spec['full'],platform=spec['platform'],
              color=spec['color'],note=spec['note'],country='Senegal',admin='Admin-2 (department)',
              admin_available=True,dates_available=bool(allyears),period=period,years=sorted(allyears),
              links=PIPELINE_LINKS.get(name,[]),
              generated='2026-09-23',version=VERSION,real=False,data_source='Synthetic design mock-up (illustrative values)',
              marker_action_pct=MARKER_PCT,min_samples=MIN_SAMPLES,
              n_units_sampled=len(chosen_names),n_units_total=len(DEPTS),n_collected=tot_col,n_qc=tot_qc,
              qc_rate=round(100*tot_qc/tot_col,1) if tot_col else 0)
    caps=dict(tabs=tabs,genes=sorted(spec['genes']),covered_markers=covered)
    # v0.8: COI (transmission) and HRP2/3 (diagnostics) sections removed from the report;
    # per-unit hrp/div inputs are accepted from loaders but not emitted.
    drop=('hrp2','hrp3','hrp2x','hrp3x','hrpn','div','coi','poly','mono')
    units=[{k:v for k,v in u.items() if k not in drop} for u in units]
    return dict(meta=meta,capabilities=caps,map=MAP,units=units,markers=natmarkers,
                stoplight=stoplight,marker_defs={k:MK[k] for k in MK})

def build_assay(name, spec):
    random.seed(hash(name)%(2**31))
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
            rec['mk']={}; rec['mkx']={}; rec['mkn']={}
            for k in covered:
                x=cnt(dept_prev(k,s),nqc); rec['mk'][k]=round(100*x/nqc,1) if nqc else 0.0
                rec['mkx'][k]=x; rec['mkn'][k]=nqc
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

reports={name:build_assay(name,spec) for name,spec in ASSAYS.items()}

def build_combined():
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
        units.append(rec)
    genes=set().union(*[ASSAYS[a]['genes'] for a in ASSAYS]); covered=[k for k in MK if MK[k]['tok'] in genes]
    natmarkers=[]
    for k,m in MK.items():
        contrib=[a for a in ASSAYS if m['tok'] in ASSAYS[a]['genes']]
        base=dict(key=k,gene=m['gene'],gene_id=m['gene_id'],aa=m['aa'],drug=m['drug'],who=m['who'],
                  category=('WHO-tracked' if m['who'] else 'Research (not WHO-tracked)'),crit=m['crit'])
        if not contrib: base['assessed']=False; natmarkers.append(base); continue
        x=sum(next((mm['x'] for mm in reports[a]['markers'] if mm['key']==k and mm.get('assessed')),0) for a in contrib)
        n=sum(next((mm['n'] for mm in reports[a]['markers'] if mm['key']==k and mm.get('assessed')),0) for a in contrib)
        est,lo,hi=wilson(x,n); base.update(assessed=True,x=x,n=n,est=est,lo=lo,hi=hi,action=(m['who'] and est>=MARKER_PCT),assays=contrib)
        natmarkers.append(base)
    res_hits=[m for m in natmarkers if m.get('assessed') and m['who'] and m['est']>=MARKER_PCT]
    res_watch=[m for m in natmarkers if m.get('assessed') and m['who'] and 5.0<=m['est']<MARKER_PCT]
    stoplight=[dict(cat='Resistance Markers',status=('red' if res_hits else 'amber' if res_watch else 'green'),
                    findings=([f"{m['gene']} {m['aa']} = {m['est']}% (≥{int(MARKER_PCT)}% — WHO criteria indicates TES)" for m in res_hits]
                              +[f"{m['gene']} {m['aa']} = {m['est']}% (watch)" for m in res_watch]) or ['No WHO-tracked marker ≥ threshold'])]
    tot_qc=sum(reports[a]['meta']['n_qc'] for a in ASSAYS); tot_col=sum(reports[a]['meta']['n_collected'] for a in ASSAYS)
    meta=dict(assay='COMBINED',assay_full='Combined multi-assay (WGS + MAD4HATTER + NOMADS)',
              platform='Illumina WGS + Illumina amplicon + ONT',color='#006dae',
              note='Harmonised view; markers pooled across assays that type each locus.',country='Senegal',
              admin='Admin-2 (department)',admin_available=True,dates_available=True,
              period=(fmt_years(set().union(*([set(u.get('years',[])) for u in units if u.get('sampled')] or [set()]))) or 'n/a'),
              years=sorted(set().union(*([set(u.get('years',[])) for u in units if u.get('sampled')] or [set()]))),
              links=PIPELINE_LINKS.get('COMBINED',[]),
              generated='2026-09-23',version=VERSION,real=False,data_source='Synthetic design mock-up (illustrative values)',
              marker_action_pct=MARKER_PCT,min_samples=MIN_SAMPLES,
              n_units_sampled=sum(1 for u in units if u['sampled']),n_units_total=len(DEPTS),
              n_collected=tot_col,n_qc=tot_qc,qc_rate=round(100*tot_qc/tot_col,1),by_assay={a:reports[a]['meta']['n_qc'] for a in ASSAYS})
    caps=dict(tabs=['summary','resistance','export','methods'],
              genes=sorted(genes),covered_markers=covered,
              assays=list(ASSAYS.keys()),assay_colors={a:ASSAYS[a]['color'] for a in ASSAYS})
    return dict(meta=meta,capabilities=caps,map=MAP,units=units,markers=natmarkers,
                stoplight=stoplight,marker_defs={k:MK[k] for k in MK})
reports['COMBINED']=build_combined()

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
             'WHO Malaria Threats Map layout: one row per admin-2 × marker (samples tested, mutant present, percent, WHO-tracked status). Representative of the schema.'),
 'afcdc':    ('Africa CDC', 'afcdc_mutation_haplotype.csv', 'Africa CDC — Mutation / Haplotype data sheet',
             'Africa CDC Mutation/Haplotype data sheet: one row per sample × observed mutant alteration (Gene symbol · Gene Alteration · Haplotype). Columns not captured in the sequencing data (host subject ID, haplotype, travel history, destinations, endemicity, study type) are left blank.'),
 'afcdc_mc': ('AF-CDC Marker-Centric', 'afcdc_marker_centric.csv', 'AF-CDC Marker-Centric — per sample × codon (wildtype / mutation counts)',
             'AF-CDC Marker-Centric: one row per sample × codon with wildtype/mutation allele calls — includes wild-type calls, so this view carries the denominator (how many samples were typed at each codon).'),
 'pha4ge':   ('PHA4GE', 'pha4ge_malaria_standard.csv', 'PHA4GE Malaria Community Standard (human sample) — one row per sample × observed alteration',
             'PHA4GE Malaria Community Standard (human sample): the 210-field per-specimen schema, one row per sample × observed alteration. Only fields the genomic data supports are populated (sample ID, geography, collection date, organism/host, assay/instrument, MOI, gene/alteration); all other fields (accessions, host demographics, sequencing kit, etc.) are left blank.'),
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
    random.seed(hash('afcdc_'+assay)%(2**31)); afc=[]; sid=0
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
    _pack_export(rep, {'who': who, 'afcdc': afc_mut, 'afcdc_mc': afc, 'pha4ge': pha4ge, 'dhis2': dhis},
        order=['who', 'afcdc', 'afcdc_mc', 'pha4ge', 'dhis2'],
        note='Africa CDC (Mutation/Haplotype) lists one row per sample × observed mutant alteration; AF-CDC Marker-Centric gives per sample × codon wildtype/mutation counts; PHA4GE follows the Malaria Community Standard (human sample); DHIS2 follows the dataValueSet schema. Values are synthetic; WHO Malaria Threats Map layout is representative.')
for a in reports: add_export(reports[a])

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
    _pack_export(rep, {'who': who, 'afcdc': afc_mut, 'afcdc_mc': afc_mc, 'pha4ge': pha4ge, 'dhis2': dhis},
        order=['who', 'afcdc', 'afcdc_mc', 'pha4ge', 'dhis2'],
        note=('All values are real measurements or fields derived from them (prevalence = carriers ÷ typed; '
              '95% Wilson CIs). WHO Threats-Map and DHIS2 rows are per admin-2 × marker. Africa CDC (Mutation/Haplotype) '
              'lists one row per sample × observed mutant alteration; AF-CDC Marker-Centric gives per sample × codon '
              'wildtype/mutation counts (includes wild-type, so it carries the denominator). Full tables are embedded '
              'compressed and rebuilt on download; the table shows a preview. Blank columns (travel, destination, '
              'endemicity, study type, host subject ID, haplotype) are not captured in the sequencing data.'))
    return rep

_os.makedirs(_os.path.join(ROOT,'build'), exist_ok=True)
for a,rep in reports.items():
    json.dump(rep,open(_os.path.join(ROOT,'build',f'data_{a.lower()}.json'),'w'),separators=(',',':'))

# ---- self-checks -----------------------------------------------------------
assert abs(wilson(10,100)[1]-5.52)<0.05
for name in ('WGS','MAD4HATTER','NOMADS','COMBINED'):
    r=reports[name]; m=r['meta']
    assert 'incidence' not in json.dumps(r).lower(), f'{name}: incidence leaked'
    assert 'validated' not in json.dumps(r['markers']).lower(), f'{name}: "validated" in markers'
    assert 'diagnostics' not in r['capabilities']['tabs'] and 'transmission' not in r['capabilities']['tabs']
    assert 'diagnostics' not in r and 'transmission' not in r
    assert m['marker_action_pct']==10.0
    nonwho=[mk for mk in r['markers'] if mk.get('assessed') and not mk['who']]
    print(f"{name:11s} units={m['n_units_sampled']:2d}/{m['n_units_total']} n={m['n_qc']:5d} "
          f"markers={sum(1 for mk in r['markers'] if mk.get('assessed'))} (nonWHO={len(nonwho)}) "
          f"tabs={','.join(r['capabilities']['tabs'])}")
print("stoplight (WGS):", [(s['cat'],s['status']) for s in reports['WGS']['stoplight']])
print("ALL CHECKS PASS")
