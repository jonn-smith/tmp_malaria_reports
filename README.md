# Senegal Malaria Molecular Surveillance — report mock-ups & pipeline

Self-contained, single-file HTML surveillance reports for *Plasmodium falciparum*
molecular surveillance in Senegal, plus the pipeline that builds them. Audience:
Africa CDC, the Gates Foundation, and national malaria control programmes.

Each report is one standalone `.html` file (inline SVG charts, no external assets)
focused on **resistance markers** — drug-resistance amino-acid changes
(k13, crt, mdr1, dhfr, dhps, cytb, …) with prevalence + 95% Wilson CIs, per admin-2
choropleth, and a WHO action-threshold flag (≥10%). Marker classes are the WHO
compendium's own — Validated / Candidate / Potential marker, plus Haplotype component
where WHO lists a codon only inside a haplotype — read from the compendium file itself;
loci WHO does not list are labelled "Not in WHO compendium". Every class label links to
the WHO compendium. A **Summary** stoplight, an **Export** tab (dashboard-ready views), and a
**Methods** tab (statistics, thresholds, pipeline links) round out each report. A
**Trends** tab adds prevalence over time: a trend chart with 95% CI bands, a
period-stepper choropleth you can flicker between consecutive periods, samples-per-period
bars, and a per-period table. The Resistance tab gains a period filter; **pooled
(all years) stays the default everywhere**.

> **Scope (since v0.8):** the Diagnostics (*pfhrp2/3* deletions) and Transmission
> (COI / diversity) sections were removed for the first release — resistance markers
> only. They may return in a later version.
>
> **v0.9:** marker catalogue rebuilt from the WHO compendium plus the codons each
> assay actually types — 80 markers, each labelled by evidence class (the class names
> introduced here were superseded by WHO's own in v0.13).
>
> **v0.10:** time dimension — Trends tab (trend chart with CI bands, period-stepper
> choropleth, samples-per-period bars, per-period table) and a period filter on the
> Resistance tab. Periods are built adaptively so each frame has a usable denominator,
> and every frame sums from per-year counts back to the pooled figure.
>
> **v0.13:** marker classes switched to WHO's own terminology, derived from
> `reference/who_combined.json` rather than hand-typed, with every class label linking to
> the WHO compendium. The word "validated" is used only inside WHO's defined class name,
> enforced by a build check.

## Two kinds of report

| Kind | Files | Data |
|---|---|---|
| **Synthetic mock-ups** (in this repo) | `reports/senegal_malaria_surveillance_{WGS,MAD4HATTER,NOMADS,COMBINED}_v0.13.html` | Illustrative, fabricated values (MOCK-UP banner). Real WHO thresholds / marker lists. |
| **Real-data reports** (not committed) | `…_{WGS,MAD4HATTER}_v0.13-real.html` | Real Senegal data. **Excluded from this repo** — they embed real per-sample genotypes/coordinates; regenerate locally (below). |

## Build

Synthetic mock-ups (no external data needed):

```bash
./build_reports.sh v0.13      # writes reports/senegal_malaria_surveillance_<ASSAY>_v0.13.html
```

Real-data reports (require the private Terra inputs, not in this repo — pass `""` to skip an assay):

```bash
# WGS  = Terra export of the sr-malaria `sample` table (per-sample genotype columns)
# MAD  = UCSF mad4hatter outputs: <resmarker_dir> (resmarker_table.txt per run),
#        <site_metadata.csv> (Sample_id,Country=site,Latitude,Longitude), <allele_dir> (allele_data.txt for COI)
./build_real_reports.sh <sample.tsv> <resmarker_dir> <site_metadata.csv> <allele_dir>
# -> reports/senegal_malaria_surveillance_{WGS,MAD4HATTER}_v0.13-real.html  (git-ignored; embed real per-sample data)
```

Under the hood this runs `scripts/load_wgs.py` / `scripts/load_mad.py` and injects the resulting JSON into
`templates/report_v05.template.html`.

Both paths funnel a per-sample intermediate through `gen_reports.assemble_report`
(aggregation, Wilson CIs, stoplight, exports, site/admin-2 maps).

## Layout

```
build_reports.sh          entry point: builds the 4 synthetic mock-ups
build_real_reports.sh     entry point: builds the real-data reports (private inputs)
scripts/
  gen_reports.py          data model + assembler + synthetic generator + export packer
  load_wgs.py             WGS sample-table  -> per-admin-2 units (real data)
  load_mad.py             MAD4HATTER UCSF outputs -> per-admin-2 units (real data)
  build_maps.py           geoBoundaries SEN ADM2 geojson -> projected SVG paths
templates/
  report_v05.template.html  shared, capability-gated renderers (the report UI)
reference/                lookup data consumed by the pipeline
  adm2/<ISO3>_adm2_map.json.gz  projected admin maps, all 54 African countries (4.2 MB)
  sen_adm2*.json/.geojson   Senegal admin-2 boundaries + projection (+ dept metadata)
  who_*                     WHO marker compendium (xlsx + parsed json)
  m4h_*.tsv, mad_resmarker.tsv  MAD4HATTER v4 panel / resmarker references
  mad_site_to_admin2.json   site -> admin-2 lookup (derived, kept for reference)
  wgs_loc.csv               WGS sample-code -> region/district/site lookup
schemas/                  export-format specifications / example sheets
  Africa MMS_Data_Sheet_Final_2026.xlsx   Africa CDC molecular-marker data sheet
  MalariaCommunityStandard_*.xlsx         PHA4GE Malaria Community Standard
  pha4ge_fields.json                      PHA4GE 210-field order (parsed)
reports/                  built HTML reports (synthetic committed; *-real.html ignored)
build/                    intermediates (data_*.json) — git-ignored
docs/
  DATA_IMPORT_PLAN.md     how real data maps into the reports (sources, computations)
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

- Synthetic reports carry **fabricated** prevalence values (layout review only).
- Validation is via jsdom + a static SVG-geometry check (no browser in the build env).

Multi-country: pass `--country-iso3 <ISO3>` to `scripts/make_report.py` (or `country_iso3`
in the WDL) to select the admin-2 boundary set. Projected maps for all 54 African
countries are committed under `reference/adm2/` (the level is whatever the source provides
— admin-2 for most, admin-1 for Mauritius, admin-4 communes for Mayotte — and the report
labels itself accordingly); rebuild or extend them with
`scripts/build_maps.py --dir <geojson dir>`.

Versioning: the version is always in the filename; current = **v0.13**.
