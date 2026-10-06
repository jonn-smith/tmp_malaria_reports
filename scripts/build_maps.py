#!/usr/bin/env python3
"""Project admin-2 boundaries (geoBoundaries gbOpen) -> compact SVG paths + centroids.

Equirectangular projection with cos(lat) correction, fit to a fixed width. The output is
the only geometry artefact the report needs: it drives the choropleth and, because the
projection is invertible, also the lat/long -> district assignment the loaders perform
(gen_reports.dept_of_point), so no geojson is read at report time.

Output per country: reference/adm2/<ISO3>_adm2_map.json.gz
  {iso, country, viewBox, W, H, pad, lonMin, lonMax, latMin, latMax,
   depts: [{name, path, cx, cy, lat, lon}]}

Usage:
  build_maps.py                                       # Senegal, from reference/sen_adm2.geojson
  build_maps.py --geojson FILE --iso SEN [--name Senegal]
  build_maps.py --dir DIR [--only SEN,NGA,KEN]        # batch; files named <ISO3>_*.geojson
"""
import argparse, glob, gzip, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.environ.get('MALARIA_REPORTS_REF_DIR') or os.path.join(ROOT, 'reference')
ADM2_DIR = os.path.join(REF, 'adm2')

W = 660
PAD = 10


def project(feats, iso=None, country=None):
    xs, ys = [], []

    def walk(c, f):
        if isinstance(c[0], (int, float)): f(c)
        else:
            for p in c: walk(p, f)
    for ft in feats:
        walk(ft['geometry']['coordinates'], lambda p: (xs.append(p[0]), ys.append(p[1])))
    lonMin, lonMax = min(xs), max(xs)
    latMin, latMax = min(ys), max(ys)
    cosLat = math.cos(math.radians((latMin + latMax) / 2))

    scale = (W - 2 * PAD) / ((lonMax - lonMin) * cosLat)
    H = round((latMax - latMin) * scale + 2 * PAD)

    def X(lon): return round((lon - lonMin) * cosLat * scale + PAD, 1)
    def Y(lat): return round((latMax - lat) * scale + PAD, 1)

    def ring_path(ring):
        pts = []
        last = None
        for lon, lat in ring:
            x, y = X(lon), Y(lat)
            if (x, y) != last:            # dedup after rounding
                pts.append((x, y)); last = (x, y)
        if len(pts) < 3: return None
        return 'M' + ' L'.join(f'{x},{y}' for x, y in pts) + 'Z'

    def poly_paths(coords, geomtype):
        polys = coords if geomtype == 'MultiPolygon' else [coords]
        out = []
        for poly in polys:
            for ring in poly:          # ring[0]=exterior, rest=holes (kept, drawn same)
                d = ring_path(ring)
                if d: out.append(d)
        return out

    def centroid(coords, geomtype):
        # area-weighted centroid of the largest exterior ring (lon/lat)
        polys = coords if geomtype == 'MultiPolygon' else [coords]
        best = None; bestA = -1
        for poly in polys:
            ring = poly[0]
            A = cx = cy = 0.0
            for i in range(len(ring) - 1):
                x0, y0 = ring[i]; x1, y1 = ring[i + 1]
                cr = x0 * y1 - x1 * y0
                A += cr; cx += (x0 + x1) * cr; cy += (y0 + y1) * cr
            if abs(A) < 1e-9: continue
            A *= 0.5; cx /= (6 * A); cy /= (6 * A)
            if abs(A) > bestA: bestA = abs(A); best = (cx, cy)
        return best

    depts = []
    for ft in feats:
        gt = ft['geometry']['type']
        co = ft['geometry']['coordinates']
        paths = poly_paths(co, gt)
        c = centroid(co, gt)
        if not paths or not c: continue
        props = ft.get('properties') or {}
        depts.append({'name': props.get('shapeName') or props.get('shapeID') or '',
                      'path': ' '.join(paths),
                      'cx': round(X(c[0]), 1), 'cy': round(Y(c[1]), 1),
                      'lat': round(c[1], 3), 'lon': round(c[0], 3)})

    out = {'viewBox': f'0 0 {W} {H}', 'W': W, 'H': H, 'pad': PAD,
           'lonMin': lonMin, 'lonMax': lonMax, 'latMin': latMin, 'latMax': latMax,
           'depts': depts}
    if iso: out['iso'] = iso
    if country: out['country'] = country
    return out


