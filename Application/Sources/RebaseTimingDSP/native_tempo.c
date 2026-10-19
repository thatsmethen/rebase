#include "native_tempo.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF

_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24,
               "Requires IEEE binary32 float");
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53,
               "Requires IEEE binary64 double");

static int represented(double value) {
    return isfinite(value) && (value == 0.0 || isnormal(value));
}

static int period(uint32_t bpm_bits, float *output) {
    if (fegetround() != FE_TONEAREST) return RB_NATIVE_TEMPO_FP_ENVIRONMENT;
    float bpm;
    memcpy(&bpm, &bpm_bits, sizeof(bpm));
    if (!isfinite(bpm) || bpm < 20.0f || bpm > 400.0f) return RB_NATIVE_TEMPO_INVALID;
    volatile float result = 60.0f / bpm;
    *output = result;
    return RB_NATIVE_TEMPO_OK;
}

int rb_native_fixed_period(uint32_t bpm_bits, uint32_t *period_bits) {
    if (!period_bits) return RB_NATIVE_TEMPO_INVALID;
    float value;
    int status = period(bpm_bits, &value);
    if (status != RB_NATIVE_TEMPO_OK) return status;
    memcpy(period_bits, &value, sizeof(value));
    return RB_NATIVE_TEMPO_OK;
}

int rb_native_fixed_seconds(uint32_t bpm_bits, double tick, double *seconds) {
    if (!seconds || tick < 0.0 || !represented(tick)) return RB_NATIVE_TEMPO_INVALID;
    float value;
    int status = period(bpm_bits, &value);
    if (status != RB_NATIVE_TEMPO_OK) return status;
    volatile double wide_period = (double)value;
    volatile double product = wide_period * tick;
    volatile double result = product / 480.0;
    if (!represented(product) || !represented(result) || (tick != 0.0 && result == 0.0))
        return RB_NATIVE_TEMPO_UNREPRESENTABLE;
    *seconds = result;
    return RB_NATIVE_TEMPO_OK;
}

int rb_native_fixed_ticks(uint32_t bpm_bits, double seconds, double *tick) {
    if (!tick || seconds < 0.0 || !represented(seconds)) return RB_NATIVE_TEMPO_INVALID;
    float value;
    int status = period(bpm_bits, &value);
    if (status != RB_NATIVE_TEMPO_OK) return status;
    volatile double wide_period = (double)value;
    volatile double quotient = seconds / wide_period;
    volatile double result = quotient * 480.0;
    if (!represented(quotient) || !represented(result) || (seconds != 0.0 && result == 0.0))
        return RB_NATIVE_TEMPO_UNREPRESENTABLE;
    *tick = result;
    return RB_NATIVE_TEMPO_OK;
}

/* New map contract only; the fixed-clock functions above are unchanged.
   Native instruction authority: 10173ad50/10173b1d4, cache10173b4cc,
   search10173b064 and iterator1016c1424. See the retained map-clock oracle. */
static double map_period(uint32_t bits) {
    float value;
    memcpy(&value, &bits, sizeof(value));
    return (double)value;
}

static int map_coordinate(double value, double maximum) {
    return represented(value) && value >= 0.0 && value <= maximum;
}

static int map_shape(const rb_native_jump_point *points, uint32_t count) {
    if (!points || (count != 1 && count != 2)) return RB_NATIVE_TEMPO_INVALID;
    if (fegetround() != FE_TONEAREST) return RB_NATIVE_TEMPO_FP_ENVIRONMENT;
    for (uint32_t i = 0; i < count; ++i) {
        float value;
        memcpy(&value, &points[i].period_bits, sizeof(value));
        if (!isnormal(value) || value <= 0.0f ||
            !map_coordinate(points[i].seconds, RB_NATIVE_MAP_MAX_SECONDS) ||
            !map_coordinate(points[i].ticks, RB_NATIVE_MAP_MAX_TICKS))
            return RB_NATIVE_TEMPO_INVALID;
    }
    if (points[0].seconds != 0.0 || signbit(points[0].seconds) ||
        points[0].ticks != 0.0 || signbit(points[0].ticks))
        return RB_NATIVE_TEMPO_INVALID;
    if (count == 2 && (points[1].seconds <= points[0].seconds ||
                       points[1].ticks <= points[0].ticks))
        return RB_NATIVE_TEMPO_INVALID;
    return RB_NATIVE_TEMPO_OK;
}

