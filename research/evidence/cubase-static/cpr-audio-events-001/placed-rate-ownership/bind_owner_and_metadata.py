"""Read-only supplemental owner and metadata bindings from retained original records."""
from pathlib import Path
import hashlib, json, re, struct, sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

def pin(path):
    data=path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

rows=[]
records=[
 ('segment-consumer/native-10036a52c.txt','AudioCluster +f8 factory passes exact cluster as constructor x1; failure returns nil'),
 ('accessor-seek-state/pass2/native-10033d530.txt','AudioFile format ID delegates current kind and bit-width getters'),
 ('accessor-seek-state/pass3/native-10033d024.txt','AudioFile kind lazy-loads then queries AudioSampleFormat'),
 ('accessor-seek-state/pass3/native-10033d308.txt','AudioFile bits lazy-loads then queries AudioSampleSize; failure uses fallback'),
]
for name,claim in records:
    path=HERE.parent/name
    words=[(int(a,16),int(w,16)) for a,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',path.read_text(),re.M)]
    assert words
    for a,w in words: assert struct.unpack_from('<I',s.data,s.offset(a,4))[0]==w
    rows.append(dict(record=pin(path),claim=claim,original_words_checked=len(words),
                     first=hex(words[0][0]),last=hex(words[-1][0])))
cell=s.region(0x104466150+0xf8,8)
assert int.from_bytes(bytes.fromhex(cell['bytes_hex']),'little')==0x10036a52c
literals=[]
for a,value in [(0x10388f5fc,b'AudioSampleFormat\0'),(0x10388f01f,b'AudioSampleSize\0')]:
    row=s.region(a,len(value));assert bytes.fromhex(row['bytes_hex'])==value;literals.append(row)
out=dict(source_sha256=s.PIN,cluster_factory_dispatch=cell,checked_original_records=rows,
         literals=literals,passed=True,target_execution=False,
         qualification='Current AudioFile property queries call the lazy backend helper. These bindings do not establish registry selection, successful property population, provider identity or format invariance from a filename/CPR metadata alone.')
with (HERE/'owner-and-metadata-bindings.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(dict(passed=True,records=len(rows),original_words=sum(r['original_words_checked'] for r in rows))))
