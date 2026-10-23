#ifndef REBASE_CPR_LIVE_STEREO_RING_H
#define REBASE_CPR_LIVE_STEREO_RING_H
#include <stdint.h>

/* Bounded value operations derived from VSTAudioStreamPlayer
   100384ac4 / 100384638. This is not a native engine, thread scheduler,
   MAudioTrack route, resampler or device-output equivalence claim.
   Caller owns two disjoint arrays of exactly 32768 floats and serializes
   access. Native blocking/polling is replaced by atomic WOULD_BLOCK.
   All errors preserve state, storage, output and result. */
enum {
    RB_CPR_LIVE_RING_CAPACITY = 32768,
    RB_CPR_LIVE_RING_OK = 0,
    RB_CPR_LIVE_RING_INVALID = 1,
    RB_CPR_LIVE_RING_RANGE = 2,
    RB_CPR_LIVE_RING_ALIAS = 3,
    RB_CPR_LIVE_RING_WOULD_BLOCK = 4
};

typedef struct rb_cpr_live_stereo_ring {
    float *left;
    float *right;
    int32_t write_index;
    int32_t read_index;
    int64_t submitted_frames;
    int64_t timeline_frames;
} rb_cpr_live_stereo_ring;

typedef struct rb_cpr_live_ring_result {
    int32_t copied_frames;
    int32_t silent_frames;
    int64_t timeline_frames;
} rb_cpr_live_ring_result;

/* Initialize/reset indices and counters to zero, without clearing PCM
   storage (native open does not clear freshly allocated sample arrays).
   Reset represents fresh stream state; it is not a native seek policy. */
int rb_cpr_live_ring_init(rb_cpr_live_stereo_ring *state, float *left, float *right);
int rb_cpr_live_ring_reset(rb_cpr_live_stereo_ring *state);

/* Active, non-stopped producer only. 0...32768 frames. Whole request must
   fit the native per-frame half-capacity space guard:
   frames <= free - 16384 + 1. Zero frames is a validated no-op.
   Interleaved L,R -> two rings, exact four-byte copies. No gain or clipping. */
int rb_cpr_live_ring_write(rb_cpr_live_stereo_ring *state,
                          const float *interleaved, int32_t frames);

/* Two output channels only. frames=end-start must be 0...32768; absolute
   start is not used to seek (the native callback only uses the difference).
   Flags must be 0/1. Stopped: zero entire block, advance timeline, retain
   read index. Normal underrun: zero block and hold indices/timeline.
   Draining underrun: copy available prefix, zero suffix, advance timeline
   by requested frames. Sufficient data: copy all and advance normally.
   Output arrays each hold frames floats and cannot alias any input/state.
   Zero-length output pointers may be null. Sample bits, including signed
   zero, are copied without floating arithmetic. */
int rb_cpr_live_ring_consume(rb_cpr_live_stereo_ring *state,
                            float *left_output, float *right_output,
                            int64_t start, int64_t end,
                            uint8_t stopped, uint8_t drain,
                            rb_cpr_live_ring_result *result);
#endif
