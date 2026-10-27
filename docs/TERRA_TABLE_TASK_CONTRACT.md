# What the report pipeline needs from the Terra table-reader task

The amplicon report runs off the **wide per-sample Terra table** (one
`resmarker_<gene>_<codon>` column per marker, plus geography and the QC columns
`02_AmpliconPanelQcReport` writes back). That table lives in Terra's entity store, not in
the bucket, and no Terra input expression can materialise a whole table as a file — only
one attribute at a time, as an array. So the pipeline currently takes the table as a TSV
that someone exported by hand.

You have a task for this; this file records the interface the report pipeline will call it
with, so the two line up without a round trip. Nothing here is a request to change your
task — if its signature differs, the adapter belongs on my side.

## What I need back

One TSV holding the whole table: a header row, then one row per entity, with the entity id
in a column named `entity:<table>_id` (the Terra export convention) or `sample_id` — both
are already recognised. Every attribute as its own column, values verbatim. That is exactly
what Terra's own "Download TSV" produces, so if your task emits that format there is
nothing to adapt.

Specifically the report reads, case-insensitively:

| Columns | Used for |
|---|---|
| `resmarker_<gene>_<codon>` | the marker calls (observed amino acid, `F/Y` for mixed) |
| `Country`, `Region`, `District`, `Latitude`, `Longitude`, `site` | placement; coordinates win over the district name |
| `Library_sample_qc_status`, `batch_pass`, `sample_type` | QC; only `pass` counts, controls excluded |
| a year or date column | the time dimension (absent from the PfPhast table today) |

Unrecognised columns are passed through untouched, so a task that emits more than this
costs nothing.

## What I expect to pass in

Whatever your task needs to identify the table. The pipeline already has, or can trivially
add, string inputs for:

- workspace billing project / namespace
- workspace name
- entity type, e.g. `pfphast_sample`
- optionally the sample-set name, if your task can resolve membership itself

`write_metrics_to_workspace_table` in `EPPIcenter/mad4hatter-wdl` takes
`workspace_name`, `workspace_billing_project` and `entity_type`, so I have assumed
something close to that shape.

## Sample sets

Restricting a report to a sample set already works without any new task, because set
membership arrives as an array rather than a file: launch against a `*_sample_set` row and
set

```
sample_ids       = this.samples.<id column>      # e.g. this.samples.pfphast_sample_id
selection_label  = this.sample_set_id
```

Verified against the real sets in
`JTS_TEST_COPY_20261024_..._Mad4Hatter_CLONE_2`: the `Good` set resolves 184 of its 192
members (the 8 unmatched are negative controls with no marker calls), 6 are excluded by
pipeline QC, and 178 are placed across 33 districts. The `All` set gives 411 of 429 matched
and 353 placed. The selection is named in the report and every denominator refers to it.

So the only gap the reader task closes is getting the table itself in without a manual
export. Sample-set scoping is done.

## Where it plugs in

`wdl/tasks/Malaria/SurveillanceReport.wdl`, in `RenderMad4hatterReport`, ahead of the
render step: the task's output TSV becomes the `resmarker_tables` value, and
`site_metadata` stays omitted because the per-sample table carries geography. The render
step itself needs no change — it already sniffs the header and routes a wide table to the
loader that understands it.
