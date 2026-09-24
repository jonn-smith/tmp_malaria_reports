# Replicating the real-data reports

How to regenerate `senegal_malaria_surveillance_{WGS,MAD4HATTER}_v0.7-real.html` in a fresh
checkout. These outputs embed real per-sample data, so they are **not** committed.

## 1. Environment
- **python3** — standard library only (json, csv, re, gzip, base64, math, os, glob). No pip installs.
- **bash** (for `build_real_reports.sh`).
- Optional (validation only): **node** + `jsdom`.

## 2. Repo files used at runtime (already committed)
`gen_reports.py`, `load_wgs.py`, `load_mad.py`, `build_real_reports.sh`,
`report_v05.template.html`, and the reference inputs `sen_admin2_map.json`,
`sen_adm2.geojson`, `pha4ge_fields.json`, `mad_resmarker.tsv`. (Nothing else is required to
build; `who_*`, `m4h_*.tsv`, `wgs_loc.csv`, `mad_site_to_admin2.json` are legacy/reference and
not read by the current loaders.)

## 3. Private inputs to fetch (NOT in the repo)

### WGS — one file
`sample.tsv` = a TSV export of the **`sample` data table** in Terra workspace
`broad-firecloud-dsde-methods/sr-malaria` (Data tab → download the `sample` table, or via FISS/terra CLI).
The loader reads these columns (others ignored):
`entity:sample_id, District, Region, Site, Latitude, Longitude, Year, date_of_collection,
qc_status` (falls back to `qc_status_original`), `barcode, hrp2, hrp3`, and the per-amino-acid
genotype columns named `pf<gene>_<Aaa>_<pos>_<Aaa>` (e.g. `pfcrt_Lys_76_Thr`) whose values are
`hom_ref | hom_var | het | missing`.

### MAD4HATTER — three inputs (from the UCSF mad4hatter outputs)
Bucket: `gs://fc-dab15d04-6d9f-4b07-9b00-045a60cdb4bf/cigass_mad4hatter/ucsf_outputs/`

```bash
# resmarker tables (markers) — one per run, into rm/
mkdir rm ad
for d in out_run1 out_run1_new out_run1Repeat out_run1Repeat_new out_run2_new out_run3 \
         out_run3_new out_run4 out_run5 out_run6 out_run7 out_run8 incomplete_out_run8 \
         out_run10 out_runCntRep; do
  gsutil cp "gs://fc-dab15d04-6d9f-4b07-9b00-045a60cdb4bf/cigass_mad4hatter/ucsf_outputs/$d/resistance_marker_module/resmarker_table.txt" "rm/${d}.txt"
  gsutil cp "gs://fc-dab15d04-6d9f-4b07-9b00-045a60cdb4bf/cigass_mad4hatter/ucsf_outputs/$d/allele_data.txt"                         "ad/${d}.txt"   # COI
done
# site metadata (Sample_id, Country=site, Latitude, Longitude)
gsutil cp "gs://fc-dab15d04-6d9f-4b07-9b00-045a60cdb4bf/All_2023_runs_metadata1.csv" .
```
`resmarker_table.txt` columns used: `SampleID, Gene, CodonID, AA, AARefAlt` (2 schema variants
handled; `Locus` optional). `allele_data.txt` columns used: `SampleID, Locus, Allele` (COI).
Sample IDs carry an Illumina `_S##_L001` suffix that the loader strips.

## 4. Build

```bash
./build_real_reports.sh <sample.tsv> rm All_2023_runs_metadata1.csv ad
#   arg1 = WGS sample.tsv      (pass "" to skip WGS)
#   arg2 = MAD resmarker dir   (pass "" to skip MAD)
#   arg3 = MAD site metadata csv
#   arg4 = MAD allele dir      ("" = skip COI; markers still built)
# -> senegal_malaria_surveillance_WGS_v0.7-real.html
# -> senegal_malaria_surveillance_MAD4HATTER_v0.7-real.html
```

Under the hood: `load_wgs.py` / `load_mad.py` build a per-sample intermediate, aggregate to
admin-2 (WGS: `District` + a health-district→dept crosswalk; MAD: point-in-polygon of site
lat/long on `sen_adm2.geojson`) and to site points, run `gen_reports.assemble_report`
(prevalence + Wilson CIs, stoplight, five export views embedded gzip+base64), then inject the
JSON into `report_v05.template.html`.

## 5. What each assay yields (sanity check)
- **WGS**: ~2,161 QC-pass samples, 16 admin-2, 28 sites, 2005–2023; 12 markers; real hrp2/hrp3;
  COI from the 24-SNP barcode.
- **MAD4HATTER**: ~880 QC-pass samples (runs 1–10), 9 admin-2, 13 sites, 2020/2023; 12 markers;
  naive COI from microhaplotype allele counts; hrp2/3 = "not assessed".

## Notes / caveats carried in the reports
- COI is a **naive** estimator (barcode heterozygosity for WGS; max distinct microhaplotype
  alleles per locus for MAD) — not a model-based eCOI (moire / THE REAL McCOIL).
- `pfhrp2/3` figures are predicted, **unvalidated**; MAD hrp2/3 is "not assessed" (needs a
  coverage-dropout analysis, e.g. EPPIcenter/copy-number-variation, not in these outputs).
- `dhps A437G` in the WGS `sample` table reads 0% due to a reference-polarity quirk in that
  column (the MAD resmarker path calls it correctly, ~87%).
