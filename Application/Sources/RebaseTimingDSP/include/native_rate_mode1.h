#ifndef REBASE_NATIVE_RATE_MODE1_H
#define REBASE_NATIVE_RATE_MODE1_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Static reconstruction of the native mode1 Float32 packet/filter branch.
   Coefficients use the traced binary64 arithmetic plus the host C sin/sqrt
   implementation. This does not establish Reference runtime/library equivalence. */
typedef struct RBMode1 RBMode1;
enum {
    RB_MODE1_OK=0, RB_MODE1_INVALID=1, RB_MODE1_CAPACITY=2,
    RB_MODE1_SAMPLE_DOMAIN=3, RB_MODE1_STATE=4, RB_MODE1_ALLOCATION=5,
    RB_MODE1_NATIVE_BOUNDS=6
};
typedef struct {
    double ratio, step, phase;
    uint64_t cumulative_input, cumulative_generated, total_returned;
    uint32_t channels, input_capacity, fresh, finished;
} RBMode1Snapshot;

/* Integral rates [8000,192000], mono/stereo, nearest-even with FTZ disabled.
   Equal rates retain the filter. Native initial input capacity is65536; a
   larger call reallocates zeroed channel storage with capacity=input+1024,
   preserving phase/counters/fresh. At most1m input frames/call and16m input
   and returned frames/stream. Unsafe native allocation accesses reject.
   Callers own serialization of access to each state. */
int rb_native_mode1_create(double source_rate, double output_rate,
                          uint32_t channels, RBMode1 **result);
void rb_native_mode1_destroy(RBMode1 *state);
int rb_native_mode1_snapshot(const RBMode1 *state, RBMode1Snapshot *result);
/* Native reset clears phase/counters and sets fresh; channel storage and
   tables are retained, including stale storage. For fresh seek/preroll use
   destroy/create, rather than assuming reset erases prior samples. */
int rb_native_mode1_reset(RBMode1 *state);
int rb_native_mode1_count(const RBMode1 *state, size_t input_frames,
                         uint32_t final_input, size_t *returned_frames);
/* Same min(remaining,block_frames) partitions; last positive call is final.
   For total0 models one NULL/zero final call. Does not alter state. */
int rb_native_mode1_count_blocks(const RBMode1 *state, size_t total_input_frames,
                                size_t block_frames, size_t *returned_frames);
/* Positive calls require interleaved input. Zero calls require NULL input.
   Zero nonfinal calls reproduce native fresh/history changes. Final appends64
   last-input copies, or zeros for NULL/zero final; generated and returned
   counts differ. Exactly one final call, then reset/create before more input.
   Only returned samples are published; native writes beyond the returned
   region are not an ABI claim. All failures leave state/output/count unchanged.
   Input/output/count and state-owned storage must be disjoint. Finite normal
   or zero Float32 input/output only; nonzero subnormal output rejects.
   Native bounds reject, notably nonfresh final blocks too near capacity. */
int rb_native_mode1_process(RBMode1 *state, const float *input,
                           size_t input_frames, float *output,
                           size_t output_capacity, uint32_t final_input,
                           size_t *returned_frames);
/* Read-only diagnostic copies for independent coefficient/history oracles.
   table0=coefficient,table1=forward difference; each has32769 doubles.
   Storage is per-channel capacity+129 doubles, including retained tail. */
int rb_native_mode1_copy_table(const RBMode1 *state, uint32_t table,
                              size_t start, size_t count, double *output);
int rb_native_mode1_copy_storage(const RBMode1 *state, uint32_t channel,
                                size_t start, size_t count, double *output);
#ifdef __cplusplus
}
#endif
#endif
