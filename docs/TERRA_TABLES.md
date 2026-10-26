# Terra sample tables as a marker source

Both gates-malaria development workspaces now carry drug-resistance calls as **columns on
the `sample` table**, one column per marker. This note records what those columns mean,
how they reach a report, and what is still missing.

| | `gates-malaria/Nomadic_development` | `gates-malaria/Mad4Hatter_development` |
|---|---|---|
| sample rows | 48 | 3953 (**5** carry marker calls) |
| column form | `aa_change_<gene>_<REF><POS><ALT>` | `resmarker_<gene>_<codon>` |
| value | verdict word | observed amino acid |
| vocabulary | `wt`, `mutant`, `mixed`, `unphased`, `absent`, `failed` | `K`, `T`, … and `F/Y`, `I/L` for mixed |
| marker columns | 45 | 58 |
| of those, in the WHO catalogue | **9** | **56** |
| geography | none | none |

## Minimum fields

Six, measured rather than assumed. Four describe the genotype, two place it in space and
time. They can all live in one table, or the last two can arrive in a separate
`--site-metadata` file keyed by sample id.

| field | alternatives accepted | leaving it out |
|---|---|---|
| `sample_id` | `sample`, `specimen_id` | row ignored |
| `gene` | `Pfcrt`, `kelch13`, … | call dropped (`no_marker`) |
| `aa_change` e.g. `K76T` | `codon` + `alt_aa` | call dropped (`no_marker`) |
| `call` | `mutant_reads` + `wildtype_reads` | call dropped (`not_typed`) |
| `district` | `admin2`, `dept`, or `lat` + `lon` | **every sample dropped** (`no_location`) |
| `year` | `date`, including day-first `28.07.2025` | builds, but `period n/a` and no Trends frames |

`site` is a display label, not a location: a table with `site` but no district or
coordinates places nothing and reports zero samples. Coordinates do double duty — they
resolve the admin unit by point-in-polygon *and* put pins on the site map. No QC-status
field is required; every placed sample counts toward the QC-pass total. Sample selection
is optional.

## Getting a report out

`scripts/terra_samples.py` reshapes the wide table into the marker-calls table that
`scripts/load_nomads.py` already consumes, so nothing downstream changes:

```bash
# Data > sample > Export to TSV, in the Terra UI
scripts/terra_samples.py --in sample.tsv --out calls.tsv --audit
scripts/make_report.py --assay NOMADS --marker-calls calls.tsv \
    --site-metadata sites.csv --out-html report.html --out-data-json report.json
```

`--audit` prints how every value was mapped. Use it: it is the only place the
judgement calls below are visible.

## Judgement calls worth knowing about

**`absent` and `unphased` are treated as not-typed, not as wild type.** `absent` means the
locus was not observed in that sample; `unphased` means the substitution needs two changes
in one codon that the reads cannot phase, so the verdict is genuinely unknown. Counting
either as wild type would enlarge every denominator and push prevalence down. On the real
Nomadic table this removes 196 of 2160 calls (128 unphased, 68 absent); `failed` removes 2
more.

**An observed residue that is neither the reference nor WHO's alternate counts as
reference for that marker.** If WHO tracks K76T and the sample reads N at codon 76, then
K76T is absent — true, but the parasite does carry a substitution the report will not
show. `--audit` counts these as `other_substitution`.

**A mixed call carries the mutation only if WHO's alternate is one of the residues.**
`F/Y` at a codon WHO tracks as K→T is reported as reference, not as mixed.

## Still missing: geography

Neither workspace has a district, site, or coordinate anywhere — not on the sample tables,
not on `experiment`, `sample_set` or the bucket manifests. Every sample is therefore
dropped as `no_location`, which is the whole report.

The join already exists; it just needs columns. `--site-metadata` takes a table keyed by
sample id and reads `district` (or `admin2`/`dept`), or `lat` + `lon`, plus optional
`site`. Two natural carriers:

- **Nomadic** — the per-experiment CSV at `experiment.metadata_file`
  (`gs://fc-e51e…/metadata/<experiment>.csv`), already keyed by `sample_id` with
  `barcode, date, strains, parasitemia, strain_percents, well, coi, source, sample_type, swga`.
  Adding `district` (or `lat`/`lon`) to that CSV is sufficient.
- **Mad4Hatter** — `gs://fc-7734…/example_manifest.tsv`, keyed by `sample_name` with
  plate position, `StudySubject`, `Barcode`, `Batch`, `Run`.

Two smaller things found while testing:

- The Nomadic `sample` table spans **both** experiments (`A_*` and `B_*` prefixes), so any
  single experiment CSV covers about half of it. Concatenate the per-experiment CSVs.
- Those CSVs write dates day-first (`28.07.2025`). `load_nomads.py` now reads that form;
  before the fix every sample landed in "period n/a".

## Panel coverage

Nomadic's 45 columns are mostly antigens rather than resistance markers, but **nothing is
dropped** — a locus the panel types is kept and labelled by class:

| class | pill | count | what it is |
|---|---|---|---|
| WHO entries | `VAL`/`CAN`/`POT`/`HAP` | 9 | `crt K76T`, `dhfr N51I/C59R/S108N`, `dhps A437G/A613S`, `mdr1 N86Y/Y184F/N1042D` |
| Antigen locus | `AGN` | 34 | 23 `ama1` and 11 `csp` — immune targets typed for antigen diversity |
| Background | `BKG` | 2 | resistance-gene codons the compendium does not list |

`ama1` and `csp` get their own class rather than "not in WHO compendium" because that
phrasing implies a gap: the compendium is a *drug resistance* compendium, and these are
not resistance markers, so their absence from it is correct rather than missing. The class
description says so on the page, the Notes column reads "Antigen diversity, not drug
resistance — no treatment implication", and an antigen locus can never raise the ≥10%
action flag (that remains `cls == 'validated'` only) or appear in the summary table.

The two `BKG` rows are `aa_change_dhps_S436F` (WHO lists S436A and S436H) and
`aa_change_mdr1_N86F` (WHO lists N86Y, and the table carries a separate `N86Y` column).
Both look like upstream near-misses worth a second opinion.

Mad4Hatter's 58 columns map cleanly: all 56 that correspond to single codons are WHO
entries, spanning `k13` (21), `crt` (14), `dhps` (7), `dhfr` (5), `mdr1` (5), and one each
of `mdr2`, `exo`, `fd`, `arps10`. Four codons are outside the catalogue
(`crt 73`, `k13 481`, `pib7 1484`, `PF3D7-1322700 236`).
