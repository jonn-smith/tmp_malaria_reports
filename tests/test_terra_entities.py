"""Run the task's embedded python against a mocked Rawls API built from the real table."""
import io, json, os, re, sys, textwrap, urllib.request, tempfile, csv

WDL = open('/workspace/malaria_reports/wdl/tasks/Utility/TerraEntities.wdl').read()
body = WDL.split("python3 <<'PYEOF'",1)[1].split("PYEOF",1)[0]
script = textwrap.dedent(body)

REAL = os.environ.get('ENTITY_JSON') or '/home/claude/.claude/projects/-workspace/6bf3c08c-67a2-4454-8302-e4ad5e2b5fbc/tool-results/mcp-fiss-mcp-get_entities-1793078025126.txt'
ents = json.load(open(REAL))['entities']
# shape them as entityQuery returns them
rows = [{'name': e['name'], 'entityType': e['entityType'], 'attributes': e['attributes']}
        for e in ents]
SETS = os.environ.get('SET_JSON') or '/home/claude/.claude/projects/-workspace/6bf3c08c-67a2-4454-8302-e4ad5e2b5fbc/tool-results/mcp-fiss-mcp-get_entities-1793077191077.txt'
setents = {e['name']: e for e in json.load(open(SETS))['entities']}

PAGE = int(__import__('os').environ.get('TEST_PAGE', 500))
calls = []

class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False

def fake_urlopen(req, *a, **kw):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    calls.append(url)
    if 'metadata.google.internal' in url:
        return FakeResp(json.dumps({'access_token': 'fake'}).encode())
    m = re.search(r'/entityQuery/([^?]+)\?page=(\d+)&pageSize=(\d+)', url)
    if m:
        page, size = int(m.group(2)), int(m.group(3))
        pages = (len(rows) + size - 1)//size
        chunk = rows[(page-1)*size: page*size]
        return FakeResp(json.dumps({
            'results': chunk,
            'resultMetadata': {'unfilteredCount': len(rows), 'filteredCount': len(rows),
                               'filteredPageCount': pages}}).encode())
    m = re.search(r'/entities/([^/]+)/([^/?]+)$', url)
    if m:
        import urllib.parse as up
        name = up.unquote(m.group(2))
        return FakeResp(json.dumps(setents[name]).encode())
    raise AssertionError('unexpected url ' + url)

urllib.request.urlopen = fake_urlopen

def run(**env):
    d = tempfile.mkdtemp()
    cwd = os.getcwd(); os.chdir(d)
    os.environ.update({'NAMESPACE':'broad-firecloud-dsde-methods',
                       'WORKSPACE':'JTS_TEST_COPY', 'ENTITY_TYPE':'pfphast_sample',
                       'SET_TYPE':'', 'SET_NAME':'', 'WANTED_IDS_FILE':'',
                       'PAGE_SIZE':str(PAGE)})
    os.environ.update(env)
    g = {'__name__':'__main__'}
    try:
        exec(compile(script, 'TerraEntities.embedded', 'exec'), g)
    except SystemExit as e:
        if e.code: raise AssertionError(f'script exited {e.code}')
    out = os.path.join(d, 'pfphast_sample.tsv')
    n = int(open(os.path.join(d,'n_rows.txt')).read())
    c = int(open(os.path.join(d,'n_columns.txt')).read())
    os.chdir(cwd)
    return out, n, c

# 1. whole table
out, n, c = run()
print(f'whole table      -> {n} rows x {c} attribute columns')
assert n == 429, n
hdr = next(csv.reader(open(out), delimiter='\t'))
assert hdr[0] == 'entity:pfphast_sample_id', hdr[0]
assert 'Year' in hdr and 'resmarker_crt_76' in hdr and 'Latitude' in hdr
print(f'                    header[0]={hdr[0]!r}, Year/resmarker/Latitude all present')
assert sum(1 for _ in open(out)) == 430, 'header + 429 rows'
print(f'                    pagination: {sum("entityQuery" in u for u in calls)} page requests')

# 2. restricted to a sample set
out2, n2, c2 = run(SET_TYPE='pfphast_sample_set', SET_NAME='Good')
print(f'set "Good"       -> {n2} rows')
assert n2 == 192, n2

# 3. explicit id list, intersected with the set
ids = tempfile.mktemp()
open(ids,'w').write('\n'.join(['# comment', 'UG_TEST_G001_S68', 'UG_TEST_G002_S90', 'NOT_A_ROW']))
out3, n3, _ = run(SET_TYPE='pfphast_sample_set', SET_NAME='Good', WANTED_IDS_FILE=ids)
print(f'set + id list    -> {n3} rows (3 ids given, 1 bogus)')
assert n3 == 2, n3

# 4. the downloaded TSV is interchangeable with the hand export
mine = os.environ.get('HAND_EXPORT_TSV', '')
if mine and os.path.exists(mine):
    a = {r[0]: r for r in csv.reader(open(out), delimiter='\t')}
    b = {r[0]: r for r in csv.reader(open(mine), delimiter='\t')}
    assert set(a) - {'entity:pfphast_sample_id'} == set(b) - {'entity:pfphast_sample_id'}, 'row ids differ'
    print(f'                    same {len(a)-1} row ids as the hand-made export')
print('\nall entities-call checks passed')
