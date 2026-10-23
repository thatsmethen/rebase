"""Read-only original-image mappings and bounded exact instruction derivatives."""
import bisect,hashlib,json,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
SOURCE=ROOT/'research/targets/derived/Cubase15-arm64'
PIN='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
data=SOURCE.read_bytes()
assert hashlib.sha256(data).hexdigest()==PIN
segments=[];sections=[];pos=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 cmd,n=struct.unpack_from('<II',data,pos)
 if cmd==0x19:
  v=struct.unpack_from('<II16sQQQQIIII',data,pos)
  segments.append(dict(name=v[2].rstrip(b'\0').decode(),address=v[3],offset=v[5],size=v[6]))
  for j in range(v[9]):
   s=struct.unpack_from('<16s16sQQIIIIIIII',data,pos+72+j*80)
   sections.append(dict(name=s[0].rstrip(b'\0').decode(),segment=s[1].rstrip(b'\0').decode(),address=s[2],size=s[3],offset=s[4]))
 if cmd==0x26: _,_,fs_offset,fs_size=struct.unpack_from('<IIII',data,pos)
 pos+=n
def address(offset):
 s,=[s for s in segments if s['offset']<=offset<s['offset']+s['size']]
 return s['address']+offset-s['offset']
def offset(address,length=1):
 s,=[s for s in segments if s['address']<=address and address+length<=s['address']+s['size']]
 return s['offset']+address-s['address']
def region(address,length):
 o=offset(address,length);b=data[o:o+length]
 return dict(address=hex(address),file_offset=o,length=length,bytes_hex=b.hex(),sha256=hashlib.sha256(b).hexdigest())
starts=[];a=next(s['address']for s in segments if s['name']=='__TEXT');delta=shift=0
for b in data[fs_offset:fs_offset+fs_size]:
 delta|=(b&127)<<shift
 if b&128:shift+=7
 else:
  if delta==0:break
  a+=delta;starts.append(a);delta=shift=0
def containing(a): return starts[bisect.bisect_right(starts,a)-1]
def derive(addresses,directory):
 rows=[];directory=Path(directory);directory.mkdir(exist_ok=True)
 for a in addresses:
  i=starts.index(a);end=starts[i+1];o=offset(a,end-a);b=data[o:o+end-a]
  name=f'function-{a:x}.arm64.bin';(directory/name).write_bytes(b)
  command=['/Library/Developer/CommandLineTools/usr/bin/llvm-objdump','-d','--start-address='+hex(a),'--stop-address='+hex(end),str(SOURCE)]
  native=subprocess.check_output(command,text=True);native_name=f'native-{a:x}.txt';(directory/native_name).write_text(native)
  rows.append(dict(entry=hex(a),next_declared_function_start=hex(end),source_file_offset=o,length=len(b),raw_file=name,raw_sha256=hashlib.sha256(b).hexdigest(),original_native_disassembly=native_name,native_command=command,native_stdout_sha256=hashlib.sha256(native.encode()).hexdigest(),boundary='LC_FUNCTION_STARTS interval, not proof of exact function body; disconnected exception tails may exist'))
 report=dict(source=str(SOURCE),source_sha256=PIN,source_bytes=len(data),derivatives=rows,losses=['Raw slices omit imports,globals,RTTI,vtables,relocations,unwind and neighboring code; original target addresses preserved but externals are unmapped. No target code executed.'])
 (directory/'derivation.json').write_text(json.dumps(report,indent=2)+'\n');return rows
