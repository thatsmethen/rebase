#ifndef REBASE_CPR_RATE_BUDGET_H
#define REBASE_CPR_RATE_BUDGET_H

#include <stdint.h>

/* Conditional count arithmetic from CPR-AUDIO-RATE-CONVERTER-001.
   No backend selection, availability detection, allocation or resampling.
   The allowance branch evaluates mode2 && first && available; the caller
   establishes those facts elsewhere. Errors leave *output unchanged. */
enum {
    RB_CPR_RATE_BUDGET_OK = 0,
    RB_CPR_RATE_BUDGET_INVALID = 1,
    RB_CPR_RATE_BUDGET_FP_ENVIRONMENT = 2,
    RB_CPR_RATE_BUDGET_RANGE = 3
};
typedef struct rb_cpr_rate_budget {
    int32_t source_frames;
    int32_t allowance_frames;
    int32_t adjusted_output_frames;
    /* Diagnostics: reference-loop decrements, not candidate loop iterations. */
    int32_t initial_source_ceiling;
    int32_t reverse_mapped_frames;
    int32_t correction_decrements;
    uint32_t search_evaluations;
    uint64_t input_ratio_bits;
    uint64_t output_ratio_bits;
    uint64_t initial_product_bits;
} rb_cpr_rate_budget;

/* Positive normal binary32 rates, Rout/Rin in [0.01,100], positive Int32
   request, all native count conversions representable, nearest-even mode.
   mode2_initial_allowance is exactly 0 or 1. Equal rates bypass allowance.
   Count zero is valid. No byte-capacity/position or backend guarantee. */
int rb_cpr_rate_read_budget(uint32_t source_rate_bits, uint32_t output_rate_bits,
                           int32_t requested_frames, int mode2_initial_allowance,
                           rb_cpr_rate_budget *output);

#endif
