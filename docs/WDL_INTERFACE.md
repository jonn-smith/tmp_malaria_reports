# WDL interface — malaria molecular-surveillance reports

Handoff contract for running the report generator in Terra. **The inputs below are the
stable surface.** Report rendering is still under active development; the whole point of
this interface is that rendering can keep changing without any of these inputs changing.

Validated 2026-10-05: all three workflows ran end-to-end under `miniwdl` in the pinned
container (WGS 2,161 QC pass samples; MAD4HATTER 883; NOMADS 240 synthetic), plus a
sample-selected WGS run (120 ids -> 102 QC pass samples, 1 admin-2 unit, 2022). `miniwdl
check` is clean (no errors, no shellcheck warnings) on all three.

---

## 1. The three workflows

| Assay | Workflow | Path |
|---|---|---|
| Short-read WGS | `MalariaSurveillanceReportWgs` | `wdl/pipelines/ILMN/Malaria/MalariaSurveillanceReportWgs.wdl` |
| MAD4HATTER amplicon | `MalariaSurveillanceReportMad4hatter` | `wdl/pipelines/ILMN/Malaria/MalariaSurveillanceReportMad4hatter.wdl` |
| NOMADS (ONT amplicon) | `MalariaSurveillanceReportNomads` | `wdl/pipelines/ONT/Malaria/MalariaSurveillanceReportNomads.wdl` |

They are three workflows because their *inputs* differ. They share one task module
(`wdl/tasks/Malaria/SurveillanceReport.wdl`), one container, and one code path: every
task calls `scripts/make_report.py --assay <ASSAY>`, so there is exactly one
implementation of the report model, the statistics and the rendering.

Example inputs JSONs are in `wdl/inputs/`.

---

## 2. Inputs

### Per-assay data inputs (the only inputs that differ between workflows)

| Workflow | Input | Type | Notes |
|---|---|---|---|
| WGS | `sample_table_tsv` | `File` | Terra export of the `sample` table, with the per-amino-acid genotype columns (`pf<gene>_<Aaa>_<pos>_<Aaa>` = `hom_ref`/`hom_var`/`het`/`missing`). Geography from `District`/`Region`/`Site`/`Latitude`/`Longitude`; time from `date_of_collection` or `Year`; QC from `qc_status`. |
| MAD4HATTER | `resmarker_tables` | `Array[File]` | One `resmarker_table.txt` per sequencing run. Both the 11-column and the `Locus`-column variants are handled. |
| MAD4HATTER | `site_metadata` | `File` | Per-sample site + coordinates (`Sample_id`, site, `Latitude`, `Longitude`). Admin-2 is resolved by point-in-polygon. |
| MAD4HATTER | `allele_tables` | `Array[File]` | Optional `allele_data.txt` files. Currently unused by the rendered report (COI was removed in v0.8) but accepted so the interface does not change when it returns. |
| NOMADS | `marker_calls_tables` | `Array[File]` | Assay-agnostic marker-calls table, schema in §5. A **wide Terra sample-table export** (one column per marker) is also accepted and reshaped automatically — see `docs/TERRA_TABLES.md`. |
| NOMADS | `site_metadata` | `File?` | Optional; only needed when the calls tables carry no geography. |

### Country / geography (identical across all three)

| Input | Type | Purpose |
|---|---|---|
| `country_iso3` | `String?` | ISO3 code selecting the admin-2 boundary set. Defaults to `SEN`. |
| `country_name` | `String?` | Country name shown in the report; defaults to the name in the boundary file. |

The image ships projected maps for **all 54 African countries**
(`reference/adm2/<ISO3>_adm2_map.json.gz`, 4.2 MB in total), built by
`scripts/build_maps.py` from geoBoundaries gbOpen for 51 of them and from OCHA COD-AB /
gbOpen ADM4 for the three gbOpen lacks ADM2 for. Other countries can be added with
`build_maps.py --geojson <file> --iso <ISO3>` and supplied through `reference_bundle_tar`
without any WDL change.

