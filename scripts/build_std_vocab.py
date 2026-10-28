#!/usr/bin/env python3
"""Build schemas/std_vocab.json: the controlled vocabularies the two export sheets enforce.

Both reporting standards shipped in `schemas/` are mostly picklist columns, and a value
outside the picklist is rejected by the sheet rather than merely frowned upon. The exports
used to write whatever the data table said - `cross_sectional_survey` into a column whose
picklist is `TES | Community survey | ... | Other`, `kelch13` into one whose only k13
spelling is `k13`, and a bare `K76T` into a column where all 120 permitted values are
gene-prefixed (`crt K76T`). So the vocabularies have to be read out of the workbooks and
matched against, which is what this writes.

Sources, both already in the repo:
  Africa MMS_Data_Sheet_Final_2026.xlsx            sheet Mutation_Haplotype
  MalariaCommunityStandard_human_draft1_refined5.xlsx   sheet 'Pickl list HumanSample'

The Africa CDC ranges are not discoverable from the header row: the picklists live in that
workbook's data validations, which point into the 'Terms Reference guide' sheet by cell
range. Those ranges are recorded in AFCDC_RANGES below, taken verbatim from the
`<x14:dataValidation>` elements of sheet1 (column letter -> range), so a future edition of
the sheet can be diffed against them rather than guessed at.

Usage:
  build_std_vocab.py                 # both workbooks from schemas/, writes schemas/std_vocab.json
"""
import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings('ignore')   # openpyxl warns about the sheets' data-validation ext

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMAS = os.path.join(os.path.dirname(HERE), 'schemas')

AFCDC_BOOK = 'Africa CDC Minimum_Standard_for_MMS_2026.xlsx'
AFCDC_SHEET = 'Template'
PHA4GE_BOOK = 'MalariaCommunityStandard_human_draft1_refined5.xlsx'

# field -> ('Terms Reference guide' column-B row range), from the Template sheet's data
# validations. Travel history is the one literal formula rather than a range.
AFCDC_RANGES = {
    'country':        (7, 18),      # col E
    'study_type':     (22, 28),     # col H
    'gene_symbol':    (30, 45),     # col I
    'gene_alteration': (47, 157),   # col J
    'haplotype':      (159, 185),   # col K
    'dest_country':   (192, 463),   # col O
    'endemicity':     (465, 468),   # col P
    'assay':          (470, 479),   # col Q
}
AFCDC_INLINE = {'travel': ['Y', 'N']}   # col L

# The superseded edition, kept so a future one can be diffed against both. Its ranges are
# different and so are its lists: it had no PfPHAST or WGS under "Assay used", spelled
# endemicity as bare low/moderate/high, and offered "Other" under gene symbol, gene
# alteration and haplotype where the current edition offers none. Building against it
# produced an export that wrote "Other" for a PfPHAST run.
SUPERSEDED = {
    'book': 'Africa MMS_Data_Sheet_Final_2026.xlsx', 'sheet': 'Mutation_Haplotype',
    'ranges': {'country': (7, 18), 'study_type': (22, 28), 'gene_symbol': (30, 47),
               'gene_alteration': (49, 169), 'haplotype': (171, 199),
               'dest_country': (206, 478), 'assay': (485, 495)},
    'inline': {'travel': ['Y', 'N'],
               'endemicity': ['low', 'moderate', 'moderate-high', 'high']},
}

# The PHA4GE picklists are one per column on a single sheet, keyed by the header cell.
PHA4GE_FIELDS = ('gene_symbol', 'gene_name', 'gene_alteration', 'sequencing_assay_type',
                 'host_sex', 'host_age_unit', 'host_age_bin', 'study', 'resistance_status')


def afcdc(path, sheet=AFCDC_SHEET, ranges=AFCDC_RANGES, inline=AFCDC_INLINE):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb['Terms Reference guide']
    out = dict(inline)
    for field, (a, b) in ranges.items():
        vals = [ws.cell(row=r, column=2).value for r in range(a, b + 1)]
        out[field] = [str(v).strip() for v in vals if v not in (None, '')]
    # the header row is the authority on column names and their order
    out['_columns'] = [str(c).strip() for c in
                       next(wb[sheet].iter_rows(min_row=1, max_row=1, values_only=True))
                       if c not in (None, '')]
    return out


def pha4ge(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True)['Pickl list HumanSample']
    cols = {}
    for row in ws.iter_rows(values_only=True):
        for i, v in enumerate(row):
            if v not in (None, ''):
                cols.setdefault(i, []).append(str(v).strip())
    by_head = {c[0]: c[1:] for c in cols.values() if c}
    return {f: by_head[f] for f in PHA4GE_FIELDS if f in by_head}


def main(argv=None):
    ap = argparse.ArgumentParser(description='Export-standard picklists -> JSON.')
    ap.add_argument('--schemas-dir', default=SCHEMAS)
    ap.add_argument('--out')
    a = ap.parse_args(argv)
    out = a.out or os.path.join(a.schemas_dir, 'std_vocab.json')

    doc = {
        '_source': f'{AFCDC_BOOK} ({AFCDC_SHEET} + Terms Reference guide); {PHA4GE_BOOK}'
                   " ('Pickl list HumanSample')",
        '_note': 'controlled vocabularies for the export columns. A value absent from a '
                 'list is rejected by the sheet; lists ending in "Other" have a sanctioned '
                 'fallback, the rest do not.',
        'afcdc': afcdc(os.path.join(a.schemas_dir, AFCDC_BOOK)),
        'pha4ge': pha4ge(os.path.join(a.schemas_dir, PHA4GE_BOOK)),
    }
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write('\n')

    for std in ('afcdc', 'pha4ge'):
        for k, v in sorted(doc[std].items()):
            if k.startswith('_'):
                continue
            print(f'{std:7s} {k:22s} {len(v):4d} values'
                  + ('  (+Other)' if 'Other' in v else '  (no Other: unmatched -> blank)'))
    print(f'\nwrote {out}  {os.path.getsize(out)/1024:.0f} KB')

    # What changed since the previous edition. Worth printing every time: the lists are the
    # reason the export is valid or not, and an edition that quietly adds PfPHAST to the
    # assay picklist changes what this repo should emit.
    old_path = os.path.join(a.schemas_dir, SUPERSEDED['book'])
    if os.path.exists(old_path):
        old = afcdc(old_path, SUPERSEDED['sheet'], SUPERSEDED['ranges'], SUPERSEDED['inline'])
        print(f"\nagainst the superseded {SUPERSEDED['book']}:")
        for k in sorted(set(old) | set(doc['afcdc'])):
            new_v, old_v = doc['afcdc'].get(k, []), old.get(k, [])
            added = [x for x in new_v if x not in old_v]
            gone = [x for x in old_v if x not in new_v]
            if added or gone:
                print(f'  {k}: +{len(added)} -{len(gone)}')
                if added: print(f'      added:   {added[:6]}')
                if gone:  print(f'      dropped: {gone[:6]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
