#!/usr/bin/env python3
"""Terra sample-table (wide) -> marker-calls table (long), for load_nomads.py.

Terra workspaces carry one COLUMN per marker; load_nomads.py consumes one ROW per
sample x marker. Rather than teach the loader a second shape, this reshapes the table and
everything downstream (selection, site join, prevalence, exports) stays on one code path.

Two column conventions are recognised, both seen in gates-malaria workspaces:

  aa_change_<gene>_<REF><POS><ALT>     Nomadic_development
      value is a verdict: wt | mutant | mixed | unphased | absent | failed

  resmarker_<gene>_<codon>             Mad4Hatter_development
      value is the OBSERVED amino acid at that codon (e.g. "K"), or two separated by
      "/" for a mixed call (e.g. "F/Y"). The verdict is derived by comparing against
      the WHO marker catalogue's reference and alternate residue for that codon.

The second convention is the awkward one: an observed residue that is neither the
reference nor WHO's alternate (say N where WHO tracks K76T) means WHO's mutation is
absent, so it counts as reference FOR THAT MARKER even though the parasite does carry a
substitution. --audit reports how often that happens so the number is never invisible.

Usage:
  terra_samples.py --in sample.tsv --out calls.tsv [--audit]
"""
import argparse, csv, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_reports as G

# Verdict words in the aa_change_* convention -> the call words load_nomads understands.
# "absent" and "unphased" deliberately become no-calls rather than reference:
#   absent    the locus was not observed in that sample, so it is not in the denominator
#   unphased  the residue needs two substitutions in one codon that the reads cannot phase,
#             so the verdict is genuinely unknown
# Counting either as wild type would inflate every denominator and depress prevalence.
VERDICT = {
    'wt': 'ref', 'wildtype': 'ref', 'wild_type': 'ref',
    'mutant': 'alt', 'mut': 'alt',
    'mixed': 'het', 'het': 'het',
    'absent': 'missing', 'unphased': 'missing', 'failed': 'missing', 'fail': 'missing',
}

# Workspace gene spellings -> catalogue tokens (gen_reports MARKERS[6]).
GENE_ALIAS = {'dhfr-ts': 'dhfr', 'dhfrts': 'dhfr', 'pfdhfr': 'dhfr', 'pfdhps': 'dhps',
              'pfcrt': 'crt', 'pfmdr1': 'mdr1', 'pfmdr2': 'mdr2', 'pfk13': 'k13',
              'kelch13': 'k13', 'k-13': 'k13'}

AA_COL = re.compile(r'^aa_change_(.+?)_([A-Z])(\d+)([A-Z])$')
RES_COL = re.compile(r'^resmarker_(.+?)_(\d+)$')


def gene_token(raw):
    g = raw.strip().lower()
    return GENE_ALIAS.get(g, g)


def catalogue_index():
    """(gene token, codon) -> list of (ref, alt) WHO tracks at that codon."""
    idx = {}
    for mid, meta in G.MK.items():
        m = re.match(r'^([A-Z])(\d+)([A-Z])$', meta['aa'])
        if not m:
            continue                      # multi-codon ids, handled as components elsewhere
        ref, pos, alt = m.group(1), int(m.group(2)), m.group(3)
        idx.setdefault((meta['tok'], pos), []).append((ref, alt))
    return idx


def residue_verdict(observed, ref, alt):
    """Observed residue(s) at a codon -> call word for the marker ref->alt."""
    parts = [p.strip().upper() for p in str(observed).replace(',', '/').split('/') if p.strip()]
    if not parts:
        return 'missing', 'empty'
    if any(p in ('X', '.', 'NA', 'N/A') for p in parts):
        return 'missing', 'nocall'
    if len(parts) > 1:
        # a mixed call carries the mutation if WHO's alternate is one of the residues
        return ('het', 'mixed_alt') if alt in parts else ('ref', 'mixed_other')
    p = parts[0]
    if p == alt:
        return 'alt', 'alt'
    if p == ref:
        return 'ref', 'ref'
    return 'ref', 'other_substitution'


