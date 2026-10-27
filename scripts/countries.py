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


def from_coordinates(points, log=None):
    """Which shipped boundary set actually contains these coordinates?

    Used when the data has no country column at all. Coordinates are unambiguous, so this
    is a stronger signal than a name: it answers exactly the question that matters, namely
    which admin boundary set the samples fall inside. Screening is by each map's bounding
    box first, which eliminates almost every country from the map header alone; only the
    survivors pay for point-in-polygon.

    -> dict(iso3, name, n_inside, n_tested, runners_up) or None.
    """
    import glob
    pts = [(la, lo) for la, lo in points
           if la is not None and lo is not None and (la, lo) != (0, 0)]
    if not pts:
        return None
    countries = table()

    isos = sorted(os.path.basename(p).split('_')[0]
                  for p in glob.glob(os.path.join(G.REF_DIR, 'adm2', '*_adm2_map.json.gz')))
    # bounding-box screen: cheap, and a point outside the box cannot be inside any unit
    boxed = []
    for iso in isos:
        try:
            m = G.load_country_map(iso)
        except SystemExit:
            continue
        n = sum(1 for la, lo in pts
                if m['latMin'] <= la <= m['latMax'] and m['lonMin'] <= lo <= m['lonMax'])
        if n:
            boxed.append((n, iso))
    if not boxed:
        return None
    boxed.sort(reverse=True)

    # point-in-polygon only for the boxed candidates, best-first
    scored = []
    saved = (G.COUNTRY_ISO, G.COUNTRY_NAME)
    try:
        for _n, iso in boxed[:8]:
            G.set_country(iso, (countries.get(iso) or {}).get('name'))
            hits = sum(1 for la, lo in pts if G.dept_of_point(la, lo))
            if log:
                log.write(f'[countries] {iso}: {hits}/{len(pts)} sampled coordinates '
                          f'fall inside its admin units\n')
            scored.append((hits, iso))
            if hits == len(pts):
                break
    finally:
        G.set_country(*saved)
    scored.sort(reverse=True)
    if not scored or not scored[0][0]:
        return None
    hits, iso = scored[0]
    c = countries.get(iso) or {}
    return {'iso3': iso, 'name': c.get('name') or iso, 'n_inside': hits,
            'n_tested': len(pts),
            'runners_up': [i for h, i in scored[1:4] if h]}


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


def sniff_points(paths, limit=400, keep=12):
    """A handful of coordinates from the given tables, for from_coordinates()."""
    import csv
    lat_names = ('lat', 'latitude')
    lon_names = ('lon', 'long', 'longitude')
    out = []
    for p in paths or []:
        delim = '\t' if str(p).lower().endswith(('.tsv', '.txt')) else ','
        try:
            with open(p, newline='', encoding='utf-8-sig') as fh:
                rd = csv.DictReader(fh, delimiter=delim)
                cols = {(h or '').strip().lower(): h for h in (rd.fieldnames or [])}
                la = next((cols[c] for c in lat_names if c in cols), None)
                lo = next((cols[c] for c in lon_names if c in cols), None)
                if not (la and lo):
                    continue
                for i, row in enumerate(rd):
                    if i >= limit or len(out) >= keep:
                        break
                    try:
                        out.append((float(row[la]), float(row[lo])))
                    except (TypeError, ValueError, KeyError):
                        continue
        except OSError:
            continue
    return out


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

    # Coordinates, for tables with no country column at all. Unit centroids are inside
    # their own unit by construction, so they are a fair probe.
    import gen_reports as _G
    saved = (_G.COUNTRY_ISO, _G.COUNTRY_NAME)
    try:
        for iso in ('UGA', 'SEN'):
            _G.set_country(iso, None)
            pts = [(d['lat'], d['lon']) for d in _G.MAP['depts'][:8]]
            _G.set_country(*saved)
            hit = from_coordinates(pts)
            assert hit and hit['iso3'] == iso, (iso, hit)
            assert hit['n_inside'] >= 6, (iso, hit)   # a centroid can miss on a sliver
        # the middle of the Atlantic belongs to no shipped boundary set
        assert from_coordinates([(0.0, -30.0)]) is None
        # and no usable points means no guess
        assert from_coordinates([]) is None
        assert from_coordinates([(None, None)]) is None
    finally:
        _G.set_country(*saved)

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
