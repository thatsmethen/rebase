#include "cpr_event_pcm.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24,
               "Requires IEEE binary32");

static int gain_arithmetic_ok(void) {
    if (fegetround() != FE_TONEAREST) return 0;
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr; __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    if (fpcr & ((UINT64_C(1) << 24) | UINT64_C(1))) return 0;
#elif defined(__x86_64__)
    uint32_t mxcsr; __asm__ volatile("stmxcsr %0" : "=m"(mxcsr));
    if (mxcsr & ((1u << 15) | (1u << 6))) return 0;
#else
    return 0;
#endif
    return 1;
}

int rb_cpr_event_pcm24_f32(const uint8_t *input, float *output,
                         size_t sample_count, uint32_t gain_bits) {
    float gain;
    memcpy(&gain, &gain_bits, sizeof(gain));
    /* This lower bound keeps even signed24 value 1 normal after gain. It is an
       application domain restriction, not a recovered native rejection rule. */
    if (!input || !output || sample_count == 0 || sample_count > 32000000 ||
        !isnormal(gain) || gain < FLT_MIN * 0x1p23f ||
        fegetround() != FE_TONEAREST) return 1;
    for (size_t i = 0; i < sample_count; ++i) {
        const uint8_t *p = input + i * 3;
        uint32_t packed = (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16);
        int32_t sample = (int32_t)(packed & 0x7fffff) - (int32_t)(packed & 0x800000);
        /* All signed24 integers are exactly representable in Float32. Native
           scalar kernels1003312c4/1037d88d4 use equivalent powers-of-two scales. */
        volatile float converted = (float)sample * 0x1p-23f;
        if (gain == 1.0f) output[i] = converted;
        else {
            /* Separate FMUL corresponds to the finite10018fb40 segment consumer,
               with explicit format5 output; no clipping or gain fitting. */
            volatile float result = converted * gain;
            output[i] = result;
        }
    }
    return 0;
}

int rb_cpr_event_gain_f32(float *samples, size_t count, uint32_t gain_bits) {
    float gain;
    memcpy(&gain, &gain_bits, sizeof(gain));
    if (!samples || !count || count > 32000000 ||
        !isnormal(gain) || gain <= 0 || !gain_arithmetic_ok()) return 1;
    for (size_t i = 0; i < count; ++i) {
        if (!isfinite(samples[i]) || (samples[i] != 0 && !isnormal(samples[i]))) return 1;
        volatile float result = samples[i] * gain;
        if (!isfinite(result) || (result != 0 && !isnormal(result))) return 1;
    }
    if (gain != 1.0f) {
        for (size_t i = 0; i < count; ++i) {
            volatile float result = samples[i] * gain;
            samples[i] = result;
        }
    }
    return 0;
}