int rb_native_map_validate(const rb_native_jump_point *points, uint32_t count) {
    int status = map_shape(points, count);
    if (status != RB_NATIVE_TEMPO_OK || count == 1) return status;
    /* 10173b5e8..5fc -> b588..59c: distinct SUB,MUL,DIV,ADD. */
    volatile double delta = points[1].ticks - points[0].ticks;
    volatile double product = delta * map_period(points[0].period_bits);
    volatile double scaled = product / 480.0;
    volatile double expected = points[0].seconds + scaled;
    if (!represented(product) || !represented(scaled) ||
        !map_coordinate(expected, RB_NATIVE_MAP_MAX_SECONDS) || product == 0.0 || scaled == 0.0)
        return RB_NATIVE_TEMPO_UNREPRESENTABLE;
    uint64_t expected_bits, actual_bits;
    double value = expected;
    memcpy(&expected_bits, &value, sizeof(value));
    memcpy(&actual_bits, &points[1].seconds, sizeof(points[1].seconds));
    return expected_bits == actual_bits ? RB_NATIVE_TEMPO_OK : RB_NATIVE_TEMPO_INVALID;
}

/* Internal pure operations are also exercised directly by the retained
   optimized oracle harness. Its out-of-public-domain quantizer controls do
   not expand the public API limits. Explicit fma is intentional despite
   FP_CONTRACT OFF: native uses FMADD at both sites. */
static double map_raw_tick(double quotient, double anchor) {
    return fma(quotient, 480.0, anchor);
}

static double map_quantize(double raw) {
    volatile double shifted = fma(raw, 1000.0, 0.5);
    volatile double floored = floor(shifted);
    volatile double result = floored / 1000.0;
    return result;
}

int rb_native_map_seconds(const rb_native_jump_point *points, uint32_t count,
                          double tick, double *seconds) {
    if (!seconds || !map_coordinate(tick, RB_NATIVE_MAP_MAX_TICKS))
        return RB_NATIVE_TEMPO_INVALID;
    int status = map_shape(points, count);
    if (status != RB_NATIVE_TEMPO_OK) return status;
    /* Count2 inverse uses the new item at equality; next/current consume it. */
    uint32_t index = count == 2 && tick >= points[1].ticks ? 1 : 0;
    rb_native_jump_point point = points[index];
    volatile double delta = tick - point.ticks;
    volatile double product = delta * map_period(point.period_bits);
    volatile double scaled = product / 480.0;
    volatile double result = point.seconds + scaled;
    if (!represented(delta) || !represented(product) || !represented(scaled) ||
        !map_coordinate(result, RB_NATIVE_MAP_MAX_SECONDS) ||
        (delta != 0.0 && (product == 0.0 || scaled == 0.0)))
        return RB_NATIVE_TEMPO_UNREPRESENTABLE;
    *seconds = result;
    return RB_NATIVE_TEMPO_OK;
}

int rb_native_map_ticks(const rb_native_jump_point *points, uint32_t count,
                       double seconds, double *tick) {
    if (!tick || !map_coordinate(seconds, RB_NATIVE_MAP_MAX_SECONDS))
        return RB_NATIVE_TEMPO_INVALID;
    int status = map_shape(points, count);
    if (status != RB_NATIVE_TEMPO_OK) return status;
    /* Zero bypasses positive-map quantization, preserving its input sign. */
    if (seconds == 0.0) {
        volatile double quotient = seconds / map_period(points[0].period_bits);
        volatile double result = quotient * 480.0;
        *tick = result;
        return RB_NATIVE_TEMPO_OK;
    }
    /* Count2 forward retains the previous item at exact seconds equality. */
    uint32_t index = count == 2 && seconds > points[1].seconds ? 1 : 0;
    rb_native_jump_point point = points[index];
    volatile double delta = seconds - point.seconds;
    volatile double quotient = delta / map_period(point.period_bits);
    volatile double raw = map_raw_tick(quotient, point.ticks);
    if (!represented(delta) || !represented(quotient) ||
        !map_coordinate(raw, RB_NATIVE_MAP_MAX_TICKS) ||
        (delta != 0.0 && quotient == 0.0))
        return RB_NATIVE_TEMPO_UNREPRESENTABLE;
    volatile double result = map_quantize(raw);
    if (!map_coordinate(result, RB_NATIVE_MAP_MAX_TICKS))
        return RB_NATIVE_TEMPO_UNREPRESENTABLE;
    *tick = result;
    return RB_NATIVE_TEMPO_OK;
}
