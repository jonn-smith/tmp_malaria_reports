version 1.0

import "../../structs/Structs.wdl"

task RenderWgsReport {

    meta {
        description: "Render the malaria molecular-surveillance report from a short-read WGS sample table (a Terra export of the sr-malaria `sample` table, carrying per-amino-acid genotype columns)."

        tool:         "make_report.py"
        tool_version: "0.12.6"
        tool_url:     "https://github.com/jonn-smith/tmp_malaria_reports"

        author: "Jonn Smith"
        email:  "jonn@broadinstitute.org"

        outputs: {
            report_html:      "Self-contained single-file HTML surveillance report",
            report_data_json: "The report's data model (every number the report draws)",
            export_csvs:      "Dashboard-ready export tables, one CSV per view (who_threat_map.csv, dhis2_datavalueset.csv, ...)",
            location_audit:   "How every sample was placed, plus each unplaced location name with spelling suggestions, each coordinate/name disagreement, and each region mismatch"
        }
    }

    parameter_meta {
        sample_table_tsv:         "Terra export of the WGS `sample` table (TSV) with per-amino-acid genotype columns"
        cohort_name:              "Cohort label used for output filenames"
        version_label:            "Version string stamped on the report (e.g. v0.12)"
        data_source:              "Provenance line shown in the report banner"
        render_config_json:       "JSON settings file; unrecognised keys pass through to the report metadata so new template features need no interface change"
        report_template_override: "Replacement report template (HTML); omit to use the template baked into the docker image"
        reference_bundle_tar:     "tar(.gz) of replacement reference data (admin boundaries, WHO compendium); omit to use the bundle baked into the docker image"
        country_iso3:             "ISO3 code selecting the admin-2 boundary set baked into the image (reference/adm2/<ISO3>_adm2_map.json.gz); defaults to SEN"
        country_name:             "Country name shown in the report; defaults to the name recorded in the boundary file"
        sample_ids_file:          "Optional allow-list of sample ids, one per line; omit to report on every sample in the inputs"
        selection_label:          "Human-readable name for the sample selection, shown in the report (e.g. a Terra sample_set name)"
        extra_args:               "Additional command-line args appended verbatim to the make_report.py invocation"
        runtime_attr_override:    "Override the default runtime attributes"
    }

    input {
        File sample_table_tsv
        String cohort_name

        String? version_label
        String? data_source
        File? render_config_json
        File? report_template_override
        File? reference_bundle_tar

        String? country_iso3
        String? country_name
        File? sample_ids_file
        String? selection_label

        String extra_args = ""

        RuntimeAttr? runtime_attr_override
    }

    Int disk_size = 10 + ceil(5.0 * (size(sample_table_tsv, "GB") + size(reference_bundle_tar, "GB") + size(sample_ids_file, "GB")))

    command <<<
        set -euxo pipefail

        # ---- Resource detection (required preamble) ----
        NUM_CPUS=$(grep '^processor' /proc/cpuinfo | tail -n1 | awk '{print $NF+1}')
        RAM_IN_GB=$(free -g | grep "^Mem" | awk '{print $2}')

        # Reserve 1 GB for OS + container overhead.
        USABLE_RAM_GB=$((RAM_IN_GB - 1))
        [[ "${USABLE_RAM_GB}" -lt 1 ]] && USABLE_RAM_GB=1

        # Per-thread RAM (used by samtools sort -m, etc.)
        MEM_PER_THREAD_GB=$(( USABLE_RAM_GB / NUM_CPUS ))
        [[ "${MEM_PER_THREAD_GB}" -lt 1 ]] && MEM_PER_THREAD_GB=1

        # Java heap (used by GATK/Picard). Same as USABLE_RAM_GB; alias for clarity.
        JAVA_MEM_GB=${USABLE_RAM_GB}

        echo "NUM_CPUS=${NUM_CPUS}  RAM_IN_GB=${RAM_IN_GB}  USABLE_RAM_GB=${USABLE_RAM_GB}  MEM_PER_THREAD_GB=${MEM_PER_THREAD_GB}  JAVA_MEM_GB=${JAVA_MEM_GB}"
        # ---- end preamble ----

        mkdir -p export_csvs

        # Optional replacement reference bundle: unpack over a writable copy of the one
        # baked into the image, so a partial bundle only overrides what it contains.
        if ~{if defined(reference_bundle_tar) then "true" else "false"}; then
            cp -r /opt/malaria_reports/reference ./reference
            tar -xf ~{default="/dev/null" reference_bundle_tar} -C ./reference
        fi

        python3 /opt/malaria_reports/scripts/make_report.py \
            --assay WGS \
            --sample-table ~{sample_table_tsv} \
            ~{"--version-label " + version_label} \
            ~{"--data-source '" + data_source + "'"} \
            ~{"--country-iso3 " + country_iso3} \
            ~{"--country-name '" + country_name + "'"} \
            ~{"--sample-ids " + sample_ids_file} \
            ~{"--selection-label '" + selection_label + "'"} \
            ~{"--config " + render_config_json} \
            ~{"--template " + report_template_override} \
            ~{if defined(reference_bundle_tar) then "--reference ./reference" else ""} \
            --out-html "~{cohort_name}.wgs_surveillance_report.html" \
            --out-data-json "~{cohort_name}.wgs_surveillance_report.data.json" \
            --out-csv-dir export_csvs \
            --out-location-audit "~{cohort_name}.location_audit.tsv" \
            ~{extra_args}
    >>>

    output {
        File report_html      = "~{cohort_name}.wgs_surveillance_report.html"
        File report_data_json = "~{cohort_name}.wgs_surveillance_report.data.json"
        Array[File] export_csvs = glob("export_csvs/*.csv")
        File location_audit = "~{cohort_name}.location_audit.tsv"
    }

    #########################
    RuntimeAttr default_attr = object {
        cpu_cores:          2,
        mem_gb:             8,
        disk_gb:            disk_size,
        boot_disk_gb:       25,
        preemptible_tries:  1,
        max_retries:        1,
        docker:             "us.gcr.io/broad-dsp-lrma/lr-malaria-reports:0.12.6"
    }
    RuntimeAttr runtime_attr = select_first([runtime_attr_override, default_attr])
    runtime {
        cpu:                    select_first([runtime_attr.cpu_cores,         default_attr.cpu_cores])
        memory:                 select_first([runtime_attr.mem_gb,            default_attr.mem_gb]) + " GiB"
        disks: "local-disk " +  select_first([runtime_attr.disk_gb,           default_attr.disk_gb]) + " HDD"
        bootDiskSizeGb:         select_first([runtime_attr.boot_disk_gb,      default_attr.boot_disk_gb])
        preemptible:            select_first([runtime_attr.preemptible_tries, default_attr.preemptible_tries])
        maxRetries:             select_first([runtime_attr.max_retries,       default_attr.max_retries])
        docker:                 select_first([runtime_attr.docker,            default_attr.docker])
    }
}

