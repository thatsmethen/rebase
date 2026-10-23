#ifndef REBASE_CPR_TRACK_OVERLAP_H
#define REBASE_CPR_TRACK_OVERLAP_H
#include <stdint.h>

/* Authored value reconstruction of the static range normalizer 10020e7c8.
   Coordinates are canonical seconds, before builder snapping. Input is already
   chronological; no source sorting or native object callbacks are inferred.
   Higher signed priority wins; equal priorities favor the higher immutable
   collector ordinal. Each split retains its original source index/ordinal.
   The exact epsilon is binary64 0x3f1a36e2eb1c432d. */
typedef struct {
    int32_t sourceIndex;
    int32_t ordinal;
    int32_t priority;
    double start;
    double end;
} RBTrackOverlapRange;

enum {
    RB_TRACK_OVERLAP_OK = 0,
    RB_TRACK_OVERLAP_INVALID = 1,
    RB_TRACK_OVERLAP_FP_ENVIRONMENT = 2,
    RB_TRACK_OVERLAP_LIMIT = 3,
    RB_TRACK_OVERLAP_ALLOCATION = 4
};
enum { RB_TRACK_OVERLAP_MAX_INPUTS = 4096, RB_TRACK_OVERLAP_MAX_OUTPUTS = 8192 };

/* Source indices equal their input positions; ordinals are distinct and >=0.
   Inputs are finite normal-or-zero coordinates 0<=start<end<=86400. Native
   nearest/even FP mode with FZ/DN/AH/FIZ disabled is required. Output is a
   positive disjoint sequence. The application work bound is 4*N*N+N comparison
   visits; exhaustion rejects the entire operation. Output/count are untouched
   on failure. No target code, media, lifecycle or fade processing runs here. */
int rb_cpr_track_overlap_normalize(const RBTrackOverlapRange *source, int32_t count,
    RBTrackOverlapRange *output, int32_t capacity, int32_t *outputCount);
#endif
