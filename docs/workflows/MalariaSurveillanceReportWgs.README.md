# MalariaSurveillanceReportWgs

Renders the malaria molecular-surveillance report from short-read whole-genome data.

Outputs and behaviour match
[`MalariaSurveillanceReportAmplicon`](MalariaSurveillanceReportAmplicon.README.md):
a self-contained HTML report, the data model behind it, dashboard-ready export CSVs, and a
location-resolution audit. See that README for location handling, the minimum field set,
and the rendering override inputs, all of which are the same here.

## The input that differs

| Input | Type | Notes |
|---|---|---|
| `sample_table_tsv` | `Array[File]` or `File` | A Terra export of the WGS `sample` table (TSV) carrying per-amino-acid genotype columns. |

## Location

Coordinates **or** `country`/`region`/`district` (admin-2), coordinates winning where
both are present. Every unplaced sample, every name absent from the boundary file, and
every coordinate/name disagreement is reported in `location_audit` and on the Methods
page rather than resolved quietly.
