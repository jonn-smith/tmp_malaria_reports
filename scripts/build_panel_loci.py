#!/usr/bin/env python3
"""Generate per-panel inputs for 03_ExtractDrugResistanceMarkers.

The published default, `default_principal_resistance_marker_info_table.bed`, is
panel-agnostic: 74 curated loci, of which PfPHAST can type 41 of its 82 and MAD4HatTeR 51
of its 147. So neither panel's extraction covers what that panel actually measures, and the
report can only show what the extraction produced.

These files fix that by deriving each panel's real reach from upstream:

  panel_information/principal_resistance_marker_info_table.tsv   codon coordinates
  panel_information/<pool>/<pool>_amplicon_info.tsv              each pool's inserts

A pool types a marker when the marker's codon interval lies inside one of that pool's
amplicon inserts; a panel is the union over its pools. Panels are pool combinations, per
the Mad4Hatter workspace documentation: PfPHAST is M1.1+M2.1, MAD4HatTeR is D1.1+R1.2+R2.1.

Output per panel, in exactly the format the workflow already consumes:
  <panel>_principal_resistance_marker_info_table.bed
  <panel>_loci_groups.tsv      haplotype groups, restricted to groups the panel can type
                               in full - a haplotype assembled from partially typed codons
                               would be wrong rather than incomplete

Usage:
  build_panel_loci.py --markers principal_resistance_marker_info_table.tsv \\
                      --pools-dir <dir of <pool>_amplicon_info.tsv> \\
                      --loci-groups default_loci_groups.tsv \\
                      --out-dir reference/panel_loci
"""
import argparse
import csv
import glob
import os
import sys

# Panels as pool combinations, from the Mad4Hatter Terra workspace documentation.
PANELS = {
    'pfphast':    ['M1.1', 'M2.1'],
    'mad4hatter': ['D1.1', 'R1.2', 'R2.1'],
}

BED_HEADER = ['#chrom', 'start', 'end', 'name', 'length', 'strand', 'gene',
              'aa_position', 'gene_id']


def long_gene_id(short):
    """0106300 -> PF3D7_0106300.1, which is the spelling the bed and loci_groups use."""
    s = str(short).strip()
    return s if s.upper().startswith('PF3D7') else f'PF3D7_{s}.1'


def read_markers(path):
    out = []
    with open(path, newline='', encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh, delimiter='\t'):
            try:
                out.append({
                    'chrom': r['chrom'], 'start': int(r['start']), 'stop': int(r['stop']),
                    'strand': r['strand'], 'gene': r['gene'],
                    'aa_position': int(r['aa_position']),
                    'gene_id': long_gene_id(r['gene_id']),
                })
            except (KeyError, ValueError):
                continue
    return out


def read_inserts(path):
    out = []
    with open(path, newline='', encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh, delimiter='\t'):
            try:
                out.append((r['chrom'], int(r['insert_start']), int(r['insert_end'])))
            except (KeyError, ValueError, TypeError):
                continue
    return out


def typed_by(markers, inserts):
    """Markers whose codon interval lies inside one of the inserts."""
    hit = []
    for m in markers:
        for c, i0, i1 in inserts:
            if c == m['chrom'] and m['start'] >= i0 and m['stop'] <= i1:
                hit.append(m)
                break
    return hit


def write_bed(path, markers):
    rows = sorted(markers, key=lambda m: (m['chrom'], m['start']))
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(BED_HEADER)
        for m in rows:
            w.writerow([m['chrom'], m['start'], m['stop'],
                        f"{m['gene_id']}-AA{m['aa_position']}",
                        m['stop'] - m['start'], m['strand'], m['gene'],
                        m['aa_position'], m['gene_id']])
    return len(rows)


def write_loci_groups(path, src, covered):
    """Keep only groups every one of whose loci the panel types."""
    groups = {}
    with open(src, newline='', encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh, delimiter='\t'):
            groups.setdefault(r['group_id'], []).append(
                (long_gene_id(r['gene_id']), int(r['aa_position'])))
    kept, dropped = {}, {}
    for g, members in groups.items():
        missing = [m for m in members if m not in covered]
        if missing:
            dropped[g] = missing
        else:
            kept[g] = members
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['group_id', 'gene_id', 'aa_position'])
        for g in sorted(kept):
            for gid, pos in kept[g]:
                w.writerow([g, gid, pos])
    return kept, dropped