task RenderAmpliconReport {

    meta {
        description: "Render the malaria molecular-surveillance report from MAD4HATTER amplicon outputs: one resistance-marker table per sequencing run, a per-sample site/coordinate table, and optionally the microhaplotype allele tables."

        tool:         "make_report.py"
        tool_version: "0.12.6"
        tool_url:     "https://github.com/jonn-smith/tmp_malaria_reports"

        author: "Jonn Smith"
        email:  "jonn@broadinstitute.org"

        outputs: {
            report_html:      "Self-contained single-file HTML surveillance report",
            report_data_json: "The report's data model (every number the report draws)",
            export_csvs:      "Dashboard-ready export tables, one CSV per view (who_threat_map.csv, dhis2_datavalueset.csv, ...)",
            location_audit:   "How every sample was placed, plus each unplaced location name with spelling suggestions, each coordinate/name disagreement, and each region mismatch"
        }
    }

    parameter_meta {
        assay:                    "AMPLICON (default) detects the panel from the loci in the tables and tolerates panels that are not catalogued. Naming MAD4HATTER or PFPHAST instead declares it: the declaration is kept and any disagreement with the detected panel is reported."
        resmarker_tables:         "Amplicon resistance-marker calls: either the wide per-sample Terra table (one column per marker, the short-read default) or the long resmarker_table.txt files, one per sequencing run. Do not mix the two shapes."
        site_metadata:            "Per-sample site and coordinate table (Sample_id, site, Latitude, Longitude). Optional: a wide per-sample Terra table already carries geography, so omit it for that input shape."
        allele_tables:            "MAD4HATTER microhaplotype allele tables (allele_data.txt); optional"
        cohort_name:              "Cohort label used for output filenames"
        version_label:            "Version string stamped on the report (e.g. v0.12)"
        data_source:              "Provenance line shown in the report banner"
        render_config_json:       "JSON settings file; unrecognised keys pass through to the report metadata so new template features need no interface change"
        report_template_override: "Replacement report template (HTML); omit to use the template baked into the docker image"
        reference_bundle_tar:     "tar(.gz) of replacement reference data (admin boundaries, WHO compendium); omit to use the bundle baked into the docker image"
        country_iso3:             "ISO3 code selecting the admin-2 boundary set baked into the image (reference/adm2/<ISO3>_adm2_map.json.gz); defaults to SEN"
        country_name:             "Country name shown in the report; defaults to the name recorded in the boundary file"
        sample_ids_file:          "Optional allow-list of sample ids, one per line; omit to report on every sample in the inputs"
        selection_label:          "Human-readable name for the sample selection, shown in the report (e.g. a Terra sample_set name)"
        extra_args:               "Additional command-line args appended verbatim to the make_report.py invocation"
        runtime_attr_override:    "Override the default runtime attributes"
    }

    input {
        Array[File] resmarker_tables
        File? site_metadata
        String cohort_name

        Array[File] allele_tables = []
        String? version_label
        String? data_source
        File? render_config_json
        File? report_template_override
        File? reference_bundle_tar

        String? country_iso3
        String? country_name
        File? sample_ids_file
        String? selection_label

        String assay = "AMPLICON"

        String extra_args = ""

        RuntimeAttr? runtime_attr_override
    }

    Int disk_size = 10 + ceil(5.0 * (size(resmarker_tables, "GB") + size(allele_tables, "GB")
                                     + size(site_metadata, "GB") + size(reference_bundle_tar, "GB") + size(sample_ids_file, "GB")))

    command <<<
        set -euxo pipefail

        # ---- Resource detection (required preamble) ----
        NUM_CPUS=$(grep '^processor' /proc/cpuinfo | tail -n1 | awk '{print $NF+1}')
        RAM_IN_GB=$(free -g | grep "^Mem" | awk '{print $2}')

        # Reserve 1 GB for OS + container overhead.
        USABLE_RAM_GB=$((RAM_IN_GB - 1))
        [[ "${USABLE_RAM_GB}" -lt 1 ]] && USABLE_RAM_GB=1

        # Per-thread RAM (used by samtools sort -m, etc.)
        MEM_PER_THREAD_GB=$(( USABLE_RAM_GB / NUM_CPUS ))
        [[ "${MEM_PER_THREAD_GB}" -lt 1 ]] && MEM_PER_THREAD_GB=1

        # Java heap (used by GATK/Picard). Same as USABLE_RAM_GB; alias for clarity.
        JAVA_MEM_GB=${USABLE_RAM_GB}

        echo "NUM_CPUS=${NUM_CPUS}  RAM_IN_GB=${RAM_IN_GB}  USABLE_RAM_GB=${USABLE_RAM_GB}  MEM_PER_THREAD_GB=${MEM_PER_THREAD_GB}  JAVA_MEM_GB=${JAVA_MEM_GB}"
        # ---- end preamble ----

        mkdir -p export_csvs

        # Optional replacement reference bundle: unpack over a writable copy of the one
        # baked into the image, so a partial bundle only overrides what it contains.
        if ~{if defined(reference_bundle_tar) then "true" else "false"}; then
            cp -r /opt/malaria_reports/reference ./reference
            tar -xf ~{default="/dev/null" reference_bundle_tar} -C ./reference
        fi

        python3 /opt/malaria_reports/scripts/make_report.py \
            --assay ~{assay} \
            --resmarker-table ~{sep=' ' resmarker_tables} \
            ~{"--site-metadata " + site_metadata} \
            ~{if length(allele_tables) > 0 then "--allele-table " else ""}~{sep=' ' allele_tables} \
            ~{"--version-label " + version_label} \
            ~{"--data-source '" + data_source + "'"} \
            ~{"--country-iso3 " + country_iso3} \
            ~{"--country-name '" + country_name + "'"} \
            ~{"--sample-ids " + sample_ids_file} \
            ~{"--selection-label '" + selection_label + "'"} \
            ~{"--config " + render_config_json} \
            ~{"--template " + report_template_override} \
            ~{if defined(reference_bundle_tar) then "--reference ./reference" else ""} \
            --out-html "~{cohort_name}.amplicon_surveillance_report.html" \
            --out-data-json "~{cohort_name}.amplicon_surveillance_report.data.json" \
            --out-csv-dir export_csvs \
            --out-location-audit "~{cohort_name}.location_audit.tsv" \
            ~{extra_args}
    >>>

    output {
        File report_html      = "~{cohort_name}.amplicon_surveillance_report.html"
        File report_data_json = "~{cohort_name}.amplicon_surveillance_report.data.json"
        Array[File] export_csvs = glob("export_csvs/*.csv")
        File location_audit = "~{cohort_name}.location_audit.tsv"
    }

    #########################
    RuntimeAttr default_attr = object {
        cpu_cores:          2,
        mem_gb:             8,
        disk_gb:            disk_size,
        boot_disk_gb:       25,
        preemptible_tries:  1,
        max_retries:        1,
        docker:             "us.gcr.io/broad-dsp-lrma/lr-malaria-reports:0.12.6"
    }
    RuntimeAttr runtime_attr = select_first([runtime_attr_override, default_attr])
    runtime {
        cpu:                    select_first([runtime_attr.cpu_cores,         default_attr.cpu_cores])
        memory:                 select_first([runtime_attr.mem_gb,            default_attr.mem_gb]) + " GiB"
        disks: "local-disk " +  select_first([runtime_attr.disk_gb,           default_attr.disk_gb]) + " HDD"
        bootDiskSizeGb:         select_first([runtime_attr.boot_disk_gb,      default_attr.boot_disk_gb])
        preemptible:            select_first([runtime_attr.preemptible_tries, default_attr.preemptible_tries])
        maxRetries:             select_first([runtime_attr.max_retries,       default_attr.max_retries])
        docker:                 select_first([runtime_attr.docker,            default_attr.docker])
    }
}

