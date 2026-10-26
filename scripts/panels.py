#!/usr/bin/env python3
"""Identify which amplicon panel produced a set of marker calls, from the data.

A panel is identified by the loci it types, so detection compares the observed
gene:codon set against the registry in `reference/panels.json`.

That registry is derived from the upstream MAD4HATTER repository
(github.com/EPPIcenter/mad4hatter), not hand-written: a panel types a principal
resistance marker when the marker's codon interval lies inside one of that panel's
amplicon inserts, so each entry is the intersection of
`panel_information/<panel>/<panel>_amplicon_info.tsv` with
`panel_information/principal_resistance_marker_info_table.tsv`. It covers the eleven
upstream panels that type at least one resistance marker (R1.1, R1.2, v1, v2, M1.1, M2.1,
R2.1, AMPLseq, spotmalaria_grc1, spotmalaria_grc2, 4cast), plus PFPHAST and NOMADS from
their own locus lists. The commit the registry was built from is recorded in its
`_provenance` block. Panels that type no resistance marker (D1.1, ama1, M1.addon,
spotmalaria_spec) are deliberately absent.

Scoring has to be symmetric. Panels nest: PfPhast's 19 loci are a complete *subset* of
R1.1's 134, so "how much of what we saw does this panel explain" scores 1.0 for both and
cannot tell them apart. Jaccard (intersection over union) also asks how much of the panel
we saw, which separates them.

A real run is usually several panel modules pooled, so no single catalogued panel explains
all of its loci. Where the best single match leaves loci unexplained, the smallest set of
panels that does explain them is reported too, rather than asserting one panel the data
is not.

An unrecognised panel is not an error. The observed loci are registered as a panel of
their own so every coverage gate downstream works, and the report says the panel was not
recognised and names what it saw. Refusing to render a panel nobody has catalogued yet
would make the catalogue a gate on new assays, which is backwards.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_reports as G

# A detection this close to its runner-up is reported as ambiguous rather than guessed.
AMBIGUOUS_MARGIN = 0.15
# Below this the best match is not credible and the panel is treated as unrecognised.
MIN_SCORE = 0.25
# If the best single panel explains less than this share of the observed loci, the run is
# reported as spanning several panels rather than labelled with one.
COMBINED_BELOW = 0.95

GENE_ALIAS = {'dhfr-ts': 'dhfr', 'dhfrts': 'dhfr', 'kelch13': 'k13', 'k-13': 'k13',
              'ap2-mu': 'ap2mu', 'ap2_mu': 'ap2mu'}


def gene_token(raw):
    g = re.sub(r'^pf', '', str(raw or '').strip().lower())
    return GENE_ALIAS.get(g, g)


def locus(gene, codon):
    return f'{gene_token(gene)}:{int(codon)}'


def registry(path=None):
    p = path or os.path.join(G.REF_DIR, 'panels.json')
    if not os.path.exists(p):
        return {}
    with open(p) as fh:
        return (json.load(fh) or {}).get('panels') or {}


def detect(observed, reg=None):
    """observed: iterable of 'gene:codon'. -> detection dict, never raises."""
    obs = {str(o) for o in observed if o}
    reg = reg if reg is not None else registry()
    ranked = []
    for name, spec in (reg or {}).items():
        panel = set(spec.get('loci') or [])
        if not panel or not obs:
            continue
        inter = obs & panel
        union = obs | panel
        ranked.append({
            'panel': name,
            'label': spec.get('label') or name,
            'assay_name': spec.get('assay_name'),
            'jaccard': round(len(inter) / len(union), 4),
            'explains_observed': round(len(inter) / len(obs), 4),
            'panel_covered': round(len(inter) / len(panel), 4),
            'n_shared': len(inter),
            'n_panel': len(panel),
        })
    ranked.sort(key=lambda r: -r['jaccard'])

    out = {'n_observed': len(obs), 'ranked': ranked[:6], 'observed_genes':
           sorted({o.split(':')[0] for o in obs})}
    if not ranked or ranked[0]['jaccard'] < MIN_SCORE:
        out.update(panel=None, recognised=False, ambiguous=False,
                   reason=('no panel in the registry matches these loci'
                           if ranked else 'the panel registry is empty'))
        return out

    best = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    margin = best['jaccard'] - (runner['jaccard'] if runner else 0.0)
    out.update(panel=best['panel'], label=best['label'], assay_name=best['assay_name'],
               recognised=True, score=best['jaccard'], margin=round(margin, 4),
               ambiguous=bool(runner and margin < AMBIGUOUS_MARGIN),
               runner_up=runner['panel'] if runner else None,
               missing_from_panel=sorted(set(best and []) or []),
               n_shared=best['n_shared'], n_panel=best['n_panel'])
    # loci the data has that the matched panel does not list: either the panel reference is
    # stale or this is a variant of it, and both are worth naming
    panel_loci = set((reg.get(best['panel']) or {}).get('loci') or [])
    out['unexpected_loci'] = sorted(obs - panel_loci)[:25]
    out['n_unexpected'] = len(obs - panel_loci)
    out['n_panel_loci_absent'] = len(panel_loci - obs)

    # A MAD4HATTER run is usually several panel modules pooled, so no single catalogued
    # panel explains all of its loci. Reporting only the best single match would assert a
    # panel the data is not. Name the smallest set of panels that does explain it.
    if best['explains_observed'] < COMBINED_BELOW:
        out['combination'] = _cover(obs, reg)
    return out


def _cover(obs, reg):
    """Greedy smallest-set-of-panels cover of the observed loci."""
    remaining = set(obs)
    chosen = []
    pool = {n: set(s.get('loci') or []) for n, s in (reg or {}).items()}
    while remaining:
        name, gain = None, 0
        for n, loci in pool.items():
            g = len(remaining & loci)
            if g > gain or (g == gain and g and name and len(loci) < len(pool[name])):
                name, gain = n, g
        if not name or not gain:
            break
        chosen.append({'panel': name, 'adds': gain})
        remaining -= pool[name]
        pool.pop(name)
    return {'panels': chosen, 'n_explained': len(obs) - len(remaining),
            'n_unexplained': len(remaining),
            'unexplained_loci': sorted(remaining)[:25]}


def register(detection, fallback_key='AMPLICON'):
    """Make the detected panel usable: give it an ASSAYS entry keyed by observed genes.

    The report decides whether an assay types a marker by looking its gene up in
    ASSAYS[assay]['genes']. Registering the observed genes is what lets an unrecognised
    panel render at all, and it is also strictly more accurate than the catalogued gene
    list for a recognised one, because it is what this run actually typed.
    """
    key = detection.get('panel') or fallback_key
    genes = set(detection.get('observed_genes') or [])
    spec = G.ASSAYS.get(key)
    if spec is None:
        G.ASSAYS[key] = {'genes': genes}
    else:
        spec['genes'] = set(spec.get('genes') or set()) | genes
    G.ASSAY_NAME.setdefault(key, detection.get('assay_name') or 'Amplicon sequencing')
    return key


def lines(detection, declared=None):
    """Human-readable detection result, including the disagreement with a declared panel."""
    d = detection
    out = []
    if not d.get('n_observed'):
        return ['no marker loci observed, so the panel could not be detected']
    if d.get('recognised'):
        out.append(f"panel detected: {d['panel']} ({d['label']}) - matched "
                   f"{d['n_shared']}/{d['n_panel']} catalogued loci from "
                   f"{d['n_observed']} observed, score {d['score']:.2f}")
        if d.get('ambiguous'):
            out.append(f"AMBIGUOUS: {d['runner_up']} scores within {AMBIGUOUS_MARGIN} "
                       f"(margin {d['margin']:.2f}); the panels overlap too much to tell "
                       f"them apart from the loci alone")
        c = d.get('combination')
        if c:
            names = ' + '.join(f"{x['panel']} ({x['adds']})" for x in c['panels'])
            out.append(f"this run spans more than one catalogued panel: "
                       f"{names} explains {c['n_explained']}/{d['n_observed']} loci"
                       + (f", {c['n_unexplained']} unexplained "
                          f"({', '.join(c['unexplained_loci'][:8])}"
                          f"{' ...' if c['n_unexplained'] > 8 else ''})"
                          if c['n_unexplained'] else ''))
        if d.get('n_unexpected'):
            ex = ', '.join(d.get('unexpected_loci') or [])
            out.append(f"{d['n_unexpected']} observed locus/loci are not in the "
                       f"{d['panel']} reference: {ex}"
                       + (' ...' if d['n_unexpected'] > 25 else ''))
    else:
        out.append(f"PANEL NOT RECOGNISED: {d['n_observed']} loci across genes "
                   f"{', '.join(d['observed_genes'])} - {d.get('reason','')}. "
                   f"Rendering anyway, from the observed loci.")
        for r in d.get('ranked') or []:
            out.append(f"  closest registry entry: {r['panel']} "
                       f"(score {r['jaccard']:.2f}, shares {r['n_shared']} loci)")
    if declared and d.get('recognised') and declared not in ('AMPLICON', 'AUTO', '') \
            and declared != d['panel']:
        out.append(f"MISMATCH: the run declared --assay {declared} but the loci look like "
                   f"{d['panel']}; the declared value was kept")
    return out


def demo():
    reg = registry()
    assert reg, 'reference/panels.json should ship a registry'
    assert {'R1.1', 'R1.2', 'PFPHAST', 'NOMADS'} <= set(reg), sorted(reg)

    pf = set(reg['PFPHAST']['loci'])
    r11 = set(reg['R1.1']['loci'])
    # PfPhast is *nearly* a subset of R1.1. The two exceptions are real, not a derivation
    # bug: crt:97 sits 6 bp past the end of an R1.1 amplicon insert and dhps:613 sits 32 bp
    # past another, so R1.1 as catalogued upstream cannot type them. This assertion is a
    # canary - if upstream changes those amplicons, it should fail and be re-checked.
    assert pf - r11 == {'crt:97', 'dhps:613'}, sorted(pf - r11)

    # the nesting case: containment cannot separate nested panels, Jaccard must
    shared = pf & r11
    # R1.1 explains every one of these loci too, so containment alone would tie them;
    # PFPHAST must still win because far less of R1.1 was seen.
    assert len(shared & r11) == len(shared), 'shared loci are by definition inside R1.1'
    d = detect(shared, reg)
    assert d['panel'] == 'PFPHAST', d
    assert d['ranked'][0]['explains_observed'] == 1.0

    # a full panel is identified as itself, not as one of its subsets
    d = detect(r11, reg)
    assert d['panel'] == 'R1.1', d
    assert not d.get('combination'), 'a single panel needs no combination'

    # a pooled run is reported as a combination rather than labelled with one panel
    d = detect(r11 | set(reg['NOMADS']['loci']), reg)
    assert d.get('combination'), d
    assert d['combination']['n_unexplained'] == 0, d['combination']

    # an unknown panel renders rather than failing, and says so
    d = detect({'xyz:1', 'xyz:2', 'abc:3'}, reg)
    assert d['recognised'] is False and d['panel'] is None, d
    assert any('NOT RECOGNISED' in l for l in lines(d))
    key = register(d)
    assert key == 'AMPLICON' and 'xyz' in G.ASSAYS['AMPLICON']['genes']

    # a declared panel that disagrees with the loci is reported
    d = detect(pf, reg)
    assert any('MISMATCH' in l for l in lines(d, declared='R1.1'))

    # extra loci beyond the matched panel are named
    d = detect(pf | {'newgene:999'}, reg)
    assert d['panel'] == 'PFPHAST' and d['n_unexpected'] == 1, d

    print('panels demo OK')
    for l in lines(detect(pf, reg)):
        print('  PfPhast loci ->', l)
    for l in lines(detect(r11, reg)):
        print('  R1.1 loci ->', l)


if __name__ == '__main__':
    demo()
