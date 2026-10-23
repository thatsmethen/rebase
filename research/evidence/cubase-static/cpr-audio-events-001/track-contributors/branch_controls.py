"""Analytical controls for selected native branches; never target execution."""
from pathlib import Path
import json,math,struct
H=Path(__file__).resolve().parent
bits=lambda x:struct.pack('>d',x).hex()
EPS=struct.unpack('>d',bytes.fromhex('3f1a36e2eb1c432d'))[0]
WATERMARK=struct.unpack('>d',bytes.fromhex('c14b774000000000'))[0]
def default(flags,global_nonzero):return (flags & (6 if global_nonzero else 4))==0
def optional(container,clip,parent):return bool(container or clip is None or clip&1 or parent is not None and parent&1)
def publish_disjoint(ranges):
 out=[];watermark=WATERMARK
 for n,(start,end)in enumerate(ranges):
  assert math.isfinite(start)and math.isfinite(end)and 0<=start<end
  if n+1<len(ranges):
   next_start=ranges[n+1][0]
   # FCMP(end,nextStart); FCCMP(abs(RN64(end-nextStart)),epsilon,8,PL)
   overlap_branch=end>=next_start and abs(end-next_start)>=EPS
   assert not overlap_branch,'outside the admitted publication-only branch'
  start=max(start,watermark);watermark=max(watermark,end)
  if end-start>0:out.append((start,end))
 return out
flags=[dict(flags=f,global_nonzero=g,result=default(f,g))for f in range(16)for g in [False,True]]
assert all(row['result']for row in flags if row['flags']==0)
root=[dict(container=c,clip_flags=f,parent_flags=p,result=optional(c,f,p))for c in [False,True]for f in [None,0,1,0x600]for p in [None,0,1]]
assert not optional(False,0,0)and optional(False,None,0)
ranges=[]
for start in [0.,1.,10.,1000.]:
 for length in [1e-8,1e-4,0.25,2.]:
  a=(start,start+length)
  for gap in [0.,1e-8,1e-4,1.]:
   b=(a[1]+gap,a[1]+gap+length)
   if b[0]==b[1]:continue
   got=publish_disjoint([a,b]);assert got==[a,b]
   ranges.append(dict(input_bits=[[bits(x)for x in p]for p in [a,b]],output_bits=[[bits(x)for x in p]for p in got],identity=True))
# Native threshold is overlap distance, not a stand-alone minimum event length.
a=(1.,math.nextafter(1.,math.inf));b=(2.,math.nextafter(2.,math.inf));assert publish_disjoint([a,b])==[a,b]
ranges.append(dict(input_bits=[[bits(x)for x in p]for p in [a,b]],output_bits=[[bits(x)for x in p]for p in [a,b]],identity=True,discriminator='positive nextafter widths smaller than epsilon survive normalization; later sample snapping may collapse'))
negative=[]
for label,r in [('unsorted',[(2.,3.),(0.,1.)]),('overlap',[(0.,2.),(1.,3.)]),('zero-width',[(0.,0.),(1.,2.)])]:
 admitted=all(a[0]>=0 and a[0]<a[1] for a in r)and all(r[i][1]<=r[i+1][0]for i in range(len(r)-1))
 assert not admitted;negative.append(dict(label=label,conservative_admission=False))
x=dict(kind='synthetic analytical branch controls, not native execution or application acceptance',source_sha256='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb',epsilon_bits=bits(EPS),watermark_bits=bits(WATERMARK),default_filter=flags,optional_filter=root,normalizer_disjoint=ranges,conservative_rejections=negative,summary=dict(default_filter_rows=len(flags),optional_root_rows=len(root),positive_disjoint_rows=len(ranges),negative_admission_rows=len(negative),total=len(flags)+len(root)+len(ranges)+len(negative)),passed=True,limitations=['Model follows retained local instructions only; it is not a target runtime oracle.','No general overlapping normalizer implementation or source-derived hosted root mode is claimed.','No subnormal, NaN, infinity, allocation failure, callback mutation or linked object lifetime contract.'])
(H/'branch-controls.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x['summary']))
