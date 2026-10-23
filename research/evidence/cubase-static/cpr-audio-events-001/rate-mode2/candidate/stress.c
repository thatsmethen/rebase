#include "native_rate_mode2.h"
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
static int create(void *context,double a,double b,uint32_t ch,void **h) {
 (void)context;(void)a;(void)b; uint32_t *p=malloc(sizeof(*p));if(!p)return 1;*p=ch;*h=p;return 0;
}
static int process(void *h,const float *in,size_t n,size_t *used,float *out,size_t cap,size_t *produced) {
 uint32_t ch=*(uint32_t*)h;*used=in?n:0;*produced=cap;
 for(size_t i=0;i<cap*ch;i++)out[i]=(float)((int)(i%17)-8)*0.125f;
 return 0;
}
static void destroy(void *h){free(h);}
int main(void) {
 const double rates[]={8000,11025,16000,32000,44100,48000,96000,192000};size_t calls=0;
 RBMode2Backend backend={0,create,process,destroy};
 for(size_t i=0;i<8;i++)for(size_t j=0;j<8;j++)for(uint32_t ch=1;ch<=2;ch++) {
  RBMode2 *s=NULL;assert(!rb_native_mode2_create(rates[i],rates[j],ch,backend,&s));
  size_t predicted=0,total=0;assert(!rb_native_mode2_count_blocks(s,17003,8192,&predicted));
  size_t left=17003;
  while(left) {
   size_t n=left<8192?left:8192,count=0,got=0;assert(!rb_native_mode2_count(s,n,n==left,&count));
   float *in=calloc(n*ch,sizeof(float)),*out=malloc((count?count:1)*ch*sizeof(float));assert(in&&out);
   assert(!rb_native_mode2_process(s,in,n,out,count,n==left,&got));assert(got==count);total+=got;
   free(in);free(out);left-=n;calls++;
  }
  assert(total==predicted);rb_native_mode2_destroy(s);
 }
 printf("UBSan reconstructed-wrapper synthetic calls=%zu passed\n",calls);return 0;
}
