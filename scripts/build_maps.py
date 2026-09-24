#!/usr/bin/env python3
"""Project Senegal ADM2 (45 departments) geojson -> compact SVG paths + centroids.
Equirectangular projection with cos(lat) correction, fit to a fixed width.
Output: sen_admin2_map.json = {viewBox, W, H, depts:[{name, path, cx, cy, lat, lon}]}
"""
import json, math, os
REF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reference')

g = json.load(open(os.path.join(REF, 'sen_adm2.geojson')))
feats = g['features']

# bbox
xs, ys = [], []
def walk(c, f):
    if isinstance(c[0], (int, float)): f(c)
    else:
        for p in c: walk(p, f)
for ft in feats:
    walk(ft['geometry']['coordinates'], lambda p: (xs.append(p[0]), ys.append(p[1])))
lonMin, lonMax = min(xs), max(xs)
latMin, latMax = min(ys), max(ys)
cosLat = math.cos(math.radians((latMin+latMax)/2))

W = 660; pad = 10
scale = (W - 2*pad) / ((lonMax - lonMin) * cosLat)
H = round((latMax - latMin) * scale + 2*pad)
def X(lon): return round((lon - lonMin) * cosLat * scale + pad, 1)
def Y(lat): return round((latMax - lat) * scale + pad, 1)

def ring_path(ring):
    pts = []
    last = None
    for lon, lat in ring:
        x, y = X(lon), Y(lat)
        if (x, y) != last:            # dedup after rounding
            pts.append((x, y)); last = (x, y)
    if len(pts) < 3: return None
    d = 'M' + ' L'.join(f'{x},{y}' for x, y in pts) + 'Z'
    return d

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
        for i in range(len(ring)-1):
            x0, y0 = ring[i]; x1, y1 = ring[i+1]
            cr = x0*y1 - x1*y0
            A += cr; cx += (x0+x1)*cr; cy += (y0+y1)*cr
        if abs(A) < 1e-9: continue
        A *= 0.5; cx /= (6*A); cy /= (6*A)
        if abs(A) > bestA: bestA = abs(A); best = (cx, cy)
    return best

depts = []
for ft in feats:
    name = ft['properties'].get('shapeName')
    gt = ft['geometry']['type']
    co = ft['geometry']['coordinates']
    paths = poly_paths(co, gt)
    c = centroid(co, gt)
    depts.append({'name': name, 'path': ' '.join(paths),
                  'cx': round(X(c[0]),1), 'cy': round(Y(c[1]),1),
                  'lat': round(c[1],3), 'lon': round(c[0],3)})

out = {'viewBox': f'0 0 {W} {H}', 'W': W, 'H': H,
       'lonMin': lonMin, 'lonMax': lonMax, 'latMin': latMin, 'latMax': latMax,
       'depts': depts}
json.dump(out, open(os.path.join(REF, 'sen_admin2_map.json'), 'w'), separators=(',', ':'))

# --- checks ---
assert len(depts) == 45, len(depts)
for d in depts:
    assert d['path'].startswith('M') and d['path'].endswith('Z'), d['name']
    assert 0 <= d['cx'] <= W and 0 <= d['cy'] <= H, (d['name'], d['cx'], d['cy'])
print('OK depts:', len(depts), 'viewBox:', out['viewBox'],
      'json KB:', round(os.path.getsize(os.path.join(REF, 'sen_admin2_map.json'))/1024,1))
print('sample:', depts[0]['name'], 'cx,cy=', depts[0]['cx'], depts[0]['cy'],
      'pathlen=', len(depts[0]['path']))
print('lat range of centroids:', round(min(d['lat'] for d in depts),2),
      round(max(d['lat'] for d in depts),2))
