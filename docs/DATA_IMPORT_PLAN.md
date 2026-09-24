# Real-data import plan — Senegal surveillance mock-ups → live data

Status: 2026-09 recon complete. Capability model in `gen_reports.py` corrected to
match the three workspaces. This doc = what to wire, from where, and what must be
computed. Everything in the current mock-ups is synthetic; this is the replacement path.

## 0. The three sources (confirmed)

| | Workspace | Senegal cohort | Granularity |
|---|---|---|---|
| **WGS** | `broad-firecloud-dsde-methods/sr-malaria` | `2025_Paper_Joint_Call_Senegal_Samples` (3,071 samples, joint VCF) | admin-2 + real `date_of_collection` |
| **MAD4HATTER** | `CIGASS-testing/Malaria_Plasmodium_Illumina_Amplicon_CIGASS_MH` | `Senegal_2023_Mad4Hatter_runs1-10` (993 incl. controls) | lat/long point (~13 sites), **no admin label, no date in metadata** |
| **Pf8** | `gates-malaria/MalariaGEN_Pf8_Data_Resource` | `Pf8_sample` filtered `Country=Senegal` | admin-1 + **year only** (reference/background layer) |

## 1. WGS — `sr-malaria`

**Samples / QC**: `sample` table (3,473). Senegal subset via the joint-call sample_set
`v3_dropped_one_from_v2_SRJointCalling_05012024_3071_samples`. QC filter on callable
fraction / coverage (workspace attr `qc_coverage_regions_bed`).

**Genotypes**: joint VCF `gs://fc-b06e896e-…/results_new_test/SRJointCallGVCFsWithGenomicsDB/…gnarly_genotyper.rescored.combined.vcf.gz` (+ per-contig; `MONO_ONLY` variant for poly/mono split; barcode subsets 24-SNP / 192-pos already carved).

