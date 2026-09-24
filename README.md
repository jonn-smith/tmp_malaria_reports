# Senegal Malaria Molecular Surveillance — report mock-ups & pipeline

Self-contained, single-file HTML surveillance reports for *Plasmodium falciparum*
molecular surveillance in Senegal, plus the pipeline that builds them. Audience:
Africa CDC, the Gates Foundation, and national malaria control programmes.

Each report is one standalone `.html` file (inline SVG charts, no external assets)
covering three surveillance domains:

- **Resistance markers** — WHO-tracked drug-resistance amino-acid changes (k13, crt,
  mdr1, dhfr, dhps, cytb, …) with prevalence + 95% Wilson CIs, per admin-2 choropleth,
  and a WHO action-threshold flag (≥10%). Research (non-WHO) markers are labelled.
- **Diagnostics** — *pfhrp2 / pfhrp3* deletions (shown greyed / **unvalidated**; a
  research / lab-confirmation priority, never decision-grade here).
- **Transmission & diversity** — complexity of infection (COI), polygenomic /
  monogenomic fractions, and (WGS) relatedness. The COI **method is stated per report**
  and is a naive estimator (not moire / THE REAL McCOIL).

A **Summary** stoplight, an **Export** tab (dashboard-ready views), and a **Methods**
tab (statistics, thresholds, pipeline links, COI method) round out each report.

## Two kinds of report

| Kind | Files | Data |
|---|---|---|
| **Synthetic mock-ups** (in this repo) | `senegal_malaria_surveillance_{WGS,MAD4HATTER,NOMADS,COMBINED}_v0.7.html` | Illustrative, fabricated values (MOCK-UP banner). Real WHO thresholds / marker lists. |
| **Real-data reports** (not committed) | `…_{WGS,MAD4HATTER}_v0.7-real.html` | Real Senegal data. **Excluded from this repo** — they embed real per-sample genotypes/coordinates; regenerate locally (below). |

## Build

Synthetic mock-ups (no external data needed):

```bash
./build_reports.sh v0.7      # writes senegal_malaria_surveillance_<ASSAY>_v0.7.html
```

Real-data reports (require private Terra inputs, not in this repo):

```bash
# WGS: export of the sr-malaria `sample` table (per-sample genotype columns)
python3 load_wgs.py sample.tsv data_wgs.json
# MAD4HATTER: UCSF mad4hatter outputs (resmarker_table.txt + allele_data.txt per run) + site metadata
python3 load_mad.py <resmarker_dir> <site_metadata.csv> <allele_dir> -o data_mad4hatter.json
# then inject the JSON into report_v05.template.html (see build_reports.sh for the inject step)
```

Both paths funnel a per-sample intermediate through `gen_reports.assemble_report`
(aggregation, Wilson CIs, stoplight, exports, site/admin-2 maps).

## Layout

```
gen_reports.py            data model + assembler + synthetic generator + export packer
load_wgs.py               WGS sample-table  -> per-admin-2 units (real data)
load_mad.py               MAD4HATTER UCSF outputs -> per-admin-2 units (real data)
report_v05.template.html  shared, capability-gated renderers (the report UI)
build_reports.sh          build driver (writes the 4 synthetic reports)
build_maps.py             geoBoundaries SEN ADM2 geojson -> projected SVG paths
sen_adm2*.json/.geojson   admin-2 boundaries + projection
pha4ge_fields.json        PHA4GE Malaria Community Standard field order
mad_resmarker.tsv         resmarker codon -> genomic ranges
who_*, m4h_*.tsv          WHO marker compendium + MAD4HATTER v4 panel references
DATA_IMPORT_PLAN.md       how real data maps into the reports (sources, computations)
JOURNAL.md                development log for the reporting work
```

## Export views

The Export tab offers five dashboard-ready formats. Full tables are embedded
**gzip + base64** and decompressed / rebuilt into CSV client-side on download (with a
progress popup), so the page stays small; the on-screen table shows a preview.

- **WHO Threat Maps** — per admin-2 × marker (tested / present / percent).
- **Africa CDC** — Mutation / Haplotype data sheet (one row per sample × observed alteration).
- **AF-CDC Marker-Centric** — per sample × codon with wildtype/mutation counts (carries the denominator).
- **PHA4GE** — Malaria Community Standard (human sample), 210-field per-specimen schema.
- **DHIS2** — `dataValueSet` import schema.

## Data sources & standards

- MAD4HATTER pipeline: <https://github.com/EPPIcenter/mad4hatter> · docs <https://eppicenter.github.io/mad4hatter/> · CNV/deletions <https://github.com/EPPIcenter/copy-number-variation>
- NOMADS: <https://github.com/nomads-community>
- WHO Compendium of molecular markers for antimalarial drug resistance
- Admin-2 boundaries: geoBoundaries (SEN ADM2)
- PHA4GE Malaria Community Standard; Africa CDC molecular-marker data sheet

## Caveats

- Synthetic reports carry **fabricated** prevalence values (layout review only); real
  reports carry real markers but **naive COI**, and MAD4HATTER **HRP2/3 = not assessed**
  (deletion calling needs a coverage-dropout analysis not in the source outputs).
- *pfhrp2/3* figures are predicted from genetic markers and are **unvalidated**.
- Validation is via jsdom + a static SVG-geometry check (no browser in the build env).

Versioning: the version is always in the filename; current = **v0.7**.
