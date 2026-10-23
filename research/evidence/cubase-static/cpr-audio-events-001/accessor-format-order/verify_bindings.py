"""Recheck exact source spans, table targets and reused instruction words."""
from pathlib import Path
import hashlib,json,re,struct,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

d=json.loads((HERE/'original-bindings.json').read_text())
assert d['source_sha256']==s.PIN and d['target_executed'] is False
for row in d['spans']+d['jump_table_cells']:
    actual=s.region(int(row['address'],16),row['length'])
    assert all(actual[k]==row[k] for k in actual)
for row in d['jump_table_cells']:
    assert int(row['base'],16)+int.from_bytes(bytes.fromhex(row['bytes_hex']),'little')*4==int(row['target'],16)
for row in d['external_references']:
    raw=(ROOT/row['path']).read_bytes()
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
words=0
for row in d['reused_word_checks']:
    entries=re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',(ROOT/row['path']).read_text(),re.M)
    assert len(entries)==row['words']
    for a,w in entries:
        assert bytes.fromhex(s.region(int(a,16),4)['bytes_hex'])==struct.pack('<I',int(w,16))
    words+=len(entries)
print(json.dumps(dict(passed=True,spans=len(d['spans']),table_cells=len(d['jump_table_cells']),reused_words=words)))
