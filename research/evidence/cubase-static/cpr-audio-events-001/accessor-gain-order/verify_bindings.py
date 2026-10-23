"""Read-only verification of gain source bindings and frozen candidate controls."""
from pathlib import Path
import hashlib,json,re,struct,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
def check(row):
    b=(ROOT/row['path']).read_bytes()
    assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],row['path']
d=json.loads((HERE/'original-bindings.json').read_text())
assert d['source_sha256']==s.PIN and not d['target_executed'];check(d['source'])
for row in d['spans']+d['jump_table_cells']+d['dispatch_cells']:
    actual=s.region(int(row['address'],16),row['length'])
    assert all(row[k]==v for k,v in actual.items())
for row in d['jump_table_cells']:
    assert int(row['base'],16)+4*int.from_bytes(bytes.fromhex(row['bytes_hex']),'little')==int(row['target'],16)
for row in d['dispatch_cells']:
    assert int.from_bytes(bytes.fromhex(row['bytes_hex']),'little')==int(row['target'],16)
for row in d['external_references']+d['reused_word_checks']:check(row)
for row in d['reused_word_checks']:
    words=re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',(ROOT/row['path']).read_text(),re.M)
    assert len(words)==row['words']
    for a,w in words:assert struct.unpack_from('<I',s.data,s.offset(int(a,16),4))[0]==int(w,16)
c=json.loads((HERE/'gain-controls.json').read_text())
assert c['status']=='passed'
for row in c['inputs']+c['reviewed_sources']:check(row)
for run in c['results']:
    for key in ['executable','build_log','run_log']:check(run[key])
    assert run['result']['passed'] and run['result']['gain_vectors']==3168 and run['result']['q24_gain_vectors']==96
print(json.dumps(dict(passed=True,reused_words=sum(r['words'] for r in d['reused_word_checks']),jump_cells=len(d['jump_table_cells']),dispatch_cells=len(d['dispatch_cells']),spans=len(d['spans']),candidate_builds=len(c['results']))))