def reshape(rows, fieldnames, audit=None):
    """Wide Terra rows -> long marker-call dicts."""
    idx = catalogue_index()
    tally = audit if audit is not None else {}

    def bump(k):
        tally[k] = tally.get(k, 0) + 1

    # the entity id column is "entity:sample_id" on a Terra export, "name" on an API dump
    id_col = next((c for c in fieldnames
                   if c.lower() in ('entity:sample_id', 'sample_id', 'name', 'sample')), None)
    if not id_col:
        raise SystemExit(f'no sample id column found in: {", ".join(fieldnames[:8])}...')

    aa_cols = [(c,) + AA_COL.match(c).groups() for c in fieldnames if AA_COL.match(c)]
    res_cols = [(c,) + RES_COL.match(c).groups() for c in fieldnames if RES_COL.match(c)]
    if not aa_cols and not res_cols:
        raise SystemExit('no aa_change_* or resmarker_* columns found')

    # Columns that are not markers ride along, so a site/date column added to the Terra
    # table later reaches the loader with no change here.
    marker_cols = {c[0] for c in aa_cols} | {c[0] for c in res_cols}
    passthrough = [c for c in fieldnames if c not in marker_cols and c != id_col]

    out = []
    for row in rows:
        sid = (row.get(id_col) or '').strip()
        if not sid:
            continue
        extra = {c: row[c] for c in passthrough if (row.get(c) or '').strip()}

        for col, graw, ref, pos, alt in aa_cols:
            v = (row.get(col) or '').strip().lower()
            if not v:
                bump('aa_change: empty'); continue
            call = VERDICT.get(v)
            if call is None:
                bump(f'aa_change: unknown verdict {v!r}'); continue
            bump(f'aa_change: {v} -> {call}')
            if call == 'missing':
                continue
            out.append(dict(extra, sample_id=sid, gene=gene_token(graw),
                            aa_change=f'{ref}{pos}{alt}', call=call))

        for col, graw, pos in res_cols:
            v = (row.get(col) or '').strip()
            tok = gene_token(graw)
            tracked = idx.get((tok, int(pos)))
            if not tracked:
                bump(f'resmarker: codon not in catalogue ({tok} {pos})'); continue
            if not v:
                bump('resmarker: empty'); continue
            for ref, alt in tracked:
                call, why = residue_verdict(v, ref, alt)
                bump(f'resmarker: {why} -> {call}')
                if call == 'missing':
                    continue
                out.append(dict(extra, sample_id=sid, gene=tok,
                                aa_change=f'{ref}{pos}{alt}', call=call))
    return out, passthrough


def main(argv=None):
    ap = argparse.ArgumentParser(description='Terra wide sample table -> marker-calls table.')
    ap.add_argument('--in', dest='src', required=True, help='Terra sample table (TSV or CSV)')
    ap.add_argument('--out', required=True, help='marker-calls table to write (TSV)')
    ap.add_argument('--audit', action='store_true', help='print how every value was mapped')
    a = ap.parse_args(argv)

    delim = '\t' if a.src.lower().endswith(('.tsv', '.txt')) else ','
    with open(a.src, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        rows, fields = list(reader), list(reader.fieldnames or [])

    tally = {}
    calls, passthrough = reshape(rows, fields, tally)
    if not calls:
        raise SystemExit('no marker calls produced; run with --audit to see why')

    cols = ['sample_id', 'gene', 'aa_change', 'call'] + passthrough
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    with open(a.out, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter='\t', extrasaction='ignore')
        w.writeheader()
        for c in calls:
            w.writerow(c)

    n_s = len({c['sample_id'] for c in calls})
    n_m = len({(c['gene'], c['aa_change']) for c in calls})
    sys.stderr.write(f'[terra_samples] {len(rows)} rows -> {len(calls)} calls, '
                     f'{n_s} samples x {n_m} markers -> {a.out}\n')
    if passthrough:
        sys.stderr.write(f'[terra_samples] carried through: {", ".join(passthrough)}\n')
    if a.audit:
        for k in sorted(tally, key=lambda k: -tally[k]):
            sys.stderr.write(f'    {tally[k]:7d}  {k}\n')
    return 0


def demo():
    """Self-check: both conventions, including the cases that are easy to get wrong."""
    cat = catalogue_index()
    assert ('crt', 76) in cat, 'catalogue should track crt codon 76'
    assert residue_verdict('T', 'K', 'T') == ('alt', 'alt')
    assert residue_verdict('K', 'K', 'T') == ('ref', 'ref')
    assert residue_verdict('N', 'K', 'T')[0] == 'ref'          # other substitution, not WHO's
    assert residue_verdict('K/T', 'K', 'T') == ('het', 'mixed_alt')
    assert residue_verdict('F/Y', 'K', 'T')[0] == 'ref'        # mixed, neither is WHO's alt
    assert residue_verdict('', 'K', 'T')[0] == 'missing'

    fields = ['entity:sample_id', 'aa_change_crt_K76T', 'resmarker_dhps_437', 'Dataset']
    rows = [{'entity:sample_id': 's1', 'aa_change_crt_K76T': 'mutant',
             'resmarker_dhps_437': 'G', 'Dataset': 'd'},
            {'entity:sample_id': 's2', 'aa_change_crt_K76T': 'absent',
             'resmarker_dhps_437': 'A', 'Dataset': 'd'}]
    calls, passthrough = reshape(rows, fields)
    by = {(c['sample_id'], c['gene'], c['aa_change']): c['call'] for c in calls}
    assert by[('s1', 'crt', 'K76T')] == 'alt'
    assert by[('s1', 'dhps', 'A437G')] == 'alt'
    assert by[('s2', 'dhps', 'A437G')] == 'ref'
    assert ('s2', 'crt', 'K76T') not in by, 'absent must not become a wild-type call'
    assert passthrough == ['Dataset']
    print('terra_samples demo OK')


if __name__ == '__main__':
    sys.exit(demo() if '--demo' in sys.argv else main())
