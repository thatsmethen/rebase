/* Candidate-only sanitizer stress. No proprietary executable or library linked. */
#include "native_rate_mode0_down.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
int main(void) {
    const float rates[][2]={{48000,44100},{88200,48000},{48000,48000},{96000,48000},{192000,44100},{192000,8000},{48000,32000}};
    unsigned calls=0;
    for(unsigned r=0;r<7;r++)for(unsigned channels=1;channels<=2;channels++)for(unsigned layout=0;layout<2;layout++) {
        RBMode0DownState state;assert(rb_native_mode0_down_init(rates[r][0],rates[r][1],channels,&state)==0);
        for(unsigned k=0;k<800;k++) {
            size_t n=(k*37)%67,cap=n+1;
            float *arena=malloc((n+cap)*channels*sizeof(float));assert(arena);
            float *input=arena+(layout?0:cap*channels),*output=arena+(layout?n*channels:0);
            for(size_t i=0;i<n*channels;i++)input[i]=(float)((int)((i*17+k)%99)-49)*0x1p-7f;
            for(size_t i=0;i<cap*channels;i++)output[i]=123;
            RBMode0DownState before=state;size_t prediction=999,produced=999;
            int rc=rb_native_mode0_down_count(&state,n,layout,k&1,&prediction);
            int rp=rb_native_mode0_down_process(&state,input,n,output,cap,layout,k&1,&produced);
            assert(rc==rp);if(!rc){assert(produced==prediction);}else{assert(rc==RB_MODE0_DOWN_LOOKAHEAD);assert(produced==999);assert(!memcmp(&state,&before,sizeof state));for(size_t i=0;i<cap*channels;i++)assert(output[i]==123);}
            free(arena);calls++;
            if(rc==RB_MODE0_DOWN_LOOKAHEAD||k%47==0)assert(rb_native_mode0_down_reset(&state)==0);
        }
    }
    printf("{\"candidate_calls\":%u,\"sanitizers\":\"address,undefined\",\"target_execution\":false}\n",calls);
}
