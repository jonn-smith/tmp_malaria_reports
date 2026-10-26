#!/usr/bin/env python3
"""One location resolver for every assay, with an audit trail.

Accepted location, in strict precedence order:

  1. lat + lon      explicit coordinates win outright. They are unambiguous, so a
                    disagreement with the named district is the name's problem.
  2. district       admin-2 name, matched exactly, then normalised, then through the
                    health-district alias table, then offered as a fuzzy suggestion.
  3. country/region admin-0 and admin-1 cannot place a sample at admin-2. They are kept
                    for cross-checking and reporting, never for placement.

Nothing here resolves quietly. Every sample that cannot be placed, every name that only
matched through an alias, every coordinate that falls outside the country, and every
explicit region that disagrees with the boundary file is recorded in an Audit, which the
loaders print to stderr, `make_report.py` writes as a TSV, and the report renders. A
spelling error in a district name silently becomes a missing sample otherwise, and a
missing sample is invisible in a prevalence denominator.
"""
import difflib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_reports as G

# Senegal health-district names that differ from the geoBoundaries admin-2 unit holding
# them. Not spelling variants - a programme's health districts are a different division
# of the country, so these are deliberate mappings and belong in the audit as such.
HEALTH2DEPT = {
    'RICHARD TOLL': 'Dagana', 'DIOULOULOU': 'Bignona', 'NDOFFANE': 'Kaolack',
    'TOUBA': 'Mbacke', 'MAKACOULIBANTANG': 'Koumpentoum', 'MBAO': 'Pikine',
    'MADIYANA 2': 'Mbacke', 'MADIYANA': 'Mbacke',
}

NULLISH = {'', 'na', 'n/a', 'none', 'null', 'unknown', 'nan', '.', '-', '—'}


def _blank(v):
    return v is None or str(v).strip().lower() in NULLISH


