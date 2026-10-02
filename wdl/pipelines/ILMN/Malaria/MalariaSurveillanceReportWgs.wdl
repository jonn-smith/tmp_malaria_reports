version 1.0

import "../../../tasks/Malaria/SurveillanceReport.wdl" as MSR
import "../../../tasks/Utility/Finalize.wdl"           as FF

workflow MalariaSurveillanceReportWgs {

    meta {
        description: "Build the malaria molecular-surveillance report for a short-read whole-genome cohort. Input is a Terra export of the WGS sample table carrying per-amino-acid genotype columns; output is a single self-contained HTML report plus the data model behind it and the dashboard export tables (WHO Malaria Threats Map, DHIS2, Africa CDC, PHA4GE)."

        outputs: {
            report_html:      "Self-contained single-file HTML surveillance report",
            report_data_json: "The report's data model (every number the report draws)",
            export_csvs:      "Dashboard-ready export tables, one CSV per view",
            finalized_dir:    "GCS directory the outputs were copied into, when gcs_out_root_dir was given"
        }
    }

    parameter_meta {
        sample_table_tsv:         "Terra export of the WGS `sample` table (TSV) with per-amino-acid genotype columns"
        cohort_name:              "Cohort label; used in the output directory path and output filenames"
        version_label:            "Version string stamped on the report (e.g. v0.11-real)"
        data_source:              "Provenance line shown in the report banner"
        render_config_json:       "JSON settings file for the renderer; unrecognised keys pass through to the report metadata, so new rendering features need no change to this interface"
        report_template_override: "Replacement report template (HTML); omit to use the template pinned by the docker image"
        reference_bundle_tar:     "tar(.gz) of replacement reference data (admin boundaries, WHO compendium); omit to use the bundle pinned by the docker image"
        gcs_out_root_dir:         "GCS bucket to copy the report into; omit to leave outputs in the execution directory"
    }

    input {
        File sample_table_tsv
        String cohort_name

        String? version_label
        String? data_source
        File? render_config_json
        File? report_template_override
        File? reference_bundle_tar
        String? gcs_out_root_dir
    }

    String outdir = sub(select_first([gcs_out_root_dir, "."]), "/$", "") + "/MalariaSurveillanceReportWgs/~{cohort_name}"

    call MSR.RenderWgsReport as t_01_RenderReport {
        input:
            sample_table_tsv         = sample_table_tsv,
            cohort_name              = cohort_name,
            version_label            = version_label,
            data_source              = data_source,
            render_config_json       = render_config_json,
            report_template_override = report_template_override,
            reference_bundle_tar     = reference_bundle_tar
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
