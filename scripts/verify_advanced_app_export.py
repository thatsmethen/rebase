#!/usr/bin/env python3
"""Independent analytical oracle for the fixed APP002 demonstration.

No application code is imported. Gain and pan are explicit formulas for this
fixture, not a second implementation of its general automation evaluator.
The fixture manifest is checked before comparison; any changed semantics reject.
"""
from pathlib import Path
from array import array
import argparse, hashlib, json, math, struct
from verify_app_demo_export import decode_source, require, f32, RATE
from audio_probe import read_wave


def verify(project, destination):
 p=json.loads((project/'Project.json').read_text())
 require(p['sampleRate']==RATE and len(p['tracks'])==3, 'Pinned three-track 48k fixture required')
 require([(x['beat'],x['bpm'],x['curve']) for x in p['tempoMap']['events']]==[(0,120,'jump'),(8,90,'jump')], 'Unexpected tempo map')
 require([(x['beat'],x['numerator'],x['denominator']) for x in p['signatureMap']['events']]==[(0,4,4),(8,3,4),(20,4,4)], 'Unexpected signatures')
 expected=array('f',[0.0])*(648000*2)
 for n,track in enumerate(p['tracks']):
  require(track['name']==['Pulse','Low Orbit','Glass Keys'][n] and not track['isMuted'] and not track['isSolo'] and track['pan']==0 and track['gainDB']==[0,0,-3][n], 'Unexpected track state')
  require(len(track['clips'])==1, 'One clip per track required')
  clip=track['clips'][0]
  require((clip['position'],clip['sourceOffset'],clip['duration'])==([0,0,1.5][n],0,12), 'Unexpected clip interval')
  require(clip['timeBase']==('musical' if n==2 else 'seconds') and (n!=2 or clip['musicalPosition']==3), 'Unexpected clip anchor')
  lane=track['automation']
  wanted=[[(0,-12,'linear'),(4,0,'step'),(8,-6,'linear')],[(0,-.75,'linear'),(6,.75,'linear')],[]][n]
  require(len(lane)==(1 if n<2 else 0), 'Unexpected automation lane')
  if lane:
   require(lane[0]['isReadEnabled'] and lane[0]['parameter']==['gainDB','pan'][n], 'Unexpected lane state')
   require([(x['time'],x['value'],x['interpolation']) for x in lane[0]['points']]==wanted, 'Unexpected curve')
  samples,_=decode_source(project/clip['mediaPath'])
  start=[0,0,72000][n]
  for frame in range(576000):
   t=(start+frame)/RATE
   db=(-12+3*t if t<4 else 0 if t<8 else -6) if n==0 else [0,0,-3][n]
   pan=(-.75+.25*t if t<6 else .75) if n==1 else 0
   amplitude=math.pow(10,db/20)
   for channel in range(2):
    balance=math.sqrt(min(1,1+pan if channel else 1-pan))
    value=f32(samples[frame*2+channel]/32768 * (amplitude*balance))
    index=(start+frame)*2+channel
    expected[index]=f32(expected[index]+value)
 actual=read_wave(destination)
 require((actual.rate,actual.channels,actual.frames,actual.bits,actual.format_tag)==(RATE,2,648000,32,3), 'Unexpected output shape')
 got=array('f')
 for frame in range(actual.frames):
  got.extend((actual.samples[0][frame],actual.samples[1][frame]))
 differences=sum(a!=b for a,b in zip(got,expected))
 zero_signs=sum(a==b==0 and struct.pack('<f',a)!=struct.pack('<f',b) for a,b in zip(got,expected))
 peak=max(abs(a-b) for a,b in zip(got,expected))
 return dict(status='pass' if differences==0 and zero_signs==0 else 'fail',frames=actual.frames,channels=2,sample_rate=RATE,numerical_differences=differences,signed_zero_differences=zero_signs,maximum_absolute_difference=peak,expected_float32_sha256=hashlib.sha256(expected.tobytes()).hexdigest(),actual_float32_sha256=hashlib.sha256(got.tobytes()).hexdigest(),project_manifest_sha256=hashlib.sha256((project/'Project.json').read_bytes()).hexdigest(),export_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),scope='APP002 independent application formula comparison; zero Cubase runtime cases')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('project',type=Path);parser.add_argument('export',type=Path);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
 result=verify(args.project,args.export)
 with args.report.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result));raise SystemExit(0 if result['status']=='pass' else 1)