class Audit:
    """Everything that went wrong, or went right only by alias, while placing samples."""

    def __init__(self):
        self.by_how = {}
        self.unplaced = {}        # raw district name -> {'n', 'suggest', 'reason'}
        self.aliased = {}         # raw name -> resolved unit
        self.region_mismatch = {} # (district, given region) -> {'n', 'expected'}
        self.coords_vs_name = {}  # (raw name, unit from coords) -> {'n'}  both valid, differ
        self.name_unknown_coords_ok = {}  # (raw name, unit from coords) -> {'n'}
        self.country_other = {}   # given country -> n
        self.coords_outside = 0
        self.coords_overrode = 0
        self.n = 0

    def _bump(self, d, k):
        d[k] = d.get(k, 0) + 1

    def record(self, how):
        self.n += 1
        self._bump(self.by_how, how)

    def problems(self):
        return (len(self.unplaced) or self.coords_outside or len(self.region_mismatch)
                or len(self.country_other) or len(self.coords_vs_name)
                or len(self.name_unknown_coords_ok))

    def lines(self):
        """Human-readable audit, one finding per line."""
        out = []
        if self.by_how:
            how = ', '.join(f'{k}={v}' for k, v in sorted(self.by_how.items()))
            out.append(f'placed {self.n} samples by: {how}')
        if self.coords_overrode:
            out.append(f'{self.coords_overrode} samples had both coordinates and a district '
                       f'name; coordinates took precedence')
        for raw, info in sorted(self.unplaced.items(), key=lambda kv: -kv[1]['n']):
            sug = f" - did you mean {' / '.join(info['suggest'])}?" if info['suggest'] else ''
            shown = raw if raw else '(blank)'
            out.append(f"UNPLACED {info['n']:4d} sample(s): district {shown!r} "
                       f"{info['reason']}{sug}")
        if self.coords_outside:
            out.append(f'UNPLACED {self.coords_outside} sample(s): coordinates fall outside '
                       f'{G.COUNTRY_ISO}; check lat/lon order and sign')
        for (raw, unit), info in sorted(self.coords_vs_name.items(), key=lambda kv: -kv[1]['n']):
            out.append(f"MISMATCH {info['n']:4d} sample(s): data says district {raw!r} but "
                       f"the coordinates fall in {unit!r}; coordinates were used")
        for (raw, unit), info in sorted(self.name_unknown_coords_ok.items(),
                                        key=lambda kv: -kv[1]['n']):
            out.append(f"MISMATCH {info['n']:4d} sample(s): district {raw!r} is not a unit in "
                       f"this boundary file; coordinates placed them in {unit!r}")
        for (dist, given), info in sorted(self.region_mismatch.items()):
            out.append(f"MISMATCH {info['n']:4d} sample(s): district {dist!r} is in region "
                       f"{info['expected']!r} per the boundary file, but the data says "
                       f"{given!r}")
        for c, n in sorted(self.country_other.items()):
            out.append(f'MISMATCH {n} sample(s): country {c!r} is not the report country '
                       f'({G.COUNTRY_NAME or G.COUNTRY_ISO})')
        for raw, unit in sorted(self.aliased.items()):
            out.append(f'alias: health district {raw!r} -> admin-2 unit {unit!r}')
        return out

    def rows(self):
        """Machine-readable audit, for the TSV a pipeline can act on."""
        rows = [('finding', 'value', 'n_samples', 'detail')]
        for how, n in sorted(self.by_how.items()):
            rows.append(('placed', how, n, ''))
        for raw, info in sorted(self.unplaced.items()):
            rows.append(('unplaced_district', raw, info['n'],
                         info['reason'] + (f"; suggest {', '.join(info['suggest'])}"
                                           if info['suggest'] else '')))
        if self.coords_outside:
            rows.append(('unplaced_coords_outside_country', G.COUNTRY_ISO,
                         self.coords_outside, 'check lat/lon order and sign'))
        for (raw, unit), info in sorted(self.coords_vs_name.items()):
            rows.append(('coords_disagree_with_district', f'{raw} / {unit}', info['n'],
                         'coordinates used'))
        for (raw, unit), info in sorted(self.name_unknown_coords_ok.items()):
            rows.append(('district_not_in_boundary_file', f'{raw} / {unit}', info['n'],
                         'coordinates used'))
        for (dist, given), info in sorted(self.region_mismatch.items()):
            rows.append(('region_mismatch', f'{dist} / {given}', info['n'],
                         f"boundary file says {info['expected']}"))
        for c, n in sorted(self.country_other.items()):
            rows.append(('country_not_report_country', c, n, ''))
        for raw, unit in sorted(self.aliased.items()):
            rows.append(('health_district_alias', raw, 0, f'resolved to {unit}'))
        return rows

    def meta(self):
        """Compact form carried in the report so a reader sees the data-quality picture."""
        return {
            'placed_by': dict(self.by_how),
            'n_placed': self.n,
            'coords_overrode_name': self.coords_overrode,
            'unplaced': [{'name': k or '(blank)', 'n': v['n'], 'suggest': v['suggest'],
                          'reason': v['reason']}
                         for k, v in sorted(self.unplaced.items(), key=lambda kv: -kv[1]['n'])],
            'coords_outside_country': self.coords_outside,
            'coords_vs_name': [{'given': r, 'from_coords': u, 'n': i['n']}
                               for (r, u), i in sorted(self.coords_vs_name.items(),
                                                       key=lambda kv: -kv[1]['n'])],
            'district_not_in_boundaries': [{'given': r, 'from_coords': u, 'n': i['n']}
                                           for (r, u), i in sorted(
                                               self.name_unknown_coords_ok.items(),
                                               key=lambda kv: -kv[1]['n'])],
            'region_mismatch': [{'district': d, 'given': g, 'expected': i['expected'],
                                 'n': i['n']}
                                for (d, g), i in sorted(self.region_mismatch.items())],
            'other_country': dict(self.country_other),
            'aliases_used': dict(self.aliased),
        }


