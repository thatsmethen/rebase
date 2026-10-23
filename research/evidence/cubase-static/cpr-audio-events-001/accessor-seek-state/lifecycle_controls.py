"""Analytical branch controls from original instructions; no target execution."""
from pathlib import Path
import json,hashlib,importlib.util,sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[4]
p=H.parent/'rate-converter/count_oracle.py';spec=importlib.util.spec_from_file_location('budget_oracle',p);o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
rows=[]
for equal in [False,True]:
 for first in [0,1,255]:
  for pos in [99,100,101]:
   for actual in [0,7,8]:
    # f360 cmp/two cset; f36c cmp; f370 ccmp(...NZCV=Z if no first); f374 cset GT.
    w8=int(pos>=100);w9=int(pos<100);w10=int(8>actual) if first!=0 else 0
    original=False if equal else bool(w8&(w9|w10))
    reduced=not equal and pos>=100 and bool(first) and 8>actual
    assert original==reduced
    rows.append({'rates_equal':equal,'old_first_byte':first,'position':pos,'length':100,'budget':8,'actual_source_frames':actual,'terminal':original})
budgets=[o.budget(sr,dr,n,mode,first)for sr,dr in[(48000,44099),(48000,47998),(44100,48000),(48000,44100),(48000,96000),(44100,44100)]for n in[1,147,1024]for mode,first in[(0,True),(1,True),(2,True),(2,False)]]
assert any(x['returned_source_frames']==0 for x in budgets)
report={'id':'ACCESSOR-LIFECYCLE-ANALYTICAL-CONTROLS','target_execution_count':0,'passed':True,'terminal_predicate_rows':rows,'budget_rows':budgets,'scope':'Truth-table equivalence for the exact native terminal expression and pinned prior Fraction instruction-budget model. These are analytical controls, not native runtime tests or candidate PCM comparisons.','original_ranges':['0x10036f338..0x10036f388','0x100330d84..0x100330dd8','0x10030a430..0x10030a4b4'],'oracle_source':{'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}
(H/'lifecycle-controls.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'terminal_rows':len(rows),'budget_rows':len(budgets)}))
