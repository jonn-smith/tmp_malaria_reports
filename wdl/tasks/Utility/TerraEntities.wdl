version 1.0

import "../../structs/Structs.wdl"

task download_terra_entity_table {

    meta {
        description: "Download a Terra data table as a TSV, from inside a running Cromwell job. Pairs with get_terra_env_info, which names the table but does not fetch its rows. Pages through the Rawls entityQuery API and writes the Terra export layout: an 'entity:<type>_id' first column followed by one column per attribute, so the result is interchangeable with a hand-made 'Download TSV'. Optionally restricts the rows to the members of a sample set, or to an explicit id list. Authenticates with the task's attached service-account token from the GCE metadata server; pure python3/urllib, so no gcloud/jq/curl/fiss."
        volatile: true
    }

    parameter_meta {
        namespace:      "Terra billing project / namespace owning the workspace"
        workspace:      "Workspace name"
        entity_type:    "Data table to download, e.g. 'pfphast_sample'"
        entity_set_type: "Optional set table, e.g. 'pfphast_sample_set'. With entity_set_name, restricts the download to that set's members."
        entity_set_name: "Optional set row id, e.g. 'Good'"
        row_ids:        "Optional explicit row ids to keep. Applied after the set filter when both are given."
        page_size:      "Rows per API request. The API caps this; 500 is comfortable."
        runtime_attr_override: "Override the default runtime attributes"
    }

    input {
        String namespace
        String workspace
        String entity_type

        String? entity_set_type
        String? entity_set_name
        Array[String] row_ids = []

        Int page_size = 500

        RuntimeAttr? runtime_attr_override
    }

    # Always materialised: an empty array writes an empty file, which the script reads as
    # "no id filter". WDL 1.0 has no None literal and a task body cannot hold a conditional.
    File wanted_ids_file = write_lines(row_ids)

    command <<<
        set -euo pipefail

        export NAMESPACE='~{namespace}'
        export WORKSPACE='~{workspace}'
        export ENTITY_TYPE='~{entity_type}'
        export SET_TYPE='~{default="" entity_set_type}'
        export SET_NAME='~{default="" entity_set_name}'
        export WANTED_IDS_FILE='~{wanted_ids_file}'
        export PAGE_SIZE='~{page_size}'

        python3 <<'PYEOF'
        import csv, json, os, sys, urllib.parse, urllib.request

        FIRECLOUD = "https://api.firecloud.org"
        NS   = os.environ["NAMESPACE"]
        WS   = os.environ["WORKSPACE"]
        TYPE = os.environ["ENTITY_TYPE"]
        PAGE = int(os.environ.get("PAGE_SIZE") or 500)

        def q(s):
            return urllib.parse.quote(s, safe="")

        def token():
            req = urllib.request.Request(
                "http://metadata.google.internal/computeMetadata/v1/"
                "instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.load(resp)["access_token"]

        def api_get(url, tok):
            req = urllib.request.Request(
                url, headers={"Authorization": "Bearer " + tok,
                              "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)

        def flatten(v):
            """A Terra attribute value -> one cell.

            Scalars pass through. A value list becomes comma-joined, which is how Terra's
            own TSV export renders it. An entity reference becomes the referenced row id,
            because the id is the only part of it that means anything in a flat table.
            """
            if v is None:
                return ""
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, (int, float, str)):
                return str(v)
            if isinstance(v, dict):
                if "entityName" in v:
                    return str(v["entityName"])
                items = v.get("items")
                if isinstance(items, list):
                    return ",".join(flatten(x) for x in items)
                return json.dumps(v, sort_keys=True)
            if isinstance(v, list):
                return ",".join(flatten(x) for x in v)
            return str(v)

        tok = token()

        # --- optional set membership filter ---
        wanted = None
        set_type, set_name = os.environ.get("SET_TYPE", ""), os.environ.get("SET_NAME", "")
        if set_type and set_name:
            ent = api_get(f"{FIRECLOUD}/api/workspaces/{q(NS)}/{q(WS)}/entities/"
                          f"{q(set_type)}/{q(set_name)}", tok)
            attrs = ent.get("attributes", {}) or {}
            members = set()
            for v in attrs.values():
                if isinstance(v, dict) and v.get("itemsType") == "EntityReference":
                    for it in v.get("items") or []:
                        if it.get("entityName"):
                            members.add(it["entityName"])
            if not members:
                sys.exit(f"ERROR: set {set_type}/{set_name} has no member references")
            wanted = members
            sys.stderr.write(f"set {set_type}/{set_name}: {len(members)} members\n")

        ids_file = os.environ.get("WANTED_IDS_FILE", "")
        explicit = set()
        if ids_file and os.path.exists(ids_file):
            explicit = {l.strip() for l in open(ids_file) if l.strip()
                        and not l.startswith("#")}
        if explicit:
            wanted = explicit if wanted is None else (wanted & explicit)
            sys.stderr.write(f"explicit id list: {len(explicit)} ids, "
                             f"{len(wanted)} after intersecting\n")

        # --- page through the table ---
        rows, page, total = [], 1, None
        while True:
            url = (f"{FIRECLOUD}/api/workspaces/{q(NS)}/{q(WS)}/entityQuery/{q(TYPE)}"
                   f"?page={page}&pageSize={PAGE}")
            payload = api_get(url, tok)
            meta = payload.get("resultMetadata", {}) or {}
            total = meta.get("unfilteredCount", total)
            got = payload.get("results") or []
            rows.extend(got)
            pages = meta.get("filteredPageCount") or 1
            sys.stderr.write(f"page {page}/{pages}: {len(got)} rows\n")
            if page >= pages or not got:
                break
            page += 1

        if not rows:
            sys.exit(f"ERROR: table {TYPE} in {NS}/{WS} returned no rows")

        if wanted is not None:
            before = len(rows)
            rows = [r for r in rows if r.get("name") in wanted]
            sys.stderr.write(f"filtered {before} -> {len(rows)} rows\n")
            if not rows:
                sys.exit("ERROR: no rows left after filtering; check the set membership "
                         "or id list against the table's row ids")

        # Union of attribute keys, in first-seen order so a table's own column order is
        # roughly preserved; a column absent from a row is written empty, not skipped.
        cols = []
        seen = set()
        for r in rows:
            for k in (r.get("attributes") or {}):
                if k not in seen:
                    seen.add(k)
                    cols.append(k)

        out = f"{TYPE}.tsv"
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter="\t", lineterminator="\n")
            w.writerow([f"entity:{TYPE}_id"] + cols)
            for r in rows:
                a = r.get("attributes") or {}
                w.writerow([r.get("name", "")] + [flatten(a.get(c)) for c in cols])

        with open("n_rows.txt", "w") as fh:
            fh.write(str(len(rows)))
        with open("n_columns.txt", "w") as fh:
            fh.write(str(len(cols)))
        sys.stderr.write(f"wrote {out}: {len(rows)} rows x {len(cols)} attribute columns "
                         f"(table holds {total})\n")
        PYEOF
    >>>

    output {
        File table_tsv  = "~{entity_type}.tsv"
        Int  n_rows     = read_int("n_rows.txt")
        Int  n_columns  = read_int("n_columns.txt")
    }

    #########################
    RuntimeAttr default_attr = object {
        cpu_cores:          1,
        mem_gb:             4,
        disk_gb:            20,
        boot_disk_gb:       15,
        preemptible_tries:  1,
        max_retries:        2,
        docker:             "us.gcr.io/broad-dsp-lrma/lr-backup-workspace:0.0.1"
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
