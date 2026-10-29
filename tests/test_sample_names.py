#!/usr/bin/env python3
"""The same sample carries three names in one workspace; matching must work in all of them.

  SAMPLE_S68_L001   mad4hatter's resmarker_table.txt / allele_data.txt
  SAMPLE_S68        the Terra row id
  SAMPLE            standardise_sample_name, applied by the QC report

Which one a report sees depends on whether the QC step ran, and that step needs a manifest
that cohorts aggregated over old runs often do not have. Before this, `--sample-ids` taken
from the data model (`this.samples.sample_id`) matched nothing against a marker table, and
a site-metadata file keyed on row ids placed no sample at all.

Run: tests/test_sample_names.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import gen_reports as G          # noqa: E402
import load_mad                  # noqa: E402

LANE, ROW, BARE = 'UG_TEST_G001_S68_L001', 'UG_TEST_G001_S68', 'UG_TEST_G001'

# ---- every spelling, longest first, no duplicates ---------------------------
assert G.name_forms(LANE) == (LANE, ROW, BARE), G.name_forms(LANE)
assert G.name_forms(ROW) == (ROW, BARE)
assert G.name_forms(BARE) == (BARE,)
assert G.name_forms('X_L002') == ('X_L002', 'X')          # lane with no S number
assert G.name_forms('X_S7_L002') == ('X_S7_L002', 'X_S7', 'X')   # any lane, not just 001
assert G.name_forms('  X_S7  ') == ('X_S7', 'X')          # whitespace
assert G.name_forms('') == ('',) and G.name_forms(None) == ('',)
assert G.name_forms('S68_L001') == ('S68_L001', 'S68')    # never strips to nothing

# ---- an allow-list selects the sample whenever the request is no longer than the
# ---- name the data carries. Matching shortens the data name; it never lengthens the
# ---- request, because that is what mis-attributes one sample's calls to another.
MATCHES = {   # (requested, as the data spells it) -> should match
    (BARE, LANE): True,  (BARE, ROW): True,  (BARE, BARE): True,
    (ROW,  LANE): True,  (ROW,  ROW): True,  (ROW,  BARE): False,
    (LANE, LANE): True,  (LANE, ROW): False, (LANE, BARE): False,
}
for (want, given), expect in MATCHES.items():
    got = bool(G.Selection([want]).keep(*G.name_forms(given)))
    assert got == expect, f'requested {want} against data {given}: {got}, wanted {expect}'
# so the bare name is the shape that always works, whatever produced the input
for given in (LANE, ROW, BARE):
    assert G.Selection([BARE]).keep(*G.name_forms(given))

# ---- but never a different sample -------------------------------------------
# The hazard is extending the *requested* name: if `X_S2_L001` could reduce to `X` and
# then re-extend, it would match row `X_S1` and attribute one sample's calls to another.
# Only forms of the name the data supplied are offered, and matching is exact.
assert not G.Selection(['X_S1']).keep(*G.name_forms('X_S2_L001'))
assert not G.Selection(['X_S1_L001']).keep(*G.name_forms('X_S2_L001'))
assert not G.Selection(['Y']).keep(*G.name_forms('X_S2_L001'))
# an empty selection means everything, which is not the same as matching nothing
assert G.Selection([]).keep(*G.name_forms('anything'))
assert not G.Selection(['nope']).keep(*G.name_forms('anything'))

# ---- site metadata keyed on any shape joins; ambiguity is refused -----------
idx, clash = load_mad.meta_index({ROW: 1, 'OTHER_S2_L001': 2, 'THIRD': 3})
assert not clash
assert idx[BARE] == ROW and idx[ROW] == ROW          # row-id key found by the bare name
assert idx['OTHER'] == 'OTHER_S2_L001' and idx['OTHER_S2'] == 'OTHER_S2_L001'
assert idx['THIRD'] == 'THIRD'

# two keys reducing to one spelling: that spelling identifies neither
idx, clash = load_mad.meta_index({'X_S1': 1, 'X_S9': 2})
assert clash == ['X'], clash
assert 'X' not in idx, 'an ambiguous name must not resolve to an arbitrary site'
assert idx['X_S1'] == 'X_S1' and idx['X_S9'] == 'X_S9', 'exact keys still work'

print('sample-name matching OK')
print(f'  three shapes collapse to one namespace ({LANE} -> {BARE})')
print('  an allow-list matches when the request is no longer than the data name, '
      'and never a different sample')
print('  site metadata keyed on any shape joins; a name two keys claim is refused')
