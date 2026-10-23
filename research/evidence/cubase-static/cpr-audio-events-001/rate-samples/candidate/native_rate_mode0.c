#include "native_rate_mode0.h"
#include <math.h>
#include <fenv.h>
#include <string.h>
#include <stdint.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
#define FRAME_LIMIT ((size_t)16000000)

/* FE_TONEAREST alone does not reject hardware flush-to-zero modes. */
static int arithmetic_ok(void) {
    if(fegetround()!=FE_TONEAREST)return 0;
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr; __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    if(fpcr & ((UINT64_C(1)<<24)|UINT64_C(1)))return 0; /* FZ or FIZ */
#elif defined(__x86_64__)
    uint32_t mxcsr; __asm__ volatile("stmxcsr %0" : "=m"(mxcsr));
    if(mxcsr & ((1u<<15)|(1u<<6)))return 0; /* FTZ or DAZ */
#else
    return 0; /* Hardware arithmetic environment has not been verified. */
#endif
    return 1;
}
static uint32_t float_bits(float value) { uint32_t b; memcpy(&b,&value,4); return b; }
static float from_bits(uint32_t bits) { float value; memcpy(&value,&bits,4); return value; }
static int sample_ok(float value) { return isfinite(value) && (value==0 || isnormal(value)); }
static int overlap(const void *a,size_t an,const void *b,size_t bn) {
    if (!an || !bn) return 0;
    uintptr_t ap=(uintptr_t)a,bp=(uintptr_t)b;
    if (an>UINTPTR_MAX-ap || bn>UINTPTR_MAX-bp) return 1;
    return ap<bp+bn && bp<ap+an;
}
static int valid(const RBMode0State *s) {
    if (!s || !arithmetic_ok() || s->reserved || (s->channels!=1 && s->channels!=2)) return 0;
    float in=from_bits(s->source_rate_bits),out=from_bits(s->output_rate_bits);
    if (!isfinite(in)||!isfinite(out)||in<8000||out>192000||!(in<out)) return 0;
    volatile double step=(double)in/(double)out;
    if (!(s->step==step) || !isfinite(s->phase) || s->phase<0 || s->phase>1) return 0;
    for (unsigned c=0;c<2;c++) {
        float prev=(float)s->previous[c];
        if (!sample_ok(prev)||!isfinite(s->previous[c])||(double)prev!=s->previous[c]) return 0;
    }
    return 1;
}
int rb_native_mode0_init(float in,float out,uint32_t channels,RBMode0State *state) {
    if (!state || !arithmetic_ok() || (channels!=1&&channels!=2) ||
        !isfinite(in)||!isfinite(out)||in<8000||out>192000||!(in<out)) return RB_MODE0_INVALID;
    RBMode0State s={0};
    volatile double step=(double)in/(double)out;
    s.step=step;s.phase=1;s.source_rate_bits=float_bits(in);s.output_rate_bits=float_bits(out);s.channels=channels;
    *state=s;return RB_MODE0_OK;
}
int rb_native_mode0_reset(RBMode0State *state) {
    if (!valid(state)) return RB_MODE0_INVALID;
    state->phase=1;state->previous[0]=0;state->previous[1]=0;return RB_MODE0_OK;
}
static int count_phase(const RBMode0State *state,size_t frames,size_t *count,double *final_phase) {
    double phase=state->phase;size_t n=0;
    for(size_t i=0;i<frames;i++) {
        while(phase<1) {
            if(n==FRAME_LIMIT)return RB_MODE0_CAPACITY;
            n++;
            volatile double next=state->step+phase;phase=next;
        }
        volatile double next=phase+(-1.0);phase=next;
    }
    *count=n;*final_phase=phase;return RB_MODE0_OK;
}
int rb_native_mode0_count(const RBMode0State *state,size_t frames,size_t *produced) {
    if(!valid(state)||!produced||frames>FRAME_LIMIT||overlap(state,sizeof(*state),produced,sizeof(*produced)))return RB_MODE0_INVALID;
    size_t n;double phase;int status=count_phase(state,frames,&n,&phase);
    if(status)return status;
    *produced=n;return RB_MODE0_OK;
}
/* FMUL is rounded first, then the nativeFMADD/FMLA is fused inbinary64.
   Casting toFloat32 happens exactly once at the output store. */
static int run(RBMode0State *state,const float *input,size_t frames,float *output) {
    size_t at=0;
    for(size_t i=0;i<frames;i++) {
        double current[2]={0,0};
        for(unsigned c=0;c<state->channels;c++)current[c]=(double)input[i*state->channels+c];
        while(state->phase<1) {
            volatile double complement=1.0-state->phase;
            for(unsigned c=0;c<state->channels;c++) {
                volatile double product=state->phase*current[c];
                double mixed=fma(complement,state->previous[c],product);
                float sample=(float)mixed;
                if(!sample_ok(sample))return RB_MODE0_SAMPLE_DOMAIN;
                if(output)output[at*state->channels+c]=sample;
            }
            at++;
            volatile double next=state->step+state->phase;state->phase=next;
        }
        volatile double next=state->phase+(-1.0);state->phase=next;
        for(unsigned c=0;c<state->channels;c++)state->previous[c]=current[c];
    }
    return RB_MODE0_OK;
}
int rb_native_mode0_process(RBMode0State *state,const float *input,size_t frames,float *output,size_t capacity,size_t *produced) {
    if(!valid(state)||!produced||frames>FRAME_LIMIT||capacity>FRAME_LIMIT)return RB_MODE0_INVALID;
    size_t n;double final_phase;int status=count_phase(state,frames,&n,&final_phase);if(status)return status;
    if(capacity<n)return RB_MODE0_CAPACITY;
    size_t ib=frames*state->channels*sizeof(float),ob=capacity*state->channels*sizeof(float);
    if((ib&&!input)||(n&&!output)||overlap(state,sizeof(*state),produced,sizeof(*produced))||
       overlap(state,sizeof(*state),input,ib)||overlap(state,sizeof(*state),output,ob)||
       overlap(produced,sizeof(*produced),input,ib)||overlap(produced,sizeof(*produced),output,ob)||overlap(input,ib,output,ob))return RB_MODE0_INVALID;
    for(size_t i=0;i<frames*state->channels;i++)if(!sample_ok(input[i]))return RB_MODE0_SAMPLE_DOMAIN;
    RBMode0State trial=*state;
    status=run(&trial,input,frames,0);if(status)return status;
    if(trial.phase!=final_phase)return RB_MODE0_INVALID;
    /* All sample/domain/capacity checks passed. Inputs are immutable/disjoint. */
    RBMode0State committed=*state;
    (void)run(&committed,input,frames,output);
    *state=committed;*produced=n;return RB_MODE0_OK;
}
