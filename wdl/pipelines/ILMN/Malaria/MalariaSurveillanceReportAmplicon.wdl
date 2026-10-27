version 1.0

import "../../../tasks/Malaria/SurveillanceReport.wdl" as MSR
import "../../../tasks/Utility/Finalize.wdl"           as FF
import "../../../tasks/Utility/TerraEnvInfo.wdl"       as TERRA
import "../../../tasks/Utility/TerraEntities.wdl"      as TE

workflow MalariaSurveillanceReportAmplicon {

    meta {
        description: "Build the malaria molecular-surveillance report for any short-read amplicon cohort. The panel is detected from the loci present in the input, so one workflow serves MAD4HatTeR, PfPHAST and panels that are not catalogued; set assay to declare it instead. Input is the per-sample Terra table (fetched from the data model when no files are given) or the pipeline's per-run resistance-marker tables; output is a single self-contained HTML report plus the data model behind it, the dashboard export tables (WHO Malaria Threats Map, DHIS2, Africa CDC, PHA4GE) and a location-resolution audit."

        outputs: {
            report_html:      "Self-contained single-file HTML surveillance report",
            report_data_json: "The report's data model (every number the report draws)",
            export_csvs:      "Dashboard-ready export tables, one CSV per view",
            location_audit:   "Location-resolution audit: how samples were placed, and every unplaced name, coordinate/name disagreement and region mismatch",
            finalized_dir:    "GCS directory the outputs were copied into, when gcs_out_root_dir was given"
        }
    }

    parameter_meta {
        resmarker_tables:         "MAD4HATTER resistance-marker tables (resmarker_table.txt), one per sequencing run"
        site_metadata:            "Per-sample site and coordinate table; optional when the per-sample Terra table already carries geography"
        allele_tables:            "MAD4HATTER microhaplotype allele tables (allele_data.txt); optional"
        cohort_name:              "Cohort label; used in the output directory path and output filenames"
        version_label:            "Version string stamped on the report (e.g. v0.12)"
        data_source:              "Provenance line shown in the report banner"
        render_config_json:       "JSON settings file for the renderer; unrecognised keys pass through to the report metadata, so new rendering features need no change to this interface"
        report_template_override: "Replacement report template (HTML); omit to use the template pinned by the docker image"
        reference_bundle_tar:     "tar(.gz) of replacement reference data (admin boundaries, WHO compendium); omit to use the bundle pinned by the docker image"
        country_iso3:             "ISO3 code selecting the admin-2 boundary set (51 malaria-endemic African countries ship in the image; SEN by default)"
        country_name:             "Country name shown in the report"
        sample_ids:               "Sample ids to report on; on a Terra sample_set use this.samples.sample_id. Empty means every sample in the inputs"
        sample_id_list:           "Alternative to sample_ids: a file with one sample id per line (# comments allowed)"
        selection_label:          "Human-readable name for the sample selection, shown in the report (e.g. the sample_set name)"
        gcs_out_root_dir:         "GCS bucket to copy the report into; omit to leave outputs in the execution directory"
    }

    input {
        Array[File] resmarker_tables = []

        # Leave resmarker_tables empty on Terra and the per-sample table is fetched from
        # the data model directly: get_terra_env_info says which workspace and table this
        # was launched from, download_terra_entity_table pulls the rows. Overrides below
        # for running outside a submission, or against a different table.
        String? sample_table
        String? entity_set_type
        String? entity_set_name
        File? site_metadata

        Array[File] allele_tables = []
        String cohort_name

        String? version_label
        String? data_source
        File? render_config_json
        File? report_template_override
        File? reference_bundle_tar
        String? country_iso3
        String? country_name
        Array[String] sample_ids = []
        File? sample_id_list
        String? selection_label
        String? gcs_out_root_dir

        # Which panel produced this? Default detects it from the loci and tolerates panels
        # that are not catalogued. Naming MAD4HATTER or PFPHAST declares it instead: the
        # declaration is kept and any disagreement with the detected panel is reported.
        String assay = "AMPLICON"
    }

    # Self-identify the Terra workspace, the per-sample table and the row(s) this was
    # launched from, so the report can state its own provenance instead of relying on
    # whoever typed data_source. Off Terra the task returns empty strings and the
    # select_first below falls back to the supplied value.
    call TERRA.get_terra_env_info as t_00_TerraEnv { input: }

    String detected_source = if t_00_TerraEnv.is_running_on_terra
        then t_00_TerraEnv.workspace_namespace + "/" + t_00_TerraEnv.workspace_name
             + " \u00b7 table " + t_00_TerraEnv.sample_table
             + " \u00b7 submission " + t_00_TerraEnv.top_level_submission_id
        else ""

    # Declared inside the conditional so it stays optional outside it: an explicit
    # data_source wins, else the detected one, else nothing - which leaves the loader's own
    # default in place rather than stamping the report "unspecified".
    if (!defined(data_source) && detected_source != "") {
        String only_detected = detected_source
    }
    String? resolved_source = if defined(data_source) then data_source else only_detected

    # No files given means: fetch the table this submission was launched from.
    Boolean fetch_from_terra = length(resmarker_tables) == 0

    if (fetch_from_terra) {
        call TE.download_terra_entity_table as t_00b_FetchTable {
            input:
                namespace       = t_00_TerraEnv.workspace_namespace,
                workspace       = t_00_TerraEnv.workspace_name,
                entity_type     = select_first([sample_table, t_00_TerraEnv.sample_table]),
                entity_set_type = entity_set_type,
                entity_set_name = entity_set_name
        }
    }

    Array[File] marker_inputs = if fetch_from_terra
        then select_all([t_00b_FetchTable.table_tsv])
        else resmarker_tables

    # a sample_set's membership arrives as an array; a curated list arrives as a file
    Boolean have_sample_array = length(sample_ids) > 0
    File? selected_ids_file = if have_sample_array then write_lines(sample_ids) else sample_id_list

    String outdir = sub(select_first([gcs_out_root_dir, "."]), "/$", "") + "/MalariaSurveillanceReportAmplicon/~{cohort_name}"

    call MSR.RenderAmpliconReport as t_01_RenderReport {
        input:
            assay                    = assay,
            resmarker_tables         = marker_inputs,
            site_metadata            = site_metadata,
            allele_tables            = allele_tables,
            cohort_name              = cohort_name,
            version_label            = version_label,
            data_source              = resolved_source,
            render_config_json       = render_config_json,
            report_template_override = report_template_override,
            reference_bundle_tar     = reference_bundle_tar,
            country_iso3             = country_iso3,
            country_name             = country_name,
            sample_ids_file          = selected_ids_file,
            selection_label          = selection_label
    }

    if (defined(gcs_out_root_dir)) {
        call FF.FinalizeToDir as t_02_FinalizeReport {
            input:
                files  = flatten([[t_01_RenderReport.report_html, t_01_RenderReport.report_data_json],
                                  t_01_RenderReport.export_csvs]),
                outdir = outdir
        }
    }

    output {
        File report_html         = t_01_RenderReport.report_html
        File report_data_json    = t_01_RenderReport.report_data_json
        Array[File] export_csvs  = t_01_RenderReport.export_csvs
        File location_audit      = t_01_RenderReport.location_audit
        String? finalized_dir    = t_02_FinalizeReport.gcs_dir
    }
}
