#!/usr/bin/env python3
"""Read-only independent verification of process-state source/native evidence."""
import hashlib
import json
import pathlib
import re
import struct
from datetime import datetime, timezone

OUT = pathlib.Path(__file__).resolve().parent
SRC = OUT.parent / 'ambisonic'
def sha(b): return hashlib.sha256(b).hexdigest()
def read(name):
    x = json.loads((SRC/name).read_text())
    return x.get('structuredContent',x)
def normalized(name):
    x = read(name)['normalized_result']
    return x.get('value',x)

derivation = read('arm64-derivation.json')
source = pathlib.Path(derivation['source_path']).read_bytes()
thin = pathlib.Path(derivation['derived_path']).read_bytes()
assert sha(source) == 'e803dd1390ee7989306b15c0fccca52e5d3097ae7a489dc6834f82b50ba485c5'
assert sha(thin) == 'e8341c6b31ac6b65cf7e8c18bdfbaa18ac24b20160b4287dc385b202eb29b883'
assert source[derivation['source_offset']:derivation['source_offset']+derivation['length']] == thin
assert struct.unpack_from('<I',thin)[0] == 0xfeedfacf
segments, sections = [], []
cursor = 32
for _ in range(struct.unpack_from('<I',thin,16)[0]):
    cmd,size = struct.unpack_from('<II',thin,cursor)
    if cmd == 0x19:
        name = thin[cursor+8:cursor+24].split(b'\0')[0].decode()
        va,vs,off,fs = struct.unpack_from('<QQQQ',thin,cursor+24)
        segments.append((name,va,vs,off,fs))
        nsects = struct.unpack_from('<I',thin,cursor+64)[0]
        for i in range(nsects):
            at = cursor+72+80*i
            sectname = thin[at:at+16].split(b'\0')[0].decode()
            sva,ssize,soff = struct.unpack_from('<QQI',thin,at+32)
            flags,res1,res2 = struct.unpack_from('<III',thin,at+64)
            sections.append((sectname,sva,ssize,soff,flags,res1,res2))
    elif cmd == 0x2:
        symoff,nsyms,stroff,strsize = struct.unpack_from('<IIII',thin,cursor+8)
    elif cmd == 0xb:
        indirect_off,indirect_count = struct.unpack_from('<II',thin,cursor+56)
    cursor += size

def offset(va,size):
    candidates=[off+va-start for _,start,_,off,fs in segments if start<=va and va+size<=start+fs]
    assert len(candidates)==1
    return candidates[0]
def raw(va,size):
    off=offset(va,size)
    return thin[off:off+size]

native_files=[]
instructions={}
for command in json.loads((OUT/'native-commands.json').read_text()):
    f=OUT/command['output']; b=f.read_bytes()
    assert sha(b)==command['stdout_sha256']
    count=0
    for line in b.decode().splitlines():
        m=re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)',line)
        if m:
            address,word=int(m[1],16),int(m[2],16)
            assert struct.unpack('<I',raw(address,4))[0]==word
            instructions[address]={'word':f'{word:08x}','assembly':m[3]}
            count+=1
    native_files.append({'file':f.name,'sha256':sha(b),'instruction_words_verified':count})

slots=[]
for address,target in [(0x1d7678,0x154a8c),(0x1d76b0,0x154b64),(0x1d7798,0x154d4c),(0x1d77d0,0x154e28)]:
    assert struct.unpack('<Q',raw(address,8))[0]==target
    slots.append({'address':hex(address),'target':hex(target),'source_bytes_hex':raw(address,8).hex()})

imports=[]
for target,expected in [(0x16e6d4,'_vDSP_maxmgv'),(0x16e6e0,'_vDSP_maxmgvD')]:
    section=next(s for s in sections if s[1]<=target<s[1]+s[2] and s[4]&0xff==8)
    _,va,_,_,_,reserved1,stride=section
    assert (target-va)%stride==0
    indirect_index=reserved1+(target-va)//stride
    assert indirect_index<indirect_count
    symbol_index=struct.unpack_from('<I',thin,indirect_off+indirect_index*4)[0]
    assert symbol_index<nsyms
    strx=struct.unpack_from('<I',thin,symoff+16*symbol_index)[0]
    end=thin.index(b'\0',stroff+strx,stroff+strsize)
    name=thin[stroff+strx:end].decode()
    assert name==expected,(hex(target),name)
    imports.append({'stub':hex(target),'symbol':name,'indirect_index':indirect_index,'symbol_index':symbol_index})

