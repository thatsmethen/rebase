#include "native_callback_adapter.h"
#include <fenv.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
_Static_assert(sizeof(float) == 4 && FLT_MANT_DIG == 24 && FLT_RADIX == 2,
               "IEEE binary32 required");
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53,
               "IEEE binary64 required");

static int nearest_environment(void) {
    if (fegetround() != FE_TONEAREST) return 0;
#if defined(__aarch64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    /* FZ, DN and alternate handling (AH/FIZ) affect subnormal arithmetic.
       Reject instead of changing the caller's floating-point environment. */
    if (fpcr & ((UINT64_C(1) << 24) | (UINT64_C(1) << 25) | 3)) return 0;
#else
    /* This candidate is qualified for the inspected arm64 floating-point
       environment only; no uninspected FTZ/DAZ environment is admitted. */
    return 0;
#endif
    return 1;
}

static int add64(int64_t a, int64_t b, int64_t *r) {
    if ((b > 0 && a > INT64_MAX - b) ||
        (b < 0 && a < INT64_MIN - b)) return 0;
    *r = a + b;
    return 1;
}
static int subtract64(int64_t a, int64_t b, int64_t *r) {
    if ((b > 0 && a < INT64_MIN + b) ||
        (b < 0 && a > INT64_MAX + b)) return 0;
    *r = a - b;
    return 1;
}
static int range(const void *p, size_t n, uintptr_t *start, uintptr_t *end) {
    if (!p || n > UINTPTR_MAX - (uintptr_t)p) return 0;
    *start = (uintptr_t)p;
    *end = *start + n;
    return 1;
}
static int overlaps(uintptr_t a, uintptr_t b, uintptr_t c, uintptr_t d) {
    return a < d && c < b;
}
static uint32_t word(float value) {
    uint32_t u;
    memcpy(&u, &value, sizeof(u));
    return u;
}

int rb_native_callback_enabled(int callback_present, int32_t transport_result,
                               int32_t forced) {
    return callback_present != 0 &&
           (((uint32_t)transport_result & 1u) != 0 || forced != 0);
}

int rb_native_callback_offset_from_frames(int32_t offset_frames,
                                          double engine_rate, double *output) {
    if (!output || !isfinite(engine_rate) || engine_rate < 1.0)
        return RB_NATIVE_CALLBACK_INVALID;
    if (!nearest_environment()) return RB_NATIVE_CALLBACK_FP_ENVIRONMENT;
    volatile double reciprocal = 1.0 / engine_rate;
    volatile double result = (double)offset_frames * reciprocal;
    if (!isfinite(result)) return RB_NATIVE_CALLBACK_RANGE;
    *output = result;
    return RB_NATIVE_CALLBACK_OK;
}

int rb_native_callback_window(int64_t position, double offset_seconds,
                              double engine_rate, int32_t frames,
                              RBCallbackWindow *output) {
    if (!output || !isfinite(offset_seconds) || !isfinite(engine_rate) ||
        engine_rate < 1.0 || frames <= 0) return RB_NATIVE_CALLBACK_INVALID;
    if (!nearest_environment()) return RB_NATIVE_CALLBACK_FP_ENVIRONMENT;
    const double rounded = fma(offset_seconds, engine_rate, 0.5);
    /* 2^63 is exactly representable; INT64_MAX converted to double is not
       a safe inclusive upper bound. Native FCVTZS truncates toward zero. */
    if (!isfinite(rounded) || rounded < -0x1p63 || rounded >= 0x1p63)
        return RB_NATIVE_CALLBACK_RANGE;
    RBCallbackWindow result;
    if (!add64(position, (int64_t)rounded, &result.startFrame) ||
        !add64(result.startFrame, frames, &result.endFrame))
        return RB_NATIVE_CALLBACK_RANGE;
    *output = result;
    return RB_NATIVE_CALLBACK_OK;
}

