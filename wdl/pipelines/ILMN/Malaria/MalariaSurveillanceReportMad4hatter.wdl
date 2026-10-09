version 1.0

import "../../../tasks/Malaria/SurveillanceReport.wdl" as MSR
import "../../../tasks/Utility/Finalize.wdl"           as FF

workflow MalariaSurveillanceReportMad4hatter {

    meta {
        description: "Build the malaria molecular-surveillance report for a MAD4HATTER amplicon cohort. Inputs are the per-run resistance-marker tables and a per-sample site/coordinate table, optionally with the microhaplotype allele tables; output is a single self-contained HTML report plus the data model behind it and the dashboard export tables (WHO Malaria Threats Map, DHIS2, Africa CDC, PHA4GE)."

        outputs: {
            report_html:      "Self-contained single-file HTML surveillance report",
            report_data_json: "The report's data model (every number the report draws)",
            export_csvs:      "Dashboard-ready export tables, one CSV per view",
            finalized_dir:    "GCS directory the outputs were copied into, when gcs_out_root_dir was given"
        }
    }

    parameter_meta {
        resmarker_tables:         "MAD4HATTER resistance-marker tables (resmarker_table.txt), one per sequencing run"
        site_metadata:            "Per-sample site and coordinate table (Sample_id, site, Latitude, Longitude)"
        allele_tables:            "MAD4HATTER microhaplotype allele tables (allele_data.txt); optional"
        cohort_name:              "Cohort label; used in the output directory path and output filenames"
        version_label:            "Version string stamped on the report (e.g. v0.13)"
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
        Array[File] resmarker_tables
        File site_metadata

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
    }

    # a sample_set's membership arrives as an array; a curated list arrives as a file
    Boolean have_sample_array = length(sample_ids) > 0
    File? selected_ids_file = if have_sample_array then write_lines(sample_ids) else sample_id_list

    String outdir = sub(select_first([gcs_out_root_dir, "."]), "/$", "") + "/MalariaSurveillanceReportMad4hatter/~{cohort_name}"

    call MSR.RenderMad4hatterReport as t_01_RenderReport {
        input:
            resmarker_tables         = resmarker_tables,
            site_metadata            = site_metadata,
            allele_tables            = allele_tables,
            cohort_name              = cohort_name,
            version_label            = version_label,
            data_source              = data_source,
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
        String? finalized_dir    = t_02_FinalizeReport.gcs_dir
    }
}
