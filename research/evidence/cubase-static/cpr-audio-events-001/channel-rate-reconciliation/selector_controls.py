"""Finite Boolean controls for the retained selector, not Cubase execution."""
from pathlib import Path
import json,itertools
H=Path(__file__).resolve().parent
rows=[]
for active,override,mode in itertools.product([0,1],repeat=3):
 for source_rate,context_rate in [(44100,44100),(44100,48000),(48000,44100)]:
  branch='ordinary' if active==0 or override!=0 else 'alternate'
  disposition='ordinary-reader-call' if branch=='ordinary' and mode==0 else ('ordinary-rejected' if branch=='ordinary' else 'alternate-scrub-state')
  rows.append(dict(active=active,channel_override=override,ordinary_block_flag=mode,source_rate=source_rate,context_rate=context_rate,expected=disposition))
for active,override,mode in itertools.product([0,1],repeat=3):
 group=[r for r in rows if (r['active'],r['channel_override'],r['ordinary_block_flag'])==(active,override,mode)]
 assert len({r['expected']for r in group})==1
x=dict(kind='Analytical branch truth table derived from original conditional instructions',target_executed=False,scope='Non-null owner and valid requested channel count; no provider/sample invocation',passed=True,controls=rows,limits=['Rates are deliberately extrinsic to the predicate: no rate argument/load participates in this selector.','This demonstrates a property of the inspected branch, not the actual runtime values of its fields.'])
(H/'selector-controls.json').write_text(json.dumps(x,indent=2)+'\n');print(len(rows),'controls')