class Resolver:
    """Resolve location for one country's boundary set, accumulating an Audit."""

    def __init__(self, audit=None):
        self.audit = audit or Audit()
        self._by_na = {G._na(d['name']): d['name'] for d in G.DEPTS}
        self._exact = {d['name']: d['name'] for d in G.DEPTS}
        self._names = [d['name'] for d in G.DEPTS]

    def _suggest(self, raw):
        if _blank(raw):
            return []
        # match on the normalised forms so case, accents and punctuation do not hide a
        # near miss, but report the real unit names
        norm = {G._na(n): n for n in self._names}
        hits = difflib.get_close_matches(G._na(raw), list(norm), n=3, cutoff=0.72)
        return [norm[h] for h in hits]

    def resolve(self, district=None, lat=None, lon=None, region=None, country=None):
        """-> (admin-2 unit name or None, how). Records findings in self.audit."""
        a = self.audit
        have_name = not _blank(district)

        if not _blank(country) and G.COUNTRY_NAME \
                and G._na(str(country)) != G._na(G.COUNTRY_NAME):
            a._bump(a.country_other, str(country).strip())

        # 1. explicit coordinates win
        if lat is not None and lon is not None:
            unit = G.dept_of_point(lat, lon)
            if unit:
                if have_name:
                    a.coords_overrode += 1
                    # Coordinates win, but a name that points somewhere else is the single
                    # most useful warning available: it catches both a misspelling and a
                    # boundary file whose units are not the division the data means.
                    raw = str(district).strip()
                    named = self._exact.get(raw) or self._by_na.get(G._na(raw))
                    if named and named != unit:
                        key = (raw, unit)
                        info = a.coords_vs_name.setdefault(key, {'n': 0})
                        info['n'] += 1
                    elif not named:
                        key = (raw, unit)
                        info = a.name_unknown_coords_ok.setdefault(key, {'n': 0})
                        info['n'] += 1
                a.record('coordinates')
                self._check_region(unit, region)
                return unit, 'coordinates'
            a.coords_outside += 1
            return None, None

        # 2. district name
        if have_name:
            raw = str(district).strip()
            unit = self._exact.get(raw) or self._by_na.get(G._na(raw))
            how = 'district_name'
            if not unit:
                mapped = HEALTH2DEPT.get(raw.upper())
                if mapped:
                    unit = self._exact.get(mapped) or self._by_na.get(G._na(mapped))
                    if unit:
                        a.aliased[raw] = unit
                        how = 'health_district_alias'
            if unit:
                a.record(how)
                self._check_region(unit, region)
                return unit, how
            info = a.unplaced.setdefault(raw, {'n': 0, 'suggest': self._suggest(raw),
                                               'reason': 'not an admin-2 unit name'})
            info['n'] += 1
            return None, None

        # 3. nothing usable. Say which of the two accepted forms was missing.
        reason = ('no district and no coordinates' if lat is None and lon is None
                  else 'only one of lat/lon given')
        info = a.unplaced.setdefault('', {'n': 0, 'suggest': [], 'reason': reason})
        info['n'] += 1
        info['reason'] = reason
        return None, None

    def _check_region(self, unit, given):
        """An explicit admin-1 that disagrees with the boundary file is worth saying."""
        if _blank(given):
            return
        expected = (G.SEN_REGION.get(unit) if G.COUNTRY_ISO == 'SEN' else None) \
            or G.region_of(unit)
        if not expected:
            return
        if G._na(str(given)) != G._na(expected):
            key = (unit, str(given).strip())
            info = self.audit.region_mismatch.setdefault(key, {'n': 0, 'expected': expected})
            info['n'] += 1

    def report(self, stream=sys.stderr, tag='geoloc'):
        for line in self.audit.lines():
            stream.write(f'[{tag}] {line}\n')


def write_audit_tsv(audit, path):
    with open(path, 'w', encoding='utf-8') as fh:
        for row in audit.rows():
            fh.write('\t'.join(str(c) for c in row) + '\n')
    return path


def demo():
    """Self-check against the committed Senegal boundary set."""
    G.set_country('SEN', 'Senegal')
    r = Resolver()

    # exact name, and a health district that only resolves through the alias table
    assert r.resolve(district='Bakel')[0] == 'Bakel'
    assert r.resolve(district='Diouloulou')[0] == 'Bignona'
    assert r.audit.aliased['Diouloulou'] == 'Bignona'

    # coordinates win over a name, even a name that would have resolved elsewhere
    d0 = G.MAP['depts'][0]
    unit, how = r.resolve(district='Bakel', lat=d0['lat'], lon=d0['lon'])
    assert how == 'coordinates' and unit == d0['name'], (unit, how)
    assert r.audit.coords_overrode == 1

    # a misspelling is unplaced AND gets a suggestion
    unit, _ = r.resolve(district='Bakeel')
    assert unit is None
    assert 'Bakel' in r.audit.unplaced['Bakeel']['suggest'], r.audit.unplaced['Bakeel']

    # coordinates in the ocean are unplaced, not silently snapped to a unit
    assert r.resolve(lat=0.0, lon=0.0)[0] is None
    assert r.audit.coords_outside == 1

    # admin-0/admin-1 alone cannot place anything
    assert r.resolve(country='Senegal', region='Kolda')[0] is None

    # a region that disagrees with the boundary file is flagged, not corrected
    r.resolve(district='Bakel', region='Nowhere Region')
    assert any(k[0] == 'Bakel' for k in r.audit.region_mismatch), r.audit.region_mismatch

    assert r.audit.problems()
    assert any('UNPLACED' in l for l in r.audit.lines())
    assert any('MISMATCH' in l for l in r.audit.lines())
    print('geoloc demo OK')
    print('  sample audit lines:')
    for l in r.audit.lines():
        print('   ', l)


if __name__ == '__main__':
    demo()
