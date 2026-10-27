#!/usr/bin/env python3
"""Work out, from inside a running Terra task, which sample set this report is for.

This exists because of a delivery asymmetry. The report code ships in a docker image,
which is pushed and picked up immediately; the pipeline ships as a WDL through Dockstore,
which caches a branch and may serve a descriptor weeks old. So a fix placed in the WDL can
sit unused indefinitely while the same fix placed here takes effect on the next push.

Scoping a report to one sample set belongs in that second category: getting it wrong means
two sets launched together each report the whole table, which is a silently wrong number
rather than an error. So it is determined here, in the image, needing nothing from the
WDL at all:

  1. read the task's own bucket, submission id and workflow id out of the execution path
     that Cromwell localises into every job
  2. ask Terra which workspace that bucket is, and which entity this workflow was
     launched on
  3. if that entity is a `*_set`, read its members

Everything uses the VM's attached service-account token and the standard library, so there
is nothing to install and no credentials to pass in. Off Terra, every function returns None
and the caller carries on unscoped.
"""
import glob
import json
import os
import re
import sys
import urllib.parse
import urllib.request

FIRECLOUD = 'https://api.firecloud.org'
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
ROOTS = ('/cromwell_root', '/mnt/disks/cromwell_root', '/mnt/miniwdl_task_container/work')


def _q(s):
    return urllib.parse.quote(str(s), safe='')


