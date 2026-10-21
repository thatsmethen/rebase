#include "cpr_accessor_format.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24,
               "IEEE binary32 required");

static int nearest_environment(void) {
    if (fegetround() != FE_TONEAREST) return 0;
#if defined(__aarch64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    return (fpcr & ((UINT64_C(1) << 24) | (UINT64_C(1) << 25) | 3)) == 0;
#else
    return 0;
#endif
}

static int32_t packed24(float scaled) {
    /* Original comparisons precede FCVTZS, so no out-of-range integer
       conversion occurs. Saturation is asymmetric by one signed24 unit. */
    if (scaled >= 8388607.0f) return 8388607;
    if (scaled < -8388608.0f) return -8388608;
    int32_t integer = (int32_t)scaled;
    volatile double remainder = (double)scaled - (double)integer;
    double absolute = remainder < 0.0 ? -remainder : remainder;
    if (absolute > 0.5 || (absolute == 0.5 && (integer & 1)))
        integer += scaled < 0.0f ? -1 : 1;
    return integer;
}

int rb_cpr_accessor_pcm24_roundtrip(float *samples, size_t count) {
    if (!samples || count == 0 || count > 32000000) return 1;
    if (!nearest_environment()) return 2;
    for (size_t i = 0; i < count; ++i) {
        if (!isfinite(samples[i]) || (samples[i] != 0.0f && !isnormal(samples[i])))
            return 1;
        volatile float scaled = samples[i] * 0x1p23f;
        if (!isfinite(scaled) || (scaled != 0.0f && !isnormal(scaled))) return 1;
    }
    for (size_t i = 0; i < count; ++i) {
        volatile float scaled = samples[i] * 0x1p23f;
        int32_t integer = packed24(scaled);
        volatile float decoded = (float)integer * 0x1p-23f;
        samples[i] = decoded;
    }
    return 0;
}

int rb_cpr_accessor_gain_f32(float *samples, size_t count, uint32_t gain_bits) {
    float gain;
    memcpy(&gain, &gain_bits, sizeof(gain));
    if (!samples || count == 0 || count > 32000000 ||
        !isfinite(gain) || (gain != 0.0f && !isnormal(gain))) return 1;
    if (!nearest_environment()) return 2;
    for (size_t i = 0; i < count; ++i) {
        if (!isfinite(samples[i]) || (samples[i] != 0.0f && !isnormal(samples[i])))
            return 1;
        volatile float result = samples[i] * gain;
        if (!isfinite(result) || (result != 0.0f && !isnormal(result))) return 1;
    }
    if (gain != 1.0f) {
        for (size_t i = 0; i < count; ++i) {
            volatile float result = samples[i] * gain;
            samples[i] = result;
        }
    }
    return 0;
}
