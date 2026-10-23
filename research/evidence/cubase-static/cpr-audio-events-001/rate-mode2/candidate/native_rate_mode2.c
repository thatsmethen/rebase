#include "native_rate_mode2.h"
#include <fenv.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
#define FRAME_LIMIT ((size_t)16000000)
#define BLOCK_LIMIT ((size_t)65408)
#define INPUT_CAPACITY ((uint32_t)65536)
#define MAGIC UINT64_C(0x52424d4f44453231)

struct RBMode2 {
    uint64_t magic;
    RBMode2Backend backend;
    void *handle;
    RBMode2Snapshot v;
    float *input, *output;
};
typedef struct { size_t requested, discarded, visible; double contribution; } Block;
static int arithmetic_ok(void) {
    if(fegetround()!=FE_TONEAREST)return 0;
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr; __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    if(fpcr&((UINT64_C(1)<<24)|UINT64_C(1)))return 0;
#elif defined(__x86_64__)
    uint32_t mxcsr; __asm__ volatile("stmxcsr %0" : "=m"(mxcsr));
    if(mxcsr&((1u<<15)|(1u<<6)))return 0;
#else
    return 0;
#endif
    return 1;
}
static int sample_ok(float x) { return isfinite(x)&&(x==0||isnormal(x)); }
static int overlap(const void *a,size_t an,const void *b,size_t bn) {
    if(!an||!bn)return 0;
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(an>UINTPTR_MAX-x||bn>UINTPTR_MAX-y)return 1;
    return x<y+bn&&y<x+an;
}
static int usable(const RBMode2 *s) {
    return s&&s->magic==MAGIC&&s->handle&&s->input&&s->output&&arithmetic_ok();
}
static int query_valid(const RBMode2 *s,size_t n,uint32_t final,const void *result) {
    if(!usable(s)||!result||n>BLOCK_LIMIT||final>1||(!n&&!final))return RB_MODE2_INVALID;
    if(s->v.failed||s->v.finished)return RB_MODE2_STATE;
    if(overlap(s,sizeof(*s),result,sizeof(size_t)))return RB_MODE2_INVALID;
    if(n>FRAME_LIMIT-s->v.cumulative_input)return RB_MODE2_CAPACITY;
    return 0;
}
/* Original 10031427c..2e4: FMUL, FADD, integer addition, SCVTF,
   FSUB, strict >1. These operations must not be fused or reassociated. */
