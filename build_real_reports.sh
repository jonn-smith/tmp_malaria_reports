#!/usr/bin/env bash
# Build the REAL-data reports from the private Terra inputs (which are NOT in this repo).
# Outputs (reports/senegal_malaria_surveillance_*_v0.12-real.html) embed real per-sample data
# and are .gitignored — do not commit them without data-sharing clearance.
#
# Usage (skip an assay by passing "" for its inputs):
#   WGS only:  ./build_real_reports.sh <sample.tsv> "" "" ""
#   MAD only:  ./build_real_reports.sh "" <resmarker_dir> <site_metadata.csv> <allele_dir>
#   Both:      ./build_real_reports.sh <sample.tsv> <resmarker_dir> <site_metadata.csv> <allele_dir>
#
#   sample.tsv        = Terra export of the sr-malaria `sample` table (per-sample genotype columns)
#   resmarker_dir     = dir of UCSF mad4hatter resmarker_table.txt files (one per run)
#   site_metadata.csv = Sample_id,Country(=site),Latitude,Longitude
#   allele_dir        = dir of UCSF mad4hatter allele_data.txt files (COI); "" to skip COI
set -euo pipefail
cd "$(dirname "$0")"
VER=v0.12-real   # FILENAME suffix only: .gitignore keys on "*-real.html" to keep real-data
                 # reports out of the repo. The version shown inside the report is v0.12.
REPORT_VER=v0.12
mkdir -p build reports

WGS_TSV="${1:-}"; RM_DIR="${2:-}"; SITE_META="${3:-}"; ALLELE_DIR="${4:-}"

inject () {  # <assay> <data.json> <outfile>
  python3 - "$1" "$2" "$3" "$REPORT_VER" <<'PY'
import sys
assay, dj, out, ver = sys.argv[1:5]
tpl = open('templates/report_v05.template.html').read()
html = (tpl.replace('/*DATA_HERE*/', 'const DATA = ' + open(dj).read() + ';')
           .replace('__ASSAY__', assay).replace('__VERSION__', ver))
open(out, 'w').write(html); print('wrote', out)
PY
}

if [[ -n "$WGS_TSV" ]]; then
  python3 scripts/load_wgs.py "$WGS_TSV" build/data_wgs_real.json
  inject WGS build/data_wgs_real.json "reports/senegal_malaria_surveillance_WGS_${VER}.html"
fi

if [[ -n "$RM_DIR" && -n "$SITE_META" ]]; then
  python3 scripts/load_mad.py "$RM_DIR" "$SITE_META" "$ALLELE_DIR" -o build/data_mad4hatter_real.json
  inject MAD4HATTER build/data_mad4hatter_real.json "reports/senegal_malaria_surveillance_MAD4HATTER_${VER}.html"
fi
