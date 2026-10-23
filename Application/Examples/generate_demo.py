#!/usr/bin/env python3
"""Generate the original Rebase Preview audio and arrangement using Python's standard library."""
import argparse
import sys
from pathlib import Path
import array,math,wave,json,uuid,random,hashlib
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", nargs="?", type=Path, default=Path("Rebase Preview.rebaseproj"), help="destination project directory (default: ./Rebase Preview.rebaseproj)")
ROOT=parser.parse_args().output
if ROOT.exists():
 raise SystemExit("Destination already exists; choose a new output directory.")
(ROOT/'Media').mkdir(parents=True,exist_ok=True)
SR=48000;DURATION=20;BPM=96;BEAT=60/BPM;TAU=2*math.pi
uid=lambda text:str(uuid.uuid5(uuid.NAMESPACE_URL,'rebase-synthetic-preview/'+text)).upper()
rng=random.Random(20261023)
chords=[(48,55,60,64),(45,52,57,60),(41,48,53,57),(43,50,55,59)]
freq=lambda m:440*2**((m-69)/12)
def env(t,a,d):return min(1,t/a)*math.exp(-t/d)
for kind in ['rhythm','pad','bass','melody']:
 samples=array.array('h')
 for i in range(SR*DURATION):
  t=i/SR;beat=t/BEAT;phase=beat%1;bar=int(beat//4);chord=chords[min(3,int(t//5))];fade=min(1,t/.02,(DURATION-t)/.04)
  if kind=='rhythm':
   q=phase*BEAT
   kick=.58*math.sin(TAU*(48*q+35*.045*(1-math.exp(-q/.045))))*math.exp(-q/.13)
   snare=0
   if int(beat)%4 in (1,3):snare=.23*rng.uniform(-1,1)*math.exp(-q/.055)+.08*math.sin(TAU*185*q)*math.exp(-q/.035)
   h=(beat*2)%1*BEAT/2;hat=.11*rng.uniform(-1,1)*math.exp(-h/.018)
   left=right=kick+snare+hat
  elif kind=='pad':
   attack=min(1,(t%5)/.18);amp=.115*attack*(.9+.1*math.sin(TAU*.2*t))
   left=sum(math.sin(TAU*freq(n)*t)+.17*math.sin(TAU*freq(n)*2*t) for n in chord)*amp/2.3
   right=sum(math.sin(TAU*freq(n)*1.001*t)+.17*math.sin(TAU*freq(n)*2.001*t) for n in chord)*amp/2.3
  elif kind=='bass':
   q=(beat%1)*BEAT;n=chord[0]-12+(7 if int(beat)%8==6 else 0);f=freq(n)
   left=right=.37*env(q,.008,.24)*(math.sin(TAU*f*q)+.22*math.sin(TAU*2*f*q))
  else:
   step=int(beat*2);q=(beat*2%1)*BEAT/2;pattern=[0,2,3,2,1,2,3,1,0,1,2,3,2,1,3,2];n=chord[pattern[step%16]]+12;f=freq(n)
   tone=.23*env(q,.006,.13)*(math.sin(TAU*f*q)+.28*math.sin(TAU*3*f*q))
   left=tone*(.85+.15*math.sin(TAU*.1*t));right=tone*(.85-.15*math.sin(TAU*.1*t))
  samples.extend((round(max(-.95,min(.95,left*fade))*32767),round(max(-.95,min(.95,right*fade))*32767)))
 if sys.byteorder != 'little':samples.byteswap()
 with wave.open(str(ROOT/'Media'/f'{kind}.wav'),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes(samples.tobytes())
def clip(key,name,pos,dur):return {'id':uid(key+name+str(pos)),'mediaPath':f'Media/{key}.wav','name':name,'position':pos,'sourceOffset':pos,'duration':dur,'timeBase':'seconds'}
def track(key,name,gain,pan,clips,automation=[]):return {'id':uid(key),'name':name,'gainDB':gain,'pan':pan,'isMuted':False,'isSolo':False,'timeBase':'seconds','clips':clips,'automation':automation}
pad_curve={'id':uid('pad-gain'),'parameter':'gainDB','isReadEnabled':True,'points':[{'id':uid('padpoint'+str(t)),'time':t,'value':v,'interpolation':'linear'} for t,v in [(0,-10),(5,-7),(10,-5),(17.5,-5),(20,-12)]]}
project={'id':uid('project'),'name':'Rebase Preview','tempo':BPM,'sampleRate':SR,'tracks':[
 track('rhythm','Rhythm',-5,0,[clip('rhythm',n,p,5) for n,p in [('Opening beat',0),('Pocket',5),('Lift',10),('Turnaround',15)]]),
 track('pad','Warm pad',-7,-.12,[clip('pad','Soft horizon',0,10),clip('pad','Open sky',10,10)],[pad_curve]),
 track('bass','Round bass',-7,0,[clip('bass','Root motion',5,5),clip('bass','Deep pulse',10,5),clip('bass','Return',15,5)]),
 track('melody','Glass melody',-9,.15,[clip('melody','First light',10,5),clip('melody','Answer',15,5)])]}
(ROOT/'Project.json').write_text(json.dumps(project,indent=2)+'\n')
# Validate Codable-required fields, domains, unique IDs, and all referenced media intervals.
seen=set();clips=0
for tr in project['tracks']:
 assert tr['id'] not in seen;seen.add(tr['id']);assert -96<=tr['gainDB']<=24 and -1<=tr['pan']<=1
 for cl in tr['clips']:
  assert cl['id'] not in seen;seen.add(cl['id']);clips+=1
  assert cl['position']>=0 and cl['duration']>0 and cl['sourceOffset']>=0
  with wave.open(str(ROOT/cl['mediaPath']),'rb') as w:
   assert w.getnchannels()==2 and w.getsampwidth()==2 and w.getframerate()==SR and (cl['sourceOffset']+cl['duration'])*SR<=w.getnframes()
files=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(ROOT.rglob('*')) if p.is_file()]
report={'purpose':'Authored synthetic example beat; no reference media, no compatibility claim','sample_rate':SR,'duration_seconds':DURATION,'tempo_bpm':BPM,'tracks':len(project['tracks']),'clips':clips,'files':files,'validation':'JSON required fields and supported domains checked against Project decoder; PCM headers and every referenced source interval verified. Actual ProjectStore load remains GUI check.'}
(ROOT.parent/'demo-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'project':str(ROOT),'tracks':4,'clips':clips,'duration_seconds':DURATION,'files':len(files),'bytes':sum(x['bytes'] for x in files)}))