int rb_native_callback_prefix(const RBCallbackWindow *window,
                              int32_t transport_result, uint8_t zero_whole_block,
                              int64_t boundary, int32_t *output) {
    if (!window || !output || zero_whole_block > 1) return RB_NATIVE_CALLBACK_INVALID;
    const RBCallbackWindow w = *window;
    int64_t frames, prefix = 0;
    if (!subtract64(w.endFrame, w.startFrame, &frames) ||
        frames < 1 || frames > INT32_MAX) return RB_NATIVE_CALLBACK_RANGE;
    if (transport_result != 0) {
        if (zero_whole_block) prefix = frames;
        else {
            if (!subtract64(boundary, w.startFrame, &prefix))
                return RB_NATIVE_CALLBACK_RANGE;
            if (prefix < 0) prefix = 0;
            if (prefix > frames) prefix = frames;
        }
    }
    *output = (int32_t)prefix;
    return RB_NATIVE_CALLBACK_OK;
}

int rb_native_callback_postprocess_f32(float *const *planes, int32_t channels,
                                       int32_t frames, int32_t capacity_frames,
                                       int32_t buffer_offset, int32_t prefix_frames,
                                       RBCallbackPostResult *output) {
    if (!planes || !output || channels < 1 || channels > 64 || frames < 1 ||
        capacity_frames < frames || buffer_offset < 0 || prefix_frames < 0 ||
        prefix_frames > frames || buffer_offset > capacity_frames - prefix_frames)
        return RB_NATIVE_CALLBACK_INVALID;
    if (!nearest_environment()) return RB_NATIVE_CALLBACK_FP_ENVIRONMENT;
    uintptr_t ps, pe, os, oe, starts[64], ends[64];
    if (!range(planes, (size_t)channels * sizeof(*planes), &ps, &pe) ||
        !range(output, sizeof(*output), &os, &oe))
        return RB_NATIVE_CALLBACK_RANGE;
    if (overlaps(ps, pe, os, oe)) return RB_NATIVE_CALLBACK_ALIAS;
    float *buffers[64];
    const size_t bytes = (size_t)capacity_frames * sizeof(float);
    for (int32_t c = 0; c < channels; ++c) {
        buffers[c] = planes[c];
        if ((uintptr_t)buffers[c] % _Alignof(float) ||
            !range(buffers[c], bytes, &starts[c], &ends[c]))
            return RB_NATIVE_CALLBACK_INVALID;
        if (overlaps(starts[c], ends[c], ps, pe) ||
            overlaps(starts[c], ends[c], os, oe))
            return RB_NATIVE_CALLBACK_ALIAS;
        for (int32_t d = 0; d < c; ++d)
            if (overlaps(starts[c], ends[c], starts[d], ends[d]))
                return RB_NATIVE_CALLBACK_ALIAS;
    }
    const uint32_t sentinel = word(buffers[0][frames - 1]);
    const uint32_t exponent = sentinel & UINT32_C(0x7f800000);
    RBCallbackPostResult result = { RB_NATIVE_CALLBACK_UNCHANGED, prefix_frames };
    if (exponent == 0 && (sentinel & UINT32_C(0x7fffffff)) != 0) {
        /* Native does not preflight other-plane nonfinite values. Exclude
           those arithmetic cases rather than claim portable NaN payloads. */
        for (int32_t c = 0; c < channels; ++c)
            for (int32_t i = 0; i < frames; ++i)
                if ((word(buffers[c][i]) & UINT32_C(0x7f800000)) ==
                    UINT32_C(0x7f800000))
                    return RB_NATIVE_CALLBACK_UNSUPPORTED_SAMPLES;
        result.action = RB_NATIVE_CALLBACK_ALTERNATING_OFFSET;
        const uint32_t bits = UINT32_C(0x2edbe6ff);
        float offset;
        memcpy(&offset, &bits, sizeof(offset));
        for (int32_t c = 0; c < channels; ++c)
            for (int32_t i = 0; i < frames; ++i) {
                volatile float value = i & 1 ? buffers[c][i] - offset :
                                             buffers[c][i] + offset;
                buffers[c][i] = value;
            }
    } else if (exponent == UINT32_C(0x7f800000)) {
        result.action = RB_NATIVE_CALLBACK_ZERO_NONFINITE_SENTINEL;
        for (int32_t c = 0; c < channels; ++c)
            memset(buffers[c], 0, (size_t)frames * sizeof(float));
    }
    if (prefix_frames)
        for (int32_t c = 0; c < channels; ++c)
            memset(buffers[c] + buffer_offset, 0, (size_t)prefix_frames * sizeof(float));
    *output = result;
    return RB_NATIVE_CALLBACK_OK;
}
