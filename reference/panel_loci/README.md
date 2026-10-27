# Per-panel inputs for `03_ExtractDrugResistanceMarkers`

The published default, `gs://broad-malaria-public/mad4hatter_workspace_data/default_principal_resistance_marker_info_table.bed`,
is panel-agnostic: 74 curated loci, of which **PfPHAST can type 41 of its 82** and
**MAD4HatTeR 51 of its 147**. Extraction therefore covers less than the assay measures,
and a report can only show what extraction produced.

These files are each panel's full reach.

| file | loci | WHO Validated covered |
|---|---|---|
| `pfphast_principal_resistance_marker_info_table.bed` | 82 | 16 of 16 |
| `mad4hatter_principal_resistance_marker_info_table.bed` | 147 | 17 of 17 |
| `pfphast_loci_groups.tsv` | 3 groups | — |
| `mad4hatter_loci_groups.tsv` | 3 groups | — |

## How they were derived

`scripts/build_panel_loci.py`, from upstream `EPPIcenter/mad4hatter @ main`:

- `panel_information/principal_resistance_marker_info_table.tsv` — 161 markers with codon
  coordinates. Verified byte-identical to `reference/mad_resmarker.tsv`.
- `panel_information/<pool>/<pool>_amplicon_info.tsv` — each pool's amplicon inserts.

A pool types a marker when the marker's codon interval lies inside one of that pool's
inserts; a panel is the union over its pools. Panel composition is from the Mad4Hatter
Terra workspace documentation: **PfPHAST = M1.1 + M2.1**, **MAD4HatTeR = D1.1 + R1.2 +
R2.1** (D1.1 is the diversity pool and contributes no resistance marker).

Two conventions are taken from the published default rather than from upstream, because
the pipeline names its output columns from the `gene` field and the existing Terra tables
already use these spellings: `dhfr-ts` (not `dhfr`), and `PF3D7-1322700` /
`PF3D7-1451200` with hyphens. Every locus shared with the published default is written
**byte for byte identically** — the generator asserts this.

`loci_groups.tsv` keeps only haplotype groups the panel types in *full*. Both panels type
all three default groups (`pfdhfr`, `pfdhps`, `pfdhfr_pfdhps`), so both files match the
default. A group that were only partially typed would be dropped rather than assembled
from incomplete codons.

## Using them

Upload alongside the existing default, then point each workspace's `03` config at its pair:

```bash
gsutil cp pfphast_principal_resistance_marker_info_table.bed \
          pfphast_loci_groups.tsv \
          mad4hatter_principal_resistance_marker_info_table.bed \
          mad4hatter_loci_groups.tsv \
          gs://broad-malaria-public/mad4hatter_workspace_data/
```

| `03_ExtractDrugResistanceMarkers` input | PfPHAST workspace | MAD4HatTeR workspace |
|---|---|---|
| `loci_of_interest_bed` | `…/pfphast_principal_resistance_marker_info_table.bed` | `…/mad4hatter_principal_resistance_marker_info_table.bed` |
| `loci_groups` | `…/pfphast_loci_groups.tsv` | `…/mad4hatter_loci_groups.tsv` |

Quote the values in Terra as the existing config does (`"gs://…"`).

## Regenerating

```bash
scripts/build_panel_loci.py \
  --markers reference/mad_resmarker.tsv \
  --pools-dir <dir of <pool>_amplicon_info.tsv from panel_information/> \
  --loci-groups default_loci_groups.tsv \
  --out-dir reference/panel_loci \
  --compare-default default_principal_resistance_marker_info_table.bed
```

`--compare-default` is not optional in practice: it supplies the gene-label conventions
and then asserts every shared row matches.
