#ifndef REBASE_CPR_ACCESSOR_FORMAT_H
#define REBASE_CPR_ACCESSOR_FORMAT_H
#include <stddef.h>

/* Conditional packed24 intermediate stage, from 100326514..5c4 followed
   by the unity PCM24 decoder. Applies only when the generic converter has
   selected the 24-bit source-format resampling branch. No rate selection,
   resampling or claim about a live backend format is made by this API.
   In-place finite normal-or-zero Float32 values; scaled values must remain
   finite. Nearest-even arm64 FP environment. count in [1,32000000].
   Returns 0 on success, 1 invalid/domain, 2 FP environment. Error leaves
   the complete buffer unchanged. Output is exact signed24/2^23. */
int rb_cpr_accessor_pcm24_roundtrip(float *samples, size_t count);
#endif