inputs=[]
for name in ['processor-process-function.json','direction-parameter-consumer.json',
             'float-bypass-process-function.json','float-channel-permutation-function.json',
             'double-channel-permutation-function.json','float-buffer-copy-function.json',
             'double-buffer-copy-function.json','algorithm-vtables.json',
             'float-conversion-process-function.json','double-conversion-process-function.json',
             'reference-ivstaudioprocessor.h','reference-ivstparameterchanges.h']:
    b=(SRC/name).read_bytes(); item={'file':'../ambisonic/'+name,'sha256':sha(b)}
    if name.endswith('.json'):
        x=read(name)
        assert x['subject']['digest']['sha256']==sha(thin)
        item['evidence_id']=x['evidence_id'];item['provider']=x['provider'];item['analysis_profile_digest']=x['analysis_profile']['digest']
    inputs.append(item)

finding=read('state-contract-finding.json')
for reference in finding['evidence']['public_abi_references']:
    assert sha((SRC/reference['local_file']).read_bytes())==reference['sha256']
provenance=read('state-analysis/byte-provenance.json')
assert sha((SRC/'state-analysis/byte-provenance.json').read_bytes())==finding['evidence']['byte_provenance_sha256']
assert sha((SRC/'state-analysis/verification.json').read_bytes())==finding['evidence']['new_verification_sha256']
retained_count=0
for fn in provenance['retained_functions']:
    assert sha((SRC/fn['file']).read_bytes())==fn['file_sha256']
    ev=read(fn['file']); assert ev['evidence_id']==fn['evidence_id']
    decoded=normalized(fn['file'])['assembly']
    assert len(decoded)==len(fn['instructions'])
    for line,item in zip(decoded,fn['instructions']):
        assert int(line.split(':',1)[0],16)==int(item['address'],16)
        assert struct.unpack('<I',raw(int(item['address'],16),4))[0]==int(item['word'],16)
        retained_count+=1
    for r in fn['ranges']:
        address=int(r['start'],16)
        assert offset(address,r['length'])==r['thin_offset']
        assert r['universal_offset']==derivation['source_offset']+r['thin_offset']
        assert sha(raw(address,r['length']))==r['sha256']
assert retained_count==656
raw_bypass=(SRC/'state-analysis/double-bypass.arm64.bin').read_bytes()
assert raw_bypass==raw(0x154b64,120)
assert sha(raw_bypass)=='90b970fc00a7f7dccaf5c8fe51dca90cbf8707185dfdd2a7713f0719dd4502cc'
ev=read('state-analysis/double-bypass-function.json')
assert ev['evidence_id']==finding['evidence']['new_double_bypass_evidence_id']
assert ev['subject']['digest']['sha256']==sha(raw_bypass)
b=normalized('state-analysis/double-bypass-bytes.json')
assert b['complete'] and b['returned_bytes']==120 and bytes.fromhex(b['bytes_hex'])==raw_bypass
assert len(normalized('state-analysis/double-bypass-function.json')['assembly'])==30
for name in ['state-contract-finding.json','state-analysis/byte-provenance.json',
             'state-analysis/verification.json','state-analysis/double-bypass.arm64.bin',
             'state-analysis/double-bypass-function.json','state-analysis/double-bypass-bytes.json']:
    inputs.append({'file':'../ambisonic/'+name,'sha256':sha((SRC/name).read_bytes())})

report={'recorded_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Independent static byte, native instruction, dispatch-slot and imported-symbol checks; no target execution.',
        'target_executed':False,'new_ghidra_import':False,'source_sha256':sha(source),'arm64_sha256':sha(thin),
        'source_slice_identical':True,'native_files':native_files,
        'instruction_words_verified':sum(x['instruction_words_verified'] for x in native_files),
        'dispatch_slots':slots,'meter_imports':imports,
        'author_retained_instruction_words_checked':retained_count,
        'new_raw_bypass':{'bytes':120,'instructions':30,'readback_equals_raw_and_source':True,
                          'evidence_id':ev['evidence_id'],'profile_digest':ev['analysis_profile']['digest']},
        'inputs':inputs}
(OUT/'native-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':'pass','instruction_words_verified':report['instruction_words_verified'],
                  'meter_imports':imports,'dispatch_slots':slots},indent=2))
