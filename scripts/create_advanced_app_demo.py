#!/usr/bin/env python3
"""Create an explicit self-authored APP002 musical/automation fixture."""
from pathlib import Path
import json, shutil, uuid
ROOT = Path(__file__).resolve().parent.parent
source = ROOT / 'research/fixtures/APP001/Studio Check.rebaseproj'
destination = ROOT / 'research/evidence/application/APP002/Timing and Automation.rebaseproj'
if destination.exists(): raise SystemExit('Refusing to overwrite the APP002 fixture')
shutil.copytree(source, destination)
p = json.loads((destination / 'Project.json').read_text())
def uid(label): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'rebase:APP002:' + label)).upper()
p['id'] = uid('project'); p['name'] = 'Timing and Automation'
p['tempoMap'] = {'events':[dict(id=uid('tempo0'),beat=0,bpm=120,curve='jump'),dict(id=uid('tempo8'),beat=8,bpm=90,curve='jump')]}
p['signatureMap'] = {'events':[dict(id=uid('signature0'),beat=0,numerator=4,denominator=4),dict(id=uid('signature8'),beat=8,numerator=3,denominator=4),dict(id=uid('signature20'),beat=20,numerator=4,denominator=4)]}
for track in p['tracks']:
 track['automation'] = []; track['timeBase'] = 'seconds'
 for clip in track['clips']: clip['timeBase'] = 'seconds'
def point(label,time,value,mode='linear'):return dict(id=uid(label),time=time,value=value,interpolation=mode)
p['tracks'][0]['automation'] = [dict(id=uid('volume'),parameter='gainDB',isReadEnabled=True,points=[point('volume0',0,-12),point('volume4',4,0,'step'),point('volume8',8,-6)])]
p['tracks'][1]['automation'] = [dict(id=uid('pan'),parameter='pan',isReadEnabled=True,points=[point('pan0',0,-.75),point('pan6',6,.75)])]
p['tracks'][2]['timeBase'] = 'musical'
p['tracks'][2]['clips'][0].update(timeBase='musical',musicalPosition=3)
(destination/'Project.json').write_text(json.dumps(p,indent=2)+'\n')
print(destination)
