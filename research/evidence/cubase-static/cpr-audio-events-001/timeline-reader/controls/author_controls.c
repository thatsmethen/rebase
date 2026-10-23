#include "cpr_timeline_reader.h"
#include <assert.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
int main(void) {
 RBTimelinePlan p, prior; RBTimelineSegment s={2,6,3};
 assert(rb_cpr_timeline_plan(0,8,0,1,&s,&p)==0);
 assert(p.action==RB_TIMELINE_READ && p.silenceFrames==2 && p.readFrames==4 && p.sourceSeek==3 && p.nextCursor==6 && p.retryAtSegmentStart);
 assert(rb_cpr_timeline_plan(5,9,5,1,&s,&p)==0 && p.readFrames==1 && p.sourceSeek==6 && !p.retryAtSegmentStart);
 assert(rb_cpr_timeline_plan(6,8,6,1,&s,&p)==0 && p.action==RB_TIMELINE_SKIP && p.skipReason==RB_TIMELINE_EMPTY_INTERSECTION);
 s=(RBTimelineSegment){8,9,0};
 assert(rb_cpr_timeline_plan(0,8,0,1,&s,&p)==0 && p.action==RB_TIMELINE_SILENCE && p.silenceFrames==8 && p.stopAfter);
 s=(RBTimelineSegment){2,2,0};
 assert(rb_cpr_timeline_plan(0,8,0,1,&s,&p)==0 && p.action==RB_TIMELINE_SKIP && p.skipReason==RB_TIMELINE_INVALID_SEGMENT);
 assert(rb_cpr_timeline_plan(0,8,3,1,NULL,&p)==0 && p.silenceFrames==5 && p.stopAfter);
 memset(&p,0x5a,sizeof p); memcpy(&prior,&p,sizeof p);
 assert(rb_cpr_timeline_plan(INT64_MIN,INT64_MAX,0,1,NULL,&p)==RB_TIMELINE_RANGE && !memcmp(&p,&prior,sizeof p));
 s=(RBTimelineSegment){NAN,2,0};
 assert(rb_cpr_timeline_plan(0,8,0,1,&s,&p)==RB_TIMELINE_INVALID && !memcmp(&p,&prior,sizeof p));
 int64_t q=99; assert(rb_cpr_timeline_quantize(1,-1.5,&q)==0 && q==-1);
 assert(rb_cpr_timeline_quantize(1,0x1p63,&q)==RB_TIMELINE_RANGE && q==-1);
 RBTimelinePartition part;
 assert(rb_cpr_timeline_partition(-1.5,2.4,10,0,&part)==0 && part.startFrame==-2 && part.frames==4 && part.endFrame==2);
 assert(rb_cpr_timeline_partition(-1.5,2.4,2,4,&part)==0 && part.frames==2 && part.silence);
 RBTimelineReadDecision d;
 assert(rb_cpr_timeline_read_result(4,2,2,0,-2147483645,&d)==0 && d.action==RB_TIMELINE_READ_RETRY);
 assert(rb_cpr_timeline_read_result(4,2,2,1,-2147483645,&d)==0 && d.action==RB_TIMELINE_READ_FAILED && d.nativeResult==-2147483645);
 assert(rb_cpr_timeline_read_result(4,2,2,0,3,&d)==0 && d.action==RB_TIMELINE_READ_FAILED && d.nativeResult==INT32_MIN);
 assert(rb_cpr_timeline_read_result(4,2,2,0,4,&d)==0 && d.action==RB_TIMELINE_READ_COMPLETE);
 puts("PASS: 16 authored planner/quantization/partition/read and transactional boundary controls; reconstruction only.");
}
