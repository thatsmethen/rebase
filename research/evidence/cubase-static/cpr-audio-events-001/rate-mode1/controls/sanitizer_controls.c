#include "native_rate_mode1.h"
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

static uint32_t random_word(uint32_t *state) {
    *state=*state*1664525u+1013904223u;return *state;
}
static void block(RBMode1 *s,size_t frames,unsigned final,unsigned channels) {
    size_t count=999,actual=998;
    assert(rb_native_mode1_count(s,frames,final,&count)==0);
    float *input=frames?malloc(frames*channels*sizeof(float)):NULL;
    float *output=malloc((count*channels+4)*sizeof(float));
    assert((!frames||input)&&output);
    uint32_t rng=(uint32_t)frames+1;
    for(size_t i=0;i<frames*channels;i++)input[i]=(float)(int32_t)(random_word(&rng)%65537-32768)/65536;
    for(size_t i=0;i<count*channels+4;i++)output[i]=19;
    assert(rb_native_mode1_process(s,input,frames,output,count,final,&actual)==0);
    assert(actual==count);
    for(size_t i=count*channels;i<count*channels+4;i++)assert(output[i]==19);
    free(input);free(output);
}
int main(void) {
    const double rates[][2]={{44100,48000},{48000,32000},{48000,48000},{8000,192000},{192000,8000}};
    for(unsigned r=0;r<5;r++)for(unsigned ch=1;ch<=2;ch++) {
        RBMode1 *s=NULL;
        assert(rb_native_mode1_create(rates[r][0],rates[r][1],ch,&s)==0);
        block(s,1,0,ch);block(s,0,0,ch);block(s,63,0,ch);
        block(s,65,0,ch);block(s,8192,0,ch);block(s,1,1,ch);
        RBMode1Snapshot before,after;
        assert(rb_native_mode1_snapshot(s,&before)==0);
        size_t n=555;
        assert(rb_native_mode1_count(s,1,0,&n)==RB_MODE1_STATE&&n==555);
        assert(rb_native_mode1_snapshot(s,&after)==0&&!memcmp(&before,&after,sizeof(before)));
        assert(rb_native_mode1_reset(s)==0);
        block(s,1,0,ch);block(s,127,1,ch);
        rb_native_mode1_destroy(s);
    }
    RBMode1 *s=NULL;assert(rb_native_mode1_create(48000,48000,2,&s)==0);
    block(s,65536,0,2);
    size_t count=999;
    assert(rb_native_mode1_count(s,65536,1,&count)==RB_MODE1_NATIVE_BOUNDS&&count==999);
    block(s,65537,1,2);
    rb_native_mode1_destroy(s);
    puts("PASS: reconstruction-only stream, reset, resize and native-bound controls.");
    return 0;
}
