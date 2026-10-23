"""Run authored gain/format kernels against independent precomputed IEEE bits."""
from pathlib import Path
import hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
def rec(p):
    b=p.read_bytes();return dict(path=str(p.relative_to(ROOT)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
oracle=HERE/'validation/gain-order-stage-oracle.json'
assert rec(oracle)['sha256']=='e28870caa88a1eda66d8cc77eaf804ea513695e3fc3694ee77d719f2d1799cc1'
d=json.loads(oracle.read_text())
rows=d['equal_rate_vectors'];stages=d['downsample_stage_vectors']
table=',\n'.join('{0x%s,0x%s,0x%s}'%(r['decoded_bits'],r['gain_bits'],r['separate_bits']) for r in rows)
stage=',\n'.join('{0x%s,0x%s,0x%s}'%(r['filter_output_bits'],r['gain_bits'],r['q24_then_gain_bits']) for r in stages)
build=HERE/'validation/controls';build.mkdir()
source=r'''
#include "cpr_accessor_format.h"
#include <fenv.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#pragma STDC FENV_ACCESS ON
typedef struct {uint32_t input,gain,output;} Row;
static const Row rows[]={TABLE},stages[]={STAGE};
static unsigned checks=0,environments=0,ignored=0;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"line%d: %s\n",__LINE__,#x);return 1;}}while(0)
static float sample(uint32_t x){float f;memcpy(&f,&x,4);return f;}
static uint32_t bits(float x){uint32_t b;memcpy(&b,&x,4);return b;}
int main(void){
 CHECK(fesetround(FE_TONEAREST)==0);
 for(size_t i=0;i<sizeof(rows)/sizeof(rows[0]);++i){
  float a[]={sample(0x3f123456),sample(rows[i].input),sample(0xbf123456)};
  CHECK(rb_cpr_accessor_gain_f32(a+1,1,rows[i].gain)==0);
  CHECK(bits(a[1])==rows[i].output);
  CHECK(bits(a[0])==0x3f123456&&bits(a[2])==0xbf123456);
 }
 for(size_t i=0;i<sizeof(stages)/sizeof(stages[0]);++i){
  float x=sample(stages[i].input);
  CHECK(rb_cpr_accessor_pcm24_roundtrip(&x,1)==0);
  CHECK(rb_cpr_accessor_gain_f32(&x,1,stages[i].gain)==0);
  CHECK(bits(x)==stages[i].output);
 }
 /* Each common-gain batch exercises count/tail boundaries independently of
    the generator's row ordering, including native scalar/vector cutoffs. */
 for(size_t i=0;i<sizeof(rows)/sizeof(rows[0]);++i){
  float a[33];for(size_t n=0;n<33;++n)a[n]=sample(rows[i].input);
  CHECK(rb_cpr_accessor_gain_f32(a,33,rows[i].gain)==0);
  for(size_t n=0;n<33;++n)CHECK(bits(a[n])==rows[i].output);
 }
 uint32_t invalid[]={1,0x80000001,0x007fffff,0x7f800000,0xff800000,0x7fc00000};
 for(size_t k=0;k<sizeof(invalid)/sizeof(invalid[0]);++k){
  float x=sample(0x3eaaaaab);CHECK(rb_cpr_accessor_gain_f32(&x,1,invalid[k])==1);
  CHECK(bits(x)==0x3eaaaaab);
  for(size_t at=0;at<3;++at){
   float a[]={0.5f,-0.75f,0.25f},saved[3];a[at]=sample(invalid[k]);memcpy(saved,a,sizeof(a));
   CHECK(rb_cpr_accessor_gain_f32(a,3,0x40000000)==1);
   CHECK(memcmp(a,saved,sizeof(a))==0);
  }
 }
 uint32_t limit[][2]={{0x7f7fffff,0x40000000},{0xff7fffff,0x40000000},{0x00800000,0x3f000000},{0x80800000,0x3f000000}};
 for(size_t k=0;k<4;++k)for(size_t at=0;at<3;++at){
  float a[]={0.5f,-0.75f,0.25f},saved[3];a[at]=sample(limit[k][0]);memcpy(saved,a,sizeof(a));
  CHECK(rb_cpr_accessor_gain_f32(a,3,limit[k][1])==1);
  CHECK(memcmp(a,saved,sizeof(a))==0);
 }
 float x=0.5f;
 CHECK(rb_cpr_accessor_gain_f32(NULL,1,0x3f800000)==1);
 CHECK(rb_cpr_accessor_gain_f32(&x,0,0x3f800000)==1&&x==0.5f);
 CHECK(rb_cpr_accessor_gain_f32(&x,32000001,0x3f800000)==1&&x==0.5f);
 int modes[]={FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO};
 for(size_t i=0;i<3;++i){
  CHECK(fesetround(modes[i])==0);int rc=rb_cpr_accessor_gain_f32(&x,1,0x3f400000);int unchanged=bits(x)==0x3f000000;
  CHECK(fesetround(FE_TONEAREST)==0);CHECK(rc==2&&unchanged);++environments;
 }
 uint64_t original;__asm__ volatile("mrs %0, fpcr":"=r"(original));
 unsigned shifts[]={0,1,24,25};
 for(size_t i=0;i<4;++i){
  uint64_t changed=original|(UINT64_C(1)<<shifts[i]),actual;
  __asm__ volatile("msr fpcr, %0"::"r"(changed));__asm__ volatile("mrs %0, fpcr":"=r"(actual));
  int rc=rb_cpr_accessor_gain_f32(&x,1,0x3f400000);int unchanged=bits(x)==0x3f000000;
  __asm__ volatile("msr fpcr, %0"::"r"(original));
  if(actual&(UINT64_C(1)<<shifts[i])){CHECK(rc==2&&unchanged);++environments;}
  else{CHECK(rc==0);++ignored;x=0.5f;}
 }
 printf("{\"passed\":true,\"gain_vectors\":%zu,\"q24_gain_vectors\":%zu,\"assertions\":%u,\"FP_rejections\":%u,\"ignored_FPCR_bits\":%u}\n",sizeof(rows)/sizeof(rows[0]),sizeof(stages)/sizeof(stages[0]),checks,environments,ignored);
 return 0;
}
'''.replace('TABLE',table).replace('STAGE',stage)
harness=build/'controls.c';harness.write_text(source)
results=[];commands=[]
for label,flags in [('optimized',[]),('ubsan',['-fsanitize=undefined','-fno-sanitize-recover=all'])]:
    output=build/label
    command=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-frounding-math',
             '-I',str(HERE/'candidate'),str(harness),str(HERE/'candidate/cpr_accessor_format.c'),*flags,'-o',str(output)]
    made=subprocess.run(command,capture_output=True,text=True)
    (build/f'{label}-build.log').write_text(made.stdout+made.stderr)
    assert made.returncode==0,made.stderr
    run=subprocess.run([str(output)],capture_output=True,text=True,timeout=60)
    (build/f'{label}-run.log').write_text(run.stdout+run.stderr)
    assert run.returncode==0,run.stdout+run.stderr
    result=json.loads(run.stdout);assert result['passed']
    results.append(dict(configuration=label,result=result,executable=rec(output),build_log=rec(build/f'{label}-build.log'),run_log=rec(build/f'{label}-run.log')))
    commands.append(command)
report=dict(status='passed',target_executions=0,scope='Own candidate arithmetic, transactional rejection and FP environment controls; not native runtime equivalence.',
    inputs=[rec(oracle),rec(HERE/'validation/gain-order-stage-oracle.py'),rec(Path(__file__)),rec(harness)],
    reviewed_sources=[rec(HERE/'candidate'/n) for n in ['cpr_accessor_format.c','cpr_accessor_format.h']],
    commands=commands,results=results)
with (HERE/'gain-controls.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(dict(report=rec(HERE/'gain-controls.json'),results=[r['result'] for r in results])))
