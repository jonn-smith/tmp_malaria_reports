#!/usr/bin/env bash
# Build the Senegal malaria surveillance mock-ups. Run from the repo root.
#   ./build_reports.sh [VERSION]   (default v0.10)
# Chain:  scripts/build_maps.py (geojson->map json) -> scripts/gen_reports.py (->build/data_*.json)
#         -> inject into templates/report_v05.template.html -> reports/*.html
set -euo pipefail
cd "$(dirname "$0")"
VER="${1:-v0.10}"
python3 scripts/gen_reports.py "$VER"   # reference/sen_admin2_map.json -> build/data_*.json (version stamped from $VER)
python3 - "$VER" <<'PY'
import sys
ver=sys.argv[1]; tpl=open('templates/report_v05.template.html').read()
for assay,dj in [('WGS','build/data_wgs.json'),('MAD4HATTER','build/data_mad4hatter.json'),
                 ('NOMADS','build/data_nomads.json'),('COMBINED','build/data_combined.json')]:
    h=tpl.replace('/*DATA_HERE*/','const DATA = '+open(dj).read()+';').replace('__ASSAY__',assay).replace('__VERSION__',ver)
    out=f'reports/senegal_malaria_surveillance_{assay}_{ver}.html'
    open(out,'w').write(h)
    print('wrote',out)
PY