**The level is not always admin-2, and the report says which it is.** Each map records the
level of the source file, and the report's headings follow it: Libya is admin-2 (22
*mantika* districts), **Mauritius is admin-1** (12 districts — its first-level units are
the finest national subdivision available), and **Mayotte is admin-4** (17 communes). The
header tagline, the summary scope bar and the locations table all name the actual level, so
an admin-1 map is never labelled admin-2. The export schemas keep their fixed column names
(e.g. Africa CDC's "District (Admin Level 2)") because those belong to the schema.

One artefact serves two purposes: the projected paths draw the choropleth, and because the
projection is invertible the loaders use the same paths to assign each sample's
latitude/longitude to a district. Paths are rounded to 0.1 px (about 100 m for a country
the size of Senegal), so a sample essentially on a district boundary may fall either side.

Geometry details that the conversion handles explicitly:

- **Multipart units are kept whole.** A MultiPolygon becomes one unit with several
  subpaths, never exploded, so unit counts match the source (Libya 22, Mauritius 12,
  Mayotte 17). One consequence: a unit whose parts straddle distant territory stretches the
  map frame — Mauritius spans 10.2° of latitude because the dependencies are included, so
  the main island occupies a small part of the canvas.
- **Holes are respected in both drawing and assignment.** Hole rings are wound opposite to
  their exterior in these sources, so SVG's nonzero fill renders them as holes; and sample
  assignment applies the even-odd rule across all of a unit's rings, so a point inside an
  enclave resolves to the enclave rather than the unit surrounding it. 14 of the 54 maps
  contain holes, and this matters most in Zimbabwe, where it changes the answer for 17 of
  91 units (the "… Urban" districts sit inside their rural namesakes).
- **Unit names are made unique at build time.** The report aggregates and joins on the
  name, so duplicates would silently merge distinct units; 10 of 54 countries had
  collisions (Egypt 34, Namibia 7 units all called "Luderitz"). Colliding names get a
  region or ordinal suffix and the original is kept as `name_raw`. `pcode` is deliberately
  **not** used as a key: it is an official P-code in some sources and an unstable
  geoBoundaries hash in others.
- Sub-pixel parts are dropped: one ~900 m² islet of Mayotte's Bandrele commune collapses
  below the 0.1 px path resolution, leaving 12 of its 13 parts drawn.

Region (admin-1) names are only available for Senegal, from a curated lookup; gbOpen ADM2
features carry no parent name, so for other countries the region fields in the exports are
blank until an ADM1 lookup is added.

### Sample selection (identical across all three)

A report can cover every sample in the inputs (the default) or an explicit subset.

| Input | Type | Purpose |
|---|---|---|
| `sample_ids` | `Array[String]` | Sample ids to report on. **On a Terra `sample_set`, bind this to `this.samples.sample_id`** — that is the idiomatic way to drive one report per set. Empty (default) means every sample in the inputs. |
| `sample_id_list` | `File?` | Alternative to `sample_ids`: one id per line, `#` comments allowed. Used when `sample_ids` is empty. |
| `selection_label` | `String?` | Name for the selection, shown in the report (e.g. the sample_set name). |

Selection is applied per sample *before* any aggregation, so unit, site, year and marker
denominators all reflect the subset. Because prevalence is a proportion, a filtered report
says so: the summary scope bar carries a `selected samples: <label>` chip and the Methods
tab gets a callout stating how many of the requested ids were found. Ids that matched
nothing are counted and listed in the task log, and a selection that matches **no** samples
fails the task rather than producing an empty report.

For MAD4HATTER, ids match either the base sample id or the run-suffixed id as written in
the resmarker table (`SNG23MAD146` and `SNG23MAD146_S25_L001` both work).

To produce several reports, run the workflow once per set — Terra does this natively when
you launch on a set entity, and it keeps each report's denominators self-contained.

### Common inputs (identical across all three)

| Input | Type | Purpose |
|---|---|---|
| `cohort_name` | `String` | Output filename + output directory component. |
| `version_label` | `String?` | Version string stamped on the report, e.g. `v0.12`. |
| `data_source` | `String?` | Provenance line in the report banner. |
| `render_config_json` | `File?` | **Rendering settings. See §3.** |
| `report_template_override` | `File?` | **Replacement template. See §3.** |
| `reference_bundle_tar` | `File?` | **Replacement reference data. See §3.** |
| `gcs_out_root_dir` | `String?` | When set, outputs are copied to `<root>/<WorkflowName>/<cohort_name>/`. |

Per-task, from the house style rules: `extra_args` (appended verbatim to the
`make_report.py` invocation) and `runtime_attr_override` (including `docker`, which is how
you run a newer renderer without editing the WDL).

## 3. Outputs

| Output | Type | Notes |
|---|---|---|
| `report_html` | `File` | The report. Single self-contained HTML file, no external assets. |
| `report_data_json` | `File` | The report's full data model — every number the report draws. Stable, machine-readable; use this rather than scraping the HTML. |
| `export_csvs` | `Array[File]` | One CSV per dashboard view: `who_threat_map.csv`, `dhis2_datavalueset.csv`, `afcdc_mutation_haplotype.csv`, `pha4ge_malaria_standard.csv`. |
| `finalized_dir` | `String?` | GCS directory the outputs were copied to, when `gcs_out_root_dir` was given. |

---

## 4. Stability contract — what does and does not require a WDL change

**Changing how the report looks requires no change to this interface.** There are four
levers, in increasing order of effort:

1. **New container tag.** The image carries the code *and* the rendering assets (template,
   reference data, export schemas), so the tag is what pins "how the report looks". Bump
   the default in `wdl/tasks/Malaria/SurveillanceReport.wdl`, or override per-run with
   `runtime_attr_override = {"docker": "...:0.13.0"}` and touch no WDL at all.
2. **`report_template_override`.** Hand the task a different template file. The template is
   the entire presentation layer (layout, tabs, charts, labels, interactions), so a
   rendering experiment needs nothing but a new file in a bucket.
3. **`render_config_json`.** A JSON object of settings. Three keys are understood by the
   report model today — `min_samples`, `marker_action_pct`, `min_frame_n` — and
   **every other key is copied verbatim into the report's metadata**, where a template can
   read it. That is the designed path for new rendering knobs: add the key to the config
   file and read it in the template; the WDL never learns about it.
4. **`extra_args`.** Free-form CLI passthrough for flags added to `make_report.py` later.

What *would* require a WDL change: a genuinely new **data input** (a new file type from a
new upstream pipeline), or a new **output artifact** (e.g. a PDF alongside the HTML).
Those are interface changes by definition. Everything presentational is covered above.

---

## 5. NOMADS marker-calls schema

NOMADS has no production workspace yet, so the loader deliberately does not depend on
nomadic's native file layout. It reads a documented, assay-agnostic table — one row per
sample × marker — and whoever runs the pipeline maps the nomadic outputs onto it. If
nomadic's format changes, that mapping changes and this interface does not.

Headers are matched case-insensitively with aliases (full list in
`scripts/load_nomads.py`):

| Field | Accepted names | Notes |
|---|---|---|
| sample | `sample_id`, `sample`, `SampleID`, `specimen_id` | required |
| gene | `gene`, `Gene`, `gene_name` | `k13`/`crt`/... or `Pfk13`/`kelch13` |
| alteration | `aa_change`, `aa`, `mutation`, `alteration` | e.g. `K76T`; or give `codon` + `alt_aa` |
| call | `call`, `genotype`, `gt`, `status` | `ref`/`wt`/`hom_ref`/`0`; `alt`/`mut`/`hom_var`/`1`; `het`/`mixed`/`0/1`; `missing`/`nocall`/`.` |
| read counts | `mutant_reads`+`wildtype_reads` (or `alt_reads`+`ref_reads`) | alternative to `call` |
| location | `district`/`admin2`/`dept`, or `lat`+`lon`, plus optional `site` | district by name, else point-in-polygon |
| time | `year`/`collection_year`, or `date`/`collection_date` | `YYYY`, `YYYYMMDD` or `YYYY-MM-DD` |

Prevalence is carriage: samples whose call is `alt` or `het`, over samples typed at that
marker. Rows whose marker is not in the report catalogue, and rows that are not typed, are
counted and reported in the task log rather than silently dropped.

---

## 6. Container

```bash
docker build -t us.gcr.io/broad-dsp-lrma/lr-malaria-reports:0.12.0 -f docker/Dockerfile .
docker push  us.gcr.io/broad-dsp-lrma/lr-malaria-reports:0.12.0
```

Notes for whoever maintains it:

- The report pipeline is **pure standard-library Python 3** by design — no third-party
  packages, nothing to resolve at build time, nothing to drift.
- The base image is full `python:3.11`, **not** `-slim`, on purpose: every task runs the
  house-standard resource-detection preamble, which calls `free`. The slim image omits
  procps and the preamble aborts under `set -e`. This was found by running the workflow,
  not by reading it. `-slim` plus `apt-get install procps` is equivalent if the build host
  has package-repo access.
- The build asserts that `free` and `tar` exist and that the entrypoint and marker
  catalogue load, so a broken image fails at build rather than in Terra.
- Bump `tool_version` in the task `meta` blocks whenever the tag moves (house rule).

---

## 7. Local equivalence

The task body is one command, so it can be reproduced outside WDL exactly:

```bash
python3 scripts/make_report.py --assay WGS \
    --sample-table sample.tsv \
    --version-label v0.12 \
    --out-html report.html --out-data-json report.data.json --out-csv-dir csv/
```

`scripts/make_report.py --help` is the authoritative flag list. `build_real_reports.sh`
remains the development shortcut for the two real cohorts and goes through the same code.

---

## 8. Known gaps at handoff

- **Rendering is still in flux.** The report content/layout is being iterated; that is
  what §4 exists for. Pin a container tag for any run whose output must be reproducible.
- **NOMADS has no real data yet.** The workflow and loader are exercised only against a
  synthetic calls table. The schema in §5 will want one review against genuine nomadic
  output before first production use.
- **MAD4HATTER `allele_tables` are accepted but unused** — complexity-of-infection was
  removed from the report in v0.8. The input exists so that restoring COI does not change
  the interface.
- **`site_metadata` for MAD4HATTER is required** because the UCSF resmarker outputs carry
  no geography. If a future run emits geography inline, the input becomes optional
  (a loader change, not an interface change).
- Admin-2 geography now covers 51 malaria-endemic African countries via `country_iso3`;
  anything outside that set needs a map built with `build_maps.py` and supplied through
  `reference_bundle_tar`.
- Admin-1 (region) names come from a curated lookup for Senegal and from the boundary
  file's parent name where the source carries one (Libya's East/South/West, for example).
  geoBoundaries ADM2 files carry no parent name, so region columns are blank for most
  countries until an ADM1 lookup is added.
