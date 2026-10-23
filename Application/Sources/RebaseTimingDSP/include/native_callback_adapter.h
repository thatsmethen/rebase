#ifndef REBASE_NATIVE_CALLBACK_ADAPTER_H
#define REBASE_NATIVE_CALLBACK_ADAPTER_H
#include <stdint.h>

/* Bounded value operations from VstOpTrack 101f2c440 and its Float32
   adapter. These are not a native scheduler, seek policy, engine lifecycle
   or device-output claim. The caller supplies established transport state.
   All failures preserve output structs and sample storage. Floating-point
   operations require the explicitly checked ARM64 or x86-64 environment in
   rebase_fp_environment.h. Unsupported environments fail closed. This host
   portability does not establish proprietary Windows target equivalence. */
enum {
    RB_NATIVE_CALLBACK_OK = 0,
    RB_NATIVE_CALLBACK_INVALID = 1,
    RB_NATIVE_CALLBACK_RANGE = 2,
    RB_NATIVE_CALLBACK_ALIAS = 3,
    RB_NATIVE_CALLBACK_FP_ENVIRONMENT = 4,
    RB_NATIVE_CALLBACK_UNSUPPORTED_SAMPLES = 5
};
enum {
    RB_NATIVE_CALLBACK_UNCHANGED = 0,
    RB_NATIVE_CALLBACK_ALTERNATING_OFFSET = 1,
    RB_NATIVE_CALLBACK_ZERO_NONFINITE_SENTINEL = 2
};
typedef struct RBCallbackWindow {
    int64_t startFrame;
    int64_t endFrame;
} RBCallbackWindow;
typedef struct RBCallbackPostResult {
    int32_t action;
    int32_t prefixFrames;
} RBCallbackPostResult;

/* Native admission uses transport_result bit 0, while later prefix
   processing tests the complete result for nonzero. */
int rb_native_callback_enabled(int callback_present, int32_t transport_result,
                               int32_t forced);

/* 101f17eb8: RN64(Double(offset_frames) * RN64(1/rate)).
   Positive finite rate >=1; IEEE nearest. No extra integral rounding. */
int rb_native_callback_offset_from_frames(int32_t offset_frames,
                                          double engine_rate, double *output);

/* 101f2c4dc..4f8: offset = truncSigned64(fma(offset_seconds,rate,0.5));
   start=position+offset; end=start+frames. Positive frames only.
   Rejects conversion/add overflow rather than reproducing saturation/wrap.
   The application must not invent a native latency or transport position. */
int rb_native_callback_window(int64_t position, double offset_seconds,
                              double engine_rate, int32_t frames,
                              RBCallbackWindow *output);

/* 101f2c628..69c: transport_result==0 ->0; otherwise whole-block or
   clamp(boundary-start,0,frames). Requires end-start in 1...INT32_MAX.
   Arithmetic overflow is rejected. */
int rb_native_callback_prefix(const RBCallbackWindow *window,
                              int32_t transport_result, uint8_t zero_whole_block,
                              int64_t boundary, int32_t *output);

/* Successful Float32 callback only. 1...64 disjoint channel planes, each
   capacity_frames floats, frames in 1...capacity_frames. Inspect ONLY
   planes[0][frames-1] before any writes:
   - nonzero subnormal: every plane alternately adds/subtracts Float32
     bits 0x2edbe6ff, starting with addition at index0;
   - exponent all ones: zero every plane's first frames samples;
   - otherwise: retain bits (including signed zero and other-plane NaNs).
   Then zero prefix_frames samples starting at buffer_offset on EVERY
   plane, after the action above. prefix_frames must be in 0...frames.
   The prefix range must fit capacity_frames.
   Correction arithmetic requires every affected sample finite; other
   branches are bit operations and permit arbitrary Float32 words.
   Qualified nearest/even gradual-underflow host arithmetic is required.
   Rebase's buffer partition and choice of prefix0 remain application
   policy; applying this helper does not recover native block partitions. */
int rb_native_callback_postprocess_f32(float *const *planes, int32_t channels,
                                       int32_t frames, int32_t capacity_frames,
                                       int32_t buffer_offset, int32_t prefix_frames,
                                       RBCallbackPostResult *output);
#endif