def main(argv=None):
    ap = argparse.ArgumentParser(description='Per-panel resistance-marker inputs.')
    ap.add_argument('--markers', required=True)
    ap.add_argument('--pools-dir', required=True)
    ap.add_argument('--loci-groups', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--compare-default', help='an existing panel-agnostic bed. Its gene '
                                              'labels are adopted (the pipeline names its '
                                              'output columns from them) and every shared '
                                              'row is then checked byte for byte.')
    a = ap.parse_args(argv)

    markers = read_markers(a.markers)

    # The published bed and the upstream marker table disagree on three gene labels:
    # dhfr-ts vs dhfr, and PF3D7-1322700 / PF3D7-1451200 vs the underscore spellings. The
    # resmarker output columns are named from this field (resmarker_dhfr-ts_108 exists in
    # the Terra tables), so the published spelling is the one downstream already expects.
    if a.compare_default:
        label = {}
        with open(a.compare_default, newline='') as fh:
            rd = csv.reader(fh, delimiter='\t')
            next(rd, None)
            for r in rd:
                if len(r) >= 9:
                    label[r[8]] = r[6]
        renamed = 0
        for m in markers:
            want = label.get(m['gene_id'])
            if want and want != m['gene']:
                m['gene'] = want
                renamed += 1
        if renamed:
            print(f'adopted {renamed} gene labels from the published bed '
                  f'(e.g. dhfr -> dhfr-ts)\n')
    pools = {}
    for p in sorted(glob.glob(os.path.join(a.pools_dir, '*.tsv'))):
        pools[os.path.basename(p)[:-4]] = read_inserts(p)
    missing = {p for pl in PANELS.values() for p in pl} - set(pools)
    if missing:
        raise SystemExit(f'no amplicon_info for pool(s): {sorted(missing)}')

    os.makedirs(a.out_dir, exist_ok=True)
    print(f'{len(markers)} principal resistance markers; '
          f'{len(pools)} pools available\n')

    for panel, pool_list in PANELS.items():
        seen, hit = set(), []
        per_pool = {}
        for pool in pool_list:
            got = typed_by(markers, pools[pool])
            per_pool[pool] = len(got)
            for m in got:
                key = (m['gene_id'], m['aa_position'])
                if key not in seen:
                    seen.add(key)
                    hit.append(m)
        bed = os.path.join(a.out_dir,
                           f'{panel}_principal_resistance_marker_info_table.bed')
        n = write_bed(bed, hit)
        lg = os.path.join(a.out_dir, f'{panel}_loci_groups.tsv')
        kept, dropped = write_loci_groups(lg, a.loci_groups, seen)
        detail = ', '.join(f'{p} {per_pool[p]}' for p in pool_list)
        print(f'{panel}: pools {" + ".join(pool_list)} ({detail})')
        print(f'  {os.path.basename(bed)}: {n} loci')
        print(f'  {os.path.basename(lg)}: groups kept {sorted(kept)}'
              + (f', dropped {sorted(dropped)} (not fully typed)' if dropped else ''))

    if a.compare_default:
        # Strong check: for every locus the default bed and ours share, the rows must be
        # identical. Any difference means a coordinate or naming convention is off.
        def rows_of(path):
            with open(path, newline='') as fh:
                rd = csv.reader(fh, delimiter='\t')
                next(rd, None)
                return {(r[8], r[7]): r for r in rd if len(r) >= 9}
        dflt = rows_of(a.compare_default)
        bad = 0
        for panel in PANELS:
            ours = rows_of(os.path.join(
                a.out_dir, f'{panel}_principal_resistance_marker_info_table.bed'))
            shared = set(dflt) & set(ours)
            diff = [k for k in shared if dflt[k] != ours[k]]
            print(f'\n{panel} vs default bed: {len(shared)} shared loci, '
                  f'{len(diff)} rows differ')
            bad += len(diff)
            for k in diff[:3]:
                print(f'  default {dflt[k]}\n  ours    {ours[k]}')
        if bad:
            raise SystemExit('generated rows disagree with the published default')
        print('\nevery shared row matches the published default byte for byte')
    return 0


if __name__ == '__main__':
    sys.exit(main())
