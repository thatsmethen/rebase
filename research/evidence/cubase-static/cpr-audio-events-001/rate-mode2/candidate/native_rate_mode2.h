#ifndef REBASE_NATIVE_RATE_MODE2_H
#define REBASE_NATIVE_RATE_MODE2_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Independently reconstructed Float32 wrapper around an injected backend.
   Backend create must use interleaved Float32 io(0,0), quality(6,0), runtime(0).
   Callbacks return zero on success and must report actual consumed/produced
   frames. No callback may retry, append padding, retain caller pointers or
   reenter this wrapper. A NULL input means EOF, even when inputFrames is zero.
   This does not assert binary/build/runtime equivalence with bundled SoXR. */
typedef struct {
    void *context;
    int (*create)(void *context, double source_rate, double output_rate,
                  uint32_t channels, void **handle);
    int (*process)(void *handle, const float *input, size_t input_frames,
                   size_t *input_used, float *output, size_t output_capacity,
                   size_t *output_produced);
    void (*destroy)(void *handle);
} RBMode2Backend;
typedef struct RBMode2 RBMode2;
enum {
    RB_MODE2_OK=0, RB_MODE2_INVALID=1, RB_MODE2_CAPACITY=2,
    RB_MODE2_SAMPLE_DOMAIN=3, RB_MODE2_BACKEND=4, RB_MODE2_STATE=5,
    RB_MODE2_ALLOCATION=6
};
typedef struct {
    double ratio, cumulative_ideal;
    uint64_t cumulative_input, cumulative_visible, total_returned;
    uint64_t backend_calls, backend_input_used, backend_output_produced;
    uint32_t channels, delay, discard, input_capacity, output_capacity;
    uint32_t input_end, input_consumed, pending_input, output_read, output_end;
    uint32_t finished, failed;
} RBMode2Snapshot;

/* Rates are finite integral [8000,192000], channels 1 or 2, strict nearest-even
   FP environment. Caller blocks are 1...65408 frames. At most 16m source and
   returned frames are admitted. Equal rates are implemented without a bypass.
   create owns its successful backend handle until destroy. */
int rb_native_mode2_create(double source_rate, double output_rate,
                          uint32_t channels, RBMode2Backend backend,
                          RBMode2 **result);
void rb_native_mode2_destroy(RBMode2 *state);
int rb_native_mode2_snapshot(const RBMode2 *state, RBMode2Snapshot *result);
/* Queries do not call the backend or change state. Count predicts wrapper
   returned frames, NOT backend-produced frames. Backend invariants may still
   fail during processing. count_blocks uses min(remaining,block_frames), and
   marks the last positive block final. A zero total means one NULL/zero final. */
int rb_native_mode2_count(const RBMode2 *state, size_t input_frames,
                         uint32_t final_input, size_t *returned_frames);
int rb_native_mode2_count_blocks(const RBMode2 *state, size_t total_input_frames,
                                size_t block_frames, size_t *returned_frames);
/* A terminal call may be NULL/zero or positive input. Exactly one terminal
   call is admitted; zero nonterminal input is outside this subset. Terminal
   padding repeats the positive call's last frame, or zero for NULL/zero final.
   Native count/discard, compaction, retained zero storage and NULL drain are
   preserved; it is not plain soxr_process. Output/count remain unchanged on
   failure. Public argument/output-capacity/input-sample preflight failures leave
   state usable. Once processing begins, any failure (including an internal
   buffer bound or allocation failure) poisons state; destroy it without retry.
   All data/count/state regions must be disjoint. Finite normal-or-zero Float32
   input/output only; input subnormals and nonfinite backend samples reject. */
int rb_native_mode2_process(RBMode2 *state, const float *input,
                           size_t input_frames, float *output,
                           size_t output_capacity, uint32_t final_input,
                           size_t *returned_frames);
#ifdef __cplusplus
}
#endif
#endif
