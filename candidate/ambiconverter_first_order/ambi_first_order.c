#include "ambi_first_order.h"
#include <fenv.h>
#include <float.h>
#include <limits.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
_Static_assert(CHAR_BIT == 8 && sizeof(float) == 4 && sizeof(double) == 8,
               "Requires binary32 and binary64 storage");
_Static_assert(FLT_RADIX == 2 && FLT_MANT_DIG == 24 && DBL_MANT_DIG == 53 &&
               FLT_MIN_EXP == -125 && DBL_MIN_EXP == -1021,
               "Requires IEEE binary32 and binary64");

static int validate(const ambi_input *in, size_t ni, const ambi_output *out,
                    size_t no, const ambi_options *opt, size_t size,
                    const void **src, void **dst, size_t *frames, int *reverse)
{
    if (!in || !out || ni != 4 || no != 4) return AMBI_INVALID_SHAPE;
    if (!opt || opt->direction_present != 1 || opt->bypass != 0 ||
        opt->input_silence_flags != 0) return AMBI_UNSUPPORTED_STATE;
    uint64_t p;
    memcpy(&p, &opt->direction, sizeof p);
    const uint64_t magnitude = p & UINT64_C(0x7fffffffffffffff);
    if (magnitude > UINT64_C(0x3ff0000000000000) ||
        ((p >> 63) && magnitude != 0)) return AMBI_UNSUPPORTED_STATE;
    if (fegetround() != FE_TONEAREST) return AMBI_FP_ENVIRONMENT;
    *reverse = opt->direction >= 0.5;
    *frames = in[0].frames;
    if (*frames == 0 || *frames > INT32_MAX || *frames > SIZE_MAX / size)
        return AMBI_INVALID_SHAPE;
    uintptr_t start[8], end[8];
    const size_t bytes = *frames * size;
    for (size_t c = 0; c < 4; ++c) {
        if (!in[c].samples || !out[c].samples || in[c].frames != *frames ||
            out[c].frames != *frames) return AMBI_INVALID_SHAPE;
        src[c] = in[c].samples;
        dst[c] = out[c].samples;
        start[c] = (uintptr_t)src[c];
        start[c + 4] = (uintptr_t)dst[c];
    }
    for (size_t i = 0; i < 8; ++i) {
        if (start[i] % size != 0 || start[i] > UINTPTR_MAX - bytes)
            return AMBI_INVALID_SHAPE;
        end[i] = start[i] + bytes;
        for (size_t j = 0; j < i; ++j)
            if (start[i] < end[j] && start[j] < end[i]) return AMBI_OVERLAP;
    }
    return AMBI_OK;
}

/* Tables 0x18d15c and 0x18d19c: source index -> destination index.
 * Source binary and function/constant digests are in AMBI-DSP-002. */
static const unsigned scatter[2][4] = {{0, 3, 1, 2}, {0, 2, 3, 1}};
/* Target applies destination-indexed gains after copying. For these first four
 * entries only, map[0] == 0 and every other gain == 1, so the loops below may
 * multiply while scattering. This simplification does not cover higher orders. */

int ambi_first_order_f32(const ambi_input *in, size_t ni, const ambi_output *out,
                         size_t no, const ambi_options *opt)
{
    const void *src[4]; void *dst[4]; size_t frames; int reverse;
    int result = validate(in, ni, out, no, opt, sizeof(float), src, dst,
                          &frames, &reverse);
    if (result) return result;
    /* Bit checks reject subnormals even in a flush-to-zero FP environment.
     * Accepted nonzero magnitudes [2*FLT_MIN, 1] keep products normal/finite. */
    for (size_t c = 0; c < 4; ++c)
        for (size_t n = 0; n < frames; ++n) {
            uint32_t bits;
            memcpy(&bits, (const float *)src[c] + n, sizeof bits);
            bits &= UINT32_C(0x7fffffff);
            if (bits && (bits < UINT32_C(0x01000000) ||
                         bits > UINT32_C(0x3f800000))) return AMBI_SAMPLE_DOMAIN;
        }
    /* FCVT S,D at 0x154d98 narrows the stored binary64 gain before multiply. */
    const uint32_t bits = reverse ? UINT32_C(0x3f3504f3) : UINT32_C(0x3fb504f3);
    float gain;
    memcpy(&gain, &bits, sizeof gain);
    for (size_t c = 0; c < 4; ++c) {
        const float *input = src[c];
        float *output = dst[scatter[reverse][c]];
        const float scalar = c == 0 ? gain : 1.0f;
        for (size_t n = 0; n < frames; ++n) output[n] = input[n] * scalar;
    }
    return AMBI_OK;
}

int ambi_first_order_f64(const ambi_input *in, size_t ni, const ambi_output *out,
                         size_t no, const ambi_options *opt)
{
    const void *src[4]; void *dst[4]; size_t frames; int reverse;
    int result = validate(in, ni, out, no, opt, sizeof(double), src, dst,
                          &frames, &reverse);
    if (result) return result;
    for (size_t c = 0; c < 4; ++c)
        for (size_t n = 0; n < frames; ++n) {
            uint64_t bits;
            memcpy(&bits, (const double *)src[c] + n, sizeof bits);
            bits &= UINT64_C(0x7fffffffffffffff);
            if (bits && (bits < UINT64_C(0x0020000000000000) ||
                         bits > UINT64_C(0x3ff0000000000000))) return AMBI_SAMPLE_DOMAIN;
        }
    /* Exact bytes at 0x18d1e0 / 0x18d260. Reverse is not sqrt(0.5). */
    const uint64_t bits = reverse ? UINT64_C(0x3fe6a09e667f3bcc)
                                  : UINT64_C(0x3ff6a09e667f3bcd);
    double gain;
    memcpy(&gain, &bits, sizeof gain);
    for (size_t c = 0; c < 4; ++c) {
        const double *input = src[c];
        double *output = dst[scatter[reverse][c]];
        const double scalar = c == 0 ? gain : 1.0;
        for (size_t n = 0; n < frames; ++n) output[n] = input[n] * scalar;
    }
    return AMBI_OK;
}
