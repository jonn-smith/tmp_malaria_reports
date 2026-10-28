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

AFCDC_BOOK = 'Africa MMS_Data_Sheet_Final_2026.xlsx'
PHA4GE_BOOK = 'MalariaCommunityStandard_human_draft1_refined5.xlsx'

# field -> ('Terms Reference guide' column-B row range), from sheet1's data validations.
# The two inline lists (Travel history, Endemicity) are literal formulas, not ranges.
AFCDC_RANGES = {
    'country':        (7, 18),      # col E
    'study_type':     (22, 28),     # col H
    'gene_symbol':    (30, 47),     # col I
    'gene_alteration': (49, 169),   # col J
    'haplotype':      (171, 199),   # col K
    'dest_country':   (206, 478),   # col O
    'assay':          (485, 495),   # col Q
}
AFCDC_INLINE = {
    'travel':     ['Y', 'N'],                                    # col L
    'endemicity': ['low', 'moderate', 'moderate-high', 'high'],   # col P
}

# The PHA4GE picklists are one per column on a single sheet, keyed by the header cell.
PHA4GE_FIELDS = ('gene_symbol', 'gene_name', 'gene_alteration', 'sequencing_assay_type',
                 'host_sex', 'host_age_unit', 'host_age_bin', 'study', 'resistance_status')


def afcdc(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True)['Terms Reference guide']
    out = dict(AFCDC_INLINE)
    for field, (a, b) in AFCDC_RANGES.items():
        vals = [ws.cell(row=r, column=2).value for r in range(a, b + 1)]
        out[field] = [str(v).strip() for v in vals if v not in (None, '')]
    # the header row is the authority on column names and their order
    mh = openpyxl.load_workbook(path, data_only=True)['Mutation_Haplotype']
    out['_columns'] = [str(c).strip() for c in
                       next(mh.iter_rows(min_row=1, max_row=1, values_only=True))
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
        '_source': f'{AFCDC_BOOK} (Mutation_Haplotype + Terms Reference guide); {PHA4GE_BOOK}'
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
                  + ('  (+Other)' if 'Other' in v else ''))
    print(f'\nwrote {out}  {os.path.getsize(out)/1024:.0f} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
