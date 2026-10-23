#ifndef REBASE_CPR_TIMELINE_READER_H
#define REBASE_CPR_TIMELINE_READER_H
#include <stdint.h>

/* Bounded value reconstruction of Cubase 15.0.30.287 arm64:
   101d3eb24 segment/read planning and 101d3e704 mapped-window rounding.
   These helpers do not select a provider, execute reads, infer coordinate
   units, expand loop/mapping state or modify sample buffers.

   The caller supplies the actual datum period. The native multiplier is
   Double(Float32(RN64(1 / period))). Coordinates are the concrete getter
   results; obtain segment.end with separately rounded start+length when
   reconstructing PAudioSegment. This is not generic seconds*sampleRate.

   Positive normal period; finite normal-or-zero coordinates; arm64 IEEE
   nearest with FZ/DN/AH/FIZ off. Native saturation/wrap and request spans over
   16,000,000 frames reject. No change to output on error. Validation is
   deliberately stricter than native; native sample writes are not transactional.
   Input/output structure storage must be disjoint. */
enum {
    RB_TIMELINE_OK = 0,
    RB_TIMELINE_INVALID = 1,
    RB_TIMELINE_RANGE = 2,
    RB_TIMELINE_FP_ENVIRONMENT = 3
};
enum {
    RB_TIMELINE_DONE = 0,
    RB_TIMELINE_SKIP = 1,
    RB_TIMELINE_READ = 2,
    RB_TIMELINE_SILENCE = 3
};
enum {
    RB_TIMELINE_NO_SKIP = 0,
    RB_TIMELINE_INVALID_SEGMENT = 1,
    RB_TIMELINE_BEFORE_REQUEST = 2,
    RB_TIMELINE_EMPTY_INTERSECTION = 3
};

typedef struct {
    double start;
    double end;
    double sourceOffset;
} RBTimelineSegment;

typedef struct {
    int32_t action;
    int32_t skipReason;
    uint32_t quantizedFields; /* bit0 start, bit1 end, bit2 source offset */
    uint32_t stopAfter;       /* remainder filled, or nextCursor==requestEnd */
    int64_t segmentStart;
    int64_t segmentEnd;
    int64_t segmentOffset;
    int64_t silenceOffset;   /* relative to original requestStart */
    int64_t silenceFrames;
    int64_t readOffset;      /* relative to original requestStart */
    int64_t readBegin;
    int64_t readFrames;
    int64_t sourceSeek;
    int64_t nextCursor;
    uint32_t retryAtSegmentStart;
} RBTimelinePlan;

int rb_cpr_timeline_quantize(double period, double coordinate, int64_t *output);

/* cursor is within [requestStart,requestEnd]. NULL segment represents a
   selector returning null. SKIP leaves cursor unchanged so the caller must
   advance its native-style selector separately. A prefix ending exactly at
   requestEnd has an empty segment intersection and returns SILENCE with
   stopAfter=1.
   A READ's nextCursor applies after a full successful read; errors do not
   authorize cursor advancement. Missing/unready native accessors instead
   zero the planned read span; accessor readiness is outside this helper. */
int rb_cpr_timeline_plan(int64_t requestStart, int64_t requestEnd,
                        int64_t cursor, double period,
                        const RBTimelineSegment *segment,
                        RBTimelinePlan *output);

typedef struct {
    int64_t startFrame;
    int64_t endFrame;
    int64_t frames;
    uint32_t silence; /* mapped flags bit2; no underlying read */
} RBTimelinePartition;

/* One already-produced mapping entry: signed ±0.5 start rounding, then
   separately rounded (mappedEnd-mappedStart)+0.5, capped to remainingFrames.
   This does not create entries or establish their semantic origin. */
int rb_cpr_timeline_partition(double mappedStart, double mappedEnd,
                             int32_t remainingFrames, uint32_t flags,
                             RBTimelinePartition *output);

enum {
    RB_TIMELINE_READ_COMPLETE = 0,
    RB_TIMELINE_READ_RETRY = 1,
    RB_TIMELINE_READ_FAILED = 2
};
typedef struct {
    int32_t action;
    int32_t nativeResult; /* full count, retry code, or native error */
} RBTimelineReadDecision;

/* Exactly one retry for -2147483645 at the quantized segment start.
   Retry repeats read with the same request/buffer; it does not repeat seek.
   Other negative errors propagate; nonnegative short/overlong read maps
   to INT32_MIN. No interpretation of the error number's name is asserted. */
int rb_cpr_timeline_read_result(int32_t requestedFrames, int64_t readBegin,
                               int64_t segmentStart, uint32_t alreadyRetried,
                               int32_t returnedFrames,
                               RBTimelineReadDecision *output);
#endif
