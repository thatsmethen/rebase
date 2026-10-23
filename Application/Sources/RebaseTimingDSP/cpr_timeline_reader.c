#include "cpr_timeline_reader.h"
#include "rebase_fp_environment.h"
#include <fenv.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
_Static_assert(sizeof(float) == 4 && FLT_MANT_DIG == 24 && FLT_RADIX == 2,
               "IEEE binary32 required");
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53,
               "IEEE binary64 required");

#define RB_TIMELINE_MAX_FRAMES INT64_C(16000000)
#define RB_TIMELINE_TRANSIENT (-INT32_C(2147483645))

static int nearest_environment(void) { return rb_fp_nearest_gradual(); }
static int normal_or_zero(double x) {
    return x == 0.0 || isnormal(x);
}
static int add64(int64_t a, int64_t b, int64_t *out) {
    if ((b > 0 && a > INT64_MAX - b) ||
        (b < 0 && a < INT64_MIN - b)) return 0;
    *out = a + b;
    return 1;
}
static int subtract64(int64_t a, int64_t b, int64_t *out) {
    if ((b > 0 && a < INT64_MIN + b) ||
        (b < 0 && a > INT64_MAX + b)) return 0;
    *out = a - b;
    return 1;
}
static int disjoint(const void *a, size_t an, const void *b, size_t bn) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (an > UINTPTR_MAX - x || bn > UINTPTR_MAX - y) return 0;
    return x + an <= y || y + bn <= x;
}
static int multiplier(double period, double *out) {
    if (!(period > 0.0) || !isnormal(period)) return RB_TIMELINE_INVALID;
    volatile double reciprocal = 1.0 / period;
    volatile float narrowed = (float)reciprocal;
    if (!(narrowed > 0.0f) || !isnormal(narrowed)) return RB_TIMELINE_RANGE;
    *out = (double)narrowed;
    return RB_TIMELINE_OK;
}
static int truncate64(double value, int64_t *out) {
    /* INT64_MAX rounds up as double; the upper limit must be exclusive. */
    if (!isfinite(value) || value < -0x1p63 || value >= 0x1p63) return 0;
    *out = (int64_t)value;
    return 1;
}
static int quantize(double scale, double coordinate, int64_t *out) {
    return truncate64(fma(coordinate, scale, 0.5), out);
}

int rb_cpr_timeline_quantize(double period, double coordinate, int64_t *output) {
    if (!output || !normal_or_zero(coordinate)) return RB_TIMELINE_INVALID;
    if (!nearest_environment()) return RB_TIMELINE_FP_ENVIRONMENT;
    double scale;
    int status = multiplier(period, &scale);
    if (status) return status;
    int64_t value;
    if (!quantize(scale, coordinate, &value)) return RB_TIMELINE_RANGE;
    *output = value;
    return RB_TIMELINE_OK;
}

