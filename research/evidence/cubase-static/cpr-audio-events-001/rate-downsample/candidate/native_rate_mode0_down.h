#ifndef REBASE_NATIVE_RATE_MODE0_DOWN_H
#define REBASE_NATIVE_RATE_MODE0_DOWN_H
#include <stddef.h>
#include <stdint.h>

/* Static-derived mode0 Float32 mono/stereo equal/downsample arithmetic only.
   Rates Float32: 8000 <= output <= source <= 192000; nearest-even, no FTZ/FIZ.
   No target execution, anti-alias filter, default-backend or live-host claim.
   history is binary64: a queued interpolation need not be Float32-exact.
   Normal-or-zero finite Float32 samples; nonzero subnormal output rejected.
   Individual inputs/results and aggregate result are bounded to16m frames. */
typedef struct {
    double step, phase, history[2];
    uint32_t source_rate_bits, output_rate_bits, channels, pending;
} RBMode0DownState;
enum { RB_MODE0_DOWN_OK=0, RB_MODE0_DOWN_INVALID=1,
       RB_MODE0_DOWN_CAPACITY=2, RB_MODE0_DOWN_SAMPLE_DOMAIN=3,
       RB_MODE0_DOWN_LOOKAHEAD=4 };
enum { RB_MODE0_DOWN_OUTPUT_BELOW=0, RB_MODE0_DOWN_OUTPUT_ABOVE=1 };
/* Output must be wholly disjoint and below/above the input as declared.
   BELOW models the native rare-tail sample/count but does not invoke its
   external diagnostic helpers; their side effects are outside this contract.
   The application selects ABOVE, making that diagnostic branch unreachable. */
int rb_native_mode0_down_init(float source_rate,float output_rate,uint32_t channels,RBMode0DownState *state);
int rb_native_mode0_down_reset(RBMode0DownState *state);
/* All failures preserve caller state, output and count. flush must be0/1;
   it is ignored, as in these complete native branches. Zero input never flushes.
   LOOKAHEAD rejects the native single-frame pending path that would read the
   next frame outside the supplied logical input. No padding is manufactured. */
int rb_native_mode0_down_count(const RBMode0DownState *state,size_t input_frames,uint32_t layout,uint32_t flush,size_t *produced);
int rb_native_mode0_down_process(RBMode0DownState *state,const float *input,size_t input_frames,float *output,size_t capacity_frames,uint32_t layout,uint32_t flush,size_t *produced);
/* Aggregate predictor uses exactly this application partition policy:
   limit>=3; if remaining==limit+1 take limit-1, else min(remaining,limit).
   No caller state changes or fabricated sample history; subsequent processing
   must use the same partitioning. Partition invariance is NOT asserted. */
size_t rb_native_mode0_down_next_block(size_t remaining,size_t limit);
int rb_native_mode0_down_count_blocks(const RBMode0DownState *state,size_t total_input_frames,size_t input_block_frames,uint32_t layout,size_t *produced);
#endif
