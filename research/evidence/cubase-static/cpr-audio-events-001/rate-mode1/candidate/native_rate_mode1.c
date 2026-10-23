#include "native_rate_mode1.h"
#include <fenv.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
#define MAGIC UINT64_C(0x52424d4f44453131)
#define TABLE_SIZE ((size_t)32769)
#define FRAME_LIMIT ((size_t)16000000)
#define BLOCK_LIMIT ((size_t)1000000)

struct RBMode1 {
    uint64_t magic;
    RBMode1Snapshot v;
    double *coefficient, *difference, *storage[2];
};
typedef struct {
    RBMode1Snapshot after;
    size_t generated, returned, consumed, initial_skip, local_frames;
} Plan;
static double add(double a,double b) { volatile double r=a+b;return r; }
static double sub(double a,double b) { volatile double r=a-b;return r; }
static double mul(double a,double b) { volatile double r=a*b;return r; }
static double divide(double a,double b) { volatile double r=a/b;return r; }
static double bits(uint64_t b) { double d;memcpy(&d,&b,8);return d; }
static int arithmetic_ok(void) {
    if(fegetround()!=FE_TONEAREST)return 0;
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr;__asm__ volatile("mrs %0, fpcr":"=r"(fpcr));
    if(fpcr&((UINT64_C(1)<<24)|UINT64_C(1)))return 0;
#elif defined(__x86_64__)
    uint32_t mxcsr;__asm__ volatile("stmxcsr %0":"=m"(mxcsr));
    if(mxcsr&((1u<<15)|(1u<<6)))return 0;
#else
    return 0;
#endif
    return 1;
}
static int overlap(const void *a,size_t an,const void *b,size_t bn) {
    if(!an||!bn)return 0;
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(an>UINTPTR_MAX-x||bn>UINTPTR_MAX-y)return 1;
    return x<y+bn&&y<x+an;
}
static int sample_ok(float x) { return isfinite(x)&&(x==0||isnormal(x)); }
static int usable(const RBMode1 *s) {
    return s&&s->magic==MAGIC&&s->coefficient&&s->difference&&
        s->storage[0]&&(s->v.channels==1||s->storage[1])&&arithmetic_ok();
}
static int owned_overlap(const RBMode1 *s,const void *p,size_t n) {
    if(overlap(p,n,s,sizeof(*s))||
       overlap(p,n,s->coefficient,TABLE_SIZE*8)||
       overlap(p,n,s->difference,TABLE_SIZE*8))return 1;
    for(uint32_t c=0;c<s->v.channels;c++)
        if(overlap(p,n,s->storage[c],((size_t)s->v.input_capacity+129)*8))return 1;
    return 0;
}
/* Native 10030ade4 and10030ab6c: deliberately separate operations. */
static double series(double half) {
    double term=1,sum=1,index=1,epsilon=bits(UINT64_C(0x3b92e3b40a0e9b4f));
    do {
        double t=divide(half,index);index=add(index,1);
        t=mul(t,t);term=mul(term,t);sum=add(sum,term);
    } while(term>=mul(sum,epsilon));
    return sum;
}
static int make_tables(RBMode1 *s) {
    double inverse=divide(1,series(bits(UINT64_C(0x4011eb851eb851ec))));
    double cutoff=s->v.ratio<1?mul(s->v.ratio,0.5):0.5;
    double increment=mul(mul(add(cutoff,cutoff),
                             bits(UINT64_C(0x400921fb54442d18))),0x1p-9);
    s->coefficient[0]=1;
    for(size_t i=1;i<TABLE_SIZE;i+=2) {
        double first=mul((double)i,increment),second=mul((double)(i+1),increment);
        /* The original vector pair calls _sin on its second lane first.
           The imported math implementation itself remains external. */
        double second_sine=sin(second),first_sine=sin(first);
        s->coefficient[i]=divide(first_sine,first);
        s->coefficient[i+1]=divide(second_sine,second);
    }
    for(size_t i=1;i<TABLE_SIZE;i++) {
        double r=mul(0x1p-15,(double)i);
        double radial=sqrt(fma(-r,r,1.0)); /* FMSUB then FSQRT. */
        double half=mul(mul(radial,bits(UINT64_C(0x4021eb851eb851ec))),0.5);
        double window=mul(series(half),inverse);
        s->coefficient[i]=mul(s->coefficient[i],window);
    }
    double sum=0;
    for(size_t i=512;i<TABLE_SIZE;i+=512)sum=add(sum,s->coefficient[i]);
    double norm=divide(1,fma(sum,2.0,1.0));
    for(size_t i=0;i<TABLE_SIZE;i++) {
        s->coefficient[i]=mul(s->coefficient[i],norm);
        if(!isfinite(s->coefficient[i]))return RB_MODE1_SAMPLE_DOMAIN;
    }
    for(size_t i=0;i<TABLE_SIZE-1;i++)
        s->difference[i]=sub(s->coefficient[i+1],s->coefficient[i]);
    s->difference[TABLE_SIZE-1]=-s->coefficient[TABLE_SIZE-1];
    return 0;
}
int rb_native_mode1_create(double rin,double rout,uint32_t ch,RBMode1 **result) {
    if(!result||!arithmetic_ok()||!isfinite(rin)||!isfinite(rout)||
       rin<8000||rin>192000||rout<8000||rout>192000||
       floor(rin)!=rin||floor(rout)!=rout||(ch!=1&&ch!=2))return RB_MODE1_INVALID;
    RBMode1 *s=calloc(1,sizeof(*s));if(!s)return RB_MODE1_ALLOCATION;
    s->magic=MAGIC;s->v.ratio=divide(rout,rin);s->v.step=divide(512,s->v.ratio);
    s->v.channels=ch;s->v.input_capacity=65536;s->v.fresh=1;
    s->coefficient=malloc(TABLE_SIZE*8);s->difference=malloc(TABLE_SIZE*8);
    for(uint32_t c=0;c<ch;c++)s->storage[c]=calloc(65536+129,8);
    if(!s->coefficient||!s->difference||!s->storage[0]||(ch==2&&!s->storage[1])) {
        rb_native_mode1_destroy(s);return RB_MODE1_ALLOCATION;
    }
    int error=make_tables(s);
    if(error){rb_native_mode1_destroy(s);return error;}
    *result=s;return 0;
}
void rb_native_mode1_destroy(RBMode1 *s) {
    if(!s)return;
    free(s->coefficient);free(s->difference);free(s->storage[0]);free(s->storage[1]);
    memset(s,0,sizeof(*s));free(s);
}
int rb_native_mode1_snapshot(const RBMode1 *s,RBMode1Snapshot *result) {
    if(!usable(s)||!result||owned_overlap(s,result,sizeof(*result)))return RB_MODE1_INVALID;
    *result=s->v;return 0;
}
int rb_native_mode1_reset(RBMode1 *s) {
    if(!usable(s))return RB_MODE1_INVALID;
    s->v.phase=0;s->v.cumulative_input=0;s->v.cumulative_generated=0;
    s->v.total_returned=0;s->v.fresh=1;s->v.finished=0;return 0;
}
/* Count the native phase loop; no floor(total*ratio) substitution. The latter
   is only the native final upper bound on the current returned region. */
