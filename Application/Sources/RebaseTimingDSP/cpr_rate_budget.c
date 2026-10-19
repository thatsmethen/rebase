#include "cpr_rate_budget.h"
#include <fenv.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF

_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24,
               "Requires IEEE binary32 float");
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53,
               "Requires IEEE binary64 double");

static int positive_normal_rate(uint32_t bits) {
    uint32_t exponent = (bits >> 23) & 255u;
    return !(bits >> 31) && exponent != 0 && exponent != 255;
}

static double widened_rate(uint32_t bits) {
    float rate;
    memcpy(&rate, &bits, sizeof(rate));
    return (double)rate;
}

static uint64_t bits(double value) {
    uint64_t result;
    memcpy(&result, &value, sizeof(result));
    return result;
}

static int reverse_count(double ratio, int32_t count, int32_t *result) {
    volatile double product = ratio * (double)count;
    /* FCVTZS uses truncation, so values in [INT32_MAX,INT32_MAX+1) fit. */
    if (!isfinite(product) || product < 0.0 || product >= 2147483648.0) return 0;
    *result = (int32_t)product;
    return 1;
}

int rb_cpr_rate_read_budget(uint32_t source_rate_bits, uint32_t output_rate_bits,
                           int32_t requested_frames, int mode2_initial_allowance,
                           rb_cpr_rate_budget *output) {
    if (!output || requested_frames <= 0 ||
        (mode2_initial_allowance != 0 && mode2_initial_allowance != 1) ||
        !positive_normal_rate(source_rate_bits) || !positive_normal_rate(output_rate_bits))
        return RB_CPR_RATE_BUDGET_INVALID;
    if (fegetround() != FE_TONEAREST) return RB_CPR_RATE_BUDGET_FP_ENVIRONMENT;

    rb_cpr_rate_budget result = {0};
    result.adjusted_output_frames = requested_frames;
    /* 10030a444..448 returns the request before querying the allowance.
       Equal-path diagnostic ratios/products are exact identities, not a
       claim that native executed the otherwise skipped arithmetic. */
    if (source_rate_bits == output_rate_bits) {
        result.source_frames = requested_frames;
        result.initial_source_ceiling = requested_frames;
        result.reverse_mapped_frames = requested_frames;
        result.input_ratio_bits = bits(1.0);
        result.output_ratio_bits = bits(1.0);
        result.initial_product_bits = bits((double)requested_frames);
        *output = result;
        return RB_CPR_RATE_BUDGET_OK;
    }

    double source = widened_rate(source_rate_bits);
    double destination = widened_rate(output_rate_bits);
    volatile double output_ratio = destination / source;
    /* This domain is a deliberate application acceptance bound, not a
       claim that the original helper rejects other rate ratios. Normal
       binary32 inputs and this bound keep all FP operands normal-or-zero,
       independent of subnormal flush controls. */
    if (output_ratio < 0.01 || output_ratio > 100.0) return RB_CPR_RATE_BUDGET_RANGE;
    result.output_ratio_bits = bits(output_ratio);

    if (mode2_initial_allowance) {
        /* 100313c14..1c: FDIV, FRINTP, FCVTZU with eleven fraction bits. */
        volatile double ceiling = ceil(output_ratio);
        volatile double allowance = ceiling * 2048.0;
        if (allowance < 0.0 || allowance > INT32_MAX) return RB_CPR_RATE_BUDGET_RANGE;
        result.allowance_frames = (int32_t)allowance;
        int64_t adjusted = (int64_t)requested_frames + result.allowance_frames;
        if (adjusted > INT32_MAX) return RB_CPR_RATE_BUDGET_RANGE;
        result.adjusted_output_frames = (int32_t)adjusted;
    }

    /* 10030a470..480: separate Float64 division/product, then FCVTPS. */
    volatile double input_ratio = source / destination;
    volatile double initial_product = input_ratio * (double)result.adjusted_output_frames;
    volatile double initial_ceiling = ceil(initial_product);
    if (!isfinite(initial_ceiling) || initial_ceiling < 0.0 || initial_ceiling > INT32_MAX)
        return RB_CPR_RATE_BUDGET_RANGE;
    result.input_ratio_bits = bits(input_ratio);
    result.initial_product_bits = bits(initial_product);
    result.initial_source_ceiling = (int32_t)initial_ceiling;

    int32_t tested = result.initial_source_ceiling, mapped;
    /* Check the native first conversion before the bounded search. Every
       later candidate is smaller, so its nonnegative rounded product and
       truncation are also representable. */
    if (!reverse_count(output_ratio, tested, &mapped)) return RB_CPR_RATE_BUDGET_RANGE;
    result.search_evaluations = 1;
    if (mapped > result.adjusted_output_frames) {
        /* Native 10030a488..4a0 decrements until the first passing value.
           For positive fixed ratio, RN multiplication and truncation are
           monotone. Zero passes; tested fails. Binary search finds the same
           largest passing integer in at most 31 midpoint evaluations. This
           avoids assuming a one-decrement bound from the sampled vectors. */
        int32_t low = 0, high = tested;
        while ((int64_t)high - low > 1) {
            int32_t midpoint = low + (high - low) / 2;
            int32_t count;
            if (!reverse_count(output_ratio, midpoint, &count)) return RB_CPR_RATE_BUDGET_RANGE;
            ++result.search_evaluations;
            if (count <= result.adjusted_output_frames) low = midpoint;
            else high = midpoint;
        }
        tested = low;
        if (!reverse_count(output_ratio, tested, &mapped)) return RB_CPR_RATE_BUDGET_RANGE;
        ++result.search_evaluations;
    }
    result.source_frames = tested;
    result.reverse_mapped_frames = mapped;
    result.correction_decrements = result.initial_source_ceiling - tested;
    *output = result;
    return RB_CPR_RATE_BUDGET_OK;
}
