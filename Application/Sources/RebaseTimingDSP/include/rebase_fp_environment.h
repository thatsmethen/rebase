#ifndef REBASE_FP_ENVIRONMENT_H
#define REBASE_FP_ENVIRONMENT_H

#include <fenv.h>
#include <float.h>
#include <stdint.h>
#if defined(__x86_64__) || defined(_M_X64)
#include <xmmintrin.h>
#endif

/* Qualification for the authored binary32/binary64 value reconstructions.
   This admits a host arithmetic environment, not another proprietary target.
   Typed operations must have their declared precision (no x87 excess
   precision), nearest/even rounding, gradual underflow, and masked traps.
   Read only: never repair the caller's floating-point environment.

   ARM64 retains the original FZ/DN/AH/FIZ exclusions. Its explicit rounding
   and exception checks also prevent mismatched fenv state and enabled traps.
   x86-64 uses SSE2 binary32/binary64; check MXCSR directly as well as fenv,
   since some CRTs report the x87 rounding state independently of MXCSR.
   x86 has no ARM default-NaN or alternate-handling mode. */
static inline int rb_fp_nearest_gradual(void) {
    if (FLT_EVAL_METHOD != 0 || fegetround() != FE_TONEAREST) return 0;
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    const uint64_t modes = (UINT64_C(1) << 24) | (UINT64_C(1) << 25) |
        (UINT64_C(3) << 22) | UINT64_C(3);
    const uint64_t traps = (UINT64_C(31) << 8) | (UINT64_C(1) << 15);
    return (fpcr & (modes | traps)) == 0;
#elif defined(__x86_64__) || defined(_M_X64)
    const uint32_t mxcsr = (uint32_t)_mm_getcsr();
    const uint32_t modes = (UINT32_C(1) << 15) | (UINT32_C(1) << 6) |
        (UINT32_C(3) << 13); /* FTZ, DAZ and rounding control. */
    const uint32_t masks = UINT32_C(0x1f80); /* All six SSE exceptions masked. */
    return (mxcsr & modes) == 0 && (mxcsr & masks) == masks;
#else
    return 0;
#endif
}
#endif
