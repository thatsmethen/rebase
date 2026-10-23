"""Supplied-state branch/data-flow controls, never native execution."""
from pathlib import Path
import json,struct
HERE=Path(__file__).resolve().parent

def choice(*,event=True,excluded=0,post=0,post_field=0,eligible=1,installed=1,decoded=True,kind=0,root=True,group=True,prepared=True,clip=True,backend=True):
 if not event or excluded&1 or (post!=0 and post_field==0) or eligible==0 or installed<1:return 'no replacement'
 if not decoded or kind>=3 or not root or not group or not prepared:return 'no replacement'
 if (post&post_field)==1:return 'backend wrapper' if backend else 'no replacement'
 return 'silence wrapper' if clip else 'no replacement'
cases=[('pre baseline',{},'silence wrapper'),('initial station count zero',{'installed':0},'no replacement'),('excluded low bit',{'excluded':1},'no replacement'),('excluded even nonzero',{'excluded':2},'silence wrapper'),('post field absent',{'post':1},'no replacement'),('post field low bit',{'post':1,'post_field':1},'backend wrapper'),('post field even nonzero',{'post':1,'post_field':2},'silence wrapper'),('kind boundary2',{'kind':2},'silence wrapper'),('kind boundary3',{'kind':3},'no replacement'),('signed negative kind',{'kind':-1},'silence wrapper'),('missing returned backend',{'post':1,'post_field':1,'backend':False},'no replacement'),('missing clip in silence branch',{'clip':False},'no replacement')]
rows=[]
for label,inputs,expected in cases:
 actual=choice(**inputs);assert actual==expected;rows.append(dict(label=label,inputs=inputs,expected=expected,actual=actual))
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def bits(x):return struct.pack('>f',x).hex()
flows=[]
for source,rate,factor,returned in [(44100,48000,1,48000),(44100,48000,1,44100),(48000,44100,1,44100),(32000,48000,1.001,96000)]:
 # The independently supplied returned rate is deliberately not derived from the request.
 flows.append(dict(source_rate=f32(source),requested_device_rate=rate,requested_factor=factor,request_product=rate*factor,silence_rate_bits=bits(source),curve_rate_bits=bits(source),supplied_backend_return_rate=f32(returned),post_snapshot_bits=bits(returned)))
result=dict(kind='Finite supplied-state controls for observed branches and value ownership',target_executed=False,branch_controls=rows,data_flow_controls=flows,passed=True,limits=['These controls exercise an authored statement of the inspected host predicates; they do not execute or test a proprietary provider.','Backend returned rate is an independent supplied input. A request at provider+0xa8 is not assumed to force its returned stream+0x38 rate.','General input validity, external callbacks, project preparation and output samples remain outside these controls.'])
with(HERE/'analytical-controls.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
print(f'{len(rows)} branch controls and {len(flows)} independent supplied-return rate flows passed')
