#include "cpr_timeline_builder.h"
#include "rebase_fp_environment.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdint.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 && FLT_RADIX == 2,
               "IEEE binary64 required");

static int nearest_environment(void) { return rb_fp_nearest_gradual(); }
static int normal_or_zero(double x) { return x == 0.0 || isnormal(x); }
static int coordinate(double x) { return normal_or_zero(x) && fabs(x) <= 86400.0; }

static int snap(double value, double period, int64_t *out) {
    /* Generic canonical(type1,period1)->type10 conversion. Explicit volatile
       steps retain operation boundaries even when compiled with optimization. */
    volatile double canonical = 1.0 * value;
    volatile double local = canonical / period;
    volatile double biased = local + (local < 0.0 ? -0.5 : 0.5);
    if (!normal_or_zero(local) || !normal_or_zero(biased) ||
        biased < -0x1p63 || biased >= 0x1p63) return 0;
    *out = (int64_t)biased;
    return 1;
}
static double back(int64_t frame, double period) {
    volatile double integer = (double)frame;
    volatile double scaled = period * integer;
    volatile double canonical = scaled / 1.0;
    return canonical;
}

int rb_cpr_timeline_builder_project(double eventStart, double eventEnd,
                                    double contextOffset,
                                    double windowStart, double windowEnd,
                                    double builderRate,
                                    RBTimelineBuilderProjection *output) {
    if (!output || !coordinate(eventStart) || !coordinate(eventEnd) ||
        !coordinate(contextOffset) || !coordinate(windowStart) ||
        !coordinate(windowEnd) || eventEnd < eventStart ||
        windowEnd < windowStart || !isfinite(builderRate) ||
        builderRate < 8000.0 || builderRate > 192000.0 ||
        trunc(builderRate) != builderRate)
        return RB_TIMELINE_BUILDER_INVALID;
    if (!nearest_environment()) return RB_TIMELINE_BUILDER_FP_ENVIRONMENT;
    RBTimelineBuilderProjection r = {0};
    /* FCSEL preserves the event operand on equality, including zero sign. */
    double start = eventStart < windowStart ? windowStart : eventStart;
    double end = windowEnd < eventEnd ? windowEnd : eventEnd;
    if (start >= end) {
        r.disposition = RB_TIMELINE_BUILDER_EMPTY;
        r.emptyReason = RB_TIMELINE_BUILDER_NO_OVERLAP;
        *output = r;
        return RB_TIMELINE_BUILDER_OK;
    }
    volatile double trim = start - eventStart;
    volatile double offset = contextOffset + trim;
    volatile double period = 1.0 / builderRate;
    if (!normal_or_zero(trim) || !normal_or_zero(offset) || !isnormal(period))
        return RB_TIMELINE_BUILDER_RANGE;
    r.period = period;
    r.clippedStart = start;
    r.clippedEnd = end;
    r.clippedSourceOffset = offset;
    if (!snap(start, period, &r.startFrame) ||
        !snap(end, period, &r.endFrame) ||
        !snap(offset, period, &r.offsetFrame)) return RB_TIMELINE_BUILDER_RANGE;
    if (r.endFrame <= r.startFrame) {
        r.disposition = RB_TIMELINE_BUILDER_EMPTY;
        r.emptyReason = RB_TIMELINE_BUILDER_SNAPPED_EMPTY;
        *output = r;
        return RB_TIMELINE_BUILDER_OK;
    }
    r.start = back(r.startFrame, period);
    r.reconstructedEnd = back(r.endFrame, period);
    r.sourceOffset = back(r.offsetFrame, period);
    volatile double difference = r.reconstructedEnd - r.start;
    r.length = difference > 0.0 ? difference : 0.0;
    volatile double getterEnd = r.start + r.length;
    r.getterEnd = getterEnd;
    if (!normal_or_zero(r.start) || !normal_or_zero(r.reconstructedEnd) ||
        !normal_or_zero(r.sourceOffset) || !normal_or_zero(difference) ||
        !normal_or_zero(getterEnd)) return RB_TIMELINE_BUILDER_RANGE;
    *output = r;
    return RB_TIMELINE_BUILDER_OK;
}
