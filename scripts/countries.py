#!/usr/bin/env python3
"""Resolve a country name to an ISO3 code, tolerantly, and say how it was resolved.

The country selects the admin boundary set, and selecting the wrong one drops every
sample whose coordinates fall outside it. Requiring the submitter to supply an ISO3 code
by hand makes that a one-keystroke mistake, so the country is read from the data's own
country column instead, matched against `reference/countries.json` (ISO 3166-1 plus
curated common names: "DRC", "Ivory Coast", "Tanzania", ...).

Matching is exact, then normalised (case, accents, punctuation, a leading "the"), then
fuzzy, in that order, and the method is always reported. A fuzzy match is a guess that
happens to be right most of the time, so it is logged as a guess rather than presented as
a fact, and anything below the cutoff resolves to nothing at all rather than to the
nearest wrong country.
"""
import difflib
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_reports as G

# Below this, the closest name is not close enough to act on. 0.84 accepts "Ugandaa" and
# "Senagal" while rejecting Niger/Nigeria confusion, which is the pair that matters most
# here: they are different countries one letter apart and both have boundary maps.
FUZZY_CUTOFF = 0.84


def _na(s):
    """Normalise for comparison: accents, case, punctuation, articles."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r'^the\s+', '', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return s


def table(path=None):
    p = path or os.path.join(G.REF_DIR, 'countries.json')
    if not os.path.exists(p):
        return {}
    with open(p, encoding='utf-8') as fh:
        return (json.load(fh) or {}).get('countries') or {}


def resolve(raw, countries=None, require_map=False):
    """-> dict(iso3, name, how, score, has_map) or None.

    how: 'iso3' | 'exact' | 'normalised' | 'fuzzy'
    """
    countries = countries if countries is not None else table()
    if not raw or not countries:
        return None
    s = str(raw).strip()
    if not s:
        return None

    def hit(iso, how, score=1.0):
        c = countries[iso]
        return {'iso3': iso, 'name': c['name'], 'how': how, 'score': score,
                'has_map': bool(c.get('has_map'))}

    # an ISO3 (or ISO2) code given directly
    up = s.upper()
    if up in countries:
        return hit(up, 'iso3')
    if len(up) == 2:
        for iso, c in countries.items():
            if c.get('alpha2') == up:
                return hit(iso, 'iso3')

    # exact name or alias
    for iso, c in countries.items():
        if s == c['name'] or s in (c.get('aliases') or []):
            return hit(iso, 'exact')

    # normalised
    n = _na(s)
    norm = {}
    for iso, c in countries.items():
        for name in [c['name']] + (c.get('aliases') or []):
            norm.setdefault(_na(name), iso)
    if n in norm:
        return hit(norm[n], 'normalised')

    # fuzzy, against the maps we actually have first: a typo is far more likely to be a
    # country this deployment covers than one of the 195 it does not
    def closest(pool):
        if not pool:
            return None, 0.0
        best = difflib.get_close_matches(n, list(pool), n=1, cutoff=FUZZY_CUTOFF)
        if not best:
            return None, 0.0
        return pool[best[0]], difflib.SequenceMatcher(None, n, best[0]).ratio()

    mapped = {k: v for k, v in norm.items() if countries[v].get('has_map')}
    iso, score = closest(mapped)
    if not iso and not require_map:
        iso, score = closest(norm)
    if iso:
        return hit(iso, 'fuzzy', round(score, 3))
    return None


def sniff(paths, column_names=('country', 'admin0', 'adm0', 'country_name'), limit=5000):
    """Most common country value across the given tables. -> (value, counts) or (None, {})."""
    import csv
    counts = {}
    for p in paths or []:
        delim = '\t' if str(p).lower().endswith(('.tsv', '.txt')) else ','
        try:
            with open(p, newline='', encoding='utf-8-sig') as fh:
                rd = csv.DictReader(fh, delimiter=delim)
                cols = {(h or '').strip().lower(): h for h in (rd.fieldnames or [])}
                col = next((cols[c] for c in column_names if c in cols), None)
                if not col:
                    continue
                for i, row in enumerate(rd):
                    if i >= limit:
                        break
                    v = (row.get(col) or '').strip()
                    if v:
                        counts[v] = counts.get(v, 0) + 1
        except OSError:
            continue
    if not counts:
        return None, {}
    return max(counts, key=counts.get), counts


def demo():
    c = table()
    assert c, 'reference/countries.json should ship'
    assert len(c) > 240, len(c)

    # the case that caused a failed Terra run: the data says "Uganda", nobody typed an ISO3
    r = resolve('Uganda', c)
    assert r['iso3'] == 'UGA' and r['how'] == 'exact' and r['has_map'], r

    # codes work too
    assert resolve('UGA', c)['how'] == 'iso3'
    assert resolve('ug', c)['iso3'] == 'UGA'

    # common names that are not the ISO string
    for name, iso in [('DRC', 'COD'), ('Democratic Republic of the Congo', 'COD'),
                      ('Ivory Coast', 'CIV'), ('Tanzania', 'TZA'), ('Gambia', 'GMB')]:
        assert resolve(name, c)['iso3'] == iso, (name, resolve(name, c))

    # accents and punctuation
    assert resolve("Côte d'Ivoire", c)['iso3'] == 'CIV'
    assert resolve('cote divoire', c)['iso3'] == 'CIV'

    # spelling errors
    for typo, iso in [('Ugandaa', 'UGA'), ('Senagal', 'SEN'), ('Mozambiqe', 'MOZ'),
                      ('Zimbabwee', 'ZWE')]:
        r = resolve(typo, c)
        assert r and r['iso3'] == iso, (typo, r)
        assert r['how'] == 'fuzzy', (typo, r)

    # Niger and Nigeria are one letter apart and both real: never silently swap them
    assert resolve('Niger', c)['iso3'] == 'NER'
    assert resolve('Nigeria', c)['iso3'] == 'NGA'

    # nonsense resolves to nothing rather than to the nearest country
    assert resolve('Wakanda', c) is None
    assert resolve('', c) is None
    assert resolve('XYZ', c) is None

    # a real country we ship no boundaries for is recognised, and says so
    r = resolve('France', c)
    assert r['iso3'] == 'FRA' and not r['has_map'], r

    print('countries demo OK')
    for n in ('Uganda', 'DRC', 'Ivory Coast', 'Ugandaa', 'Senagal', 'France', 'Wakanda'):
        r = resolve(n, c)
        if not r:
            print(f'  {n!r:24s} -> unresolved')
            continue
        score = '' if r['score'] == 1.0 else f" score {r['score']}"
        nomap = '' if r['has_map'] else '   [recognised, but no boundary map shipped]'
        print(f"  {n!r:24s} -> {r['iso3']} {r['name']!r} via {r['how']}{score}{nomap}")


if __name__ == '__main__':
    demo()