def check(out, iso):
    assert out['depts'], f'{iso}: no admin-2 units projected'
    for d in out['depts']:
        assert d['path'].startswith('M') and d['path'].endswith('Z'), f"{iso}: bad path for {d['name']!r}"
        assert -1 <= d['cx'] <= out['W'] + 1 and -1 <= d['cy'] <= out['H'] + 1, \
            f"{iso}: centroid outside viewBox for {d['name']!r}"


def write_map(out, iso, outdir=ADM2_DIR, gz=True):
    os.makedirs(outdir, exist_ok=True)
    blob = json.dumps(out, separators=(',', ':'))
    path = os.path.join(outdir, f'{iso}_adm2_map.json' + ('.gz' if gz else ''))
    if gz:
        # mtime=0 so rebuilds are byte-identical
        with gzip.GzipFile(path, 'wb', compresslevel=9, mtime=0) as fh:
            fh.write(blob.encode())
    else:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(blob)
    return path, len(blob)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Project admin-2 boundaries to SVG paths.')
    ap.add_argument('--geojson', help='single boundary file to project')
    ap.add_argument('--iso', help='ISO3 code for --geojson')
    ap.add_argument('--name', help='country name for --geojson')
    ap.add_argument('--dir', help='directory of <ISO3>_*.geojson files to project')
    ap.add_argument('--only', help='comma-separated ISO3 list to restrict --dir')
    ap.add_argument('--out-dir', default=ADM2_DIR)
    ap.add_argument('--no-gz', action='store_true')
    a = ap.parse_args(argv)

    jobs = []
    if a.dir:
        only = {t.strip().upper() for t in a.only.split(',')} if a.only else None
        for p in sorted(glob.glob(os.path.join(a.dir, '*.geojson'))):
            iso = re.split(r'[_.]', os.path.basename(p))[0].upper()
            if only and iso not in only: continue
            jobs.append((p, iso, None))
    elif a.geojson:
        jobs.append((a.geojson, (a.iso or 'XXX').upper(), a.name))
    else:
        jobs.append((os.path.join(REF, 'sen_adm2.geojson'), 'SEN', 'Senegal'))

    total = 0
    for path, iso, name in jobs:
        feats = json.load(open(path))['features']
        out = project(feats, iso, name)
        check(out, iso)
        dest, raw = write_map(out, iso, a.out_dir, gz=not a.no_gz)
        total += os.path.getsize(dest)
        if len(jobs) <= 12:
            print(f'{iso}: {len(out["depts"]):5d} units  viewBox {out["viewBox"]:14s} '
                  f'{raw/1024:8.1f} KB json -> {os.path.getsize(dest)/1024:7.1f} KB '
                  f'{os.path.basename(dest)}')
    if len(jobs) > 1:
        print(f'{len(jobs)} countries projected, {total/1024/1024:.1f} MB on disk in {a.out_dir}')

    # keep the legacy Senegal artefact in step: it is committed and loaded by default
    sen_jobs = [j for j in jobs if j[1] == 'SEN']
    if sen_jobs:
        out = project(json.load(open(sen_jobs[0][0]))['features'])
        legacy = {k: out[k] for k in ('viewBox', 'W', 'H', 'lonMin', 'lonMax', 'latMin', 'latMax', 'depts')}
        p = os.path.join(REF, 'sen_admin2_map.json')
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(legacy, fh, separators=(',', ':'))
        print(f'refreshed reference/sen_admin2_map.json ({os.path.getsize(p)/1024:.1f} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