static size_t requested(const RBMode2Snapshot *v,size_t n,double *ideal) {
    volatile double x=(double)n*v->ratio;
    size_t base=(size_t)x;
    volatile double sum=v->cumulative_ideal+x;
    volatile double drift=sum-(double)(v->cumulative_visible+base);
    *ideal=x;return base+(drift>1.0);
}
static Block block_plan(RBMode2Snapshot *v,size_t n) {
    Block b={0};double ideal;
    b.requested=requested(v,n,&ideal);
    if(!b.requested)b.requested=1;
    b.discarded=v->discard<b.requested?v->discard:b.requested;
    b.visible=b.requested-b.discarded;
    if(v->discard>=b.requested)b.contribution=0;
    else if(v->discard){volatile double contribution=ideal-(double)v->discard;b.contribution=contribution;}
    else b.contribution=ideal;
    v->discard-=(uint32_t)b.discarded;
    v->cumulative_input+=n;v->cumulative_visible+=b.visible;
    volatile double sum=b.contribution+v->cumulative_ideal;v->cumulative_ideal=sum;
    return b;
}
static int planned(RBMode2Snapshot *v,size_t n,uint32_t final,size_t *count) {
    size_t total=0;
    if(n)total=block_plan(v,n).visible;
    else {double ignored;total=requested(v,0,&ignored);}
    if(final) {
        uint64_t saved=v->cumulative_input;
        volatile double extra_d=(double)v->delay/v->ratio;
        size_t extra=(size_t)extra_d;
        if(!extra||extra>BLOCK_LIMIT)return RB_MODE2_STATE;
        total+=block_plan(v,extra).visible;
        v->cumulative_input=saved;
        volatile double ideal=(double)saved*v->ratio;
        int64_t remainder=(int64_t)ideal-(int64_t)v->cumulative_visible;
        if(remainder>0)total+=(size_t)remainder;
        v->finished=1;
        /* Native final NULL-drain addition does not increment +0x28. */
    }
    if(total>FRAME_LIMIT-v->total_returned)return RB_MODE2_CAPACITY;
    v->total_returned+=total;*count=total;return 0;
}
int rb_native_mode2_create(double rin,double rout,uint32_t ch,RBMode2Backend backend,RBMode2 **result) {
    if(!result||!backend.create||!backend.process||!backend.destroy||!arithmetic_ok()||
       !isfinite(rin)||!isfinite(rout)||rin<8000||rin>192000||rout<8000||rout>192000||
       floor(rin)!=rin||floor(rout)!=rout||(ch!=1&&ch!=2))return RB_MODE2_INVALID;
    RBMode2 *s=calloc(1,sizeof(*s));if(!s)return RB_MODE2_ALLOCATION;
    s->magic=MAGIC;s->backend=backend;s->v.channels=ch;
    volatile double ratio=rout/rin;s->v.ratio=ratio;
    volatile double padding=ceil(ratio)*2048.0;s->v.delay=(uint32_t)padding;
    s->v.discard=s->v.delay;s->v.input_capacity=INPUT_CAPACITY;
    /* 10031518c FMADD, then 100315198 FADD and FCVTPU. */
    double fused=fma((double)INPUT_CAPACITY,ratio,(double)s->v.delay);
    volatile double capacity=fused+1024.0;
    s->v.output_capacity=(uint32_t)ceil(capacity);
    s->v.output_end=s->v.delay;
    s->input=calloc((size_t)INPUT_CAPACITY*ch,sizeof(float));
    s->output=calloc((size_t)s->v.output_capacity*ch,sizeof(float));
    if(!s->input||!s->output){rb_native_mode2_destroy(s);return RB_MODE2_ALLOCATION;}
    int status=backend.create(backend.context,rin,rout,ch,&s->handle);
    if(status||!s->handle||!arithmetic_ok()){rb_native_mode2_destroy(s);return RB_MODE2_BACKEND;}
    *result=s;return 0;
}
void rb_native_mode2_destroy(RBMode2 *s) {
    if(!s)return;
    if(s->magic!=MAGIC)return;
    if(s->handle)s->backend.destroy(s->handle);
    free(s->input);free(s->output);s->magic=0;free(s);
}
int rb_native_mode2_snapshot(const RBMode2 *s,RBMode2Snapshot *result) {
    if(!s||s->magic!=MAGIC||!result||overlap(s,sizeof(*s),result,sizeof(*result)))return RB_MODE2_INVALID;
    *result=s->v;return 0;
}
int rb_native_mode2_count(const RBMode2 *s,size_t n,uint32_t final,size_t *result) {
    int status=query_valid(s,n,final,result);if(status)return status;
    RBMode2Snapshot v=s->v;size_t count;status=planned(&v,n,final,&count);
    if(!status)*result=count;return status;
}
int rb_native_mode2_count_blocks(const RBMode2 *s,size_t n,size_t limit,size_t *result) {
    if(!usable(s)||!result||n>FRAME_LIMIT||!limit||limit>BLOCK_LIMIT||overlap(s,sizeof(*s),result,sizeof(*result)))return RB_MODE2_INVALID;
    if(s->v.failed||s->v.finished)return RB_MODE2_STATE;
    if(n>FRAME_LIMIT-s->v.cumulative_input)return RB_MODE2_CAPACITY;
    RBMode2Snapshot v=s->v;size_t total=0;
    do {
        size_t block=n<limit?n:limit,count;
        int status=planned(&v,block,n==block,&count);if(status)return status;
        total+=count;n-=block;
    }while(n);
    *result=total;return 0;
}
/* Native 100315438: shift retained prefixes only; do not clear storage after
   compaction. A library call can produce fewer frames than requested. The
   wrapper still copies requested frames from its initialized allocation. */
