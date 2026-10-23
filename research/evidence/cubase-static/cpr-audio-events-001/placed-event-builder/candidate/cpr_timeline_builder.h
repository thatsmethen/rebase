#ifndef REBASE_CPR_TIMELINE_BUILDER_H
#define REBASE_CPR_TIMELINE_BUILDER_H
#include <stdint.h>

/* Bounded singleton/no-fade arithmetic reconstructed from Cubase15 arm64
   10020e354, 10020e7c8, 10020f2e8 and PAudioSegment setter101a17cec.
   Inputs are already-resolved canonical coordinates. This helper does not
   infer CPR units, context/track shifts, source rate, source extent, fade or
   overlap state. builderRate is the explicit builder context rate, which
   need not equal the selected source stream rate.

   P=RN64(1/builderRate). Each coordinate is separately divided by P,
   separately added to +/-0.5 (negative iff coordinate<0), then truncated
   to signed64. This is NOT the reader's FMADD(coord,multiplier,+0.5).
   Stored coordinates are RN64(Double(integer)*P); stored length is
   max(RN64(reconstructedEnd-storedStart),0), and the concrete end getter
   returns RN64(storedStart+storedLength).

   Defensive domain: integral rate8k..192k, finite normal-or-zero input
   coordinates within +/-86400, ordered event and window bounds. Nonzero
   subnormal intermediate values reject. ARM64 round-to-nearest with
   FZ/DN/AH/FIZ off. Errors leave output unchanged. No source samples or
   target code are executed. Empty results have only the documented fields
   meaningful; unused fields are zeroed by this reconstruction. */
enum {
    RB_TIMELINE_BUILDER_OK = 0,
    RB_TIMELINE_BUILDER_INVALID = 1,
    RB_TIMELINE_BUILDER_RANGE = 2,
    RB_TIMELINE_BUILDER_FP_ENVIRONMENT = 3
};
enum { RB_TIMELINE_BUILDER_SEGMENT = 0, RB_TIMELINE_BUILDER_EMPTY = 1 };
enum {
    RB_TIMELINE_BUILDER_NOT_EMPTY = 0,
    RB_TIMELINE_BUILDER_NO_OVERLAP = 1,
    RB_TIMELINE_BUILDER_SNAPPED_EMPTY = 2
};
typedef struct {
    int32_t disposition;
    int32_t emptyReason;
    double period;
    double clippedStart;
    double clippedEnd;
    double clippedSourceOffset;
    int64_t startFrame;
    int64_t endFrame;
    int64_t offsetFrame;
    double start;
    double reconstructedEnd;
    double length;
    double sourceOffset;
    double getterEnd;
} RBTimelineBuilderProjection;

/* Positive overlap clips [eventStart,eventEnd] to the window. The offset is
   RN64(contextOffset+RN64(clippedStart-eventStart)), before quantization.
   NO_OVERLAP sets only disposition/reason; SNAPPED_EMPTY additionally
   provides period, clipped values and the three quantized integer values.
   Native admission/lifecycle and caller-owned range policies remain outside
   this helper. The singleton flattening sentinel is below the admitted
   coordinate domain, so it does not change these inputs. */
int rb_cpr_timeline_builder_project(double eventStart, double eventEnd,
                                    double contextOffset,
                                    double windowStart, double windowEnd,
                                    double builderRate,
                                    RBTimelineBuilderProjection *output);
#endif
