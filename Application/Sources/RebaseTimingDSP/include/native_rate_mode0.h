#ifndef REBASE_NATIVE_RATE_MODE0_H
#define REBASE_NATIVE_RATE_MODE0_H
#include <stddef.h>
#include <stdint.h>

/* Bounded independent reconstruction of Reference15.0.30.287 arm64 mode0
   Float32 mono/stereo UPSAMPLING only (10030ffb0 /1003101ec).
   No SoXR, anti-alias filter, final-frame padding or default-mode claim.
   All calls require FE_TONEAREST and hardware denormal flushing disabled. Rates are Float32,8k..192k,source<output.
   Samples/history must be finite normal-or-zero; nonzero subnormal outputs are rejected.
   A binary64 result rounding to Float32 zero is accepted with flushing disabled.
   Limit each request and result to16,000,000frames. State may be copied byvalue.
   No target code is linked or executed. */
typedef struct {
    double step;
    double phase;
    double previous[2];
    uint32_t source_rate_bits;
    uint32_t output_rate_bits;
    uint32_t channels;
    uint32_t reserved;
} RBMode0State;

enum { RB_MODE0_OK=0, RB_MODE0_INVALID=1, RB_MODE0_CAPACITY=2,
       RB_MODE0_SAMPLE_DOMAIN=3 };

/* Success initializesphase1,zero history; failure does not modify state. */
int rb_native_mode0_init(float source_rate,float output_rate,uint32_t channels,RBMode0State *state);
/* Keep rates/channels, resetphase/history. */
int rb_native_mode0_reset(RBMode0State *state);
/* Recurrence-exact count for thisstate; does not mutate state. */
int rb_native_mode0_count(const RBMode0State *state,size_t input_frames,size_t *produced);
/* Interleaved buffers. Input/output/state/produced storage must be disjoint.
   Failures leave state,output and produced unchanged. count0 is a successful
   no-op onstate,returnsproduced0,does notflush. No concurrent input mutation.
   Successful finalblock retains the lastframe; it emits no artificial tail. */
int rb_native_mode0_process(RBMode0State *state,const float *input,size_t input_frames,
                           float *output,size_t capacity_frames,size_t *produced);
#endif
