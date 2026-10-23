#include "cpr_accessor_seek.h"
#include "rebase_fp_environment.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
_Static_assert(FLT_RADIX == 2 && FLT_MANT_DIG == 24 && DBL_MANT_DIG == 53,
               "IEEE binary32/binary64 required");
static int environment_ok(void) { return rb_fp_nearest_gradual(); }
static uint64_t bits(double x) { uint64_t result; memcpy(&result,&x,8); return result; }
static int rate_ok(float x) { return isfinite(x) && x >= 8000 && x <= 192000 && truncf(x) == x; }

int rb_cpr_accessor_seek(uint32_t sourceRateBits, uint32_t outputRateBits,
                         int64_t outputFrame, RBAccessorSeek *output) {
    float source, destination;
    memcpy(&source,&sourceRateBits,4); memcpy(&destination,&outputRateBits,4);
    if (!output || !rate_ok(source) || !rate_ok(destination) ||
        outputFrame < 0 || outputFrame > INT64_C(9007199254740992)) return 1;
    if (!environment_ok()) return 2;
    RBAccessorSeek result = {0};
    if (source == destination) {
        result.sourceFrame = outputFrame;
        result.returnedOutputFrame = outputFrame;
        result.sourcePerOutputBits = UINT32_C(0x3f800000);
        result.sourceProductBits = bits((double)outputFrame);
        result.outputQuotientBits = result.sourceProductBits;
    } else {
        volatile float ratio = source / destination;
        float ratioCopy = ratio;
        memcpy(&result.sourcePerOutputBits,&ratioCopy,4);
        volatile double product = (double)outputFrame * (double)ratio;
        if (!isfinite(product) || product < 0.0 || product >= 0x1p63) return 3;
        result.sourceProductBits = bits(product);
        result.sourceFrame = (int64_t)product;
        volatile double quotient = (double)result.sourceFrame / (double)ratio;
        if (!isfinite(quotient) || quotient < 0.0 || quotient >= 0x1p63) return 3;
        result.outputQuotientBits = bits(quotient);
        result.returnedOutputFrame = (int64_t)quotient;
    }
    *output = result;
    return 0;
}
