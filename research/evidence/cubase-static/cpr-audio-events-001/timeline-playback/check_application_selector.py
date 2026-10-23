"""Independent finite-vector check of our reconstruction only, never Cubase code."""
from pathlib import Path
import ctypes,json,hashlib,subprocess,math,shutil
H=Path(__file__).resolve().parent;ROOT=H.parents[4]
source=ROOT/'Application/Sources/RebaseTimingDSP/cpr_timeline_selector.c';header=source.parent/'include/cpr_timeline_selector.h';swift=ROOT/'Application/Sources/RebaseCore/CPRTimelineSelection.swift'
S=H/'application-review';S.mkdir(exist_ok=True)
for p in [source,header,swift]:shutil.copyfile(p,S/p.name)
cmd=['/usr/bin/clang','-O2','-dynamiclib','-ffp-contract=off','-I',str(S),str(S/source.name),'-o',str(S/'selector-control.dylib')]
p=subprocess.run(cmd,text=True,capture_output=True);(S/'compile-output.txt').write_text(p.stdout+p.stderr);assert p.returncode==0
lib=ctypes.CDLL(str(S/'selector-control.dylib'));f=lib.rb_cpr_timeline_select
D=ctypes.c_double;I=ctypes.c_int64;U=ctypes.c_uint32
f.argtypes=[ctypes.POINTER(D),ctypes.POINTER(D),ctypes.POINTER(I),ctypes.c_size_t,U,D,I,U,ctypes.POINTER(I),ctypes.POINTER(U)];f.restype=ctypes.c_int
import struct
def val(h):return struct.unpack('>d',bytes.fromhex(h))[0]
checks=[]
for row in json.loads((H/'analytical-controls.json').read_text())['controls']:
 query=val(row['query_bits'])
 if query<0:continue # stricter application admission, not native finite scope
 rows=row['segments'];n=len(rows);ss=(D*n)(*[val(x['start_bits'])for x in rows]);ll=(D*n)(*[val(x['length_bits'])for x in rows]);nn=(I*n)(*[x['successor']if x['successor']is not None else -1 for x in rows]);out=I(-99);gen=U(0xbad)
 status=f(ss,ll,nn,n,row['generation'],query,row['current']if row['current']is not None else -1,row['cursor_generation'],ctypes.byref(out),ctypes.byref(gen))
 expected=row['result']['selected'];assert(status,out.value,gen.value)==(0,expected if expected is not None else -1,row['result']['cursor_generation']),row['name']
 checks.append(row['name'])
refs=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in [source,header,swift]]
report=dict(scope='Read-only source review plus optimized execution of independently implemented C selector, not target code; no device or Cubase execution',files=refs,compile_command=cmd,controls_passed=len(checks),controls=checks,analytical_negative_query_controls_excluded='The application intentionally requires nonnegative coordinates; native finite selector itself has no such check.',review=dict(fixed='Initial array-index scan replaced by linked traversal from head0, matching native list iterator. The negative linked-order control discriminates this error.',no_remaining_issue_in_scope=True,limits=['Normal-or-zero finite coordinate/domain check,4096 cap,nearest-even enforcement,cycle failure and safe bounds are application guards absent in native selector.','C uses indices and stable arrays, not pointer/reference ownership or lock callbacks.','Swift reset mirrors null current+u32 generation; selecting updates only generation.','Current field remains caller-owned; cached successor ignores query.','Half-open sample scheduling and seconds-to-frame policy are outside this source review.']),target_execution=False)
(S/'review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'controls_passed':len(checks),'source_sha256':refs[0]['sha256']}))
