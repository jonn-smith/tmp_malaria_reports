# MalariaSurveillanceReportPfphast

The amplicon surveillance report pipeline with the panel declared as **PfPHAST**
(primer pools `M1.1` + `M2.1`) rather than detected from the loci.

Identical inputs and outputs to
[`MalariaSurveillanceReportAmplicon`](MalariaSurveillanceReportAmplicon.README.md) — see
that README for the full table. The only difference is that `assay` is preset, which turns
the panel into a cross-check: it is honoured, and if the loci in the input look like a
different panel the disagreement is reported rather than silently accepted.

Use this when you know the run is PfPHAST. Use `MalariaSurveillanceReportAmplicon` when you
want the panel worked out from the data, including panels that are not catalogued.

## Typical launch against a sample set

| Input | Value |
|---|---|
| `resmarker_tables` | the `pfphast_sample` table exported to TSV, in the workspace bucket |
| `sample_ids` | `this.samples.pfphast_sample_id` |
| `selection_label` | `this.sample_set_id` |
| `country_iso3` | `UGA` |
| `country_name` | `Uganda` |
| `site_metadata` | omit — the per-sample table carries the geography |
