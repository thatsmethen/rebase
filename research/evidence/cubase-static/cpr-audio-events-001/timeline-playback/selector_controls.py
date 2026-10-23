"""Finite analytical controls for the native selector contract; no Cubase execution.
Python computes an abstract linked-segment model, not memory/lifetime callbacks.
"""
from pathlib import Path
from fractions import Fraction
import math,json,struct
H=Path(__file__).resolve().parent

def bits(v):return struct.pack('>d',v).hex()
def rounded_end(s,n):
    # Independent exact rational addition then one binary64 rounding.
    return float(Fraction.from_float(s)+Fraction.from_float(n))
def select(segments,generation,current,cursor_generation,query):
    assert all(math.isfinite(x)for row in segments for x in row[:2]) and math.isfinite(query)
    assert all(math.isfinite(rounded_end(*row[:2]))for row in segments)
    assert 0<=generation<=0xffffffff and 0<=cursor_generation<=0xffffffff
    before=current
    if generation==cursor_generation and current is not None:
        result=segments[current][2];branch='cached_successor'
    else:
        cursor_generation=generation;result=None;branch='search'
        # Iterator order is head, then each stored successor, rather than sort by start.
        i=0 if segments else None;visited=set()
        while i is not None:
            assert i not in visited;visited.add(i)
            start,length,next_i=segments[i]
            if rounded_end(start,length)>=query:result=i;break
            i=next_i
    assert current==before
    return dict(selected=result,cursor_generation=cursor_generation,current_unchanged=current,branch=branch)

cases=[]
def check(name,segments,generation,current,cursor_generation,query,expected,new_generation,branch):
    got=select(segments,generation,current,cursor_generation,query)
    assert got==dict(selected=expected,cursor_generation=new_generation,current_unchanged=current,branch=branch),(name,got)
    # Cross-check native operation order with Python's binary64 add, finite domain only.
    assert all(bits(rounded_end(*r[:2]))==bits(r[0]+r[1])for r in segments)
    cases.append(dict(name=name,segments=[dict(start_bits=bits(a),length_bits=bits(b),successor=c,end_bits=bits(rounded_end(a,b)))for a,b,c in segments],generation=generation,current=current,cursor_generation=cursor_generation,query_bits=bits(query),result=got))
single=[(0.,24.,None)]
for name,q,expected in [('before_origin',-1.,0),('origin',0.,0),('before_end',math.nextafter(24.,-math.inf),0),('exact_end',24.,0),('after_end',math.nextafter(24.,math.inf),None)]:
    check(name,single,7,None,7,q,expected,7,'search')
check('future_start_still_selected',[(10.,2.,None)],7,None,7,0.,0,7,'search')
check('empty',[],7,None,3,0.,None,7,'search')
check('stale_generation_search',single,7,0,6,0.,0,7,'search')
check('stale_after_end_writes_generation_keeps_current',single,7,0,6,25.,None,7,'search')
check('matching_last_ignores_backward_query',single,7,0,7,-1.,None,7,'cached_successor')
pair=[(0.,10.,1),(20.,4.,None)]
for name,q in [('cached_ignores_past',-100.),('cached_ignores_future',100.),('cached_exact_end',10.)]:check(name,pair,9,0,9,q,1,9,'cached_successor')
for name,q,e in [('gap_selects_future',15.,1),('adjacent_inclusive_prior',10.,0),('last_exact_end',24.,1),('past_all',25.,None)]:check(name,pair,9,None,9,q,e,9,'search')
check('iterator_order_not_minimum_start',[(20.,10.,1),(0.,2.,None)],4,None,4,1.,0,4,'search')
check('linked_order_skips_unlinked_storage',[(0.,1.,2),(0.,100.,None),(3.,1.,None)],4,None,4,2.,2,4,'search')
check('zero_length_exact_end',[(2.,0.,None)],4,None,4,2.,0,4,'search')
check('equal_generation_all_bits',single,0xffffffff,None,0xffffffff,0.,0,0xffffffff,'search')
check('generation_wrap_stale',single,0,0,0xffffffff,0.,0,0,'search')
check('generation_wrap_equality_has_no_epoch',single,0,0,0,-1.,None,0,'cached_successor')
# One-rounding discriminator: (nextDown(1) + 2^-54) rounds to1 by nearest-even;
# replacing it with query-start <= length would reject this endpoint.
a=math.nextafter(1.,0.);b=2.**-54
assert a+b==1. and 1.-a>b
check('one_addition_not_subtracted_comparison',[(a,b,None)],1,None,1,1.,0,1,'search')
resets=[]
for cur,g in [(None,0),(0,7),(42,0xffffffff)]:
    out=dict(current=None,cursor_generation=g)
    resets.append(dict(before_current=cur,owner_generation=g,after=out))
report=dict(schema_version=1,kind='analytical finite control vectors, not target executions',arithmetic='IEEE binary64 nearest-even single addition; exact rational independent sum check',controls=cases,reset_controls=resets,counts=dict(selection=len(cases),reset=len(resets)),passed=True,target_execution=False,excluded=['NaN/Infinity/overflow', 'callback or concurrent mutation','actual pointer lifetime/refcounts','native host format or timeline callback','seek-to-frame conversion'])
(H/'analytical-controls.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['counts']))
