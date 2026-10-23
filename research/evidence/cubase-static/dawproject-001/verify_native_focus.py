#!/usr/bin/env python3
"""Read original bytes and compare bounded REA/LLVM static evidence; no execution."""
import hashlib
import json
import pathlib
import re
import struct

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[3]
thin = (OUT / 'DAWproject.arm64.macho').read_bytes()
def sha(data): return hashlib.sha256(data).hexdigest()
assert sha(thin) == '771f67c3d3b9b549a91406b2b6ee7b2b2ecfe74673c68e93a88c9a68f52d875a'
source = ROOT / 'research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/Cubase 15.app/Contents/Components/DAWproject.bundle/Contents/MacOS/DAWproject'
universal = source.read_bytes()
assert sha(universal) == '363f6e6cd3dd6424564f258a21bd478ea712b2b3fa449a55cac6bd1159ce41f0'
assert universal[1949696:1949696+len(thin)] == thin
assert struct.unpack_from('<I', thin)[0] == 0xfeedfacf
segments = []
offset = 32
for _ in range(struct.unpack_from('<I', thin, 16)[0]):
    command, size = struct.unpack_from('<II', thin, offset)
    if command == 0x19:
        name, vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<16sQQQQ', thin, offset + 8)
        segments.append((vmaddr, fileoff, filesize))
    offset += size
def bytes_at(address, size):
    matches = [fileoff + address - vmaddr for vmaddr, fileoff, filesize in segments
               if vmaddr <= address and address + size <= vmaddr + filesize]
    assert len(matches) == 1
    return thin[matches[0]:matches[0]+size]
llvm_rows = {}
for line in (OUT/'interpolation-helper-llvm.txt').read_text().splitlines():
    m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)', line)
    if m:
        address, word = int(m[1],16), int(m[2],16)
        assert struct.unpack('<I', bytes_at(address,4))[0] == word
        llvm_rows[address] = m[3]
rea = json.loads((OUT/'native-focus/0010-response.json').read_text())['result']['structuredContent']
rea_rows = {int(m[1],16):m[2] for m in re.finditer(r'^0x([0-9a-f]+): (.*)$',rea['normalized_result'],re.M)}
assert set(llvm_rows) == set(rea_rows) == set(range(0x6c1e0,0x6c294,4))
assert all(llvm_rows[a].split()[0] == rea_rows[a].split()[0] for a in rea_rows)
checks = [{'address':hex(a),'bytes':n,'sha256':sha(bytes_at(a,n))} for a,n in
          [(0x6c1e0,180),(0x60f08,8),(0x60f10,8),(0x53a74,8),(0x16207e,7),(0x16242d,14)]]
assert bytes_at(0x16207e,7) == b'linear\0'
assert bytes_at(0x16242d,14) == b'interpolation\0'
record = {'thin_sha256':sha(thin),'universal_sha256':sha(universal),
          'source_path':str(source.relative_to(ROOT)), 'slice_offset':1949696,'slice_bytes':len(thin),
          'slice_equals_original':True,'llvm_word_matches':len(llvm_rows),'rea_address_mnemonic_matches':len(rea_rows),
          'ranges':checks,'limitations':['Instruction operands were inspected manually; the automated cross-check compares original word values, address sets and mnemonic names.','Static bytes and analysis do not establish runtime reachability or host parameter semantics.']}
(OUT/'native-byte-provenance.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
