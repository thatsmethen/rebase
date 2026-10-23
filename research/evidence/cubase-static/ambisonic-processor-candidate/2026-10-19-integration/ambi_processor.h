#ifndef AMBI_PROCESSOR_H
#define AMBI_PROCESSOR_H
#include <stddef.h>
#include <stdint.h>

/* Static-derived audio/state subset, not a VST3 ABI or runtime-validated clone.
 * Every pointer and declared extent must designate valid, stable caller storage.
 * State, descriptors, queues and report must not alias audio/scratch storage.
 * No allocation, locking, logging, target code or imported DSP runs in process.
 * See README.md for precision, alias, parameter and numerical-domain limits. */

enum ambip_status {
    AMBIP_OK = 0, AMBIP_CONFIGURATION = 1, AMBIP_SHAPE = 2,
    AMBIP_PARAMETER = 3, AMBIP_OVERLAP = 4, AMBIP_SAMPLE_DOMAIN = 5,
    AMBIP_FP_ENVIRONMENT = 6, AMBIP_INVALID_SILENCE = 7
};
enum ambip_disposition {
    AMBIP_NO_AUDIO = 0, AMBIP_CONVERTED = 1,
    AMBIP_BYPASS_COPIED = 2, AMBIP_SILENCE_SKIPPED = 3
};
enum { AMBIP_BINARY32 = 32, AMBIP_BINARY64 = 64, AMBIP_ABI_VERSION = 1 };

typedef struct {
    uint32_t abi_version, channels, precision, direction_table, bypass, reserved;
    size_t maximum_frames;
    void *scratch;
    size_t scratch_bytes;
} ambip_state;

typedef struct {
    int32_t sample_offset; /* Deliberately ignored by this recovered consumer. */
    double value;
} ambip_point;

/* Host adapter omits null queue objects. last_point_result reproduces the
 * getPoint result: zero succeeds, any other numeric result leaves state alone.
 * Only points[point_count-1] is read. ID1=bypass, ID2=direction; others ignored. */
typedef struct {
    uint32_t parameter_id;
    int32_t point_count;
    int32_t last_point_result;
    const ambip_point *points;
} ambip_queue;

typedef struct {
    uint32_t channels;
    size_t frame_capacity;
    const void *const *planes;
    uint64_t silence_flags;
} ambip_input;

typedef struct {
    uint32_t channels;
    size_t frame_capacity;
    void *const *planes;
    uint64_t silence_flags;
} ambip_output;

typedef struct {
    uint32_t disposition, staged_all_inputs, successful_parameter_updates;
} ambip_report;

/* Initialization writes A/low direction and bypass off, matching the traced
 * fresh allocation/constructor subset. This is not serialized target state.
 * Caller supplies channels*maximum_frames*(precision/8) aligned scratch bytes.
 * Configuration is immutable while processing; recreate on precision/count
 * changes outside the real-time callback. Not thread-safe for shared state. */
int ambip_init(ambip_state *, uint32_t channels, uint32_t precision,
               size_t maximum_frames, void *scratch, size_t scratch_bytes);

/* Zero frames, null input, or zero input channels consume valid parameter
 * updates and return NO_AUDIO without accessing output or output flags.
 * Otherwise only equal-N, adequately sized first buses are accepted.
 * All candidate errors leave state, output samples, output flags and report
 * unchanged; this is a caller-safety restriction, not target error behavior.
 * Normal: scatter, then destination gains. Bypass: bit-preserving same-index
 * copy. Silence skip: output sample bytes untouched. Both positive audio
 * branches and silence skip copy the input's entire 64-bit mask unchanged. */
int ambip_process_f32(ambip_state *, const ambip_input *, ambip_output *,
                      size_t frames, const ambip_queue *, size_t queue_count,
                      ambip_report *);
int ambip_process_f64(ambip_state *, const ambip_input *, ambip_output *,
                      size_t frames, const ambip_queue *, size_t queue_count,
                      ambip_report *);
#endif