int rb_cpr_timeline_plan(int64_t requestStart, int64_t requestEnd,
                        int64_t cursor, double period,
                        const RBTimelineSegment *segment,
                        RBTimelinePlan *output) {
    if (!output || requestEnd < requestStart ||
        cursor < requestStart || cursor > requestEnd)
        return RB_TIMELINE_INVALID;
    if (segment && !disjoint(segment, sizeof(*segment), output, sizeof(*output)))
        return RB_TIMELINE_INVALID;
    if (!nearest_environment()) return RB_TIMELINE_FP_ENVIRONMENT;
    double scale;
    int status = multiplier(period, &scale);
    if (status) return status;
    int64_t span;
    if (!subtract64(requestEnd, requestStart, &span) ||
        span > RB_TIMELINE_MAX_FRAMES) return RB_TIMELINE_RANGE;
    RBTimelineSegment s = {0};
    if (segment) {
        s = *segment;
        if (!normal_or_zero(s.start) || !normal_or_zero(s.end) ||
            !normal_or_zero(s.sourceOffset)) return RB_TIMELINE_INVALID;
    }
    RBTimelinePlan r = {0};
    r.nextCursor = cursor;
    r.silenceOffset = cursor - requestStart;
    if (cursor == requestEnd) {
        r.action = RB_TIMELINE_DONE;
        r.stopAfter = 1;
        *output = r;
        return RB_TIMELINE_OK;
    }
    if (!segment) goto tail_silence;
    if (!quantize(scale, s.start, &r.segmentStart)) return RB_TIMELINE_RANGE;
    r.quantizedFields = 1;
    if (r.segmentStart > requestEnd) goto tail_silence;
    if (!quantize(scale, s.end, &r.segmentEnd)) return RB_TIMELINE_RANGE;
    r.quantizedFields |= 2;
    if (r.segmentStart >= r.segmentEnd) {
        r.action = RB_TIMELINE_SKIP;
        r.skipReason = RB_TIMELINE_INVALID_SEGMENT;
        *output = r;
        return RB_TIMELINE_OK;
    }
    if (r.segmentEnd < requestStart) {
        r.action = RB_TIMELINE_SKIP;
        r.skipReason = RB_TIMELINE_BEFORE_REQUEST;
        *output = r;
        return RB_TIMELINE_OK;
    }
    if (!quantize(scale, s.sourceOffset, &r.segmentOffset))
        return RB_TIMELINE_RANGE;
    r.quantizedFields |= 4;
    r.sourceSeek = r.segmentOffset;
    r.readBegin = cursor > r.segmentStart ? cursor : r.segmentStart;
    if (cursor < r.segmentStart)
        r.silenceFrames = r.segmentStart - cursor;
    else if (cursor > r.segmentStart) {
        int64_t delta;
        if (!subtract64(cursor, r.segmentStart, &delta) ||
            !add64(r.segmentOffset, delta, &r.sourceSeek))
            return RB_TIMELINE_RANGE;
    }
    r.readOffset = r.readBegin - requestStart;
    int64_t end = r.segmentEnd < requestEnd ? r.segmentEnd : requestEnd;
    if (end <= r.readBegin) {
        r.action = r.silenceFrames ? RB_TIMELINE_SILENCE : RB_TIMELINE_SKIP;
        r.skipReason = RB_TIMELINE_EMPTY_INTERSECTION;
        r.nextCursor = r.readBegin;
        r.stopAfter = r.nextCursor == requestEnd;
        *output = r;
        return RB_TIMELINE_OK;
    }
    r.readFrames = end - r.readBegin;
    r.nextCursor = end;
    r.action = RB_TIMELINE_READ;
    r.retryAtSegmentStart = r.readBegin == r.segmentStart;
    r.stopAfter = end == requestEnd;
    *output = r;
    return RB_TIMELINE_OK;

tail_silence:
    r.action = RB_TIMELINE_SILENCE;
    r.silenceFrames = requestEnd - cursor;
    r.nextCursor = requestEnd;
    r.stopAfter = 1;
    *output = r;
    return RB_TIMELINE_OK;
}

int rb_cpr_timeline_partition(double mappedStart, double mappedEnd,
                             int32_t remainingFrames, uint32_t flags,
                             RBTimelinePartition *output) {
    if (!output || !normal_or_zero(mappedStart) || !normal_or_zero(mappedEnd) ||
        mappedEnd < mappedStart || remainingFrames < 0 ||
        remainingFrames > RB_TIMELINE_MAX_FRAMES)
        return RB_TIMELINE_INVALID;
    if (!nearest_environment()) return RB_TIMELINE_FP_ENVIRONMENT;
    RBTimelinePartition r = {0};
    volatile double difference = mappedEnd - mappedStart;
    volatile double roundedLength = difference + 0.5;
    if (!isfinite(roundedLength)) return RB_TIMELINE_RANGE;
    double count = roundedLength > (double)remainingFrames
                 ? (double)remainingFrames : roundedLength;
    if (!truncate64(count, &r.frames)) return RB_TIMELINE_RANGE;
    r.silence = (flags & 4u) != 0;
    if (!r.silence) {
        volatile double roundedStart = mappedStart + (mappedStart < 0.0 ? -0.5 : 0.5);
        if (!truncate64(roundedStart, &r.startFrame) ||
            !add64(r.startFrame, r.frames, &r.endFrame))
            return RB_TIMELINE_RANGE;
    }
    *output = r;
    return RB_TIMELINE_OK;
}

int rb_cpr_timeline_read_result(int32_t requestedFrames, int64_t readBegin,
                               int64_t segmentStart, uint32_t alreadyRetried,
                               int32_t returnedFrames,
                               RBTimelineReadDecision *output) {
    if (!output || requestedFrames < 1 ||
        requestedFrames > RB_TIMELINE_MAX_FRAMES || alreadyRetried > 1)
        return RB_TIMELINE_INVALID;
    RBTimelineReadDecision r;
    if (returnedFrames == RB_TIMELINE_TRANSIENT &&
        readBegin == segmentStart && !alreadyRetried) {
        r.action = RB_TIMELINE_READ_RETRY;
        r.nativeResult = returnedFrames;
    } else if (returnedFrames == requestedFrames) {
        r.action = RB_TIMELINE_READ_COMPLETE;
        r.nativeResult = requestedFrames;
    } else {
        r.action = RB_TIMELINE_READ_FAILED;
        r.nativeResult = returnedFrames < 0 ? returnedFrames : INT32_MIN;
    }
    *output = r;
    return RB_TIMELINE_OK;
}
