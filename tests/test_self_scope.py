"""make_report scopes to the sample set its task was launched on.

Two layers, tested separately: terra_scope resolves the set from Cromwell's execution path
and the Terra API (tests/test_terra_entities.py covers the API shape), and make_report turns
that into a report selection. This file is the second layer, so terra_scope.detect is
stubbed rather than the network.
"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
TABLE = os.environ.get('PFPHAST_TSV') or sys.argv[1] if len(sys.argv) > 1 else None
assert TABLE and os.path.exists(TABLE), 'pass the wide Terra table as argv[1]'

import terra_scope
import make_report

SETS = json.load(open(os.environ['SET_JSON']))['entities']
members = {e['name']: [i['entityName'] for i in e['attributes']['samples']['items']]
           for e in SETS}

out = tempfile.mkdtemp()
results = {}
for name in ('Good', 'Poor'):
    terra_scope.detect = (lambda n: (lambda log=None: {
        'namespace': 'ns', 'workspace': 'ws', 'submission_id': 's', 'workflow_id': 'w',
        'entity_type': 'pfphast_sample_set', 'entity_name': n, 'members': members[n]}))(name)
    rc = make_report.main(['--assay', 'AMPLICON', '--resmarker-table', TABLE,
                           '--out-html', f'{out}/{name}.html',
                           '--out-data-json', f'{out}/{name}.json'])
    assert rc == 0, rc
    m = json.load(open(f'{out}/{name}.json'))['meta']
    results[name] = m
    print(f"  {name:5s} requested={m['n_requested']} matched={m['n_matched']} "
          f"qc_pass={m['n_qc']} selection={m['sample_selection']!r} "
          f"scope={m['terra_scope']['entity_name']}")
    assert m['sample_selection'].endswith(name)
    assert m['terra_scope']['entity_name'] == name
    assert m['n_requested'] == len(members[name])

# the whole point: the two reports must not be the same cohort
assert results['Good']['n_qc'] != results['Poor']['n_qc'], 'both sets reported the same count'
assert results['Good']['n_requested'] + results['Poor']['n_requested'] == 429

# and with no Terra context at all, nothing is scoped
terra_scope.detect = lambda log=None: None
make_report.main(['--assay', 'AMPLICON', '--resmarker-table', TABLE,
                  '--out-html', f'{out}/all.html', '--out-data-json', f'{out}/all.json'])
m = json.load(open(f'{out}/all.json'))['meta']
print(f"  off-Terra qc_pass={m['n_qc']} selection={m.get('sample_selection')!r}")
assert not m.get('sample_selection')
assert m['n_qc'] > results['Good']['n_qc']

print('\nself-scope checks passed')
