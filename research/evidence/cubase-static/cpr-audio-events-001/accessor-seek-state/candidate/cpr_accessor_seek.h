#ifndef REBASE_CPR_ACCESSOR_SEEK_H
#define REBASE_CPR_ACCESSOR_SEEK_H
#include <stdint.h>

typedef struct {
    int64_t sourceFrame;
    int64_t returnedOutputFrame;
    uint32_t sourcePerOutputBits;
    uint64_t sourceProductBits;
    uint64_t outputQuotientBits;
} RBAccessorSeek;

/* 10036f89c fixed-rate mapping. It changes a source cursor, not converter
   state: native seek does not reset or preroll. Supplied positive integral
   binary32 rates in [8000,192000], outputFrame in [0,2^53]. Equal rates
   bypass floating-point conversion. Error leaves output unchanged.
   Returns 0 success, 1 invalid, 2 FP environment, 3 arithmetic range. */
int rb_cpr_accessor_seek(uint32_t sourceRateBits, uint32_t outputRateBits,
                         int64_t outputFrame, RBAccessorSeek *output);
#endif
