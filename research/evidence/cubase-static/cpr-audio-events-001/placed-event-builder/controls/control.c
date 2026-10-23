#include "cpr_timeline_builder.h"
#include <assert.h>
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#pragma STDC FENV_ACCESS ON
int main(void) {
 unsigned checked=0;
 RBTimelineBuilderProjection r={0},saved={0};
#define CHECK(x) do { assert(x); ++checked; } while(0)
 CHECK(rb_cpr_timeline_builder_project(2,6,.5,3,5,48000,&r)==0);
 CHECK(r.startFrame==144000 && r.endFrame==240000 && r.offsetFrame==72000);
 CHECK(r.start==3 && r.length==2 && r.sourceOffset==1.5 && r.getterEnd==5);
 CHECK(rb_cpr_timeline_builder_project(-.5/8192,.5/8192,-.5/8192,-1,1,8192,&r)==0);
 CHECK(r.startFrame==-1 && r.endFrame==1 && r.offsetFrame==-1);
 CHECK(r.length==2.0/8192 && r.getterEnd==1.0/8192);
 CHECK(rb_cpr_timeline_builder_project(-0.0,1,0,0,1,8192,&r)==0);
 CHECK(signbit(r.clippedStart) && !signbit(r.start));
 CHECK(rb_cpr_timeline_builder_project(0,1,0,1,2,8192,&r)==0);
 CHECK(r.disposition==1 && r.emptyReason==1);
 CHECK(rb_cpr_timeline_builder_project(0,.25/8192,0,0,1,8192,&r)==0);
 CHECK(r.disposition==1 && r.emptyReason==2);
 r.startFrame=77;r.sourceOffset=88;saved=r;
 double bad[]={NAN,INFINITY,-INFINITY,DBL_TRUE_MIN,86401};
 for(unsigned i=0;i<5;i++){
  CHECK(rb_cpr_timeline_builder_project(bad[i],1,0,0,1,48000,&r)==1);
  CHECK(memcmp(&r,&saved,sizeof(r))==0);
 }
 CHECK(rb_cpr_timeline_builder_project(DBL_MIN,2*DBL_MIN,0,nextafter(DBL_MIN,INFINITY),2*DBL_MIN,48000,&r)==2);
 CHECK(memcmp(&r,&saved,sizeof(r))==0);
 CHECK(rb_cpr_timeline_builder_project(0,1,0,0,1,44100.5,&r)==1);
 CHECK(memcmp(&r,&saved,sizeof(r))==0);
 int modes[]={FE_UPWARD,FE_DOWNWARD,FE_TOWARDZERO};
 for(unsigned i=0;i<3;i++){
  assert(fesetround(modes[i])==0);
  CHECK(rb_cpr_timeline_builder_project(0,1,0,0,1,48000,&r)==3);
  CHECK(memcmp(&r,&saved,sizeof(r))==0);
 }
 assert(fesetround(FE_TONEAREST)==0);
 printf("{\"passed\":true,\"controls\":%u,\"scope\":\"Authored reconstruction only; no target execution\"}\n",checked);
 return 0;
}
