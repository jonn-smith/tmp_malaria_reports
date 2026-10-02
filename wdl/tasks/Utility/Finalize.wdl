version 1.0

import "../../structs/Structs.wdl"

task FinalizeToDir {

    meta {
        description: "Copy a set of files into a GCS output directory, preserving their basenames."

        tool:         "gsutil cp"
        tool_version: "6.30"
        tool_url:     "https://cloud.google.com/storage/docs/gsutil"

        author: "Jonn Smith"
        email:  "jonn@broadinstitute.org"

        outputs: {
            gcs_dir: "GCS directory the files were copied into"
        }
    }

    parameter_meta {
        files: {
            description: "files to copy into outdir",
            localization_optional: true
        }
        outdir:                "GCS directory to copy the files into"
        keyfile:               "Optional service-account key; when given, the copy is retried after activating it"
        extra_args:            "Additional command-line args appended verbatim to the gsutil cp invocation"
        runtime_attr_override: "Override the default runtime attributes"
    }

    input {
        Array[File] files
        String outdir

        File? keyfile

        String extra_args = ""

        RuntimeAttr? runtime_attr_override
    }

    String gcs_output_dir = sub(outdir, "/+$", "")

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

        if ~{if defined(keyfile) then "true" else "false"}; then
            gcloud auth activate-service-account --key-file=~{default="/dev/null" keyfile}
        fi

        gsutil -m cp -I ~{extra_args} "~{gcs_output_dir}/" < ~{write_lines(files)}
    >>>

    output {
        String gcs_dir = gcs_output_dir
    }

    #########################
    RuntimeAttr default_attr = object {
        cpu_cores:          2,
        mem_gb:             4,
        disk_gb:            10,
        boot_disk_gb:       25,
        preemptible_tries:  1,
        max_retries:        1,
        docker:             "gcr.io/google.com/cloudsdktool/google-cloud-cli:490.0.0-slim"
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
