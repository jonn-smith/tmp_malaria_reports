#!/usr/bin/env bash
# Build the Senegal malaria surveillance mock-ups. Run from this directory.
#   ./build_reports.sh [VERSION]   (default v0.7)
# Chain:  build_maps.py (geojson->map json) -> gen_reports.py (->data_*.json) -> inject into template.
set -euo pipefail
cd "$(dirname "$0")"
VER="${1:-v0.7}"
python3 gen_reports.py "$VER"      # sen_admin2_map.json -> data_*.json (version stamped from $VER)
python3 - "$VER" <<'PY'
import sys
ver=sys.argv[1]; tpl=open('report_v05.template.html').read()
for assay,dj in [('WGS','data_wgs.json'),('MAD4HATTER','data_mad4hatter.json'),
                 ('NOMADS','data_nomads.json'),('COMBINED','data_combined.json')]:
    h=tpl.replace('/*DATA_HERE*/','const DATA = '+open(dj).read()+';').replace('__ASSAY__',assay).replace('__VERSION__',ver)
    open(f'senegal_malaria_surveillance_{assay}_{ver}.html','w').write(h)
    print('wrote',f'senegal_malaria_surveillance_{assay}_{ver}.html')
PY
