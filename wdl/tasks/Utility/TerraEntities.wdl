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
        launch_row_id:  "The row id(s) the submission was launched on, from get_terra_env_info.input_row_id. Submission-wide, so it is only used when it names exactly one row."
        submission_id:  "The submission this task belongs to, from get_terra_env_info.top_level_submission_id. With it, the task identifies its OWN workflow from its execution path and asks Terra which entity that workflow is for, which is what makes one report per sample set work when several are launched together."
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
        String? launch_row_id
        String? submission_id

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
        export LAUNCH_ROW_ID='~{default="" launch_row_id}'
        export SUBMISSION_ID='~{default="" submission_id}'
        export WANTED_IDS_FILE='~{wanted_ids_file}'
        export PAGE_SIZE='~{page_size}'

        python3 <<'PYEOF'
        import csv, glob, json, os, re, sys, urllib.parse, urllib.request

        FIRECLOUD = "https://api.firecloud.org"
        UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
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

        def own_entity():
            """The entity THIS workflow is for, or None.

            Cromwell writes each job under
            .../submissions/<submission>/<workflow name>/<workflow id>/call-<task>/, so the
            task can read its own workflow id out of its delocalization script and ask the
            submission which entity that workflow was launched on. That is per-workflow and
            exact, unlike the submission-wide launch row list, which cannot distinguish two
            sets launched together.
            """
            sub_id = os.environ.get("SUBMISSION_ID", "")
            if not sub_id:
                return None
            wf_id = None
            cands = []
            for root in ("/cromwell_root", "/mnt/disks/cromwell_root", os.getcwd()):
                cands += glob.glob(root + "/**/gcs_delocalization.sh", recursive=True)
                cands += glob.glob(root + "/gcs_delocalization.sh")
            for script in sorted(set(cands), key=len):
                txt = open(script).read()
                found = set(re.findall(
                    r"/submissions/" + re.escape(sub_id) + r"/[^/]+/(" + UUID + r")/call-",
                    txt))
                if len(found) == 1:
                    wf_id = found.pop()
                    break
            if not wf_id:
                sys.stderr.write("could not read this workflow's own id from its "
                                 "execution path\n")
                return None
            try:
                sub = api_get(f"{FIRECLOUD}/api/workspaces/{q(NS)}/{q(WS)}/submissions/"
                              f"{q(sub_id)}", tok)
            except Exception as e:
                sys.stderr.write(f"could not read submission {sub_id} ({e})\n")
                return None
            for w in sub.get("workflows") or []:
                if w.get("workflowId") == wf_id and w.get("workflowEntity"):
                    e = w["workflowEntity"]
                    sys.stderr.write(f"this workflow ({wf_id}) was launched on "
                                     f"{e.get('entityType')}/{e.get('entityName')}\n")
                    return e.get("entityType", ""), e.get("entityName", "")
            sys.stderr.write(f"workflow {wf_id} not found in submission {sub_id}\n")
            return None

        def set_members(stype, sname):
            """Member row ids of a set, or None when that set does not exist."""
            try:
                ent = api_get(f"{FIRECLOUD}/api/workspaces/{q(NS)}/{q(WS)}/entities/"
                              f"{q(stype)}/{q(sname)}", tok)
            except Exception as e:
                sys.stderr.write(f"no set {stype}/{sname} ({e})\n")
                return None
            got = set()
            for v in (ent.get("attributes", {}) or {}).values():
                if isinstance(v, dict) and v.get("itemsType") == "EntityReference":
                    for it in v.get("items") or []:
                        if it.get("entityName"):
                            got.add(it["entityName"])
            return got or None

        # --- optional set membership filter ---
        wanted = None
        set_type, set_name = os.environ.get("SET_TYPE", ""), os.environ.get("SET_NAME", "")

        # Launched on a single set row and told nothing else? Scope to that set.
        #
        # input_row_id from get_terra_env_info lists EVERY entity in the submission, not
        # this workflow's own row, so when two sets are launched together every workflow
        # sees "Good,Poor". Taking the union produced one combined cohort reported twice
        # under two different names - a silent merge, the worst outcome available. So a
        # single row is used and several are refused outright: Terra resolves
        # `this.samples.<id>` per workflow, which is the mechanism that actually works.
        # Judge this on CONTENT, not file size. write_lines([]) in WDL writes a single
        # newline, so the file is 1 byte rather than 0, and a size test treated "no ids
        # given" as "ids given" - which skipped all set scoping and then applied no filter
        # either, silently downloading the whole table with nothing in the log.
        ids_file = os.environ.get("WANTED_IDS_FILE", "")
        explicit = set()
        if ids_file and os.path.exists(ids_file):
            explicit = {l.strip() for l in open(ids_file)
                        if l.strip() and not l.startswith("#")}
        explicit_ids_given = bool(explicit)
        if not (set_type and set_name) and not explicit_ids_given:
            mine = own_entity()
            if mine and mine[0].endswith("_set") and mine[1]:
                m = set_members(mine[0], mine[1])
                if m:
                    sys.stderr.write(f"scoping to {mine[0]}/{mine[1]}: {len(m)} members\n")
                    wanted = m
            elif mine:
                sys.stderr.write(f"this workflow was launched on {mine[0]}/{mine[1]}, "
                                 f"which is not a set; no set scoping applied\n")

        if wanted is None and not (set_type and set_name) and not explicit_ids_given:
            launched = [r.strip() for r in os.environ.get("LAUNCH_ROW_ID", "").split(",")
                        if r.strip()]
            auto = f"{TYPE}_set"
            if len(launched) > 1:
                sys.exit(
                    f"ERROR: this submission launched {len(launched)} rows "
                    f"({', '.join(launched[:6])}), and the launch row list is "
                    f"submission-wide rather than per-workflow, so it cannot tell which "
                    f"row THIS workflow is for. Scoping from it would merge every "
                    f"launched set into one cohort and report it under each set's name. "
                    f"Bind sample_ids = this.samples.<id column> (Terra resolves that per "
                    f"workflow), or set entity_set_type/entity_set_name, or launch one "
                    f"row at a time.")
            for row in launched:
                m = set_members(auto, row)
                if m:
                    sys.stderr.write(f"launch row {row!r} is a {auto} with {len(m)} "
                                     f"members; scoping the download to it\n")
                    wanted = m
                else:
                    sys.stderr.write(f"launch row {row!r} is not a row of {auto}; "
                                     f"no set scoping applied from it\n")

        if set_type and set_name:
            members = set_members(set_type, set_name)
            if not members:
                sys.exit(f"ERROR: set {set_type}/{set_name} has no member references")
            wanted = members
            sys.stderr.write(f"set {set_type}/{set_name}: {len(members)} members\n")

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
