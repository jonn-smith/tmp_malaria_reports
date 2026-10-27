# MalariaSurveillanceReportNomads

Renders the malaria molecular-surveillance report from NOMADS nanopore amplicon data.

Outputs and behaviour match
[`MalariaSurveillanceReportAmplicon`](MalariaSurveillanceReportAmplicon.README.md):
a self-contained HTML report, the data model behind it, dashboard-ready export CSVs, and a
location-resolution audit. See that README for location handling, the minimum field set,
and the rendering override inputs, all of which are the same here.

## The input that differs

| Input | Type | Notes |
|---|---|---|
| `marker_calls_tables` | `Array[File]` or `File` | Either the assay-agnostic marker-calls table (one row per sample x marker) or a wide per-sample Terra table (one column per marker), which is reshaped automatically. |

## Location

Coordinates **or** `country`/`region`/`district` (admin-2), coordinates winning where
both are present. Every unplaced sample, every name absent from the boundary file, and
every coordinate/name disagreement is reported in `location_audit` and on the Methods
page rather than resolved quietly.
