#include "native_rate_mode0_down.h"
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
static int valid(const RBMode0DownState *s) {
    if(!s||!arithmetic_ok()||(s->channels!=1&&s->channels!=2)||s->pending>1)return 0;
    float in=from_bits(s->source_rate_bits),out=from_bits(s->output_rate_bits);
    if(!isfinite(in)||!isfinite(out)||out<8000||in>192000||in<out)return 0;
    volatile double step=(double)in/(double)out;
    if(s->step!=step||!isfinite(s->phase))return 0;
    if(step<2) { if(s->phase<0||s->phase>1)return 0; }
    else if(s->phase < -1||s->phase>=step||s->pending!=(s->phase<0))return 0;
    for(unsigned c=0;c<2;c++)if(!isfinite(s->history[c])||fabs(s->history[c])>0x1.fffffep127)return 0;
    return 1;
}
int rb_native_mode0_down_init(float in,float out,uint32_t channels,RBMode0DownState *s) {
    if(!s||!arithmetic_ok()||(channels!=1&&channels!=2)||!isfinite(in)||!isfinite(out)||out<8000||in>192000||in<out)return RB_MODE0_DOWN_INVALID;
    RBMode0DownState t={0};volatile double step=(double)in/(double)out;
    t.step=step;t.phase=1;t.source_rate_bits=float_bits(in);t.output_rate_bits=float_bits(out);t.channels=channels;*s=t;return 0;
}
int rb_native_mode0_down_reset(RBMode0DownState *s) {
    if(!valid(s))return RB_MODE0_DOWN_INVALID;
    s->phase=1;s->history[0]=0;s->history[1]=0;s->pending=0;return 0;
}
/* Separate FMUL then fused FMADD/FMLA, followed only at emission by FCVTN. */
static double interpolate(double previous,double next,double phase) {
    volatile double complement=1.0-phase;
    volatile double product=phase*next;
    return fma(complement,previous,product);
}
static int emit(const RBMode0DownState *s,const double values[2],float *output,size_t *n,int samples) {
    if(*n==FRAME_LIMIT)return RB_MODE0_DOWN_CAPACITY;
    if(samples)for(unsigned c=0;c<s->channels;c++) {
        float value=(float)values[c];if(!sample_ok(value))return RB_MODE0_DOWN_SAMPLE_DOMAIN;
        if(output)output[*n*s->channels+c]=value;
    }
    ++*n;return 0;
}
static int run(RBMode0DownState *s,const float *input,size_t frames,uint32_t layout,float *output,size_t *produced,int samples) {
    size_t n=0;if(!frames){*produced=0;return 0;}
    double p=s->phase;int status;
    if(s->step>=2) {
        if(p<0) {
            double values[2]={0,0};
            if(samples)for(unsigned c=0;c<s->channels;c++) {
                double previous=(double)(float)s->history[c];
                volatile double nextWeight=p+1.0;
                if(s->channels==1) {
                    volatile double product=nextWeight*(double)input[c];
                    values[c]=fma(-p,previous,product); /* native FMSUB */
                } else {
                    volatile double previousWeight=1.0-nextWeight;
                    volatile double adjustedNextWeight=1.0-previousWeight;
                    volatile double product=adjustedNextWeight*(double)input[c];
                    values[c]=fma(previousWeight,previous,product);
                }
            }
            status=emit(s,values,output,&n,samples);if(status)return status;
            volatile double next=s->step+p;p=next;
        }
        while(floor(p)<(double)(frames-1)) {
            size_t i=(size_t)floor(p);double values[2]={0,0};
            volatile double fraction=p-(double)i;
            if(samples)for(unsigned c=0;c<s->channels;c++)values[c]=interpolate((double)input[i*s->channels+c],(double)input[(i+1)*s->channels+c],fraction);
            status=emit(s,values,output,&n,samples);if(status)return status;
            volatile double next=s->step+p;p=next;
        }
        volatile double next=p-(double)frames;s->phase=next;s->pending=(next<0);
        if(samples)for(unsigned c=0;c<s->channels;c++)s->history[c]=(double)input[(frames-1)*s->channels+c];
    } else {
        volatile double delta=s->step+(-1.0);
        size_t i=0;int64_t remaining=(int64_t)frames;int queued=0,lastSkip=0;
        if(p<1&&s->pending) {
            volatile double next=p+delta;
            if(frames==1&&next>=1)return RB_MODE0_DOWN_LOOKAHEAD;
            if(samples)for(unsigned c=0;c<s->channels;c++) {
                double mixed=interpolate((double)(float)s->history[c],(double)input[c],p);
                float narrowed=(float)mixed;if(!sample_ok(narrowed))return RB_MODE0_DOWN_SAMPLE_DOMAIN;
                s->history[c]=(double)narrowed;
            }
            p=next;
            if(p>=1) {
                volatile double reduced=p+(-1.0);p=reduced;
                status=emit(s,s->history,output,&n,samples);if(status)return status;
                i=1;--remaining;
            } else queued=1;
        }
        if(remaining>=2) {
            --remaining;
            do {
                if(p<1) {
                    do {
                        double values[2]={0,0};
                        if(samples)for(unsigned c=0;c<s->channels;c++)values[c]=interpolate((double)input[i*s->channels+c],(double)input[(i+1)*s->channels+c],p);
                        if(queued) {
                            status=emit(s,s->history,output,&n,samples);if(status)return status;
                            if(samples)for(unsigned c=0;c<s->channels;c++)s->history[c]=values[c];
                        } else {status=emit(s,values,output,&n,samples);if(status)return status;}
                        volatile double next=delta+p;p=next;++i;--remaining;
                    } while(p<1&&remaining!=0);
                }
                lastSkip=(p>=1);
                if(lastSkip) {
                    volatile double next=p+(-1.0);p=next;++i;--remaining;
                    if(queued){status=emit(s,s->history,output,&n,samples);if(status)return status;queued=0;}
                }
            } while(remaining>0);
        }
        if(queued&&layout==RB_MODE0_DOWN_OUTPUT_BELOW){status=emit(s,s->history,output,&n,samples);if(status)return status;}
        if(!lastSkip) {
            if(i>=frames)return RB_MODE0_DOWN_LOOKAHEAD;
            if(samples)for(unsigned c=0;c<s->channels;c++)s->history[c]=(double)input[i*s->channels+c];
        }
        s->pending=!lastSkip;s->phase=p;
    }
    *produced=n;return 0;
}
int rb_native_mode0_down_count(const RBMode0DownState *s,size_t frames,uint32_t layout,uint32_t flush,size_t *produced) {
    if(!valid(s)||!produced||frames>FRAME_LIMIT||layout>1||flush>1||overlap(s,sizeof(*s),produced,sizeof(*produced)))return RB_MODE0_DOWN_INVALID;
    RBMode0DownState trial=*s;size_t count;int status=run(&trial,0,frames,layout,0,&count,0);if(status)return status;
    *produced=count;return 0;
}
size_t rb_native_mode0_down_next_block(size_t remaining,size_t limit) {
    if(limit<3||limit>FRAME_LIMIT)return 0;
    if(remaining==limit+1)return limit-1;
    return remaining<limit?remaining:limit;
}
int rb_native_mode0_down_count_blocks(const RBMode0DownState *s,size_t frames,size_t limit,uint32_t layout,size_t *produced) {
    if(!valid(s)||!produced||frames>FRAME_LIMIT||limit<3||limit>FRAME_LIMIT||layout>1||overlap(s,sizeof(*s),produced,sizeof(*produced)))return RB_MODE0_DOWN_INVALID;
    RBMode0DownState trial=*s;size_t total=0;
    while(frames) {
        size_t block=rb_native_mode0_down_next_block(frames,limit),count;
        int status=run(&trial,0,block,layout,0,&count,0);if(status)return status;
        if(count>FRAME_LIMIT-total)return RB_MODE0_DOWN_CAPACITY;
        total+=count;frames-=block;
    }
    *produced=total;return 0;
}
int rb_native_mode0_down_process(RBMode0DownState *s,const float *input,size_t frames,float *output,size_t capacity,uint32_t layout,uint32_t flush,size_t *produced) {
    if(!valid(s)||!produced||frames>FRAME_LIMIT||capacity>FRAME_LIMIT||layout>1||flush>1)return RB_MODE0_DOWN_INVALID;
    RBMode0DownState trial=*s;size_t count;int status=run(&trial,0,frames,layout,0,&count,0);if(status)return status;
    if(count>capacity)return RB_MODE0_DOWN_CAPACITY;
    size_t ib=frames*s->channels*sizeof(float),ob=capacity*s->channels*sizeof(float);
    if((ib&&!input)||(count&&!output)||overlap(s,sizeof(*s),produced,sizeof(*produced))||overlap(s,sizeof(*s),input,ib)||overlap(s,sizeof(*s),output,ob)||overlap(produced,sizeof(*produced),input,ib)||overlap(produced,sizeof(*produced),output,ob)||overlap(input,ib,output,ob))return RB_MODE0_DOWN_INVALID;
    if(ib&&ob&&output) {
        uintptr_t src=(uintptr_t)input,dst=(uintptr_t)output;
        if((layout==RB_MODE0_DOWN_OUTPUT_ABOVE&&dst<src+ib)||(layout==RB_MODE0_DOWN_OUTPUT_BELOW&&src<dst+ob))return RB_MODE0_DOWN_INVALID;
    }
    for(size_t i=0;i<frames*s->channels;i++)if(!sample_ok(input[i]))return RB_MODE0_DOWN_SAMPLE_DOMAIN;
    trial=*s;size_t checked;status=run(&trial,input,frames,layout,0,&checked,1);if(status)return status;
    if(checked!=count)return RB_MODE0_DOWN_INVALID;
    RBMode0DownState committed=*s;size_t actual;
    (void)run(&committed,input,frames,layout,output,&actual,1);
    *s=committed;*produced=actual;return 0;
}