task RenderNomadsReport {

    meta {
        description: "Render the malaria molecular-surveillance report from NOMADS (ONT amplicon) marker calls. Input is the assay-agnostic marker-calls table documented in scripts/load_nomads.py: one row per sample x marker, so a change in nomadic's own output layout is absorbed by the mapping into that table rather than by this interface."

        tool:         "make_report.py"
        tool_version: "0.12.6"
        tool_url:     "https://github.com/jonn-smith/tmp_malaria_reports"

        author: "Jonn Smith"
        email:  "jonn@broadinstitute.org"

        outputs: {
            report_html:      "Self-contained single-file HTML surveillance report",
            report_data_json: "The report's data model (every number the report draws)",
            export_csvs:      "Dashboard-ready export tables, one CSV per view (who_threat_map.csv, dhis2_datavalueset.csv, ...)",
            location_audit:   "How every sample was placed, plus each unplaced location name with spelling suggestions, each coordinate/name disagreement, and each region mismatch"
        }
    }

    parameter_meta {
        marker_calls_tables:      "Marker-calls tables (TSV/CSV), one row per sample x marker; schema documented in scripts/load_nomads.py"
        cohort_name:              "Cohort label used for output filenames"
        site_metadata:            "Per-sample site and coordinate table; optional when the calls tables already carry geography"
        version_label:            "Version string stamped on the report (e.g. v0.12)"
        data_source:              "Provenance line shown in the report banner"
        render_config_json:       "JSON settings file; unrecognised keys pass through to the report metadata so new template features need no interface change"
        report_template_override: "Replacement report template (HTML); omit to use the template baked into the docker image"
        reference_bundle_tar:     "tar(.gz) of replacement reference data (admin boundaries, WHO compendium); omit to use the bundle baked into the docker image"
        country_iso3:             "ISO3 code selecting the admin-2 boundary set baked into the image (reference/adm2/<ISO3>_adm2_map.json.gz); defaults to SEN"
        country_name:             "Country name shown in the report; defaults to the name recorded in the boundary file"
        sample_ids_file:          "Optional allow-list of sample ids, one per line; omit to report on every sample in the inputs"
        selection_label:          "Human-readable name for the sample selection, shown in the report (e.g. a Terra sample_set name)"
        extra_args:               "Additional command-line args appended verbatim to the make_report.py invocation"
        runtime_attr_override:    "Override the default runtime attributes"
    }

    input {
        Array[File] marker_calls_tables
        String cohort_name

        File? site_metadata
        String? version_label
        String? data_source
        File? render_config_json
        File? report_template_override
        File? reference_bundle_tar

        String? country_iso3
        String? country_name
        File? sample_ids_file
        String? selection_label

        String extra_args = ""

        RuntimeAttr? runtime_attr_override
    }

    Int disk_size = 10 + ceil(5.0 * (size(marker_calls_tables, "GB") + size(site_metadata, "GB")
                                     + size(reference_bundle_tar, "GB") + size(sample_ids_file, "GB")))

    command <<<
        set -euxo pipefail

        # ---- Resource detection (required preamble) ----
        NUM_CPUS=$(grep '^processor' /proc/cpuinfo | tail -n1 | awk '{print $NF+1}')
        RAM_IN_GB=$(free -g | grep "^Mem" | awk '{print $2}')

        # Reserve 1 GB for OS + container overhead.
        USABLE_RAM_GB=$((RAM_IN_GB - 1))
        [[ "${USABLE_RAM_GB}" -lt 1 ]] && USABLE_RAM_GB=1

        # Per-thread RAM (used by samtools sort -m, etc.)
        MEM_PER_THREAD_GB=$(( USABLE_RAM_GB / NUM_CPUS ))
        [[ "${MEM_PER_THREAD_GB}" -lt 1 ]] && MEM_PER_THREAD_GB=1

        # Java heap (used by GATK/Picard). Same as USABLE_RAM_GB; alias for clarity.
        JAVA_MEM_GB=${USABLE_RAM_GB}

        echo "NUM_CPUS=${NUM_CPUS}  RAM_IN_GB=${RAM_IN_GB}  USABLE_RAM_GB=${USABLE_RAM_GB}  MEM_PER_THREAD_GB=${MEM_PER_THREAD_GB}  JAVA_MEM_GB=${JAVA_MEM_GB}"
        # ---- end preamble ----

        mkdir -p export_csvs

        # Optional replacement reference bundle: unpack over a writable copy of the one
        # baked into the image, so a partial bundle only overrides what it contains.
        if ~{if defined(reference_bundle_tar) then "true" else "false"}; then
            cp -r /opt/malaria_reports/reference ./reference
            tar -xf ~{default="/dev/null" reference_bundle_tar} -C ./reference
        fi

        python3 /opt/malaria_reports/scripts/make_report.py \
            --assay NOMADS \
            --marker-calls ~{sep=' ' marker_calls_tables} \
            ~{"--site-metadata " + site_metadata} \
            ~{"--version-label " + version_label} \
            ~{"--data-source '" + data_source + "'"} \
            ~{"--country-iso3 " + country_iso3} \
            ~{"--country-name '" + country_name + "'"} \
            ~{"--sample-ids " + sample_ids_file} \
            ~{"--selection-label '" + selection_label + "'"} \
            ~{"--config " + render_config_json} \
            ~{"--template " + report_template_override} \
            ~{if defined(reference_bundle_tar) then "--reference ./reference" else ""} \
            --out-html "~{cohort_name}.nomads_surveillance_report.html" \
            --out-data-json "~{cohort_name}.nomads_surveillance_report.data.json" \
            --out-csv-dir export_csvs \
            --out-location-audit "~{cohort_name}.location_audit.tsv" \
            ~{extra_args}
    >>>

    output {
        File report_html      = "~{cohort_name}.nomads_surveillance_report.html"
        File report_data_json = "~{cohort_name}.nomads_surveillance_report.data.json"
        Array[File] export_csvs = glob("export_csvs/*.csv")
        File location_audit = "~{cohort_name}.location_audit.tsv"
    }

    #########################
    RuntimeAttr default_attr = object {
        cpu_cores:          2,
        mem_gb:             8,
        disk_gb:            disk_size,
        boot_disk_gb:       25,
        preemptible_tries:  1,
        max_retries:        1,
        docker:             "us.gcr.io/broad-dsp-lrma/lr-malaria-reports:0.12.6"
    }
    RuntimeAttr runtime_attr = select_first([runtime_attr_override, default_attr])
    runtime {
        cpu:                    select_first([runtime_attr.cpu_cores,         default_attr.cpu_cores])
        memory:                 select_first([runtime_attr.mem_gb,            default_attr.mem_gb]) + " GiB"
        disks: "local-disk " +  select_first([runtime_attr.disk_gb,           default_attr.disk_gb]) + " HDD"
        bootDiskSizeGb:         select_first([runtime_attr.boot_disk_gb,      default_attr.boot_disk_gb])
        preemptible:            select_first([runtime_attr.preemptible_tries, default_attr.preemptible_tries])
        maxRetries:             select_first([runtime_attr.max_retries,       default_attr.max_retries])
        docker:                 select_first([runtime_attr.docker,            default_attr.docker])
    }
}