**Metadata**: `sample.date_of_collection` (confirmed) + `sample_location_metadata`
(workspace attr) → admin-2 district. **TODO: confirm exact admin-2 column name** in the
`sample` table (couldn't page 3,473 rows without dropping the fiss session).

**Per-report-field sources**:
- Markers (all 16 incl. coronin/ubp1/ap2mu): extract genotypes at loci in
  `pf3D7_drug_resistance_bed_file` / `drug_resistance_list_v3_genes_of_interest`.
- CNV (mdr1, pfpm2/3): GATK gCNV using `cnv_intervals` + `cnv_contig_ploidy_priors`.
- hrp2/hrp3 deletion: read-depth over the loci in `genomic_region_annotation_bed_files`.
- COI / poly-mono: `barcode_haplotype_db` → barcode → THE REAL McCOIL / Fws.
- RH / cotx / between-host IBD: **hmmIBD** (the `HmmIBD` / `FilterVcfForHmmIBD` WDL we
  refactored) on the joint VCF → pairwise IBD + relatedness network.

## 2. MAD4HATTER — `CIGASS`

**Pipeline that produced the data** (method configs, ns `malaria-featured-workspaces`):
- `01_Illumina_Amplicon_Processing` = dockstore `broadinstitute/malaria/AmpSeq`,
  panel = `workspace.Pool_combined` (pools **1A + 1B + 2**), ref PlasmoDB-59.
  **Output = `ampseq_object_f`** (allele + coverage + resmarker object) — this is the
  core results file. Successful full-set run: submission `c20bdcdc-4b72-4205-b2c4-a41d71ba06a8`.
- `02_Plasmodium_Genotype_Population_Analysis` = dockstore `broadinstitute/malaria/MHap`,
  markers = `workspace.WHO_Drug_Resistance_Markers`. **Output = `drs_minimal_report_f`**
  (drug-resistance summary) + microhaplotype/relatedness.

**Panel capability (confirmed from `MAD4HAtTer_v4_MarkersTable.csv`, 276 amplicons):**
- SNP resmarkers: k13, crt, mdr1, dhfr, dhps, cytb (+ partners arps10/fd/exo/mdr2/atp6/csp).
- **hrp2** `PF3D7_0831800` + **hrp3** `PF3D7_1372200` amplicons present → deletion by dropout.
- **pfpm2/pfpm3** `PF3D7_1408000/1408100` (+ PM1/PM4) → coverage-based CNV (piperaquine).
- Non-falciparum species: Pv / Pm / Poc / Pk ldh amplicons.
- **Not** coronin/ubp1/ap2mu (absent from resmarker table).

**Metadata gap (real problem)** — `All_2023_runs_metadata1.csv` (993 rows) has only:
`Sample_id, Country, Latitude, Longitude`, where **`Country` actually holds the site name**
(Bandafassi, Dialocoto, Diourbel, Gabou, Kabendou, Ndoga Babacar, …; ~13 sites) and
controls (NTC1, NTC2, DD2 = lab strain) are mixed in. **No admin-2 label. No collection date.**
- → must **spatial-join lat/long → admin-2 polygon** (`sen_adm2.geojson`, point-in-polygon).
- → must **drop controls** before any prevalence.
- → **date is missing here** — check `All_2023_runs_metadata.tsv` (the other attr) or the
  run/sample IDs; if truly absent, MAD contributes counts+markers but not a date range.

## 3. Pf8 — `MalariaGEN` (reference/background layer)

`Pf8_sample` filter `Country=Senegal`. Provides admin-1 + year + QC + population + Fws +
`Pf8_distance_matrix` (relatedness) + `Pf8_tandem_duplication_breakpoints` (CNV). Per-sample
resistance classification: **locate — columns in `Pf8_sample` vs a separate release file (TBD).**
Use for continental/historical comparison only; coarser than the report's admin-2 + date design.

## 4. Computations required (all currently mocked)

1. **QC + control filter** — drop NTC/DD2, drop below-QC samples per assay.
2. **Marker prevalence per admin-2** — numerator = samples with mutant allele
   (define WSAF cutoff for amplicon mixed calls), denominator = successfully genotyped at
   that locus; attach **Wilson 95% CI** (already in the mock; keep formula).
3. **COI** — THE REAL McCOIL / coiaf / moire (microhaps for MAD, barcode for WGS);
   **poly/mono** = fraction COI>1 with denominator.
4. **RH** (intra-host relatedness) — Wong et al. RH from within-sample allele frequencies.
5. **cotx** (co-transmission fraction) — from the within-host relatedness distribution.
6. **Between-host IBD** — hmmIBD (WGS) / Dcifer or hmmIBD (MAD microhaps).
7. **CNV** — gCNV (WGS) / amplicon coverage-ratio (MAD) → per-sample copy number.
8. **hrp2/hrp3 deletion** — coverage dropout (both assays).
9. **Spatial join** — MAD site lat/long → admin-2 (point-in-polygon).
10. **Date parsing / windowing** — WGS `date_of_collection`; MAD date TBD; Pf8 year.
11. **Aggregate to admin-2 unit** — n, date_min/max, mk{}, hrp2/hrp3, div{coi,poly,mono,rh,cotx},
    with the existing n<5 suppression + slider.
12. **Export builders** — AFCDC (per-sample × per-codon wildtype/mutation counts), WHO MTM,
    DHIS2 dataValueSet.

## 5. Changes to the build pipeline (`gen_reports.py` + template)

- **Replace synthetic generators** (`dept_prev`, `hrp_dept`, random COI/RH/cotx) with a
  loader that reads a **per-sample intermediate** and aggregates. Proposed contract
  (one row per sample): `sample_id, assay, admin2, date, {marker: {call, wsaf}}, coi,
  hrp2_del, hrp3_del, cnv{gene:copies}, qc_pass`. gen_reports keeps the aggregation +
  suppression + CI + export logic; only the data intake changes.
- **Capability flags** (`cnv`, `hrp`, `species`) added to the ASSAYS model (done). Template
  can gate CNV/species sections on them (currently no CNV or species section — see below).
- **Add CNV markers** — pfpm2/3 & mdr1 amplification are WHO-relevant (piperaquine, lumefantrine).
  New marker kind `type=cnv` (copy number, not a codon %). **Template change**: copy-number
  display distinct from the codon-prevalence bars.
- **Add species panel (optional)** — MAD + Pf8 can report non-falciparum co-infection.
- **Geo** — real admin-2 join for MAD; confirm WGS admin-2 column; Pf8 stays admin-1
  (either exclude from the admin-2 map or render as a separate coarser layer).
- **Time** — real dates span 2019–2023 (WGS) vs 2023 (MAD) vs many years (Pf8). Decide whether
  the report is a single window or gains a time filter.

## 6. Decisions needed from Jonn

1. **Mixed-call threshold** — WSAF % at which an amplicon sample "carries" the mutant.
2. **COI + RH/cotx tooling** — McCOIL vs coiaf vs moire; RH/cotx estimator for amplicon.
3. **MAD admin level** — aggregate ~13 sites → admin-2 by spatial join (recommended), or show sites?
4. **MAD collection date** — where is it? (not in `…metadata1.csv`).
5. **Pf8 role** — include as a background/comparison layer, or leave out (continental, coarse)?
6. **CNV + species** — promote to first-class report sections, or keep resistance SNP-focused?

---

## 7. Gap resolution (2026-09-23)

### MAD4HATTER geo + date — RESOLVED
- All three metadata files inspected. `All_2023_runs_metadata.tsv` and `…metadata1.csv` = only
  `Sample-ID, Country(=site name), Latitude, Longitude`. `All_2023_Mad4Hatter_runs.tsv` adds
  `Site, Geo_Level, Temp_Level, …` **but `Geo_Level` and `Temp_Level` are NA for all 964 non-control samples.**
- **Admin-2**: not stored → derived by spatial join. Built `mad_site_to_admin2.json` (point-in-polygon of
  each site's lat/long against `sen_adm2.geojson`). 13 sites → departments:
  Bagadadji→Goudiry · Bandafassi→Kedougou · Dalaba→Kedougou · Dialocoto→Tambacounda ·
  Diourbel→Diourbel · Gabou→Bakel · Kabendou→Velingara · KeurSerigneMbayeSarr→Diourbel ·
  Madiyanah2→Mbacke · Ndoga Babacar→Tambacounda · Parcelles→Kaolack · Sessene→Diourbel · Thies→Thies.
  **Low-confidence to verify**: SESSENE shares identical coords with DIOURBEL (placeholder) — real Sessène is
  Thiès/Mbour; PARCELLES/KEURSERIGNEMBAYESARR coords look approximate. Confirm site coords with CIGASS.
- **Date**: none finer than year exists anywhere. Cohort = 2023 (IDs `SNG23…`/`SN23…`). Use **year = 2023**.
- Controls to drop: `Sample-ID` in {NTC*, DD2, Dd2*, DC3*} and the junk `Site=0` / lat=0 row.

### WGS admin-2 + date — RESOLVED (schema via method config, table too big to page)
- `get_entities` on `sample` (3,473) expires the fiss session; `test_sample`/`background_samples` are thin
  (BAMs / set refs). Recovered the real `sample` columns from method config `02b_GenerateMalariaReport`
  (rooted on `sample`): `sample_id, Code, Country(locality), Latitude, Longitude, Year, barcode,
  drug_res_markers, hrp2, hrp3, average_identity, aligned_est_fold_cov`.
- **Key finding**: WGS stores the SAME shape as MAD — point coords + a locality name in `Country` + `Year`,
  **no pre-computed admin-2 column**. So ONE spatial-join step (lat/long → `sen_adm2.geojson`) serves both
  assays; reuse the point-in-polygon that built `mad_site_to_admin2.json` on `this.Latitude/this.Longitude`.
- Date → `Year` (a `date_of_collection` column may also exist per Jonn; use it if finer than year, else Year).
- Ready-made per-sample fields: `drug_res_markers` (parse to marker calls), `hrp2`/`hrp3` (already run —
  workflow `01a_Plasmodium_HRP2_HRP3_Status_Detection`, 98 samples Succeeded), `barcode` (→ COI),
  `average_identity`/`aligned_est_fold_cov` (QC).

### Pf8 resistance columns — CONFIRMED location, enumeration method given (not dumpable here)
- Per-sample metadata + resistance calls are in `Pf8_sample` (33,325 rows). No public metadata file
  (only images under `gs://broad-malaria-public/pf8_workspace/resources/`), so columns exist ONLY in the table.
- Can't dump 33k rows (session dies at 3.4k). AA-change columns follow **`gene_codon[allele]`**
  (Jonn's example `mdr2_484[T]`; same format as Pf7).
- **Enumerate at import without paging rows**: use the Terra entity-type metadata endpoint
  (`fapi.list_entity_types` → `attributeNames` + count; returns zero rows) then regex-filter
  `^\w+_\d+\[[A-Za-z*]\]$`. `get_workspace_data_tables` (fiss-mcp) already calls that endpoint but strips
  `attributeNames` — so use raw FISS or the Rawls API for the column list.
- Pull only the Senegal subset via paginated `entity_query` (`Country == Senegal`), not the full 33k.

### Net effect on the import
- Geo for BOTH primary assays = one spatial-join (lat/long → admin-2). Lookup for MAD already built.
- Time = year (2023 for MAD; per-sample Year for WGS).
- Decisions #3 (MAD admin level) and #4 (MAD date) from §6 are now answered: spatial-join to admin-2; year 2023.
