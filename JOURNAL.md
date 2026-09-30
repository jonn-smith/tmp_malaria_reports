# Development journal — Senegal malaria surveillance reports

Append-only log of the reporting work (mock-ups -> real-data pipeline -> export formats). Extracted from the broader project journal; WDL / hmmIBD / reference-comparison entries live elsewhere. UTC timestamps.

## 2026-09-17T00:00:00Z  — Cohort malaria surveillance report mock-up: research + design decisions

**Context.** User (Jonn) wants a mock-up cohort-level malaria molecular-surveillance report (single self-contained HTML) modeled loosely on the existing single-sample "SR WGS Report" at gs://fc-b06e896e-.../SEN_2010_SLP.CXX_0112_lrma_report.html, but for MAD4HATTER amplicon cohort data. To be shown at a follow-up meeting tomorrow. Audience: Africa CDC, Gates Foundation, national malaria control programs (NMCPs).

**Decision / action.** Downloaded + dissected the reference report (fiss-mcp bridge). It is a tabbed single-sample report: Summary / Analysis / QC Report; content = sample+location metadata, HRP2/HRP3 deletion (RDT escape), Pf7 drug-resistance markers, 24-SNP barcode, sequencing QC, IGV snapshots. Design language: Rubik font, light card UI, teal/cyan accents (#2494c7 / #23bfdf / #006dae), neutral greys, maroon/navy, green positives. Building a NEW multi-country cohort report reusing that visual language.

**Why.** Meeting notes asked for: summary-level report first (sample-level maybe in Terra table); frequency/prevalence with CI (of QC-pass samples); UCSF (MAD4HATTER) workflow frequency estimates; CIs via standardized means; functional unit = country w/ district/site within; QC at batch+sample level; lab-strain contamination tool. Chose a multi-country sentinel-network framing because "cohort" + Africa-CDC/Gates audience wants continental headline numbers, and it still supports country→district/site drilldown.

**Evidence / research.** MAD4HATTER (EPPIcenter/UCSF Greenhouse) confirmed via GitHub README + wonderland-docs: amplicon panel, pools D1/R1/R2, DADA2 ASV inference, resmarker module (principal_resistance_marker_info_table.tsv), outputs = allele table + core QC metrics + drug-resistance info + diversity (COI). WHO Malaria Threats Map tracks 4 categories: pfhrp2/3 deletions (5% RDT-switch threshold), artemisinin partial resistance (validated pfk13), partner-drug/molecular markers, drug-efficacy (TES). Established marker sets used: pfk13 validated ART-R (C580Y,R561H,R622I,A675V,P553L,R539T,I543T,...); pfcrt K76T (CQ); pfmdr1 N86Y+copy number; plasmepsin2/3 amplification + pfcrt novel muts (PPQ); pfdhfr(51/59/108/164)+pfdhps(437/540/581) quintuple/sextuple (SP for IPTp/SMC/PMC). CI method: Wilson score for site proportions; country pooled = sample-size-weighted/standardized mean w/ CI (matches "standardized means").

**Outcome.** Design locked: tabs = Summary / Drug Resistance / RDT (HRP2/3) / Diversity / QC / Methods. Self-contained HTML, inline SVG charts (no CDN) so it renders/prints anywhere. Fake-but-plausible data. Next: load dataviz skill, build /workspace deliverable.

## 2026-09-17T00:30:00Z  — Cohort report mock-up built & verified (Session summary)

**Read first.** Deliverable: /workspace/mad4hatter_cohort_report_mockup.html (single self-contained HTML, 62 KB, inline-SVG charts, no CDN except optional Rubik webfont). Open in any browser; prints to PDF cleanly (@media print un-hides all tabs).

**What it is.** Multi-country MAD4HATTER cohort molecular-surveillance report mock-up (synthetic data). 6 countries / 18 sentinel sites / 3,660 QC-pass of 4,240 collected. Tabs: Summary · Drug resistance · RDT escape (HRP2/3) · Diversity & transmission · Quality control · Methods. Reuses the single-sample SR-WGS report's visual language (Rubik, teal chrome) but data marks use the dataviz-validated CVD-safe categorical palette (worst adjacent ΔE 13.3) + sequential-blue ramp for heatmap/map.

**Elements delivered (mapping to meeting asks).** (1) Frequency/prevalence w/ 95% Wilson CI of QC-pass samples — bars w/ CI whiskers + full tables. (2) UCSF/MAD4HATTER frequency estimates — resistance-marker matrix + per-marker charts. (3) CIs via standardized means — country = sample-size-weighted pooled estimate; documented in Methods. (4) Functional unit country w/ district/site — country tables + site-level HRP2 bars + site network map. (5) QC batch+sample — batch table, sample-QC donut, note that per-sample rows live in Terra data table. (6) Lab-strain contamination — 3D7/Dd2/HB3 control-read flag tile + per-batch counts. Plus HRP2 5% RDT-switch threshold flagging (4/18 sites over), ART-R trend 2019-24, COI/diversity, SP chemoprevention watch (dhps540/581).

**Verification (no browser available — Chromium download + apt both blocked by sandbox network).** (a) Wilson CI self-check in gen_data.py: wilson(10,100)=(10.0,5.52,17.44) ✓, all CIs bracket estimates ✓. (b) jsdom execution: 0 JS errors, all 6 tabs populate (svg+table counts non-zero), no undefined/NaN/[object Object] in visible text. Caught+fixed a real bug: partner-drug table used short code 'crt' vs data 'crt76' → crash on DR tab. (c) Static SVG geometry check: 14 SVGs / 746 primitives / 0 overflow after fixing two clipping issues (long HRP2 site labels overflowing left gutter → ISO codes + wider pad; rotated heatmap headers rising above top → horizontal labels).

**Open questions for the meeting.** Single-country vs multi-country framing (built multi-country; easy to reframe). Dark mode not built (light-only; forced light bg so dark browsers don't break). Real geo choropleth deferred (used approximate lat/lon scatter map). Whether to embed a real WHO-TB-style country-profile page per country.

**Next iteration hooks.** All data is one embedded JSON blob (const DATA); regenerate via scratchpad/gen_data.py. Renderers are data-driven, so new countries/markers need only data edits.

## 2026-09-17T01:30:00Z  — v0.2 scope: single-country, 3 assays + combined, real WHO markers & admin2 map

**Context.** Jonn's feedback on v0.1: version filenames; go single-country; want admin2 (or admin3) choropleth AND graduated-dot map; drug markers/phenotypes from the WHO compendium xlsx; keep RDT + CoI; and produce 4 mock-ups — WGS, MAD4HATTER, NOMADS (ONT), and a combined multi-assay one — each consistent with what that method actually measures.

**Decision / action.** Country = Senegal (matches reference sample + West-Africa assay relevance). Downloaded real inputs (curl works from container; earlier apt/google failures were host-specific): WHO "Compendium of molecular markers for antimalarial drug resistance" xlsx (263 KB, Dec-2025 v?) and geoBoundaries SEN ADM2 (45 departments, simplified geojson 424 KB). Parsed WHO "Combined (Pf)" sheet → 117 markers across 12 drugs, classes Validated(30)/Candidate(32)/Potential(55), genes Pfk13/Pfcrt/Pfdhfr/Pfdhps/Pfcytb/Pfmdr1/Pfcoronin/Pfpm2-3/Pfgch1. This is the authoritative marker+phenotype source for all mock-ups.

**NOMADS panel (researched via nomads-community GitHub org — Gates INV-003660/048316).** sWGA+PCR+ONT assay. BED files: nomads8 = crt,kelch13,dhfr,msp2,dhps,mdr1,pm2/3; nomads16 adds csp,ama1,hrp2(+up/dwn),hrp3(+up/dwn); MVP = ama1,crt,csp,dhfr,dhps,hrp2,hrp3,kelch13,mdr1. So NOMADS covers drug-R genes crt/k13/dhfr/dhps/mdr1/pm2-3, HRP2/3 deletions (flanking amplicons), and msp2/ama1/csp for COI. Does NOT cover cytb(atovaquone), coronin, gch1, or genome-wide diversity/IBD. (nomadsIR/SpeciesID BEDs are Anopheles vector panels — out of scope.) This defines NOMADS report's coverage limits.

**Why single template.** Building 4 reports from ONE HTML template + per-assay DATA (capability flags gate tabs/markers/diversity depth). Map projection done in Python (geojson→SVG paths, rounded coords), JS just draws precomputed paths. Version tag v0.2 in every filename per new standing instruction [[project_mad4hatter_cohort_report]].

**Evidence.** who_combined.json (117 rows) + sen_adm2.geojson (45 feats, bbox lon -17.53..-11.35 lat 12.31..16.69) in scratchpad. NOMADS BEDs quoted above from raw.githubusercontent nomads-community/resources/main/beds/.

## 2026-09-17T02:45:00Z  — v0.2 delivered: 4 single-country assay reports (Session summary)

**Read first.** Four self-contained HTML mock-ups in /workspace (~170 KB each, inline SVG, no CDN except optional Rubik):
- senegal_malaria_surveillance_WGS_v0.2.html
- senegal_malaria_surveillance_MAD4HATTER_v0.2.html
- senegal_malaria_surveillance_NOMADS_v0.2.html
- senegal_malaria_surveillance_COMBINED_v0.2.html

**What changed from v0.1 (per Jonn's feedback).** Single-country (Senegal); real admin-2 choropleth (45 departments, geoBoundaries) + graduated-dot map on a Burden tab, with a metric selector (incidence / cases / samples) and resistance/HRP2 choropleths; drug markers + classifications (Validated/Candidate/Potential) and predicted drug phenotypes driven by the WHO Compendium of molecular markers; RDT + CoI tabs kept. Version tag in every filename.

**Assay fidelity (the key requirement — "don't show what a method can't measure").** Built one template gated by a capability model. WGS: all 11 marker genes incl. cytb/coronin, high-res COI (Fws), IBD, population structure, barcode. MAD4HATTER: broad marker set + microhaplotype COI (no genome-wide IBD). NOMADS (ONT nomads16): only crt/k13/dhfr/dhps/mdr1/pm2-3 + hrp2/3 + msp2/ama1/csp → cytb/coronin shown as "not covered", Atovaquone & Mefloquine phenotypes "Not assessed", COI = msp2 counting, no IBD/barcode. COMBINED: coverage matrix (gene×assay, feature×assay), markers pooled across assays that type them, per-assay contribution.

**Inputs (real).** WHO compendium xlsx → who_combined.json (117 markers/12 drugs). NOMADS panel from nomads-community GitHub BEDs. Senegal ADM2 geojson → build_maps.py → sen_admin2_map.json (projected SVG paths). gen_reports.py builds all 4 DATA blobs (Wilson-CI + capability self-checks). report_v2.template.html = shared renderers.

**Verification (no browser — sandbox blocks Chromium/apt; curl to data hosts works).** jsdom run of all 4: 0 JS errors, every tab populates, no undefined/NaN/[object leaks. Static SVG geometry: 0 overflow after fixing barCI right-edge value labels, long DR bar labels, and choropleth edge labels. Content assertions confirmed the capability gating above (NOMADS hides atovaquone/cytb/coronin/IBD; WGS/combined include them; combined coverage matrix + 45-path maps + 3-metric selector render).

**Bugs found & fixed this session.** Combined crashed on Diversity (no diversity/qc/phenotypes built for combined) → added. Marker short-code mismatch fixed earlier. Label-overflow fixes as above.

**Open for the meeting / next iter.** Admin-3 (arrondissement) available if finer resolution wanted. Real projection is equirectangular+cosLat (fine at country scale). Dark mode still not built. Could add ART-R time-trend per assay and an importation/relatedness view for WGS/combined.

## 2026-09-17T03:20:00Z  — v0.2 fixes: RDT choropleth render bug + WHO link/rubric

**Bug.** RDT-tab choropleth rendered wrong: not-sampled departments blank/black. Root cause: every choropleth() emitted `<pattern id="nd">`, so with several choropleths in one document the IDs collided; `url(#nd)` resolved to the FIRST match (in the hidden Burden tab), whose pattern has no render tree while display:none → hatch failed to paint on visible RDT map. Fix: unique pattern id per choropleth (counter `nd0,nd1,…`) and reference the local id. Verified: RDT not-sampled paths all reference their own svg's pattern.

**Feature.** Added real WHO source link (https://www.who.int/publications/m/item/compendium-of-molecular-markers-for-antimalarial-drug-resistance) in DR tab intro, phenotype-rubric card, and Methods; and rendered the phenotype **rubric itself** as a table (drug · markers used · call thresholds) sourced from RUBRIC in gen_reports.py (mirrors drug_phenotype). All 4 reports rebuilt; jsdom+geometry PASS; 4 WHO links each; pattern ids unique.

## 2026-09-17T04:15:00Z  — v0.3: Panel & loci tab, real panel links, tightened coverage

**Change.** Added a "Panel & loci" tab to all 4 reports. Each shows: links to the assay (MAD4HATTER → EPPIcenter github + wonderland docs + resmarker TSV; NOMADS → nomads-community github + nomadic + resources BEDs; WGS → MalariaGEN Pf7 + PlasmoDB), a panel summary, and a loci table (gene · PlasmoDB Pf3D7 ID · chr · product · surveillance relevance). NOMADS also lists its 16 real amplicons with Pf3D7 v3 coordinates (from nomads16.amplicons.bed). Combined report shows all three panel cards + a unified "loci covered by assay" matrix.

**Coverage tightened using ground-truth panel files.** Pulled MAD4HATTER panel_information: D1.1 (170 diversity amplicons) + R1.1/R1.2 (resistance) + principal_resistance_marker_info_table.tsv (16 genes: k13,crt,mdr1,dhfr,dhps,cytb,mdr2,atp6,arps10,fd,exo,csp,...). So MAD4HATTER DOES type cytb (atovaquone) but NOT coronin, plasmepsin2/3 or copy number. Reclassified copy-number markers (mdr1 amp, pm2/3 amp) as WGS-only, and coronin as WGS-only. Net marker coverage: WGS 11/11, MAD4HATTER 8/11, NOMADS 7/11. NOMADS now also correctly not-assessed for Mefloquine/Piperaquine/Atovaquone phenotypes.

**Loci reference.** Curated LOCI dict (20 genes) with PlasmoDB IDs (k13 PF3D7_1343700, crt PF3D7_0709000, mdr1 PF3D7_0523000, dhfr PF3D7_0417200, dhps PF3D7_0810800, cytb mal_mito_3, hrp2 PF3D7_0831800, hrp3 PF3D7_1372200, msp2 PF3D7_0206800, ama1 PF3D7_1133400, csp PF3D7_0304600, plasmepsin2/3 PF3D7_1408000/_1408100, etc.), products and drug relevance.

**Verify.** gen_reports self-checks extended: WGS types cytb/coronin/ppq/mdrCN; MAD types cytb but NOT coronin/ppq/mdrCN; NOMADS types none of those; every panel has loci with IDs; NOMADS lists exactly 16 amplicons. All 4 rebuilt (v0.3), jsdom + geometry PASS (0 errors, 0 overflow), panel-tab probe confirms links + PF3D7 ids + real amplicon coords. Removed superseded v0.2 files; kept v0.1 (multi-country) as history.

## 2026-09-17T05:00:00Z  — v0.4: DR choropleth + co-occurrence heatmap + hrp3 in RDT

**Changes (Jonn feedback).** (1) Drug-resistance tab: added a resistance-prevalence choropleth with a marker selector (11/8/7 markers for WGS/MAD/NOMADS) — recolours the 45-department map per selected marker via wireDR(). (2) "Multiple resistances in a region": added a department × marker heatmap (top 20 depts by burden × covered markers, cell = prevalence %, RR ramp, numeric labels) so co-occurring resistances per area read at a glance. (3) RDT-escape tab: added pfhrp3 alongside pfhrp2 — hrp3 dept bar chart, hrp3 choropleth (beside hrp2), and a dept table with both hrp2 & hrp3; note that hrp3 has no action threshold but dual hrp2+hrp3 deletion = full RDT escape.

**Bug fixed.** Combined report crashed in R.rdt: combined dept_data carried averaged hrp2 but no hrp3 (and no per-dept mk), so hrp3 bars hit undefined.toFixed. Added rec['hrp3'] and rec['mk'] (union-averaged across contributing assays) in build_combined → combined DR maps + RDT hrp3 now work.

**Verify.** All 4 rebuilt v0.4, jsdom+geometry PASS (0 errors, 0 overflow). Probe confirms DR selector options, choropleth svg, heatmap rects, RDT hrp3 text + two map choropleths + dept table (11/38/19/40 rows). Removed superseded v0.3; kept v0.1 (multi-country).

## 2026-09-23T17:00:00Z  — Moved report build pipeline to durable /workspace/malaria_reports/

**Context.** The mock-up build scripts (gen_reports.py, build_maps.py, report_v2.template.html, inputs, data_*.json) had been living in the session scratchpad (/tmp/claude-1015/.../scratchpad) — ephemeral. Before iterating to v0.5 + real data, moved them to durable storage.

**Action.** Copied the full flat pipeline to /workspace/malaria_reports/ (kept flat so relative-path opens keep working), added build_reports.sh (build_maps -> gen_reports -> template inject; takes VERSION arg, default v0.5) and README.md. Test rebuild from the new dir produced all 4 HTML cleanly. Shipped v0.4 HTML remain at /workspace root. Next iteration (v0.5, colleague feedback pending) works from /workspace/malaria_reports/.

## 2026-09-23T18:00:00Z  — v0.5 colleague feedback captured (planning; not yet implemented)

**Requirements (clear, will implement):** prevalence only (drop incidence); NO drug-resistance phenotype prediction — instead show WHO criteria + associated genes/AA changes only; rename "drug res markers" -> "Genetic alterations associated with Antimalarial drug resistance"; never say "validated" (use "WHO-tracked"); include NON-WHO markers, clearly labeled; per-marker (AA change) show/hide toggle across maps/tables; small-sample masking (don't say 100% when n=1 — threshold, user-choosable min-n / confidence; show n per region as a bar graph on maps); 3 top-nav categories = Resistance markers / Diagnostics (HRP2/3) / Transmission; Summary "stoplight of concerns" (3 categories, click into details, WHO action-trigger flags e.g. >5%); choropleth legend graduated by 50/100 + mouseover-shows-numbers + clickable regions to highlight/show values; standardize sampling symbology/plot sizes; admin-3 if available else admin-2, contingency if admin/date missing; dashboard-compat export views (buttons: "As reported for WHO Threat Maps / AFCDC / DHIS2"); download whole marker table; use epidemiologist per-1000 (‰) symbol where applicable; Diversity per-admin-unit not aggregate (another map; proportion polygenomic WITH denominator; ~5 metrics Wes pulled — within-host vs across-pop vs within-unit).

**Contradictions/ambiguities raised to Jonn BEFORE implementing:** (1) HRP2/3: "remove HRP2/3" vs "diagnostics (HRP2/3) top-nav category" vs "grey out but don't plot" -> proposed: keep Diagnostics nav tab as greyed-out placeholder w/ caveats (not lab-validated, research/funding priority). (2) Incidence: "don't put incidence" vs "use standard incidence ‰/1000 symbol" -> prevalence only; clarify % vs per-1000. (3) The 5% action threshold listed under Diagnostics but described as "triggers a therapeutic efficacy study" (a resistance concept) while diagnostics is greyed -> clarify pfhrp2-deletion RDT-switch 5% vs resistance-marker TES trigger, and where flags live. Also need: the 5 diversity metrics list; dashboard field schemas vs representative mockups; default min-n threshold.

## 2026-09-23T19:00:00Z  — v0.5 research findings + diversity metrics

**Thresholds (ran #3 to ground).** pfhrp2/3: WHO ">=5% pfhrp2/3 deletions causing negative HRP2-RDT results" = high-prevalence setting -> switch to non-HRP2 RDT (confirmed; WHO Response plan to pfhrp2 gene deletions, 2nd ed 2024). Resistance markers -> TES: NO documented WHO "molecular marker >=5% -> TES" rule found; WHO's formal policy-change trigger is >=10% treatment failure in a TES; WHO-tracked ART-R markers (pfk13) presence prompts enhanced surveillance. So Jonn's "told >=5% triggers TES for markers" appears to conflate the pfhrp2 5% (diagnostics). Plan: use >=5% concern flag for both (per Jonn) but label precisely — HRP2/3 >=5% = WHO RDT-switch threshold (real); resistance >=5% = "elevated/watch, consider TES" w/ footnote that formal WHO trigger is >=10% treatment failure. Raised to Jonn.

**Dashboards (#5).** DHIS2 confirmed: dataValueSet import (dataElement, period, orgUnit, categoryOptionCombo, attributeOptionCombo, value[, comment]); CSV col order dataelement,period,orgunit,catoptcombo,attroptcombo,value; admin units -> orgUnit, period from collection date. WHO Malaria Threats Map + Africa CDC: no exact schema fetched -> will build representative export layouts, clearly labeled.

**Diversity metrics (from Jonn):** THE REAL McCOIL COI (within-host), polygenomic fraction (per-unit, w/ denominator), monogenomic clone fraction (per-unit), RH (meaning TBC — asked), cotx = co-transmission fraction (IBD-based). All to be shown PER admin unit, not aggregate.

## 2026-09-23T21:00:00Z  — v0.5 mock-ups built (colleague-feedback redesign)

**Built.** /workspace/malaria_reports/report_v05.template.html + updated gen_reports.py + build_reports.sh (v0.5). 4 reports (WGS/MAD4HATTER/NOMADS/COMBINED) at /workspace root as senegal_malaria_surveillance_<ASSAY>_v0.5.html.

**Feedback incorporated:** prevalence only (no incidence; reworded disclaimer to drop the word); NO phenotype prediction — markers show gene+AA+drug+WHO-tracked+criterion only; renamed section "Genetic alterations associated with antimalarial drug resistance"; never "validated" (markers = "WHO-tracked"; "validated" only in the diagnostics NOT-VALIDATED caveat); non-WHO research markers labelled (Pfcoronin/Pfubp1/Pfap2-mu, WGS+COMBINED); per-marker AA toggles (filter table + map selector); min-sample suppression n<5 with live slider + per-region sample bar; 3-category nav (Resistance/Diagnostics/Transmission) + Summary/Export/Methods; Summary stoplight (red/amber/green/grey, clickable to section) with WHO action flags (resistance >=10%, hrp2/3 >=5%); binned+clickable choropleth legend (bins + suppressed key + action flag, click pins region value, hover tooltip); Diagnostics greyed + big NOT-VALIDATED banner (data kept, not plotted heavily); Transmission per-unit (McCOIL COI, poly/mono fraction w/ denominator, RH + cotx WGS-only) + map + per-unit table; Export views (WHO Threat Map + AFCDC representative, DHIS2 real dataValueSet schema) w/ CSV download.

**Validation.** jsdom: 0 JS errors, no empty tabs, no NaN/undefined; static SVG geometry 0 overflow all 4; content checks pass (WHO-tracked present, incidence absent, stoplight 3 lights, resistance controls+download, export 3 views, diagnostics NOT-VALIDATED banner). No browser screenshot possible (sandbox) — interactions (slider/click/toggle/CSV) verified structurally, need eyeball.

**Deferred / for real-data:** admin-3 + missing-admin/date contingency UI (mock has admin-2 only, flags admin_available/dates_available); the 5 diversity metrics are mocked; WHO-MTM + AFCDC export layouts are representative (DHIS2 schema real). Next: wire real per-assay inputs.

## 2026-09-23T22:30:00Z  — v0.6 (colleague feedback round 2)

Edits (template report_v05.template.html + gen_reports.py strings), rebuilt -> /workspace/senegal_malaria_surveillance_<ASSAY>_v0.6.html:
- "What this is" callout moved to TOP of Summary (above the concerns heading).
- "consider TES" -> "WHO criteria indicates TES" (marker pill, caption, stoplight findings in gen_reports).
- Removed "No resistance phenotype is predicted." (resistance sec-desc + methods).
- Diagnostics banner: "not confirmed on real data" -> "predicted based on genetic markers"; removed the "(people will ask...)" parenthetical; gen_reports diagnostics note aligned.
- Maps: clicking outside a province now clears the highlight (global clearRegions() + document click listener; region paths keep selection).
- Restored original Summary elements BELOW stoplight/kpis: "Where sampling happened" graduated-dot map (size ∝ samples), "Method at a glance" tile, and "Admin-2 units by sample count" table (# samples only, + collection window).
- Vertical separator added before Methods in the nav (now Summary | Resistance/Diagnostics/Transmission | Export | Methods).

Validated (jsdom, all 4): 0 JS errors, no empty tabs, 0 SVG geometry overflow, incidence absent, WHO-tracked present, stoplight 3, controls/download/export/diag-banner present; content checks confirm each edit. clearRegions verified present (outside-click deselect needs browser eyeball). "validated" only in the required NOT-VALIDATED diagnostics caveat.

## 2026-09-23T23:30:00Z  — v0.6 fixes (feedback round 3)

- Version consistency: gen_reports.py hardcoded version='v0.5' -> DATA.meta.version leaked into v0.6 (footer/badge). Fixed to single source: gen_reports reads VERSION=sys.argv[1]; build_reports.sh passes "$VER" to both the generator and the template __VERSION__ inject. Verified no 'v0.5' in v0.6 outputs.
- "What this is" moved from Summary body into the header banner (new .whatis div, below the Platform/Admin-2 tagline, above the nav); populated in JS from M.note.
- Nav label + stoplight category capitalized to "Resistance Markers" (LABEL.resistance, gen_reports stoplight cat x2, R.summary jump-map key kept in sync).
Rebuilt v0.6 -> /workspace root; jsdom 0 errors all 4; targeted checks pass (header whatis present, summary callout gone, nav "Resistance Markers", version clean).

## 2026-09-24T00:10:00Z  — Africa CDC export = real per-sample schema

Jonn supplied the Africa CDC molecular-marker submission schema (per-sample × per-codon, with wildtype/mutation read COUNTS). Rewrote gen_reports add_export afcdc to emit exactly those 15 columns: Sample ID, Date of sample collection, Facility name, District, Region, Country name, Study type, Gene name, Codon, Wildtype count, Mutation count, Travel_history, Travel location (if Y), Endemicity, Assay used. Gene names mapped to AFCDC style (Pf-stripped; k13->kelch13); District=admin-2; Region via SEN_REGION dept->region map with accent-insensitive lookup (_na; geoBoundaries names are un-accented); Endemicity from unit polygenomic fraction; Assay from meta; wildtype/mutation counts synthesised per sample (mutant with prob = marker prevalence). 30 rows in the mock view. Template AFCDC view retitled "molecular-marker submission (per-sample schema)"; DHIS2 remains real dataValueSet, WHO MTM representative. Rebuilt v0.6, shipped; jsdom 0 errors all 4; Region confirmed populated.

## 2026-09-23T00:00:00Z — Recon of 3 Terra workspaces for real-data population of the mock-ups

**Context.** Jonn pointed at 3 Senegal-relevant Terra workspaces and asked what report fields each can populate: WGS (broad-firecloud-dsde-methods/sr-malaria), MAD4HATTER (CIGASS-testing/Malaria_Plasmodium_Illumina_Amplicon_CIGASS_MH), Pf8 (gates-malaria/MalariaGEN_Pf8_Data_Resource).

**Action.** Listed data tables in all three (fiss-mcp get_workspace_data_tables). Pulled schemas: MAD4HatTeR_Mozambique (demo, 50) for the MAD input schema; sr-malaria analysis_ready_dataset (25) for WGS dataset layout; Pf8_populations (10, offloaded 1.7MB) for Pf8 structure.

**Findings.**
- WGS/sr-malaria: sample(3473), pf7_sample(20864), sample_set(59), analysis_ready_dataset(25). Senegal joint VCF = "2025_Paper_Joint_Call_Senegal_Samples" (3071 samples, gnarly-genotyper, all 14 chr + API + MIT) + MONO_ONLY + barcode subsets (192-pos, 24-SNP, mad4hatter_v2_loci). Richest source: all 16 markers incl CNV, HRP2/3, full diversity incl RH+cotx (WGS-only). Open: does `sample` carry admin-2 + collection date (couldn't fetch — 3473 rows kills the session).
- MAD4HATTER/CIGASS: Senegal_2023_Mad4Hatter_runs1-10 (993). Input table schema = name(SRR/sample), fastq1/2, run_id, Country, Latitude, Longitude, Geo_Level(admin), Temp_Level(time). Geo+date live in metadata (demo shows "NA"). Marker/COI results are pipeline OUTPUTS (resmarker/microhaplotype), not table columns. Covers SNP resistance markers + COI/poly/mono; NOT CNV, NOT RH/cotx.
- Pf8/MalariaGEN: Pf8_sample(33325 continental; Senegal=subset), Pf8_vcf(16 by-chr), Pf8_genomics_db(16), Pf8_distance_matrix(2), Pf8_populations(10: AF-C/E/NE/W, AS-*, OC-NG, SA — AF-W=West Africa holds Senegal), Pf8_tandem_duplication_breakpoints(65). Reference layer: WHO-tracked markers + HRP2/3 + Fws COI + relatedness, but admin-1/year granularity (not admin-2/date), historical not new surveillance.

**Constraint hit.** get_entities on 3473/33325-row tables overflows and expires the fiss-mcp session. Schema recon must use small analog tables or page the offloaded result files, not inline full fetches.

**Outcome.** Produced a field-by-field mapping (report data model → each workspace) with 3 open confirmations flagged: WGS sample geo/date columns; MAD Senegal Geo_Level/Temp_Level populated + submission-output locations; Pf8 per-sample resistance-call location (columns vs separate file).

## 2026-09-23T00:30:00Z — MAD4HATTER capability cross-check vs paper+repo; my capability model was too restrictive

**Context.** Jonn asked me to verify what MAD4HATTER actually claims and reconcile with my per-workspace field mapping.

**Sources.** Paper: Aranda-Díaz et al., Sci Rep 2025, 10.1038/s41598-025-94716-5 ("Sensitive and modular amplicon sequencing of P. falciparum diversity and resistance"), PMC11953298. Repo: github.com/EPPIcenter/mad4hatter (principal_resistance_marker_info_table.tsv + panel_information/README.md). Supporting: Katairo et al. Malar J 2025 (DR23K vs MAD4HatTeR); Kiyaga et al. Malar J 2026 (COI/relatedness predict prevalence/incidence in Uganda).

**Findings — MAD4HATTER claims (acronym = Drug, Diagnostic, Diversity, Differentiation Haplotypes):**
- 165 diverse loci; multiallelic microhaplotypes; minor alleles to 1% WSAF; non-falciparum species ID; CSP/vaccine targets.
- Drug resistance SNPs (principal resmarker table): k13(44 codons), crt(12), mdr1(8), dhfr(6), dhps(6), cytb/mal_mito(4), plus background/partner markers arps10, fd, exo, mdr2(53), atp6(4), csp(17), pph, pib7. NO coronin, NO ubp1, NO ap2mu in the principal table.
- "duplications and deletions" — CNV (mdr1/plasmepsin dup) via coverage module (bin/asv_coverage.R, *coverage.nf); hrp2/hrp3 deletions via the Diagnostic pools (PfPHAST M1.1/M2.1). Panel/pool-dependent.
- Diversity/relatedness: COI/eCOI + between-host relatedness are headline outputs (Uganda paper); Aster/asterTES does IBD.

**Corrections to my 2026-09-23 mapping (MAD column):**
1. CNV markers ❌ → ✅ (coverage-based, panel-dependent).
2. HRP2/3 deletions "~marginal" → ✅ (Diagnostic pools, panel-dependent).
3. Research markers coronin/ubp1/ap2mu "~coronin" → ❌ (none in principal resmarker table); but MAD DOES cover arps10/fd/exo/mdr2/atp6/csp that the mock-up currently omits.
4. RH intra-host relatedness ❌ → feasible via microhaplotype WSAF (not WGS-only).
5. cotx co-transmission ❌ → feasible via within-host relatedness (not WGS-only).
6. Between-sample IBD "~limited" → ✅ (Dcifer/hmmIBD on microhaps).

**Implication.** The mock-up's baked capability tiers (gen_reports.py ASSAYS: MAD = coi/poly/mono only, no rh/cotx, no CNV, no HRP) are demonstrably too restrictive. MAD4HATTER is a near-complete surveillance panel, not a SNP-only assay. Correct framing = capability is PANEL/POOL-dependent, and coverage-based CNV/deletion is lower-confidence than WGS. Open: which pools the Senegal_2023 runs used (determines whether hrp2/3 + CNV are actually in-hand for that dataset vs merely panel-capable).

**Also.** Jonn confirmed WGS `sample` table has a `date_of_collection` column → resolves the WGS date-range open item; admin-2 district column still to confirm.

## 2026-09-23T01:15:00Z — Confirmed MAD pools + rewrote capability model + wrote import plan

**Context.** Jonn: confirm which pools Senegal_2023 used, rewrite the assay-capability model, and flag everything needed to import real data.

**Pools — confirmed.** CIGASS method config `01_Illumina_Amplicon_Processing` = dockstore `broadinstitute/malaria/AmpSeq`, panel = `workspace.Pool_combined` = pools 1A + 1B + 2 (Reference_Pools/Pool1A|1B|Pool2.tsv). Output `ampseq_object_f`. Downstream `02_…` = `broadinstitute/malaria/MHap` → `drs_minimal_report_f`. Read `MAD4HAtTer_v4_MarkersTable.csv` (276 amplicons, gs://broad-malaria-public): hrp2 (PF3D7_0831800) + hrp3 (PF3D7_1372200) amplicons present; pfpm2/3 (PF3D7_1408000/1408100) + PM1/PM4 present → coverage CNV; Pv/Pm/Poc/Pk ldh species amplicons. So the Senegal MAD data DOES carry hrp2/3 + plasmepsin CNV + species — my "panel-dependent, maybe" is resolved to YES for this dataset.

**WGS attrs (from sr-malaria workspace metadata):** cnv_intervals, cnv_contig_ploidy_priors (gCNV), barcode_haplotype_db (COI), pf3D7_drug_resistance_bed_file + drug_resistance_list_v3_genes_of_interest, qc_coverage_regions_bed, genomic_region_annotation_bed_files, sample_location_metadata. Confirms full WGS stack. Jonn confirmed `date_of_collection` exists on the sample table.

**MAD metadata gap (dead end for geo/date):** All_2023_runs_metadata1.csv = only Sample_id, Country, Latitude, Longitude. `Country` column actually holds the SITE name (~13 Senegal sites) and controls (NTC/DD2) are mixed in. No admin-2 label, no collection date. → import needs a lat/long→admin-2 spatial join + control drop; MAD date must come from elsewhere or is absent.

**Capability model rewrite** (`gen_reports.py` ASSAYS): MAD4HATTER now cnv=True, hrp=True, species=True, div rh=True/cotx=True (method 'THE REAL McCOIL + Dcifer/hmmIBD (165 microhaplotypes)'); genes unchanged (no coronin/ubp1/ap2mu). WGS gained cnv/hrp flags + hmmIBD in method label. NOMADS cnv=False, hrp=True. Rebuilt v0.6, all 4 reports validate 0 errors / 0 SVG overflow. MAD now renders RH=0.47, cotx=48; NOMADS RH/cotx correctly gated None.

**Deliverable.** Wrote `/workspace/malaria_reports/DATA_IMPORT_PLAN.md` — per-field source map (table/file/workflow output + gs:// paths), the 12 computations required (all currently mocked), the pipeline/template changes (per-sample intermediate contract, CNV marker kind, species panel, geo join, time handling), and 6 decisions needed from Jonn.

**Outcome.** Capability model is now evidence-based and shipped; import path is documented. Blocking unknowns for real import: exact WGS admin-2 column name; MAD collection date location; Pf8 per-sample resistance-call location; the analytical tool choices (COI/RH/cotx, WSAF cutoff).

## 2026-09-23T02:00:00Z — Ran down the three import gaps

**Context.** Jonn: run down the gaps; build an admin-2 lookup; MAD date→year if none; check District/Region/Site cols; Pf8 resistance calls are per-AA columns (mdr2_484[T]) in Pf8_sample.

**MAD geo/date — resolved.** Downloaded all 3 MAD metadata files. `All_2023_Mad4Hatter_runs.tsv` has Site/Geo_Level/Temp_Level but Geo_Level+Temp_Level are NA for all 964 non-control samples; only Site + lat/long populated. No collection date anywhere → use year 2023 (cohort + SNG23/SN23 IDs). Built `mad_site_to_admin2.json` by ray-casting point-in-polygon of 13 site coords against sen_adm2.geojson (shapeName). Result: 13 sites → 9 departments (Kedougou/Tambacounda/Diourbel/Thies/Kaolack/Bakel/Goudiry/Velingara/Mbacke). Flagged low-confidence: SESSENE shares placeholder coords with DIOURBEL (real Sessène is Thiès/Mbour); PARCELLES/KeurSerigneMbayeSarr coords approximate.

**WGS schema — resolved without paging.** get_entities on `sample`(3473) expired the fiss session twice; test_sample/background_samples are thin. Recovered real columns from method config `02b_GenerateMalariaReport` (rooted on sample): sample_id, Code, Country(locality), Latitude, Longitude, Year, barcode, drug_res_markers, hrp2, hrp3, average_identity, aligned_est_fold_cov. Key finding: WGS stores the SAME shape as MAD (point coords + locality + Year, NO admin-2 column) → one spatial-join serves both. HRP2/3 already computed in-workspace (workflow 01a_Plasmodium_HRP2_HRP3_Status_Detection, 98 samples Succeeded 2025-10-13).

**Pf8 — location confirmed, enumeration method given.** No public Pf8 metadata file (gs://broad-malaria-public/pf8_workspace/resources/ has only PNGs). Resistance calls exist only in Pf8_sample (33,325 rows), columns `gene_codon[allele]` (e.g. mdr2_484[T]). Can't dump 33k rows (session dies at 3.4k). Import route: pull column list from Terra entity-type metadata (attributeNames, zero rows) — fiss-mcp get_workspace_data_tables calls that endpoint but strips attributeNames, so use raw FISS/Rawls — then regex `^\w+_\d+\[[A-Za-z*]\]$`; fetch Senegal subset via paginated entity_query, not the full table.

**Outcome.** Appended §7 (gap resolution) to DATA_IMPORT_PLAN.md; wrote mad_site_to_admin2.json. Import geo is now a single lat/long→admin-2 join for both primary assays; time=year. Remaining true unknowns are analytical choices (WSAF cutoff, COI/RH/cotx tooling) + verifying a few MAD site coordinates with CIGASS.

## 2026-09-23T03:00:00Z — Built the WGS real-data loader against the per-sample contract

**Context.** Jonn: build the WGS loader; easiest choice for missing analytics, don't care this iteration.

**Real formats pinned** (one real sample's resolved inputs from submission cb58672e + repo): sample columns via config 02b_GenerateMalariaReport (sample_id, Code, Country, Latitude, Longitude, Year, date_of_collection=YYYYMMDD, barcode=24-SNP, drug_res_markers, hrp2/hrp3=+/-, average_identity, aligned_est_fold_cov). drug_res_markers format = "gene codon variant presence(+/-)" (parser confirmed in docker/lr-malaria-reports/report-files/report_gen.py plot_dr_bubbles). Admin-2 = Senegal_Terra_Metadata.csv CODE->REGION/DISTRICT/SITE; sample_id SEN_<yr>_<CODE>. -> CODE -> DISTRICT. So WGS admin-2 is a direct code lookup, not a spatial join.

**Refactor.** Split gen_reports.build_assay into synth_units + shared assemble_report(name,spec,units) that recomputes nationals from per-unit integer counts (mkx/mkn/hrp2x/hrp3x/hrpn). Random-draw order preserved -> synthetic output unchanged (verified crt_K76T=10.2%, n_qc=362 identical). Added guard: markers with natn==0 -> assessed=False (so cytb/coronin/ubp1/ap2mu, absent from the WGS drug-text source, don't render as spurious 0%).

**load_wgs.py.** Intake per-sample TSV -> parse drug_res_markers to WHO target codons, hrp2/3 deletion=('-'), COI from 24-SNP barcode (poly if any 'N', COI=1+#N), aggregate to 45 depts via code->dept (+6-entry health-district->dept crosswalk), emit data_wgs.json via assemble_report. Analytics kept minimal per request: RH/cotx = null (pending hmmIBD), CNV = null. Includes --make-fixture (real codes + real field formats) as stand-in until the 3,071-row sample table is exported (can't page it via fiss).

**Result.** Fixture 400 -> 17/45 depts, 375 QC samples, period 2019–2022, 12 WHO markers with real Wilson CIs (dhfr 56–64%, crt/mdr1 8.5%, dhps540 4.8%, k13 low), cytb/research unassessed, hrp2 3.7%/hrp3 6.9%, stoplight Resistance=red/Transmission=red. Injected -> senegal_malaria_surveillance_WGS_v0.6-real.html; jsdom 0 errors, 0 SVG overflow; shipped to /workspace.

**Outcome.** WGS loader done end-to-end on real-format data. To run on the true cohort, feed a Terra export of the `sample` table (Senegal subset) as the TSV. Open analytics for a later iteration: COI via THE REAL McCOIL/barcode, RH/cotx via the hmmIBD run (submission 990_HmmIBD_Test currently Running), CNV via gCNV.

## 2026-09-23T04:00:00Z — Real WGS sample.tsv wired in; loader rewritten for real schema; found a dhps A437G annotation bug

**Context.** Jonn delivered the real `sample` table (/workspace/sample.tsv, 3473 rows x 164 cols) and confirmed all drug-res info is in the table.

**Schema reality.** The export carries pre-parsed per-AA genotype columns `pf<gene>_<Aaa>_<pos>_<Aaa>` with values {hom_ref|hom_var|het|missing|''} — the drug-res calls themselves, not a file path. Also real columns: District/Region/Site/Lat/Long, Year + date_of_collection(YYYYMMDD), qc_status(Pass/Fail), hrp2/hrp3(+/-), barcode. `mono_poly_genomic_barcode_estimate` is empty (3440/3443) so COI falls back to barcode 'N' count. Rewrote load_wgs.py to consume this schema (dropped the inline-text contract + fixture): District(+health->dept crosswalk)->admin-2, genotype cols->carriage prevalence (hom_var+het)/(hom_ref+hom_var+het), qc_status filter, hrp deletion=('-').

**Result on real data.** 16/45 depts, 2161 QC-pass of 3428 SEN samples, 2005-2023. 12/16 report markers mapped. Real prevalences plausible: crt K76T 50.5%, mdr1 N86Y 11.9%, dhfr N51I/C59R/S108N 94.9/95.3/96.9%, dhps K540E 5.1% / A581G 2.8%, k13 561/580/675 all 0% (no ART-R, expected), coronin G50E 0%. hrp2 5.3% / hrp3 13.2%. COI 1.65 / poly 22% (barcode). Injected -> senegal_malaria_surveillance_WGS_v0.6-real.html, jsdom 0 errors / 0 SVG overflow, shipped.

**Finding (flag to Jonn): dhps A437G reads 0% — upstream annotation bug.** Column `pfdhps_Lys_437_Gly` is 100% hom_ref (1101 hom_ref, 0 hom_var, 0 het among QC-pass); neighbouring `pfdhps_Ser_436_Ala` varies normally (461 hom_var/77 het). The WHO marker is Ala437Gly but the column is annotated Lys437Gly — so the single most common Senegalese dhps mutation is called against the wrong reference AA and always returns hom_ref -> false 0%. Not a loader bug (raw column is all hom_ref). Needs an upstream fix to the drug-resistance marker definition.

**4 markers unassessed (table types different codons than the mock's MK set):** k13_R622I (table has 633), cytb_Y268S (no column), ubp1_D1525E (table has V3275F), ap2mu_S160N (table has I592T). Cheap fix if wanted: repoint MK's research/k13 codons to what the pipeline actually types.

**Outcome.** WGS report now runs on the real cohort end-to-end. Open: dhps A437G annotation fix (upstream); COI source (barcode crude vs qc_stat_jc_het_fract); RH/cotx pending hmmIBD; whether to realign MK codons to the table.

## 2026-09-23T05:00:00Z — Built MAD4HATTER loader (ampseq_object xlsx -> units)

**Context.** Jonn: move to mad4hatter.

**Data reality.** Full 993-sample run (Senegal 2023_data_set) FAILED; only subsets succeeded — KDG_2020_set (Kedougou/DALABA 2020, 70 samples) + Miniset. So real MAD data = one site right now. ampseq_object_f is an xlsx (sheets: gt, metadata, markers, loci_performance, asv_table, vcf_like, controls_*, discarded_*).

**xlsx format decoded.** metadata: Sample_id, Strata(site), Lat/Long, sample_ampl_rate(QC). gt: sample x amplicon-locus, cell 'hap:depth' ('_'-joined haps = polyclonal, '.'=ref) -> COI. vcf_like: CHROM,POS,REF,ALT,FORMAT(GT:AD:DP)+per-sample GT -> marker calls by genomic position. loci_performance: per-amplicon ampl rate (hrp2/3 dropout).

**load_mad.py.** Site->admin-2 via mad_site_to_admin2.json; marker codon genomic ranges from mad_resmarker.tsv (principal_resistance_marker_info_table) intersected with vcf_like for the mutant numerator. KEY FIX: vcf_like lists only VARIANT positions, so a monomorphic wild-type codon has no row -> initially k13/dhfr_C59R came back unassessed instead of 0%. Fixed denominator to use `gt` amplicon coverage (amplicon amplified => genotyped); now k13 correctly reports 0% (no ART-R). COI from gt haplotype counts (max across loci; poly if >=2 multi-hap loci). hrp2/3, RH, cotx, CNV left null this iteration (per request).

**Result (KDG_2020, 68 QC of 69, Kedougou 2020).** 12 markers assessed: k13 561/580/675/622 all 0.0% (no ART-R), crt K76T 41.8%, mdr1 N86Y 8.2%, dhfr N51I 97.0% / S108N 97.1%, dhps A437G 36.8%, K540E/A581G 1.5%. COI 1.87 / poly 40%. Injected -> senegal_malaria_surveillance_MAD4HATTER_v0.6-real.html; jsdom 0 errors / 0 overflow; shipped.

**Cross-check finding.** dhps A437G = 36.8% in MAD (vcf_like position) vs 0% in WGS -> CONFIRMS the WGS `pfdhps_Lys_437_Gly` column is mis-annotated (should be Ala437Gly); MAD gets it right. Two faithful data limits flagged: dhfr_C59R=0% (no vcf_like variant row at codon 59 in this run — verify vs epidemiology), cytb unassessed (no mito amplicon column in gt for this run).

**Outcome.** Both loaders (WGS, MAD4HATTER) now run on real data via the shared assemble_report. MAD is single-site until the full 993 run is re-run successfully. Marker calls use position-approx (any non-ref GT in the codon range) not full AA resmarker translation — adequate for surveillance codons, flagged.

## 2026-09-24T00:00:00Z — Fixed 3 real-report bugs (one root cause) + dropped "THE REAL McCOIL" wording

**Context.** Jonn reported on the real reports: resistance section had no map; Methods+Export empty; COI mislabelled "THE REAL McCOIL".

**Root cause (single).** Real data JSON lacked the `export` key — the loaders called assemble_report but not add_export (add_export runs in a post-loop only for the synthetic path). At load, R.export() dereferences D.export.note -> throws inside the `TABS.forEach(... el.innerHTML=R[t]())` loop -> aborts the whole inline script: Methods (rendered after Export) never set, and the post-loop wireResistance()/wireExport() never run -> resistance #drmap never drawn. So all three symptoms = the export exception halting render.

**Fixes.** (1) load_wgs.py + load_mad.py call G.add_export(rep) after assemble_report. (2) add_export.afdate assumed 'YYYY-MM'; real date_min is year-only ('2020') -> ValueError on split -> made afdate handle year-only. (3) Removed "THE REAL McCOIL" from report_v05.template.html (transmission KPI, COI-by-admin2 hint, methods bullet) and from ASSAYS coi_method (WGS -> '24-SNP barcode heterozygosity', MAD -> 'microhaplotype allele counts (per-locus)'); COI now names the actual method via t.method.

**Verify (jsdom).** Real WGS + real MAD + synthetic WGS all: jsdomErr 0, drmap has <svg>, export renders a table, methods ~2.4-2.5k chars, no "REAL McCOIL" in HTML. Reshipped both real reports + rebuilt synthetic v0.6.

**Note.** add_export's afcdc view still fabricates per-sample rows (format demo); who_mtm + dhis2 use the real pooled marker prevalences. who_mtm year field is a placeholder (pooled national across 2005-2023 / 2020). Real per-sample AfCDC export = later.

## 2026-09-24T01:00:00Z — Real reports: removed all fabricated export data (real-only)

**Context.** Jonn: don't fake any data in the real reports — real data + derived fields only.

**Problem.** add_export (used by real loaders as of the prior fix) fabricates the Africa CDC view — random sample IDs (…-MSMT-…), random travel history (Mali/Guinea/Mauritania), endemicity, and random wildtype/mutation read counts — plus a hardcoded year=2024. WHO/DHIS2 rows were real prevalences but pooled '(national)/(pooled)' with the fake year.

**Fix.** Added gen_reports.real_export(rep, samples, assay_name) — NO random:
- WHO Threats-Map + DHIS2: per admin-2 x marker from unit mkx/mkn (real tested/present/percent), real region (WGS = Region column; MAD = SEN_REGION[dept]) and real collection year(s).
- Africa CDC: real per-sample x codon; wildtype/mutation = allele calls derived from genotypes (WGS hom_ref/hom_var/het -> (1,0)/(0,1)/(1,1); MAD mutant/wildtype from vcf_like GT). Real Sample ID/site/district/region/date. Travel history, travel location, endemicity, study type left BLANK (not captured in sequencing data). Capped to 500 rows/report with "showing N of M" note.
Loaders now retain a per-sample `samples` list and call real_export instead of add_export. Synthetic mock keeps add_export (no real data; labeled synthetic).

**Verify.** Real WGS: WHO/DHIS2 192 rows, AfCDC 500 of ~25932, sample IDs real (SEN_2005_VLG.CXX_0042 etc). MAD: WHO/DHIS2 12, AfCDC 500. Cross-check Bakel/Pfcrt 18/50=36.0% == unit aggregate. jsdom 0 errors, drmap<svg> true, export table renders, no 'MSMT'/McCOIL. Reshipped both real reports.

**Note.** WGS AfCDC wildtype/mutation are allele indicators from genotype calls (sample.tsv has no per-read AD); MAD likewise from GT. If true read-count columns are wanted for AfCDC, source AD (MAD vcf_like has it; WGS would need the VCF).

## 2026-09-24T02:30:00Z — WGS maps now site-level (real coords); explained MAD single-site

**Context.** Jonn: WGS spatial granularity is finer than admin-2 — display it. And MAD maps "all from one place" looks wrong.

**WGS site-level.** sample.tsv has per-sample Site + Latitude/Longitude. Added gen_reports.sites_from_samples() + project() (replicates build_maps.py equirectangular projection via MAP bounds) -> per-site points with real x,y, n, per-marker prevalence, COI/poly, hrp. Loaders now emit rep['sites'] (WGS=28 sites across 16 districts; MAD=1). Template: new siteMap() helper draws collection-site points over the admin-2 outline; Summary "Where sampling happened" and the Resistance prevalence map now render site-level when D.sites present (else fall back to admin-2 choropleth/dotmap for assays without coords). Labels switch site/admin-2 accordingly. Verified: WGS real summary+resistance = 28 circles, MAD = 1, jsdomErr 0; synthetic (no sites) still uses admin-2 maps, ALL CHECKS PASS.

**MAD single-site = correct, not a bug.** Only the KDG_2020_set AmpSeq run succeeded (Kedougou region, Dalaba site, 2020, 68 QC samples). The full 993-sample Senegal_2023 run (2023_data_set) FAILED; the other successful object is Miniset_Test (a test subset). So all real MAD data is one site -> the map shows one point (now visibly a single site point). Multi-site MAD requires the full run to be re-run successfully (or processing the other run subsets).

**Bug caught in passing.** Verified against a stale /workspace copy first (forgot to cp fresh injected files); fixed the process, confirmed on the fresh files, then shipped.

**Outcome.** Reshipped both real reports. WGS now shows true sampling granularity (28 sites); MAD single point is explained by data availability.

## 2026-09-24T04:00:00Z — Why the 993 MAD run failed + made it work via UCSF outputs

**Why it failed.** Submission 475a6685 (01_Illumina_Amplicon_Processing on 2023_data_set) failed at task t_002_cutadapters. That task scatters cutadapt per sample over all 993; 22 samples have BLANK fastq1/fastq2 paths in the manifest (All_2023_Mad4Hatter_runs.tsv) -> those shards have no input file -> cutadapt fails -> Cromwell fails the whole workflow. The KDG_2020 subset that succeeded contained none of the 22. Of the 22: 19 have no good counterpart (real data gaps: SNG23NDO*, SNG23SES1DM*/SES2DM*, SNG23MAD335), 3 are -RC1 duplicates of good samples, plus the DD2 control. (Cromwell metadata for the 2025 run is purged; diagnosed from the bucket task dirs + the run manifest.)

**Made it work WITHOUT re-running Terra.** Jonn pointed at gs://fc-dab15d04-.../cigass_mad4hatter/ucsf_outputs/ — UCSF already ran the mad4hatter (nextflow) pipeline for every sequencing run (out_run1..10 + _new/Repeat + cigass), each with resistance_marker_module/resmarker_table.txt + allele_data.txt. Rewrote load_mad.py to consume these: union marker calls across 15 resmarker tables by base SampleID (strip _S##_L001), join to site via mad_meta.csv (dot decimals; runs.tsv uses comma decimals -> float fails, don't use it), assign admin-2 by point-in-polygon on sen_adm2.geojson. Result: 880 non-control samples, 9 departments, 13 sites, 2020-2023 — the full multi-site cohort, no Terra re-run, no compute spend.

**dhps A437G polarity bug fixed.** resmarker at dhps codon 437 has RefAA=Gly (the panel reference encodes the mutant), so 437G is called REF and 437A is ALT. Matching on AARefAlt==ALT missed it (0%). Fixed by matching the observed AA against the resistance amino acid directly (polarity-independent): A437G now 86.6% (was 0). Same root cause as the WGS A437G=0 (WGS uses genotype columns, left as-is per Jonn "fine for now"). Two schema variants handled (only out_run1 has a Locus column; rest are 11-col).

**Template null-guards.** Full-cohort MAD has no COI yet (allele_data not loaded) -> div.coi null. R.transmission did u.div.coi.toFixed(2) -> threw -> aborted render (resistance map vanished, 1 jsdomError). Guarded coi/poly/mono nulls (show '—'); COI-by-admin2 bars show "not computed" when absent. Verified: WGS real 28 site circles, MAD real 13 site circles, jsdomErr 0, ALL CHECKS PASS; synthetic unaffected.

**Real MAD cohort markers:** crt K76T 67.7%, mdr1 N86Y 22.0%, dhfr N51I/C59R/S108N 97.3/85.5/98.6%, dhps A437G 86.6% / K540E 2.8% / A581G 23.7%, k13 all 0% (no ART-R). cytb unassessed (not in resmarker panel).

**Open:** COI/poly for MAD full cohort (from allele_data.txt, 15x~3MB, not yet loaded); RH/cotx pending. Re-running the Terra 993 set would need the 22 blank-fastq samples fixed first (or the workflow set to tolerate empty shards) — but UCSF outputs already supersede that need.

## 2026-09-24T05:00:00Z — MAD COI from allele_data.txt (labeled naive)

Added coi_from_alleles() to load_mad.py: reads the 15 UCSF allele_data.txt (microhaplotype tables), per base sample computes COI = max distinct alleles at any single locus (within-run diversity, max across runs), poly = >=2 loci with >1 allele. Wired into per-sample -> site + admin-2 aggregation. Labeled everywhere as "naive COI (max distinct microhaplotype alleles per locus)" (ASSAYS coi_method; template shows t.method); NOT McCOIL. Result: national COI 3.16 / poly 92%; per-dept Kedougou 3.65/94%, Diourbel 3.13/92%, etc; per-site COI populated. Verified jsdomErr 0, resistance map 13 site points, transmission renders COI, no McCOIL. Shipped. Naive estimator runs high (single noisy locus inflates max) — labeled as naive; a model-based COI (moire/coiaf) is a future upgrade.

## 2026-09-24T05:30:00Z — Clarified: mad4hatter does not output COI (moire does)

Jonn asked if COI is in the UCSF output folder / thought mad4hatter computes it. Confirmed via full listing (276 objects, not truncated): NO coi/moire/mccoil/complexity/fws file anywhere; parent cigass_mad4hatter/ has only raw_files/ + ucsf_outputs/. mad4hatter = QC + DADA2 denoise + postprocessing + resmarker; outputs allele_data.txt (haplotypes), resmarker, coverage, QC — no COI module. COI is a downstream step: EPPIcenter's moire (Bayesian MCMC; github.com/EPPIcenter/moire) estimates COI/MOI + allele freqs + within-host relatedness from the microhaplotype allele table. UCSF never ran moire -> no COI file. My naive COI (max alleles/locus) is a stand-in, labeled "naive". Offered to run moire in-container on the combined allele_data (would give real eCOI + within-host relatedness/RH). Awaiting go.

## 2026-09-24T06:15:00Z — Removed mock-up banner/disclaimers from the REAL reports

Real reports still showed the synthetic-data warnings (top mockwarn banner, footer "(synthetic data)", methods "Design mock-up … fabricated", resistance caption "prevalence values are synthetic", WHO title "(representative)"). Added meta.real + meta.data_source: assemble_report defaults real=False; loaders set real=True + a provenance string. Template: REAL=!!M.real; top banner now green "REAL DATA · <source>" when real (yellow MOCK-UP only for synthetic); footer, methods Data-status callout, resistance caption, WHO export title all conditional. Verified (jsdom, scripts stripped): both real reports show 0 visible mock/synthetic/fabricated words, banner "REAL DATA · …", footer "v0.6-real (real data)"; synthetic v0.6 still warns. Fixed a version leak: gen_reports reads sys.argv[1] on import so the loader's input path leaked into meta.version -> footer showed /workspace/sample.tsv; loaders now set meta.version='v0.6-real' explicitly. Reshipped both real reports.

## 2026-09-24T07:00:00Z — Summary/diagnostics/export/label polish + MAD HRP2/3 not-assessed

Edits per Jonn: (1) Summary WHO KPI foot now hyperlinks to Resistance tab (showTab). (2) Polygenomic KPI got a method sublabel "share of infections with COI>1 · <coi_method>". (3) Removed "greyed for research prioritisation only" from the diagnostics stoplight finding + trimmed the diagnostics note. (4) Export view titles: dropped "(per-sample schema)" and "(real import schema)". (5) Table column header "Admin-2 unit" -> "Location (Admin Level 2)" (all tables) + summary card title. (6) Top banner: dropped "REAL DATA ·", now shows just meta.data_source (WGS: Illumina WGS · sr-malaria; MAD: MAD4HATTER v4 · UCSF outputs runs 1-10). loader data_source strings cleaned.

MAD HRP2/3: not in the report because the UCSF resmarker+allele outputs carry SNP/microhaplotype calls only, not hrp2/hrp3 deletion (which is a coverage-dropout call). Added diagnostics.assessed=(hrpn>0) in assemble_report; R.diagnostics now returns a "Not assessed in this dataset" callout when false (was showing a misleading 0%); stoplight Diagnostics finding shows "not assessed" when hrpn==0. WGS keeps real hrp2/3 (sample-table columns). Verified jsdom: both real reports err 0, banner=provenance only, WHO link present, poly method label, Location(Admin Level 2) headers, no per-sample/import-schema/greyed-research strings, MAD diag = Not assessed. Reshipped. Offered to add MAD hrp2/3 from amplicon_coverage.txt dropout.

## 2026-09-24T07:40:00Z — Session summary (meeting deadline)

**Decision.** MAD4HATTER HRP2/3 stays "Not assessed in this dataset" (no deletion calls in the UCSF resmarker/allele outputs; faithful calling needs EPPIcenter/copy-number-variation estCNV.Rmd with per-batch 3D7 CNV-controls + batch grouping — code exists, compute is minutes, but total ~30-45 min mostly R install and gated on confirming DC3=3D7 control). Out of time for the meeting; not run.

**Shipped, current, validated (jsdom 0 errors):**
- /workspace/senegal_malaria_surveillance_WGS_v0.6-real.html — real WGS, sr-malaria Senegal joint call: 2,161 QC samples, 16 admin-2, 28 site points, 2005-2023; 12 markers; hrp2 5.3%/hrp3 13.2% (real, greyed/unvalidated); COI from 24-SNP barcode heterozygosity; real-only WHO/AfCDC/DHIS2 export.
- /workspace/senegal_malaria_surveillance_MAD4HATTER_v0.6-real.html — full UCSF cohort (runs 1-10): 880 QC samples, 9 admin-2, 13 site points, 2020-2023; 12 markers (crt K76T 67.7%, dhfr 97/86/99%, dhps A437G 86.6%/K540E 2.8%/A581G 23.7%, k13 0%); naive COI (max alleles/locus) national 3.16/poly 92%; HRP2/3 Not assessed; real-only export.
- Synthetic design mock-ups still at /workspace/senegal_malaria_surveillance_{WGS,MAD4HATTER,NOMADS,COMBINED}_v0.6.html (MOCK-UP banner retained).

**Report reads first:** both real reports show a provenance banner (dataset name), no mock/synthetic language, site-level maps + resistance, WHO-markers link on summary, COI method labelled. Pipeline in /workspace/malaria_reports (gen_reports.py + load_wgs.py + load_mad.py + report_v05.template.html); DATA_IMPORT_PLAN.md documents sources.

**Open (post-meeting):** MAD HRP2/3 + CNV via estCNV (needs control/batch confirmation); MAD/WGS RH+cotx via relatedness (moire/hmmIBD, ~hours); WGS dhps A437G still 0 (pfdhps_Lys_437_Gly polarity bug in the WGS genotype column — MAD gets 86.6% correctly); NOMADS has no workspace yet.

## 2026-09-24T09:30:00Z — Report feedback round: maps, years, turnaround, COI detail, methods links, compressed full export

Implemented Jonn's batch (both real reports + synthetic, jsdom 0 errors):
1. Maps: detail pages (resistance, transmission) now admin-2 CHOROPLETH only (reverted siteMap/circles); summary keeps site-point circles (both allowed there). Verified resistance drmap = 45 polygons / 0 circles; summary = 28 (WGS) / 13 (MAD) site circles. Finer-than-admin-2 shown via site circles on summary + tables; true ADM3 choropleth deferred (needs ADM3 geometry) — noted.
2. Years: added fmt_years (Python) + fmtYears (JS) — contiguous runs use en-dash, non-contiguous use commas. WGS period '2005–2023' (contiguous); MAD '2020, 2023' (non-contiguous → comma). Units carry full year lists; used for meta.period, per-unit collection window, WHO/DHIS2 export year.
3. Removed turnaround everywhere (methodTile row + meta.turnaround field). Confirmed gone from data + rendered text.
4. COI method detail: per-assay coi_detail string (WGS = 24-SNP barcode heterozygosity proxy; MAD = naive max-distinct-microhap-alleles-per-locus, poly if ≥2 loci multiallelic; explicitly "not moire/McCOIL") shown on Methods tab.
5. Methods tab: added Pipelines & data sources card with real links (MAD4HATTER GitHub+docs+copy-number repo+Terra featured workspace; NOMADS GitHub+nomadic; WGS sr-malaria workspace + Pf7 + PlasmoDB) + the COI-method card.
6. Export = ALL data, compressed. real_export/add_export now embed the FULL WHO/AfCDC/DHIS2 tables as gzip+base64 (via _pack_export) + a 200-row on-screen preview + row count; download decompresses client-side (DecompressionStream, no lib) and rebuilds the CSV, with a progress-bar modal. Verified round-trip: WGS afcdc 20,461 rows / MAD 10,012 rows decompress intact; HTML stays ~360–460 KB (gz: afcdc 102/46 KB) instead of embedding ~3 MB uncompressed.

Deferred/notes: ADM3-level choropleth (needs geoBoundaries SEN ADM3 + sites→ADM3 aggregation) — detail maps are admin-2 for now; granularity visible on summary + tables. DHIS2 period now uses the same comma/dash year string.

## 2026-09-24T10:00:00Z — Fix: stale bold outline when clicking circle→circle

pickRegion() and clearRegions() cleared only `path.region-sel`, so clicking one site circle then another left the first circle's `.region-sel` (bold outline, generic CSS) applied. Changed both querySelectors to `.region-sel` (any element). jsdom: two successive circle clicks now leave exactly 1 selected. Rebuilt + reshipped real + synthetic.

## 2026-09-24T10:45:00Z — Added Africa CDC Mutation/Haplotype export (main) + renamed old to Marker-Centric

Read Africa MMS_Data_Sheet_Final_2026.xlsx (sheet Mutation_Haplotype, 17 cols: Sample ID, Host subject ID, Date MMM-YYYY, Facility, Country, Region/Province Admin1, District Admin2, Study type, Gene symbol, Gene Alteration, Haplotype, Travel Y/N, 3x Destination, Endemicity, Assay). Implemented as the primary "Africa CDC" export view (one row per sample x observed mutant alteration). Renamed the prior per-sample x codon (wildtype/mutation counts) view to "AF-CDC Marker-Centric" (keeps the denominator). Export is now 4 view-driven tabs: WHO Threat Maps, Africa CDC, AF-CDC Marker-Centric, DHIS2 — built from D.export.order + per-view label/title/name. Refactored _pack_export to take rows_by_key+order; both real_export and synthetic add_export produce all four. Added _mmm_yyyy date formatter + VIEW_META. Verified jsdom 0 errors (both), 4 buttons, Africa CDC gz round-trips (WGS 6660 / MAD 4036 mutant-alteration rows), Marker-Centric (WGS 20461 / MAD 10012). Reshipped.

## 2026-09-24T11:20:00Z — Added PHA4GE Malaria Community Standard export view

Read MalariaCommunityStandard_human_draft1_refined5.xlsx (sheet 'Template Example HumanSample' = 210-field per-specimen standard). Dumped field order to pha4ge_fields.json. Added a 'pha4ge' export view (build_pha4ge): one row per sample × observed mutant alteration; fills the ~19 fields our data supports (specimen_collector_sample_ID; geo country/state-province=region/county-region=district/city=site; lat/long; sample_collection_date + precision; organism=P.falciparum; host taxid/common/scientific=human; sequencing_assay_type; sequencing_instrument=platform; multiplicity_of_infection=COI; gene_name/gene_symbol/gene_alteration), everything else blank per real-only. Wired into real_export + synthetic add_export via _pack_export; VIEW_META + order now who, afcdc(Africa CDC), afcdc_mc(Marker-Centric), pha4ge(PHA4GE), dhis2. Template export UI is view-driven so 5 tabs appear automatically. Verified jsdom 0 errors, 5 buttons, PHA4GE 210 cols × 6660(WGS)/matching(MAD) rows, gz round-trips, geo mapping correct (Admin1=state/province, Admin2=county/region, site=city). Note: PHA4GE 210-col table grew HTML to ~1.9 MB each (compressed blob dominates); still self-contained. Reshipped.

## 2026-09-24T11:40:00Z — Version bump to v0.7

Bumped single-source version: gen_reports VERSION default v0.6->v0.7; build_reports.sh default ->v0.7; loaders meta.version 'v0.6-real'->'v0.7-real'. Rebuilt synthetic (senegal_malaria_surveillance_{WGS,MAD4HATTER,NOMADS,COMBINED}_v0.7.html) + real (WGS,MAD _v0.7-real.html). jsdom 0 errors; footer/badge show v0.7 (synthetic) / v0.7-real (real). Removed superseded v0.4/v0.5/v0.6 HTML from /workspace to avoid version leaks. Current shipped set = v0.7 (4 synthetic) + v0.7-real (WGS, MAD).

## 2026-09-24T12:00:00Z — Export note now per-format/per-tab

Removed the universal export note (was one callout above all views). Added a per-view note to VIEW_META (4-tuple: label,name,title,note) -> _pack_export stores views[k].note; wireExport render() shows it inside the active tab's card only. Notes are format-specific (WHO layout / Africa CDC Mutation-Haplotype / AF-CDC Marker-Centric denominator / PHA4GE 210-field / DHIS2 dataValueSet). Verified jsdom 0 errors, 0 callouts outside exportview, correct note per tab on switch. Rebuilt + reshipped v0.7 real + synthetic.

## 2026-09-24T18:40:00Z — Rebuilt both real reports in fresh container from copied data

**Context.** Jonn copied the real inputs into this container and relayed a command from a prior session: `./build_real_reports.sh sample.tsv rm mad_meta.csv ad`. Bare filenames were wrong for this container — the script cd's to its own dir and the data lives elsewhere: sample.tsv at /workspace/data/, and rm/ (15 resmarker tables), ad/ (15 allele tables), mad_meta.csv at /workspace/fiss_downloads/.

**Action.** Ran with absolute paths: `./build_real_reports.sh /workspace/data/sample.tsv /workspace/fiss_downloads/rm /workspace/fiss_downloads/mad_meta.csv /workspace/fiss_downloads/ad`. Both loaders + gen self-checks passed (ALL CHECKS PASS).

**Evidence (matches prior session exactly).** WGS: 2,161 QC of 3,473, 16/45 depts, 28 sites, 2005–2023; crt K76T 50.5%, dhfr 94.9/95.3/96.9%, dhps K540E 5.1%, dhps A437G 0% (known upstream pfdhps_Lys_437_Gly polarity bug, unchanged), k13 0%; hrp2 5.3%/hrp3 13.2%; COI 1.65/poly 22%. MAD: 880 samples (28 controls + 29 no-dept dropped), 9 depts, 13 sites, 2020+2023; crt K76T 67.7%, dhps A437G 86.6%, A581G 23.7%, k13 0%; naive COI 3.16/poly 92%; HRP2/3 Not assessed. jsdom (fresh install, scratchpad): 0 errors both, drmap 45 admin-2 polygons, summary 28/13 site circles, 5 export tabs, no visible mock/synthetic/undefined text ("McCOIL" hits are the deliberate Methods coi_detail disclaimer). 

**Outcome.** senegal_malaria_surveillance_{WGS,MAD4HATTER}_v0.7-real.html rebuilt in /workspace/malaria_reports/ and copied to /workspace/ (shipped set). Reproducibility of the v0.7-real build from raw inputs in a clean environment confirmed.

## 2026-09-24T19:45:00Z — Repository reorganized from flat layout into folders

**Context.** Repo was flat (30 tracked files at root: scripts, template, reference data, schema xlsx, built HTML, docs). Jonn asked for a sensible folder structure (formats / data / artifacts / scripts separated).

**Decision / action.** New layout: `scripts/` (gen_reports.py, load_wgs.py, load_mad.py, build_maps.py), `templates/` (report_v05.template.html), `reference/` (sen_adm2 geo + who_* compendium + m4h_*/mad_resmarker panel refs + wgs_loc.csv + mad_site_to_admin2.json), `schemas/` (Africa CDC + PHA4GE xlsx + pha4ge_fields.json — export-format specs), `reports/` (built HTML; synthetic committed, *-real ignored), `build/` (data_*.json intermediates, git-ignored), `docs/` (DATA_IMPORT_PLAN.md). Entry-point shell scripts + README + JOURNAL stay at root. Path fixes: gen_reports.py now resolves reference/schemas/build via repo ROOT (script-relative); load_mad geojson via ../reference; build_maps reads/writes reference/; both .sh scripts point at scripts/, templates/, build/, reports/. .gitignore: data_*.json rule replaced by build/; real-report pattern generalized to *-real.html. README layout section rewritten.

**Evidence.** Full pipeline re-run from new layout: build_maps OK (45 depts), synthetic v0.7 ALL CHECKS PASS (4 reports), real build from copied data ALL CHECKS PASS (WGS 2161 QC/28 sites; MAD 880/13 sites — same numbers as pre-reorg). jsdom: 0 errors, 45 choropleth shapes, 5 export tabs on WGS-real, MAD-real, WGS-synthetic. Rebuilt WGS-real byte-identical to pre-reorg shipped copy; MAD-real differs only in JSON dict key order (set-iteration nondeterminism under hash randomization, pre-existing; values identical). Shipped copies at /workspace refreshed.

**Outcome.** Repo navigable by role; git history preserved via renames (git mv). Real data & reports remain excluded.

## 2026-09-24T20:30:00Z — v0.8: removed Diagnostics (HRP2/3) and Transmission (COI) sections entirely

**Context.** Jonn: v0.8 = drop the COI tab and the HRP2/3 tab completely for the first release; make the rest of the document consistent; regenerate everything including real data.

**Changes.** Template (report_v05.template.html): deleted R.diagnostics + R.transmission renderers (~6 KB), LABEL/CATS/jump reduced to resistance-only, stoplight sec-desc reworded (no 5% RDT-switch mention), polygenomic Summary KPI removed, Methods lost the COI-method card + hrp/transmission threshold bullets + "COI method noted on the Transmission tab" phrase. gen_reports.py: assemble_report no longer computes/emits diagnostics or transmission (per-unit hrp/div inputs from loaders accepted but stripped before emission — loaders unchanged except version string); stoplight = Resistance Markers card only; tabs = summary/resistance/export/methods; meta drops hrp_action_pct + coi_detail; sites drop coi/poly/hrp fields; build_combined updated to match (no longer reads reports[..]['transmission'/'diagnostics'], which would have crashed); PHA4GE export no longer fills multiplicity_of_infection; synthetic AfCDC Endemicity now blank (was derived from polygenomic fraction); dead COI_DETAIL/endem code removed; self-checks assert diagnostics/transmission absent from tabs and report keys. Version single-source bumped v0.7→v0.8 (gen default, build_reports.sh, build_real_reports.sh, loader meta v0.8-real). README rewritten for single-domain scope with a v0.8 note.

**Verify.** All 6 reports rebuilt (4 synthetic ALL CHECKS PASS + WGS/MAD real from the copied inputs, same marker numbers: crt 50.5%/67.7%, n=2161/880). jsdom on all 6: 0 errors, nav = Summary·Resistance Markers·Export·Methods, 1 stoplight card, 45 choropleth shapes, 5 export tabs, no empty pages, and ZERO visible occurrences of HRP2/HRP3/COI/polygenomic/transmission/diagnostics/RDT/McCOIL. v0.7 HTML removed (git rm for synthetic; local delete for real + /workspace copies).

**Outcome.** Shipped v0.8 set: reports/ in-repo (synthetic committed, *-real ignored) + /workspace/senegal_malaria_surveillance_{WGS,MAD4HATTER}_v0.8-real.html. HRP/COI computation paths in the loaders are intact, so re-enabling the sections later is an assemble_report/template change only.

## 2026-09-24T21:15:00Z — Summary site map: choropleth region backdrop + clickable regions

Jonn: summary map circles should sit on a region choropleth (shaded by total samples), regions clickable for their region-total like the other maps, circles keep working. siteMap() polygons now binned-BLU by per-unit QC-pass n ("nice" bins via nBreaks), clickable via the shared pickRegion (readout: "N QC-pass samples (region total)"); legend added (binnedLegend gained showSupp flag — no suppression key for raw counts); hint text updated. Circles untouched. jsdom click simulation: region click pins the total, subsequent circle click replaces the selection (1 selected element), 0 errors; WGS-real 16 shaded regions/28 circles, MAD-real 9/13. Synthetic reports use the dotmap branch (no site coords) — already clickable, unchanged. Rebuilt + reshipped all.

## 2026-09-28T00:45:00Z — Summary/marker-table feedback batch + WHO marker expansion + table widget

**Jonn's batch (all implemented, template + gen_reports):** (1) "What this is" banner rewritten per assay to describe only what v0.8 shows (SNP marker prevalence; dropped CNV/species/transmission claims). (2) Summary marker table drops the WHO-criterion column (mkRow(summary) variant). (3) Heading "Summary — concerns for this population" -> "Summary". (4) New summary description: WHO markers ≥10% aggregated across years, click to details. (5) Status word ("Concern") removed from the card. (6) Research-markers KPI removed; remaining two KPIs auto-fill the row. (7) Marker catalogue expanded 16->27: +9 WHO-validated pfk13 (F446I N458Y C469Y M476I Y493H R539T I543T P553L P574L), +dhfr_I164L, +dhps_A613S — chosen after checking both datasets type those codons (WGS genotype columns; MAD resmarker). WGS now maps 22/27 (was 12/16), assessed WHO markers 21 (was 11); MAD 23. (8) methodTile "Marker genes typed" (gene count) -> "Markers typed" = assessed marker count (WGS 22 / MAD 23 / NOMADS 23 — differs per assay as required). (9) Locations table gains bold TOTAL row (M.n_qc + full period).

**Mid-turn additions:** resistance marker-table rows are now clickable — row click selects that marker in the choropleth selector, redraws the map, highlights the row (new tr.region-sel CSS; .region-sel stroke rule is SVG-only), scrolls the map card into view. New filter/sort widget above the table: Show (all / WHO-tracked / research / ≥10%), numeric min-prevalence input, Sort (gene order / prevalence desc / asc); rebuilds tbody via shared mkRow, respects the existing per-marker toggles.

**Side effect (explained, kept).** MAD cohort n 880 -> 881: one sample's only resmarker calls are at newly-added codons; previously matched zero report markers and was dropped from aggregation.

**Verify (jsdom, WGS-real + MAD-real + NOMADS + COMBINED).** 0 errors; summary head has 7 cols (no criterion); sec-desc/heading/no-Concern/2-KPIs/bold-TOTAL all confirmed; widget: filter all->WHO->action->minprev row counts 22->21->5->4 (WGS), sort desc verified monotonic, row click drives #drsel (clickDrivesMap true both real reports).

## 2026-09-29T01:30:00Z — Marker catalogue rebuilt from source: 16 -> 80, WHO evidence classes + per-panel background markers

**Context.** Jonn: "make sure you've got all the markers now. For Mad4Hatter and NOMADS, I imagine they have their own markers. Those should be counted, but labeled properly. look it up."

**What I looked up (three authoritative sources, not memory).**
1. `reference/who_combined.json` (WHO Compendium, 117 entries) grouped by class: 29 "Validated (Epi.,Lab.&Clin.)" + 1 "Validated (Lab.&Clin.)", 8+18 Candidate, 9+3+43 Potential. This gave the real WHO tiering per gene/alteration, including markers we never had: Pfcrt T93S/H97Y/F145I/I218F/C350R/M343L/G353V/C101F (piperaquine), nine more WHO-confirmed Pfk13 codons, Pfcoronin G50E/R100K/E107V as WHO *potential* (lab), Pfdhfr I164L/A16V, Pfdhps S436A/A613S/A613T/I431V, Pfmdr1 S1034C/N1042D/D1246Y, Pfcytb Y268C.
2. Codons actually typed by WGS: enumerated the `pf<gene>_<Aaa>_<pos>_<Aaa>` columns in the real sample.tsv — 18 k13, 10 crt, 6 dhps, 5 each mdr1/dhfr/carl, 4 each coronin/aat1, 1 each ubp1/mdr2/exo/atg18/arps10/ap2-mu.
3. Codons actually typed by MAD4HATTER: enumerated Gene+CodonID across all 15 UCSF resmarker tables — crt 17, k13 63, dhfr 6, dhps 6, mdr1 8, mdr2 4, coronin 3, arps10 2, fd, exo, ubp1, pib7, csp 17, Rh5, Ripr.

**Correction to a previous entry.** See 2026-09-23T00:30Z, which recorded "NO coronin, NO ubp1, NO ap2mu in the principal resmarker table". The *deployed* UCSF panel output does type coronin (50/100/107) and ubp1 (1525); that conclusion came from the older principal_resistance_marker_info_table.tsv, not the shipped panel. ASSAYS comment + MAD note corrected in place.

**New catalogue (scripts/gen_reports.py).** 80 markers with an explicit evidence class: `confirmed` (WHO highest class) / `candidate` / `potential` (incl. codons WHO lists only inside haplotypes, e.g. the Pfcrt CQ haplotype components and the Pfmdr1 1034/1042/1246 trio) / `background` (panel loci WHO does not track: Pfarps10 V127M+D128H, Pffd D193Y, Pfmdr2 T484I, Pfexo E415G, Pfmdr1 Y184F) / `research` (Pfaat1 x4, Pfcarl x4, Pfatg18, Pfcoronin P76S, Pfubp1 x2, Pfap2-mu). Never uses the word "validated" (self-check still enforces this) — tiers read "WHO-tracked / WHO candidate / WHO potential". Action flag (>=10% TES) now fires only on WHO-confirmed markers; stoplight escalation likewise. Deliberately excluded: amplification markers (Pfmdr1/Pfpm2-3/Pfgch1 — CNV not in v0.8), the ~40 remaining k13 propeller codons MAD scans but WHO does not name, and the panel's csp/Rh5/Ripr vaccine/invasion loci (not drug resistance).

**Per-assay counts now differ as intended.** Assessed markers: WGS real 56, MAD4HATTER real 54, NOMADS 57 (synthetic; core 5 genes only), COMBINED 80. WGS marker->column mapping went 22/27 -> 57/80.

**Loader fix (real correctness bug this exposed).** load_wgs matched columns on (gene, codon) only, so the new dhps A613S/A613T pair collided (last-wins) and the k13 553/574 columns with mis-annotated reference AAs were picked arbitrarily. Now matches (gene, codon, refAA, altAA) exactly, falling back to (gene, codon, altAA) then codon. A437G still maps to the mis-annotated `pfdhps_Lys_437_Gly` via the alt-AA fallback, preserving the known upstream-bug behaviour rather than silently dropping it.

**Template.** Status column renders the class with its own pill style (WHO-tracked / candidate / potential / panel-background / research, criterion on hover); summary table now filters to WHO-tracked markers >=10% (matches its description); filter widget gained per-class options; Methods documents the class scheme.

**Verify (jsdom, all 4 + real).** 0 errors. Filter counts WGS-real all/who/confirmed/candidate/potential/background/research/action = 56/40/16/8/16/4/12/10; MAD-real 54/53/20/14/19/1/0/15. Summary shows only WHO classes (7 rows WGS, 14 MAD). "validated" absent from rendered text. Export blobs round-trip: WGS who 894 / afcdc 10,753 / marker-centric 92,321 / PHA4GE 10,753x210 cols / DHIS2 894. New real values look right: Pfcrt CQ-haplotype components track K76T (67.7% MAD), Pfdhps S436A 59.1%, A613S 32.4%, I431V 25.3%, Pfaat1 S258L 85.1% (WGS), all k13 confirmed markers 0%.

## 2026-09-29T02:00:00Z — Version bump to v0.9

Single-source bump v0.8 -> v0.9: gen_reports VERSION default, build_reports.sh default, build_real_reports.sh VER, loader meta.version 'v0.9-real'; README + REPLICATION.md paths; .gitignore superseded-version pattern widened to v0.[0-8]. Historical "v0.8:" comments in gen_reports (why COI/HRP were removed) left as-is — they date the change, not the current version. README scope note reworded to "since v0.8" + a v0.9 line for the 80-marker catalogue. Rebuilt all 6 (synthetic v0.9 x4 + real WGS/MAD v0.9-real), removed superseded v0.8 HTML from reports/ and /workspace. jsdom 0 errors; rendered version strings are v0.9 / v0.9-real only (no v0.8 leak); markers typed WGS-real 56, MAD-real 54, WGS-synth 77, NOMADS 57.

## 2026-09-29T03:00:00Z — Marker toggles: real abbreviations + spelled-out class key + gene-grouped grid

**Problem (Jonn).** After the 80-marker expansion the toggle pills showed `(m.cls).slice(0,4)` — "conf/cand/pote/back/rese" — visually cut off and unexplained, and 56-80 toggles in a `display:flex;flex-wrap` row looked ragged and disorganised.

**Fix.** (1) Real abbreviations: CLSABBR = WHO / CAN / POT / BKG / RES, each keeping its class pill colour. (2) New `classLegend()` renders a key mapping each coloured pill -> full label -> one-line meaning (CLSFULL + CLSDESC), placed directly under the section description on BOTH the Summary and the Resistance sections (both show the pills). (3) Toggles regrouped: one bordered block per gene (gene name + marker count + PlasmoDB ID), chips inside a `repeat(auto-fill,minmax(136px,1fr))` grid with the pill pushed right by `margin-left:auto`, so columns and pills line up; the chip text is now just the AA change (gene is the block header), which is what stopped the clipping. Blocks themselves sit on a `repeat(auto-fit,minmax(330px,1fr))` grid. (4) Added per-gene "all / none" links (genuinely useful at this marker count) that flip the group's checkboxes and re-dispatch change so the existing row-hide/selector-disable wiring runs unchanged. Full marker detail (gene, AA, class, WHO criterion) is on each chip's tooltip.

**Also fixed.** NOMADS assay note claimed the panel carries no background loci, but Pfmdr1 Y184F is on it — reworded to name the dedicated background loci it lacks (Pfarps10/Pffd/Pfmdr2/Pfexo) while acknowledging Y184F.

**Verify (jsdom, all 6).** 0 errors; 0 truncated class stubs remain; 2 legend blocks per report (Summary + Resistance) listing WHO/CAN/POT/BKG/RES with full labels; gene groups WGS-real 14, MAD-real 5, NOMADS 5, COMBINED 16; longest chip label 6 chars; per-gene "none" on Pfk13 hides exactly that gene's rows (WGS 56->42, MAD 54->31) and "all" restores.

## 2026-09-29T03:40:00Z — Verified shipped v0.9 set; found and fixed build non-reproducibility

**Context.** Jonn asked whether the latest versions are updated. Mtime comparison was inconclusive (source edit and build landed in the same second), so I verified by content and by rebuilding.

**Content verification.** All 8 shipped files (6 in reports/, 2 copies at /workspace) carry every feature from the last several commits: 80-marker catalogue, class abbreviations + `classLegend()` + `.clslegend` CSS, gene-grouped `.tgroups` toggles with per-gene all/none (`data-gsel`), marker-table filter widget incl. the `background` option, row-click-to-map, `siteLegend`, region-total choropleth backdrop, bold TOTAL row, "Markers typed" tile, and the summary table's suppressed WHO-criterion column. meta.version reads v0.9 (synthetic) / v0.9-real. No v0.[0-8] artifacts anywhere. Real reports in reports/ and /workspace are byte-identical (md5 match).

**Finding: synthetic mock-ups were not reproducible.** Rebuilding from unchanged sources produced a different DATA blob every time (WGS n_qc 364 -> 350, different sampled departments). Root cause: `build_assay` seeded with `random.seed(hash(name)%2**31)` — `str.__hash__` is salted by PYTHONHASHSEED, which Python randomises per process. So the committed synthetic reports could never be regenerated, and any earlier claim that a rebuild was "byte-identical" held only by luck within a single process. Fixed with `zlib.crc32(name.encode())` (same for the synthetic AfCDC seed).

**Second, smaller cause (real reports).** `load_mad` built each sample's `calls` dict by iterating the `cov[b]` **set**, so the per-sample AfCDC/PHA4GE export row order tracked PYTHONHASHSEED — this is the "key order" difference noted at 2026-09-24T19:45Z, now diagnosed rather than assumed. Fixed by iterating `sorted(cov[b])`.

**Evidence.** Two consecutive synthetic builds now byte-identical; identical again under PYTHONHASHSEED=1. Real reports byte-identical across PYTHONHASHSEED=0/5/42 (WGS md5 2a3fbcb4224f, MAD 867b6205ae74 in all three). jsdom across all 6: 0 errors, 4 nav tabs, 45 choropleth polygons, 5 export tabs, no empty pages.

**Outcome.** Everything shipped is current, and the build is now deterministic — a rebuild from a clean checkout reproduces the committed synthetic reports exactly, which is what makes the committed HTML auditable.

## 2026-09-30T00:20:00Z — Marker table: filter for TES-flagged markers

Jonn: add a filter for markers that indicate a TES. Added `<option value="tes">Flagged — WHO criteria indicates TES</option>` to the marker-table Show filter, backed by `rows.filter(m=>m.action)` — i.e. the report's existing action flag (WHO-confirmed class AND prevalence ≥10%), not merely ≥10%. Kept the pre-existing threshold option but relabelled it "≥10% prevalence (any class)" so the two are distinguishable: on real WGS, TES = 2 markers (Pfcrt K76T 50.5%, Pfmdr1 N86Y 11.9%) while any-class ≥10% = 10 (which includes WHO-potential dhfr/dhps, background Pfmdr1 Y184F and research Pfaat1 S258L — none of which carry the TES flag).

Verified (jsdom, 3 reports): filter output matches `markers.filter(assessed && action)` from the embedded DATA exactly, every returned row shows the TES flag pill, and each report's count is right (WGS-real 2, MAD-real 2, NOMADS 1). 0 errors; standard checks still pass.
