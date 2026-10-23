"""Bind gain dispatch and reused native words to the preserved original image."""
from pathlib import Path
import hashlib,json,re,struct,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
BASE=ROOT/'research/evidence/cubase-static/cpr-audio-events-001'
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

def pin(p):
    b=p.read_bytes()
    return dict(path=str(p.relative_to(ROOT)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())

reused=[]
for name in [
    'rate-converter/native-10033035c.txt',
    'rate-converter/native-100330cd4.txt',
    'rate-converter/native-10032ddd0.txt',
    'rate-converter/native-10032f014.txt',
    'accessor-format-order/pass1/native-100326c4c.txt',
    'accessor-format-order/pass1/native-1003312c4.txt',
    'accessor-format-order/pass1/native-1037d88d4.txt',
    'accessor-seek-state/pass1/native-10036eff0.txt',
    'segment-consumer/native-10036fb74.txt',
    'placed-rate-ownership/pass1/native-100370538.txt',
]:
    p=BASE/name
    words=re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',p.read_text(),re.M)
    assert words
    for a,w in words:
        assert struct.unpack_from('<I',s.data,s.offset(int(a,16),4))[0]==int(w,16)
    reused.append(dict(**pin(p),words=len(words)))

cells=[]
for table,index,base,target,role in [
    (0x1039346b8,3,0x10032d2d4,0x10032d4a4,'generic gain destination bits32 dispatch'),
    (0x103934718,2,0x10032ddf0,0x10032e4fc,'equal-rate interleaved source PCM24 fast path'),
    (0x103934718,3,0x10032ddf0,0x10032e538,'equal-rate interleaved source bits32 fast path'),
]:
    row=s.region(table+index*2,2)
    assert base+int.from_bytes(bytes.fromhex(row['bytes_hex']),'little')*4==target
    cells.append(dict(**row,table=hex(table),index=index,base=hex(base),target=hex(target),role=role))
dispatch=[]
for off,target,role in [(0x160,0x100370538,'gain setter'),(0x188,0x10036fb74,'conversion-needed predicate')]:
    row=s.region(0x1044664f0+off,8)
    assert int.from_bytes(bytes.fromhex(row['bytes_hex']),'little')==target
    dispatch.append(dict(**row,base='0x1044664f0',slot=hex(off),target=hex(target),role=role))

spans=[]
for begin,end,role in [
    (0x1003303e0,0x1003303f8,'gain!=1 sets the generic gain flag'),
    (0x1003306e4,0x1003308f0,'rate/type/channel/gain/rate phase order'),
    (0x1003309e0,0x100330a08,'gain-only final phase'),
    (0x10032dddc,0x10032de00,'first fast path rejects unequal rates'),
    (0x10032f020,0x10032f044,'second fast path rejects unequal rates'),
    (0x10032de08,0x10032de9c,'equal-rate Float32 destination and layout/endian checks'),
    (0x10032e0a8,0x10032e0c8,'equal-rate source-width jump dispatch'),
    (0x10032e4fc,0x10032e544,'PCM24 and Float32 source kinds, gain load and decoder alternatives'),
    (0x10032e63c,0x10032e674,'equal-rate Float32 kind2 helpers receive gain'),
    (0x10032e6dc,0x10032e6f4,'CPU mask chooses one of the two helpers'),
    (0x10032d4a4,0x10032d548,'Float32 gain vector/scalar FMUL with no clipping'),
    (0x10036fc58,0x10036fc88,'otherwise-matching format requires conversion for gain!=1'),
    (0x10036f060,0x10036f0e4,'predicate, retained converter, per-call gain copy and first-flag clear'),
    (0x100370538,0x100370540,'gain setter only stores gain; no history or first-flag reset'),
]:
    spans.append(dict(**s.region(begin,end-begin),role=role))

report=dict(source=pin(s.SOURCE),source_sha256=s.PIN,target_executed=False,
    reused_word_checks=reused,jump_table_cells=cells,dispatch_cells=dispatch,spans=spans,
    external_references=[pin(BASE/n) for n in [
        'accessor-format-order/finding.json','accessor-format-order/artifact-manifest.json',
        'accessor-seek-state/finding.json','accessor-seek-state/artifact-manifest.json',
        'placed-rate-ownership/finding.json','placed-rate-ownership/artifact-manifest.json',
        'rate-converter/finding.json','segment-consumer/finding.json']],
    scope='Exact original-image words and dispatch. Explicit source format, stereo interleaved buffers and Float32 destination; no hosted backend, channel context or runtime selection inferred.')
with (HERE/'original-bindings.json').open('x') as f:
    json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(dict(reused_words=sum(r['words'] for r in reused),jump_cells=len(cells),dispatch_cells=len(dispatch),spans=len(spans),passed=True)))