static int child(RBMode2 *s,const float *input,size_t n,size_t request,float *dest) {
    RBMode2Snapshot *v=&s->v;size_t ch=v->channels;
    if(v->input_consumed>v->input_end||v->input_end>v->input_capacity||
       v->output_read>v->output_capacity||v->output_end>v->output_capacity)return RB_MODE2_STATE;
    if((size_t)v->input_end+n>=v->input_capacity&&v->input_consumed) {
        size_t remaining=v->input_end-v->input_consumed;
        memmove(s->input,s->input+(size_t)v->input_consumed*ch,remaining*ch*sizeof(float));
        v->input_end=(uint32_t)remaining;v->input_consumed=0;
    }
    if((size_t)v->output_end+request>=(v->output_capacity>>1)&&v->output_read) {
        if(v->output_read>v->output_end)return RB_MODE2_STATE;
        size_t remaining=v->output_end-v->output_read;
        memmove(s->output,s->output+(size_t)v->output_read*ch,remaining*ch*sizeof(float));
        v->output_end=(uint32_t)remaining;v->output_read=0;
    }
    if(n>v->input_capacity-v->input_end||request>v->output_capacity-v->output_end||
       request>v->output_capacity-v->output_read)return RB_MODE2_CAPACITY;
    if(input&&n)memcpy(s->input+(size_t)v->input_end*ch,input,n*ch*sizeof(float));
    size_t available;
    const float *backend_input;
    if(input&&n) {
        available=(size_t)v->pending_input+n;
        if(available>(size_t)v->input_end+n-v->input_consumed)return RB_MODE2_STATE;
        backend_input=s->input+(size_t)v->input_consumed*ch;
    } else {v->pending_input=0;available=0;backend_input=NULL;}
    size_t used=0,produced=0;
    int status=s->backend.process(s->handle,backend_input,available,&used,
             s->output+(size_t)v->output_end*ch,request,&produced);
    ++v->backend_calls;
    if(status||!arithmetic_ok())return RB_MODE2_BACKEND;
    if(used>available||produced>request||used>UINT32_MAX||produced>UINT32_MAX)return RB_MODE2_BACKEND;
    for(size_t i=0;i<produced*ch;i++)if(!sample_ok(s->output[(size_t)v->output_end*ch+i]))return RB_MODE2_SAMPLE_DOMAIN;
    v->backend_input_used+=used;v->backend_output_produced+=produced;
    v->pending_input+=(uint32_t)n-(uint32_t)used;
    v->input_consumed+=(uint32_t)used;v->output_end+=(uint32_t)produced;
    if(request)memcpy(dest,s->output+(size_t)v->output_read*ch,request*ch*sizeof(float));
    v->input_end+=(uint32_t)n;v->output_read+=(uint32_t)request;
    if(v->input_end==v->input_consumed)v->input_end=v->input_consumed=0;
    if(v->output_read==v->output_end)v->output_read=v->output_end=0;
    return 0;
}
static int positive(RBMode2 *s,const float *input,size_t n,float *dest,size_t *visible) {
    RBMode2Snapshot count=s->v;Block b=block_plan(&count,n);
    float *work=malloc(b.requested*s->v.channels*sizeof(float));if(!work)return RB_MODE2_ALLOCATION;
    int status=child(s,input,n,b.requested,work);
    if(!status) {
        if(b.visible)memcpy(dest,work+b.discarded*s->v.channels,b.visible*s->v.channels*sizeof(float));
        s->v.cumulative_input=count.cumulative_input;s->v.cumulative_visible=count.cumulative_visible;
        s->v.cumulative_ideal=count.cumulative_ideal;s->v.discard=count.discard;*visible=b.visible;
    }
    free(work);return status;
}
int rb_native_mode2_process(RBMode2 *s,const float *input,size_t n,float *output,size_t capacity,uint32_t final,size_t *result) {
    int status=query_valid(s,n,final,result);if(status)return status;
    if(capacity>FRAME_LIMIT||(n&&!input)||(!n&&input))return RB_MODE2_INVALID;
    RBMode2Snapshot expected=s->v;size_t predicted;
    status=planned(&expected,n,final,&predicted);if(status)return status;
    if(predicted>capacity)return RB_MODE2_CAPACITY;
    size_t ib=n*s->v.channels*sizeof(float),ob=capacity*s->v.channels*sizeof(float);
    if((predicted&&!output)||overlap(input,ib,output,ob)||overlap(s,sizeof(*s),input,ib)||
       overlap(s,sizeof(*s),output,ob)||overlap(result,sizeof(*result),input,ib)||overlap(result,sizeof(*result),output,ob))return RB_MODE2_INVALID;
    for(size_t i=0;i<n*s->v.channels;i++)if(!sample_ok(input[i]))return RB_MODE2_SAMPLE_DOMAIN;
    float *work=calloc((predicted?predicted:1)*s->v.channels,sizeof(float));
    if(!work)return RB_MODE2_ALLOCATION;
    size_t emitted=0;
    if(n)status=positive(s,input,n,work,&emitted);
    else {double ignored;emitted=requested(&s->v,0,&ignored);}
    if(!status&&final) {
        uint64_t saved=s->v.cumulative_input;
        volatile double extra_d=(double)s->v.delay/s->v.ratio;
        size_t extra=(size_t)extra_d,ch=s->v.channels;
        float *padding=calloc(extra*ch,sizeof(float));
        if(!padding)status=RB_MODE2_ALLOCATION;
        else {
            if(n)for(size_t i=0;i<extra;i++)memcpy(padding+i*ch,input+(n-1)*ch,ch*sizeof(float));
            size_t added=0;
            status=positive(s,padding,extra,work+emitted*ch,&added);free(padding);
            if(!status) {
                emitted+=added;s->v.cumulative_input=saved;
                volatile double ideal=(double)saved*s->v.ratio;
                int64_t remainder=(int64_t)ideal-(int64_t)s->v.cumulative_visible;
                if(remainder>0) {
                    status=child(s,NULL,0,(size_t)remainder,work+emitted*ch);
                    if(!status)emitted+=(size_t)remainder;
                }
            }
        }
    }
    if(!status&&(emitted!=predicted||s->v.cumulative_input!=expected.cumulative_input||
       s->v.cumulative_visible!=expected.cumulative_visible||s->v.cumulative_ideal!=expected.cumulative_ideal||s->v.discard!=expected.discard))status=RB_MODE2_STATE;
    if(status){s->v.failed=1;free(work);return status;}
    if(predicted)memcpy(output,work,predicted*s->v.channels*sizeof(float));
    s->v.finished=final;s->v.total_returned+=predicted;*result=predicted;free(work);return 0;
}
