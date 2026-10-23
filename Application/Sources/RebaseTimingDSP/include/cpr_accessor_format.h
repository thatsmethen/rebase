#ifndef REBASE_CPR_ACCESSOR_FORMAT_H
#define REBASE_CPR_ACCESSOR_FORMAT_H
#include <stddef.h>
#include <stdint.h>

/* Conditional packed24 intermediate stage, from 100326514..5c4 followed
   by the unity PCM24 decoder. Applies only when the generic converter has
   selected the 24-bit source-format resampling branch. No rate selection,
   resampling or claim about a live backend format is made by this API.
   In-place finite normal-or-zero Float32 values; scaled values must remain
   finite. Qualified nearest/even host FP environment
   (rebase_fp_environment.h); source evidence remains arm64. count in [1,32000000].
   Returns 0 on success, 1 invalid/domain, 2 FP environment. Error leaves
   the complete buffer unchanged. Output is exact signed24/2^23. */
int rb_cpr_accessor_pcm24_roundtrip(float *samples, size_t count);

/* Destination Float32 gain stage from10032d4a4..544 and equal-rate helpers
   100333200/1037c3b34. Separate binary32 multiply, with no clipping. Gain,
   samples and results must be finite normal-or-zero; signed zero is retained.
   In-place, count in [1,32000000], same FP environment/error codes as above.
   Validate the entire buffer before writing. These bounds are app policy. */
int rb_cpr_accessor_gain_f32(float *samples, size_t count, uint32_t gain_bits);
#endif