def token(timeout=10):
    req = urllib.request.Request(
        'http://metadata.google.internal/computeMetadata/v1/'
        'instance/service-accounts/default/token',
        headers={'Metadata-Flavor': 'Google'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)['access_token']


def api_get(url, tok, timeout=60):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + tok,
                                               'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def execution_ids(search_roots=None, cwd=True):
    """-> (bucket_uuid, submission_id, workflow_id), any of which may be None.

    Cromwell localises a delocalization script into every job that names the job's own
    output path: gs://fc-<bucket>/submissions/<submission>/<workflow name>/<workflow id>/
    call-<task>/. That path is the only place a task is told which workflow it is.
    """
    # read the module global at call time, not at definition time, so a test (or a
    # different Cromwell layout) can point this somewhere else
    search_roots = search_roots if search_roots is not None else ROOTS
    texts = []
    cands = []
    for root in search_roots:
        cands += glob.glob(root + '/**/gcs_delocalization.sh', recursive=True)
        cands += glob.glob(root + '/gcs_delocalization.sh')
    for p in sorted(set(cands), key=len)[:4]:
        try:
            texts.append(open(p).read())
        except OSError:
            pass
    if cwd:
        texts.append(os.getcwd())

    bucket = submission = workflow = None
    for t in texts:
        if not bucket:
            b = set(re.findall(r'fc-(?:secure-)?(' + UUID + r')\b', t))
            if len(b) == 1:
                bucket = b.pop()
        m = re.search(r'/submissions/(' + UUID + r')/[^/]+/(' + UUID + r')/call-', t)
        if m:
            submission, workflow = m.group(1), m.group(2)
            break
        if not submission:
            s = set(re.findall(r'/submissions/(' + UUID + r')\b', t))
            if len(s) == 1:
                submission = s.pop()
    return bucket, submission, workflow


def workspace_of(bucket_uuid, tok):
    """-> (namespace, name) for the workspace owning that bucket."""
    full = api_get(f'{FIRECLOUD}/api/workspaces/id/{_q(bucket_uuid)}', tok)
    ws = full.get('workspace', {}) or {}
    return ws.get('namespace'), ws.get('name')


def entity_of_workflow(ns, name, submission_id, workflow_id, tok):
    """-> (entityType, entityName) this workflow was launched on, or None."""
    sub = api_get(f'{FIRECLOUD}/api/workspaces/{_q(ns)}/{_q(name)}/submissions/'
                  f'{_q(submission_id)}', tok)
    for w in sub.get('workflows') or []:
        if w.get('workflowId') == workflow_id and w.get('workflowEntity'):
            e = w['workflowEntity']
            return e.get('entityType'), e.get('entityName')
    return None


def set_members(ns, name, etype, ename, tok):
    """-> member row ids of a set entity, or an empty set."""
    ent = api_get(f'{FIRECLOUD}/api/workspaces/{_q(ns)}/{_q(name)}/entities/'
                  f'{_q(etype)}/{_q(ename)}', tok)
    out = set()
    for v in (ent.get('attributes') or {}).values():
        if isinstance(v, dict) and v.get('itemsType') == 'EntityReference':
            for it in v.get('items') or []:
                if it.get('entityName'):
                    out.add(it['entityName'])
    return out


def detect(log=sys.stderr):
    """-> dict(ids/members) describing this task's own sample set, or None.

    Never raises: anything unavailable means "not on Terra, or not launched on a set",
    and the caller reports on everything instead.
    """
    def say(msg):
        if log:
            log.write(f'[terra_scope] {msg}\n')

    bucket, submission, workflow = execution_ids()
    if not (submission and workflow):
        say('not running under a Terra submission (no submission/workflow id in the '
            'execution path); no set scoping')
        return None
    try:
        tok = token()
    except Exception as e:
        say(f'no metadata server, so not on Terra ({e}); no set scoping')
        return None
    try:
        ns = os.environ.get('WORKSPACE_NAMESPACE') or None
        nm = os.environ.get('WORKSPACE_NAME') or None
        if not (ns and nm):
            if not bucket:
                say('could not identify the workspace bucket; no set scoping')
                return None
            ns, nm = workspace_of(bucket, tok)
        if not (ns and nm):
            say('could not resolve the workspace; no set scoping')
            return None
        ent = entity_of_workflow(ns, nm, submission, workflow, tok)
        if not ent:
            say(f'workflow {workflow} not found in submission {submission}; no set scoping')
            return None
        etype, ename = ent
        say(f'this workflow was launched on {etype}/{ename}')
        if not (etype or '').endswith('_set'):
            say('launched on a single row rather than a set; no set scoping')
            return None
        members = set_members(ns, nm, etype, ename, tok)
        if not members:
            say(f'{etype}/{ename} lists no members; no set scoping')
            return None
        say(f'scoping this report to {etype}/{ename}: {len(members)} members')
        return {'namespace': ns, 'workspace': nm, 'submission_id': submission,
                'workflow_id': workflow, 'entity_type': etype, 'entity_name': ename,
                'members': sorted(members)}
    except Exception as e:
        say(f'could not resolve the launched set ({e}); no set scoping')
        return None


def demo():
    """Self-check of the path parsing, which is the part that has no network."""
    sub = 'ffffffff-1111-2222-3333-444444444444'
    wf = 'aaaaaaaa-1111-2222-3333-444444444444'
    buck = 'd0429fed-8741-41bf-b883-4e0bb09a8df9'
    import tempfile
    d = tempfile.mkdtemp()
    with open(os.path.join(d, 'gcs_delocalization.sh'), 'w') as fh:
        fh.write(f'gsutil cp out gs://fc-{buck}/submissions/{sub}/'
                 f'MalariaSurveillanceReportAmplicon/{wf}/call-t_01_RenderReport/x\n')
    b, s, w = execution_ids(search_roots=(d,), cwd=False)
    assert (b, s, w) == (buck, sub, wf), (b, s, w)

    # the secure-bucket spelling Terra uses for protected workspaces
    d2 = tempfile.mkdtemp()
    with open(os.path.join(d2, 'gcs_delocalization.sh'), 'w') as fh:
        fh.write(f'gs://fc-secure-{buck}/submissions/{sub}/WF/{wf}/call-x/y\n')
    assert execution_ids(search_roots=(d2,), cwd=False) == (buck, sub, wf)

    # nothing to find: returns Nones rather than raising
    d3 = tempfile.mkdtemp()
    assert execution_ids(search_roots=(d3,), cwd=False) == (None, None, None)

    # and detect() degrades quietly off Terra
    import io
    buf = io.StringIO()
    assert detect(log=buf) is None
    assert 'no set scoping' in buf.getvalue()
    print('terra_scope demo OK')
    print('  parsed submission/workflow from a Cromwell path, handled fc-secure-, and '
          'returned None off Terra')


if __name__ == '__main__':
    demo()
