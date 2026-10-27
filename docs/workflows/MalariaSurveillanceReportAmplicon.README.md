# MalariaSurveillanceReportAmplicon

Renders the malaria molecular-surveillance report from amplicon resistance-marker calls and
writes a self-contained single-file HTML report, the data model behind every number in it,
dashboard-ready export CSVs, and a location-resolution audit.

The panel is detected from the loci present in the input, so this one workflow serves
MAD4HatTeR, PfPHAST and any other panel; `MalariaSurveillanceReportPfphast` is the same
pipeline with the panel declared rather than detected.

## Inputs

| Input | Type | Notes |
|---|---|---|
| `resmarker_tables` | `Array[File]` | **Either** the wide per-sample Terra table exported to TSV (one `resmarker_<gene>_<codon>` column per marker — the short-read default) **or** the pipeline's long `resmarker_table.txt` files, one per run. Do not mix the two shapes in one submission. |
| `cohort_name` | `String` | Used for output filenames. |
| `site_metadata` | `File?` | Per-sample site and coordinates. **Omit for the wide per-sample table**, which already carries `Country`/`Region`/`District`/`Latitude`/`Longitude`. Required with the long tables. |
| `country_iso3` | `String?` | Selects the admin-2 boundary set baked into the image, e.g. `UGA`. Defaults to `SEN`. |
| `country_name` | `String?` | Shown in the report. |
| `sample_ids` | `Array[String]` | Restrict to a selection. Launching against a `*_sample_set` row, set this to `this.samples.<id column>`. |
| `selection_label` | `String?` | Name of the selection shown in the report, e.g. `this.sample_set_id`. |
| `version_label`, `data_source` | `String?` | Stamped on the report. |
| `render_config_json` | `File?` | JSON settings. Unrecognised keys pass through to the report metadata, so a new template takes new settings with no interface change. `qc_statuses` widens which QC grades count. |
| `report_template_override`, `reference_bundle_tar` | `File?` | Replace the presentation layer or the reference data without a new image. |
| `gcs_out_root_dir` | `String?` | Copies the outputs to this prefix. |

## Outputs

| Output | Notes |
|---|---|
| `report_html` | Self-contained single-file report. No network access needed to view it. |
| `report_data_json` | Every number the report draws, including the panel detection and location audit blocks. |
| `export_csvs` | One CSV per view: WHO Threats Map, DHIS2 dataValueSet, Africa CDC, PHA4GE. |
| `location_audit` | How each sample was placed, every unplaced name with spelling suggestions, every coordinate/name disagreement. Written even when clean. |

## Location

Accepts coordinates **or** `country`/`region`/`district`, where district is admin-2.
Coordinates win where both are present. Nothing about location resolves quietly: an
unplaced sample, a district absent from the boundary file, a name that disagrees with its
coordinates, and a region drawn from a different vocabulary than the boundary file's
admin-1 are all reported in `location_audit`, in the task log, and on the report's Methods
page.

## Sample QC

The report defers to the amplicon QC workflow rather than inventing thresholds. Only
`Library_sample_qc_status = pass` counts; anything marked a control in `sample_type` and
anything with a failed `batch_pass` is excluded. That status is written onto the per-sample
table by `02_AmpliconPanelQcReport` and is the worst grade across a sample's reactions,
from its `reprep_threshold` / `repool_threshold` on the proportion of good loci. Set
`qc_statuses` in the render config to include `repool` or `reprep`. Exclusions are listed
on the Methods page, never applied silently.

## Minimum fields

Six: `sample_id`, `gene`, `aa_change` (or `codon` + `alt_aa`), `call`, a location
(`district`, or `lat` + `lon`), and a date (`year` or `date`). Without a location every
sample drops and the run fails rather than producing an empty report. Without a date the
report builds but the Trends tab is empty. See `docs/TERRA_TABLES.md`.
