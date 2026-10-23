"""Exact-rational analytical frame-count controls; never executes target code.

Rounds each arithmetic instruction independently to IEEE nearest/ties-even.
FRINTP/FCVTPS and FCVTZS are modeled explicitly. The process-state model covers
positive finite counts, successful initialized mode2, no flush and no mutation.
It predicts wrapper bookkeeping, not the external SoXR algorithm's samples or
actual input-used/output-produced counters.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib, importlib.util, json, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
ORACLE=ROOT/'research/evidence/cubase-static/cpr-map-clock-001/oracle-iterator/map_oracle.py'
spec=importlib.util.spec_from_file_location('ieee_fraction',ORACLE)
ieee=importlib.util.module_from_spec(spec);spec.loader.exec_module(ieee)
MAX=(1<<31)-1
ceil=lambda x:-((-x.numerator)//x.denominator)

def rates(source,output):
    a=ieee.encode(F(source),p=24,eb=8);b=ieee.encode(F(output),p=24,eb=8)
    x=ieee.decode(a,p=24,eb=8);y=ieee.decode(b,p=24,eb=8)
    assert x>0 and y>0 and F(1,100)<=y/x<=100
    return a,b,x,y

def budget(source,output,requested,mode=1,first=False,available=True):
    assert 0<requested<=MAX and mode in [0,1,2]
    a,b,x,y=rates(source,output)
    ratio_in=ieee.encode(x/y);ratio_out=ieee.encode(y/x)
    pad=ceil(ieee.decode(ratio_out))*2048 if mode==2 and first and available and x!=y else 0
    n=requested+pad;assert n<=MAX
    if x==y:
        initial=result=requested;tested=[requested];mapped=requested;product=ieee.encode(requested)
    else:
        product=ieee.op(ratio_in,ieee.encode(n),'mul')
        initial=ceil(ieee.decode(product));assert 0<=initial<=MAX
        result=initial;tested=[]
        while True:
            tested.append(result)
            mapped=int(ieee.decode(ieee.op(ratio_out,ieee.encode(result),'mul')))
            assert 0<=mapped<=MAX
            if mapped<=n:break
            result-=1;assert result>=0
        assert len(tested)<=initial+1
    f32ratio=ieee.decode(ieee.encode(x/y,p=24,eb=8),p=24,eb=8)
    wrong_f32=ceil(ieee.decode(ieee.op(ieee.encode(f32ratio),ieee.encode(n),'mul')))
    rational_ceil=ceil(F(n)*x/y)
    return dict(source_rate=str(source),output_rate=str(output),source_f32_bits=f'{a:08x}',output_f32_bits=f'{b:08x}',
        requested=requested,mode=mode,first=first,available=available,padding=pad,total_budget=n,
        input_ratio_f64_bits=f'{ratio_in:016x}',output_ratio_f64_bits=f'{ratio_out:016x}',
        initial_product_f64_bits=f'{product:016x}',initial_ceil=initial,returned_source_frames=result,
        reverse_mapped_frames=mapped,correction_decrements=len(tested)-1,tested_source_counts=tested,
        wrong_f32_ratio_ceil=wrong_f32,unrounded_rational_ceil=rational_ceil,
        differs_from_ceil_alone=result!=initial,differs_from_f32_ratio_initial=initial!=wrong_f32,
        differs_from_unrounded_rational_initial=initial!=rational_ceil)

class NoFlushState:
    def __init__(self,source,output,discard=None):
        _,_,x,y=rates(source,output)
        self.ratio=ieee.encode(y/x)
        self.discard=ceil(ieee.decode(self.ratio))*2048 if discard is None else discard
        self.input=0;self.output=0;self.ideal=ieee.encode(0)
    def block(self,count):
        assert 0<count<=MAX
        rows=[];remaining=count
        while remaining>65408:
            rows.append(self.small(65408));remaining-=65408
        rows.append(self.small(remaining))
        assert sum(r['input_count'] for r in rows)==count
        return dict(input_count=count,visible_output_count=sum(r['visible_output'] for r in rows),chunks=rows,
            cumulative_input=self.input,cumulative_output=self.output,cumulative_ideal_f64_bits=f'{self.ideal:016x}',remaining_discard=self.discard)
    def small(self,count):
        assert 0<count<=65408
        ideal=ieee.op(ieee.encode(count),self.ratio,'mul')
        base=int(ieee.decode(ideal));assert 0<=base<=MAX
        delta=ieee.op(ieee.op(self.ideal,ideal,'add'),ieee.encode(self.output+base),'sub')
        n=base+int(ieee.decode(delta)>1)
        if n==0:n=1
        assert 0<n<=MAX
        old_discard=self.discard
        if self.discard>=n:
            visible=0;self.discard-=n;contribution=ieee.encode(0)
        elif self.discard:
            visible=n-self.discard;contribution=ieee.op(ideal,ieee.encode(self.discard),'sub');self.discard=0
        else:visible=n;contribution=ideal
        self.input+=count;self.output+=visible;self.ideal=ieee.op(self.ideal,contribution,'add')
        assert self.input<1<<53 and self.output<1<<53
        return dict(input_count=count,ideal_f64_bits=f'{ideal:016x}',truncated_base=base,drift_f64_bits=f'{delta:016x}',
            strict_greater_than_one=ieee.decode(delta)>1,wrapper_requested_output=n,discard_before=old_discard,
            visible_output=visible,remaining_discard=self.discard)

def main():
    pairs=[(44100,48000),(48000,44100),(48000,96000),(96000,48000),(8000,192000),(192000,8000),(44100,44100),
           (F(4410000390625,100000000),48000)]
    counts=[1,2,3,7,64,127,147,1024,2048,48000,65408,65409,131000,1000001,10000003]
    vectors=[budget(s,o,n,mode,first) for s,o in pairs for n in counts for mode,first in [(1,False),(2,True)]]
    # An unavailable mode2 allowance is zero; equal-rate fast path ignores it.
    controls=[budget(44100,48000,1024,2,True,False),budget(44100,44100,1024,2,True),budget(44100,48000,1024,2,False),budget(48000,96000,1)]
    assert controls[-1]['returned_source_frames']==0 and controls[-1]['initial_ceil']==1
    assert controls[0]['padding']==controls[1]['padding']==controls[2]['padding']==0
    assert any(r['differs_from_ceil_alone'] for r in vectors)
    assert any(r['differs_from_f32_ratio_initial'] for r in vectors)
    assert any(r['differs_from_unrounded_rational_initial'] for r in vectors)
    states=[]
    for s,o,counts in [(44100,48000,[4704,940,940,65409,131000]),(48000,44100,[3344,1115,1115,65408]),(8000,192000,[2049,1,7])]:
        state=NoFlushState(s,o)
        states.append(dict(source_rate=s,output_rate=o,blocks=[state.block(n) for n in counts]))
    # Exact drift==1 must not take the strict increment branch. The chosen
    # artificial state is a control for the branch, not a claimed reachable state.
    s=NoFlushState(2,3,discard=0);s.ideal=ieee.encode(F(1,2));strict=s.small(1)
    assert ieee.decode(int(strict['drift_f64_bits'],16))==1 and not strict['strict_greater_than_one'] and strict['visible_output']==1
    result=dict(scope='Static analytical count and bookkeeping controls; no Cubase, SoXR or candidate DSP execution.',
      assumptions=['IEEE nearest/ties-even for floating arithmetic; finite positive normal source/output Float32 rates',
       'Positive Int32 request, no overflow or FCVT range saturation, ratio in [0.01,100]',
       'Mode2 state controls assume successful prior format-specific initialization, adequate buffers, fixed rate/channels and no flush'],
      rational_helper=dict(path=str(ORACLE.relative_to(ROOT)),sha256=hashlib.sha256(ORACLE.read_bytes()).hexdigest()),
      budget_vectors=vectors,controls=controls,no_flush_state_controls=states,strict_drift_control=strict,
      termination='Budget correction strictly decreases a nonnegative integer and the reverse product is zero at k=0; chunk recursion uses 65408 positive input frames, nested calls fit the bound, and only the final bounded block remains. These claims exclude integer overflow, changed state and external calls that do not return.',
      nonclaims=['Wrapper visible count is not the actual soxr_process output-produced count.','No resampling sample values or flush-state conformance are established by this oracle.'],target_execution_count=0)
    with (HERE/'analytical-count-controls.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    summary=dict(vectors=len(vectors),controls=len(controls),state_blocks=sum(len(x['blocks']) for x in states),
        ceil_discriminators=sum(x['differs_from_ceil_alone'] for x in vectors),f32_discriminators=sum(x['differs_from_f32_ratio_initial'] for x in vectors),
        rational_discriminators=sum(x['differs_from_unrounded_rational_initial'] for x in vectors),maximum_correction=max(x['correction_decrements'] for x in vectors))
    print(json.dumps(summary))
if __name__=='__main__':main()
