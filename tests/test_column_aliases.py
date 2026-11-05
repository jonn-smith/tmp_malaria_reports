#!/usr/bin/env python3
"""Africa CDC Minimum Standard column names are recognised, and alias order never changes.

Sites fill their metadata in on the Africa CDC sheet, so a Terra table built from it
carries the sheet's own column names - `district(admin_level_2)`, not `district` - and its
country values carry the GAZ ontology id: `Tanzania [GAZ:00001103]`. Both defeated the
loader, and because the country chain has no default the whole run stopped with "could not
determine which country this data is from" (gates-malaria/Africa PGI MMS, the Tanzania
pfPHAST table, 376 rows).

The fix is additive, and the safety property is the ORDER: _colmap and xf() both take the
first alias present, so the sheet's spellings are appended and a table that already
matched a short name still matches it. This file pins that, because prepending would
silently change which column an existing report reads.

Run: tests/test_column_aliases.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import countries as C        # noqa: E402
import gen_reports as G      # noqa: E402
import load_nomads as L      # noqa: E402

# ---- the real table that failed: headers copied from the live workspace ----
LIVE = ['entity:mms_nphl_sequence_data_pfphast_Tanzania_id', 'read1', 'read2', 'sample_id',
        'country', 'district(admin_level_2)', 'region_province(admin_level_1)',
        'facility_name', 'date_of_sample_collection', 'endemicity', 'study_type',
        'travel_history_[Y/N]', 'assay_used', 'resmarker_crt_76']
cm = L._colmap(LIVE)
# The Terra row id wins over the sheet's own `sample_id` column. On this table that column
# holds the site-local specimen number, which repeats across districts, so keying on it
# would merge two different samples into one row.
assert cm['sample_id'] == 'entity:mms_nphl_sequence_data_pfphast_Tanzania_id', cm['sample_id']
assert L._colmap(['entity:t_id', 'sample_id'])['sample_id'] == 'entity:t_id'
assert L._colmap(['sample_id'])['sample_id'] == 'sample_id', 'with no row id, use what there is'
assert cm['district'] == 'district(admin_level_2)', cm.get('district')
assert cm['region'] == 'region_province(admin_level_1)', cm.get('region')
assert cm['site'] == 'facility_name'
assert cm['date'] == 'date_of_sample_collection', cm.get('date')
assert cm['country'] == 'country'

# punctuation the next export of that sheet may or may not survive with
for header, canon in (('district_(admin_level_2)', 'district'),
                      ('district (admin_level_2)', 'district'),
                      ('district_admin_level_2', 'district'),
                      ('region_province', 'region'),
                      ('REGION_PROVINCE(ADMIN_LEVEL_1)', 'region')):
    got = L._colmap(['x', header]).get(canon)
    assert got == header, f'{header!r} should map to {canon}, got {got!r}'

# ---- ORDER: a short name already in use keeps priority -----------------------
# This is the whole reverse-compatibility argument. If these flip, reports that work
# today start reading a different column.
both = L._colmap(['district', 'district(admin_level_2)',
                  'region', 'region_province(admin_level_1)',
                  'date', 'date_of_sample_collection'])
assert both['district'] == 'district', 'appended alias must not outrank `district`'
assert both['region'] == 'region', 'appended alias must not outrank `region`'
assert both['date'] == 'date', 'appended alias must not outrank `date`'
# and the historical aliases still beat the new ones
assert L._colmap(['admin2', 'district(admin_level_2)'])['district'] == 'admin2'
assert L._colmap(['province', 'region_province(admin_level_1)'])['region'] == 'province'
# every alias tuple must keep its original head, in its original position
for canon, head in (('district', 'district'), ('region', 'region'), ('country', 'country'),
                    ('site', 'site'), ('date', 'date'), ('sample_id', 'sample_id')):
    assert L.ALIASES[canon][0] == head, f'{canon} alias order changed at the head'

# ---- export fields: same first-match rule -----------------------------------
s = {'extra': {'travel_history_[Y/N]': 'N', 'endemicity': 'Moderate/Mesoendemic',
               'study_type': 'Health facility',
               'destination_of_most_recent_travel_country': 'Kenya'}}
assert G.xf(s, 'travel') == 'N'
assert G.xf(s, 'travel_dest') == 'Kenya'
assert G.xf(s, 'endemicity') == 'Moderate/Mesoendemic'
assert G.xf(s, 'study_type') == 'Health facility'
# a shorter name present as well still wins
s2 = {'extra': {'travel_history': 'Y', 'travel_history_[Y/N]': 'N'}}
assert G.xf(s2, 'travel') == 'Y', 'appended export alias must not outrank travel_history'

# ---- GAZ-tagged country values resolve --------------------------------------
for raw, iso in (('Tanzania [GAZ:00001103]', 'TZA'), ('Uganda [GAZ:00001102]', 'UGA'),
                 ('tanzania [gaz:00001103]', 'TZA'), ('Tanzania[GAZ:00001103]', 'TZA'),
                 ('Democratic Republic of the Congo [GAZ:00001086]', 'COD')):
    hit = C.resolve(raw)
    assert hit and hit['iso3'] == iso, f'{raw!r} -> {hit}'
assert C.resolve('Tanzania')['iso3'] == 'TZA', 'the plain name still resolves'
assert C.resolve('Tanzania [GAZ:00001103]')['how'] in ('exact', 'iso3', 'normalised'), \
    'a GAZ-tagged name should resolve exactly, not by fuzzy guess'
# only this suffix is stripped: brackets in general are left alone
assert C.resolve('[GAZ:00001103]') is None
assert C.resolve('Narnia [GAZ:00000001]') is None
assert C.resolve('Niger') ['iso3'] == 'NER' and C.resolve('Nigeria')['iso3'] == 'NGA'

print('column aliases OK')
print('  the live Tanzania headers now map: district/region/site/date/country')
print('  appended aliases never outrank an existing shorter name (order pinned)')
print('  GAZ-tagged country values resolve exactly; other brackets still rejected')
