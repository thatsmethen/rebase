"""Compare authored format candidate with a precomputed independent oracle."""
from pathlib import Path
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CANDIDATE = ROOT / "research/evidence/cubase-static/cpr-audio-events-001/accessor-format-order/candidate"
ORACLE = HERE / "accessor-pcm24-oracle-v2.json"
ORACLE_SHA = "c9031fc3ba4f72298fcd7ebcef631e1912ef61b6e83395a1b110f85e1e4163d6"


def rec(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    assert hashlib.sha256(ORACLE.read_bytes()).hexdigest() == ORACLE_SHA
    data = json.loads(ORACLE.read_text())
    rows = data["vectors"]
    build = HERE / "accessor-pcm24-controls"
    build.mkdir(exist_ok=False)
    table = ",\n".join("{0x%s,0x%s,%d}" %
                      (r["input_f32_bits"], r.get("output_f32_bits", r["input_f32_bits"]), r["accepted"])
                      for r in rows)
    source = r'''
#include "cpr_accessor_format.h"
#include <fenv.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#pragma STDC FENV_ACCESS ON
typedef struct {uint32_t input, output; int accepted;} Row;
static const Row rows[] = {TABLE};
static unsigned checks=0, environments=0, ignored_bits=0;
#define CHECK(x) do {++checks;if (!(x)) {fprintf(stderr,"failed line %d: %s\n",__LINE__,#x);return 1;}} while(0)
static float sample(uint32_t bits) {float x;memcpy(&x,&bits,4);return x;}
static uint32_t bits(float x) {uint32_t v;memcpy(&v,&x,4);return v;}
int main(void) {
  size_t count=sizeof(rows)/sizeof(rows[0]), good=0,bad=0;
  CHECK(fesetround(FE_TONEAREST)==0);
  for (size_t i=0;i<count;++i) {
    float guarded[3]={sample(0x3eaaaaab),sample(rows[i].input),sample(0xbeaaaaab)};
    float before[3];memcpy(before,guarded,sizeof(before));
    int rc=rb_cpr_accessor_pcm24_roundtrip(guarded+1,1);
    CHECK(rc==(rows[i].accepted?0:1));
    CHECK(bits(guarded[1])==rows[i].output);
    CHECK(bits(guarded[0])==bits(before[0])&&bits(guarded[2])==bits(before[2]));
    if(rows[i].accepted)++good;
    else {
      ++bad;
      for (size_t at=0;at<3;++at) {
        float a[3]={sample(0x33800000),sample(0x34400000),sample(0xb4400000)},saved[3];
        a[at]=sample(rows[i].input);memcpy(saved,a,sizeof(a));
        CHECK(rb_cpr_accessor_pcm24_roundtrip(a,3)==1);
        CHECK(memcmp(saved,a,sizeof(a))==0);
      }
    }
  }
  float *batch=malloc(good*4),*split=malloc(good*4);CHECK(batch&&split);
  size_t n=0;for(size_t i=0;i<count;++i)if(rows[i].accepted)batch[n++]=sample(rows[i].input);
  memcpy(split,batch,good*4);
  CHECK(rb_cpr_accessor_pcm24_roundtrip(batch,good)==0);
  n=0;for(size_t i=0;i<count;++i)if(rows[i].accepted)CHECK(bits(batch[n++])==rows[i].output);
  CHECK(rb_cpr_accessor_pcm24_roundtrip(split,1)==0);
  CHECK(rb_cpr_accessor_pcm24_roundtrip(split+1,good-1)==0);
  CHECK(memcmp(batch,split,good*4)==0);
  CHECK(rb_cpr_accessor_pcm24_roundtrip(split,good)==0);
  CHECK(memcmp(batch,split,good*4)==0);
  free(batch);free(split);
  float x=sample(0x33800000), saved=x;
  CHECK(rb_cpr_accessor_pcm24_roundtrip(NULL,0)==1);
  CHECK(rb_cpr_accessor_pcm24_roundtrip(NULL,1)==1);
  CHECK(rb_cpr_accessor_pcm24_roundtrip(&x,0)==1&&bits(x)==bits(saved));
  CHECK(rb_cpr_accessor_pcm24_roundtrip(&x,32000001)==1&&bits(x)==bits(saved));
  int modes[]={FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO};
  for(size_t i=0;i<3;++i){
    CHECK(fesetround(modes[i])==0);
    int rc=rb_cpr_accessor_pcm24_roundtrip(&x,1);
    int unchanged=bits(x)==bits(saved);
    CHECK(fesetround(FE_TONEAREST)==0);CHECK(rc==2&&unchanged);++environments;
  }
#if defined(__aarch64__)
  uint64_t original;__asm__ volatile("mrs %0, fpcr":"=r"(original));
  unsigned shifts[]={0,1,24,25};
  for(size_t i=0;i<4;++i){
    uint64_t changed=original|(UINT64_C(1)<<shifts[i]),actual;
    __asm__ volatile("msr fpcr, %0"::"r"(changed));
    __asm__ volatile("mrs %0, fpcr":"=r"(actual));
    int rc=rb_cpr_accessor_pcm24_roundtrip(&x,1);
    int unchanged=bits(x)==bits(saved);
    __asm__ volatile("msr fpcr, %0"::"r"(original));
    if(actual&(UINT64_C(1)<<shifts[i])){CHECK(rc==2&&unchanged);++environments;}
    else {CHECK(rc==0);++ignored_bits;x=saved;}
  }
#else
  CHECK(0); /* This native candidate explicitly admits arm64 only. */
#endif
  printf("{\"passed\":true,\"vectors\":%zu,\"accepted\":%zu,\"rejected\":%zu,\"assertions\":%u,\"fp_environment_rejections\":%u,\"unsupported_fpcr_bits\":%u}\n",count,good,bad,checks,environments,ignored_bits);
  return 0;
}
'''.replace("TABLE", table)
    harness = build / "controls.c"
    harness.write_text(source)
    commands, results = [], []
    common = ["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fno-fast-math", "-ffp-contract=off", "-frounding-math",
              "-I", str(CANDIDATE), str(harness), str(CANDIDATE / "cpr_accessor_format.c")]
    for name, flags in [("optimized", []), ("ubsan", ["-fsanitize=undefined", "-fno-sanitize-recover=all"])]:
        executable = build / name
        command = common + flags + ["-o", str(executable)]
        made = subprocess.run(command, capture_output=True, text=True, check=False)
        (build / f"{name}-build.log").write_text(made.stdout + made.stderr)
        assert made.returncode == 0, made.stderr
        run = subprocess.run([str(executable)], capture_output=True, text=True, check=False, timeout=60)
        (build / f"{name}-run.log").write_text(run.stdout + run.stderr)
        assert run.returncode == 0, run.stdout + run.stderr
        result = json.loads(run.stdout)
        assert result["passed"] and result["vectors"] == len(rows)
        commands.append(command)
        results.append(dict(configuration=name, result=result, executable=rec(executable),
                            build_log=rec(build/f"{name}-build.log"), run_log=rec(build/f"{name}-run.log")))
    prior = json.loads((HERE / "accessor-pcm24-oracle.json").read_text())
    changed = [(a["input_f32_bits"],a["scaled_f32_bits"],b["scaled_f32_bits"])
               for a,b in zip(prior["vectors"],rows) if a.get("scaled_f32_bits")!=b.get("scaled_f32_bits")]
    assert changed == [("80000000","00000000","80000000")]
    assert all(a.get("output_f32_bits")==b.get("output_f32_bits") and a["accepted"]==b["accepted"]
               for a,b in zip(prior["vectors"],rows))
    report = dict(schema_version=1, status="passed", scope="Conditional format candidate only; no app integration, resampling or target execution.",
                  reviewed_sources=[rec(CANDIDATE / name) for name in ["cpr_accessor_format.c","cpr_accessor_format.h"]],
                  inputs=[rec(ORACLE),rec(HERE/"accessor-pcm24-oracle.py"),rec(Path(__file__)),rec(harness)],
                  results=results, commands=commands,
                  oracle_metadata_correction=dict(previous=rec(HERE/"accessor-pcm24-oracle.json"),
                      previous_generator=rec(HERE/"accessor-pcm24-oracle-generator-v1.py"),
                      detail="Only scaled intermediate negative-zero metadata corrected; all final expected outputs and admission decisions unchanged.",changes=changed),
                  limits=["Input format selection, rate conversion, gain/layout order, native backend availability, accessor lifetime and complete playback remain separate.",
                          "Defensive domain/transactionality rules are application policy, not native ABI side-effect reproduction.",
                          "UBSan success is a bounded authored test result, not proof of all memory safety."])
    destination=HERE/"accessor-pcm24-controls.json"
    with destination.open("x") as output:json.dump(report,output,indent=2);output.write("\n")
    print(json.dumps(dict(report=rec(destination),results=[r["result"] for r in results])))


if __name__ == "__main__":
    main()
