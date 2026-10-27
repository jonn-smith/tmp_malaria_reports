#!/usr/bin/env python3
"""Build reference/admin_names.json.gz: admin-1 and admin-2 place names -> ISO3 countries.

Used as the last resort when deciding which country a dataset came from, after an explicit
code, a country column and the coordinates have all failed. Names are the weakest of those
signals because they are not unique - there is a Kolda in Senegal and dozens of
duplicated district names worldwide - so the index keeps *every* country a name occurs in
and the caller is responsible for requiring a clear winner.

Sources, both names-only and global:
  GeoNames admin1CodesASCII.txt   CC.A1       -> admin-1 name
  GeoNames admin2Codes.txt        CC.A1.A2    -> admin-2 name
  the shipped projected maps      reference/adm2/<ISO3>_adm2_map.json.gz

The maps are folded in deliberately: they are the units the report actually aggregates
into, so a name that appears there must resolve to that country even if GeoNames spells it
differently or omits it.

Usage:
  build_admin_index.py --admin1 admin1CodesASCII.txt --admin2 admin2Codes.txt
"""
import argparse
import glob
import gzip
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.environ.get('MALARIA_REPORTS_REF_DIR') or os.path.join(ROOT, 'reference')

# Names too generic to identify a country. Every one of these occurs as an admin unit in
# many places, so a match on one is noise rather than evidence.
STOPWORDS = {
    'north', 'south', 'east', 'west', 'central', 'northern', 'southern', 'eastern',
    'western', 'centre', 'center', 'capital', 'city', 'district', 'province', 'region',
    'municipality', 'county', 'rural', 'urban', 'metropolitan', 'upper', 'lower',
    'middle', 'nord', 'sud', 'est', 'ouest', 'centro', 'norte', 'sur', 'none', 'unknown',
}


def na(s):
    """Normalise a place name for comparison: accents, case, punctuation, articles."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r'^(the|le|la|les|el)\s+', '', s)
    # drop a trailing unit noun: "Kolda District" and "Kolda" are the same place
    s = re.sub(r'\s+(district|province|region|county|municipality|departement|'
               r'department|prefecture|governorate|state)$', '', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return s


def iso2_to_iso3(countries):
    return {v['alpha2']: k for k, v in countries.items() if v.get('alpha2')}


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the admin-name -> country index.')
    ap.add_argument('--admin1', required=True, help='GeoNames admin1CodesASCII.txt')
    ap.add_argument('--admin2', required=True, help='GeoNames admin2Codes.txt')
    ap.add_argument('--out', default=os.path.join(REF, 'admin_names.json.gz'))
    a = ap.parse_args(argv)

    with open(os.path.join(REF, 'countries.json'), encoding='utf-8') as fh:
        countries = (json.load(fh) or {}).get('countries') or {}
    i2to3 = iso2_to_iso3(countries)

    adm = {'1': {}, '2': {}}

    def add(level, name, iso3):
        n = na(name)
        if not n or n in STOPWORDS or len(n) < 3:
            return
        adm[level].setdefault(n, set()).add(iso3)

    for level, path in (('1', a.admin1), ('2', a.admin2)):
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                parts = line.rstrip('\n').split('\t')
                if len(parts) < 3:
                    continue
                cc = parts[0].split('.')[0]
                iso3 = i2to3.get(cc)
                if not iso3:
                    continue
                add(level, parts[1], iso3)
                if parts[2] and parts[2] != parts[1]:
                    add(level, parts[2], iso3)

    # the units the report actually aggregates into take priority of existence
    maps = 0
    for p in sorted(glob.glob(os.path.join(REF, 'adm2', '*_adm2_map.json.gz'))):
        iso3 = os.path.basename(p).split('_')[0]
        with gzip.open(p, 'rt', encoding='utf-8') as fh:
            d = json.load(fh)
        maps += 1
        for unit in d.get('depts') or []:
            add('2', unit.get('name'), iso3)
            if unit.get('name_raw'):
                add('2', unit['name_raw'], iso3)
            if unit.get('region'):
                add('1', unit['region'], iso3)

    doc = {
        '_source': ('GeoNames admin1CodesASCII.txt + admin2Codes.txt, plus the unit names '
                    'from the projected maps in reference/adm2/'),
        '_note': ('values are every ISO3 a name occurs in; a name shared by several '
                  'countries is evidence for none of them on its own'),
        'stopwords': sorted(STOPWORDS),
        'admin1': {k: sorted(v) for k, v in sorted(adm['1'].items())},
        'admin2': {k: sorted(v) for k, v in sorted(adm['2'].items())},
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    blob = json.dumps(doc, separators=(',', ':'), sort_keys=True)
    with gzip.GzipFile(a.out, 'wb', compresslevel=9, mtime=0) as fh:
        fh.write(blob.encode())

    uniq1 = sum(1 for v in doc['admin1'].values() if len(v) == 1)
    uniq2 = sum(1 for v in doc['admin2'].values() if len(v) == 1)
    print(f'admin-1 names: {len(doc["admin1"]):6d}  ({uniq1} unique to one country)')
    print(f'admin-2 names: {len(doc["admin2"]):6d}  ({uniq2} unique to one country)')
    print(f'folded in {maps} projected maps')
    print(f'wrote {a.out}  {os.path.getsize(a.out)/1024:.0f} KB gz '
          f'({len(blob)/1024/1024:.1f} MB raw)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
