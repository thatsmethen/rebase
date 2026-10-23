"""Verify every retained native interval and every completed REA readback."""
from pathlib import Path
import datetime, hashlib, json, re, struct
HERE=Path(__file__).resolve().parent
manifests=[json.loads((HERE/name).read_text()) for name in ['derivation.json']+[f'derivation-pass{i}.json' for i in range(2,13)]]
SOURCE=Path(manifests[0]['source']);before=SOURCE.stat();data=SOURCE.read_bytes();after=SOURCE.stat()
identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
assert identity(before)==identity(after)
assert hashlib.sha256(data).hexdigest()==manifests[0]['source_sha256']
def evidence(path):
    obj=json.loads(path.read_text());assert not obj.get('isError',False)
    return obj.get('structuredContent') or json.loads(obj['content'][0]['text'])
rows=[]
for m in manifests:
    assert m['source_sha256']==manifests[0]['source_sha256']
    for r in m['derivatives']:
        raw=(HERE/r['raw_file']).read_bytes();a=int(r['entry'],16);key=r['entry'][2:]
        assert len(raw)==r['length'] and raw==data[r['source_file_offset']:r['source_file_offset']+len(raw)]
        assert hashlib.sha256(raw).hexdigest()==r['raw_sha256']
        native=(HERE/r['native_file']).read_bytes();assert hashlib.sha256(native).hexdigest()==r['native_sha256']
        words={int(pc,16):int(w,16) for pc,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native.decode(),re.M)}
        assert len(words)*4==len(raw)
        for pc,w in words.items():assert struct.unpack_from('<I',raw,pc-a)[0]==w
        row=dict(entry=r['entry'],source_offset=r['source_file_offset'],bytes=len(raw),raw_sha256=r['raw_sha256'],native_words=len(words),rea=None)
        if (HERE/f'function-{key}.json').exists():
            read=evidence(HERE/f'bytes-{key}.json')['raw_result']
            assert read['complete'] and read['returned_bytes']==len(raw) and bytes.fromhex(read['bytes_hex'])==raw
            value=evidence(HERE/f'function-{key}.json')['raw_result']['value']
            pcs=[int(x.split(':')[0],16) for x in value['assembly']]
            assert len(set(pcs))==len(pcs) and all(pc in words for pc in pcs)
            for span in value['procedure']['body']['ranges']:
                assert a<=int(span['start'],16)<=int(span['end'],16)<a+len(raw)
            evidence(HERE/f'bundle-{key}.json');evidence(HERE/f'close-{key}.json')
            assert (HERE/f'snapshot-{key}.json').exists()
            row['rea']=dict(addresses=len(pcs),readback_exact=True,body=value['procedure']['body'],warnings=[s for s in value['pseudocode'].splitlines() if 'WARNING' in s])
        rows.append(row)
assert len({r['entry'] for r in rows})==len(rows)
result=dict(at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source=str(SOURCE),source_sha256=manifests[0]['source_sha256'],source_unchanged_during_read=True,functions=rows,counts=dict(native_functions=len(rows),native_bytes=sum(r['bytes'] for r in rows),native_words=sum(r['native_words'] for r in rows),rea_functions=sum(r['rea'] is not None for r in rows),rea_addresses=sum(r['rea']['addresses'] for r in rows if r['rea'])),scope='Static source/readback/address custody only. No semantic or runtime conformance inferred from verification.',target_executed=False,passed=True)
with (HERE/'verification-final.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result['counts']))