static int plan(const RBMode1Snapshot *before,size_t n,uint32_t final,Plan *p) {
    if(n>BLOCK_LIMIT||final>1)return RB_MODE1_INVALID;
    if(before->finished)return RB_MODE1_STATE;
    if(n>FRAME_LIMIT-before->cumulative_input)return RB_MODE1_CAPACITY;
    memset(p,0,sizeof(*p));p->after=*before;
    if(n>p->after.input_capacity)p->after.input_capacity=(uint32_t)n+1024;
    size_t allocated=(size_t)p->after.input_capacity+129;
    size_t write_start=before->fresh?64:128;
    if(write_start+n+(final?64:0)>allocated)return RB_MODE1_NATIVE_BOUNDS;
    size_t i=before->fresh?64:0,limit=n+(final?64:0);
    p->initial_skip=i;p->local_frames=limit;
    double phase=before->phase;
    while((int64_t)phase>=512&&i<limit){phase=add(phase,-512);++i;++p->consumed;}
    while(i<limit) {
        ++p->generated;
        if(p->generated>FRAME_LIMIT+2048)return RB_MODE1_CAPACITY;
        phase=add(phase,before->step);
        while((int64_t)phase>=512&&i<limit){phase=add(phase,-512);++i;++p->consumed;}
    }
    /* Final native memmove is128 doubles from center−64. */
    if(p->consumed+128>allocated)return RB_MODE1_NATIVE_BOUNDS;
    p->after.phase=phase;p->after.fresh=0;
    p->after.cumulative_input+=n;p->after.cumulative_generated+=p->generated;
    p->returned=p->generated;
    if(final) {
        int64_t desired=(int64_t)mul(before->ratio,(double)p->after.cumulative_input);
        int64_t total=(int64_t)p->after.cumulative_generated;
        if(desired<total) {
            int64_t visible=(int64_t)p->generated+desired-total;
            p->returned=visible>0?(size_t)visible:0;
        }
        p->after.finished=1;
    }
    if(p->returned>FRAME_LIMIT-before->total_returned)return RB_MODE1_CAPACITY;
    p->after.total_returned+=p->returned;
    return 0;
}
int rb_native_mode1_count(const RBMode1 *s,size_t n,uint32_t final,size_t *result) {
    if(!usable(s)||!result||owned_overlap(s,result,sizeof(*result)))return RB_MODE1_INVALID;
    Plan p;int error=plan(&s->v,n,final,&p);if(error)return error;
    *result=p.returned;return 0;
}
int rb_native_mode1_count_blocks(const RBMode1 *s,size_t n,size_t block,size_t *result) {
    if(!usable(s)||!result||owned_overlap(s,result,sizeof(*result))||
       !block||block>BLOCK_LIMIT||n>FRAME_LIMIT)return RB_MODE1_INVALID;
    RBMode1Snapshot v=s->v;size_t remaining=n,total=0;Plan p;int error;
    do {
        size_t take=remaining<block?remaining:block;
        error=plan(&v,take,take==remaining,&p);if(error)return error;
        total+=p.returned;v=p.after;remaining-=take;
    } while(remaining);
    *result=total;return 0;
}
static int run(const RBMode1 *s,double *storage[2],const float *input,size_t n,
               uint32_t final,float *output,const Plan *p) {
    uint32_t channels=s->v.channels;
    size_t write=s->v.fresh?64:128;
    for(uint32_t c=0;c<channels;c++) {
        if(s->v.fresh) {
            double first=input?(double)input[c]:0;
            for(size_t i=0;i<64;i++)storage[c][i]=first;
        }
        for(size_t i=0;i<n;i++)storage[c][write+i]=(double)input[i*channels+c];
        if(final) {
            double last=n?(double)input[(n-1)*channels+c]:0;
            for(size_t i=0;i<64;i++)storage[c][write+n+i]=last;
        }
    }
    size_t i=p->initial_skip,center=64,produced=0;
    double phase=s->v.phase;
    while((int64_t)phase>=512&&i<p->local_frames){phase=add(phase,-512);++i;++center;}
    while(i<p->local_frames) {
        int32_t left=(int32_t)phase;double fraction=sub(phase,(double)left);
        double complement=sub(512,phase);
        int32_t right=(int32_t)complement;double rf=sub(complement,(double)right);
        if(left<0||left>511||right<0||right>512)return RB_MODE1_STATE;
        for(uint32_t c=0;c<channels;c++) {
            double acc=0;
            for(size_t k=0;k<64;k++) {
                size_t index=(size_t)left+k*512;
                double weight=fma(fraction,s->difference[index],s->coefficient[index]);
                acc=fma(storage[c][center-k],weight,acc);
            }
            for(size_t k=0;k<64;k++) {
                size_t index=(size_t)right+k*512;
                double weight=fma(rf,s->difference[index],s->coefficient[index]);
                acc=fma(storage[c][center+k+1],weight,acc);
            }
            float value=(float)acc;
            if(!sample_ok(value))return RB_MODE1_SAMPLE_DOMAIN;
            output[produced*channels+c]=value;
        }
        ++produced;phase=add(phase,s->v.step);
        while((int64_t)phase>=512&&i<p->local_frames){phase=add(phase,-512);++i;++center;}
    }
    if(produced!=p->generated||phase!=p->after.phase||center-64!=p->consumed)return RB_MODE1_STATE;
    for(uint32_t c=0;c<channels;c++)memmove(storage[c],storage[c]+center-64,128*8);
    return 0;
}
int rb_native_mode1_process(RBMode1 *s,const float *input,size_t n,float *output,
                           size_t capacity,uint32_t final,size_t *result) {
    if(!usable(s)||!result||((n>0)!=(input!=NULL))||
       owned_overlap(s,result,sizeof(*result)))return RB_MODE1_INVALID;
    Plan p;int error=plan(&s->v,n,final,&p);if(error)return error;
    if(capacity<p.returned||(!output&&p.returned))return RB_MODE1_CAPACITY;
    if(capacity>SIZE_MAX/(sizeof(float)*s->v.channels))return RB_MODE1_INVALID;
    size_t inbytes=n*s->v.channels*4,outbytes=capacity*s->v.channels*4;
    if((outbytes&&!output)||owned_overlap(s,input,inbytes)||owned_overlap(s,output,outbytes)||
       overlap(input,inbytes,output,outbytes)||overlap(input,inbytes,result,sizeof(*result))||
       overlap(output,outbytes,result,sizeof(*result)))return RB_MODE1_INVALID;
    for(size_t i=0;i<n*s->v.channels;i++)if(!sample_ok(input[i]))return RB_MODE1_SAMPLE_DOMAIN;
    double *storage[2]={NULL,NULL};
    size_t bytes=((size_t)p.after.input_capacity+129)*8;
    for(uint32_t c=0;c<s->v.channels;c++) {
        if(p.after.input_capacity!=s->v.input_capacity)storage[c]=calloc(1,bytes);
        else {storage[c]=malloc(bytes);if(storage[c])memcpy(storage[c],s->storage[c],bytes);}
        if(!storage[c]){error=RB_MODE1_ALLOCATION;goto done;}
    }
    float *staged=NULL;
    if(p.generated) {
        staged=malloc(p.generated*s->v.channels*4);
        if(!staged){error=RB_MODE1_ALLOCATION;goto done;}
    }
    error=run(s,storage,input,n,final,staged,&p);
    if(!error) {
        if(p.returned)memcpy(output,staged,p.returned*s->v.channels*4);
        for(uint32_t c=0;c<s->v.channels;c++){free(s->storage[c]);s->storage[c]=storage[c];storage[c]=NULL;}
        s->v=p.after;*result=p.returned;
    }
    free(staged);
done:
    free(storage[0]);free(storage[1]);return error;
}
static int copy_valid(const RBMode1 *s,size_t start,size_t count,size_t limit,double *out) {
    if(!usable(s)||start>limit||count>limit-start||(!out&&count)||
       owned_overlap(s,out,count*8))return RB_MODE1_INVALID;
    return 0;
}
int rb_native_mode1_copy_table(const RBMode1 *s,uint32_t table,size_t start,size_t count,double *out) {
    int error=copy_valid(s,start,count,TABLE_SIZE,out);
    if(error||table>1)return RB_MODE1_INVALID;
    if(count)memcpy(out,(table?s->difference:s->coefficient)+start,count*8);return 0;
}
int rb_native_mode1_copy_storage(const RBMode1 *s,uint32_t channel,size_t start,size_t count,double *out) {
    if(!usable(s)||channel>=s->v.channels)return RB_MODE1_INVALID;
    int error=copy_valid(s,start,count,(size_t)s->v.input_capacity+129,out);if(error)return error;
    if(count)memcpy(out,s->storage[channel]+start,count*8);return 0;
}
