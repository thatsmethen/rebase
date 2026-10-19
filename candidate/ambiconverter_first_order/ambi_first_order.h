#ifndef AMBI_FIRST_ORDER_H
#define AMBI_FIRST_ORDER_H
#include <stddef.h>
#include <stdint.h>

/* Static-derived research candidate; no target runtime conformance established.
 * See README.md for the deliberately restricted accepted domain. */
typedef struct { const void *samples; size_t frames; } ambi_input;
typedef struct { void *samples; size_t frames; } ambi_output;
typedef struct {
    double direction;
    uint32_t direction_present;
    uint32_t bypass;
    uint64_t input_silence_flags;
} ambi_options;

enum ambi_result {
    AMBI_OK = 0,
    AMBI_INVALID_SHAPE = 1,
    AMBI_UNSUPPORTED_STATE = 2,
    AMBI_SAMPLE_DOMAIN = 3,
    AMBI_OVERLAP = 4,
    AMBI_FP_ENVIRONMENT = 5
};

/* Four planar inputs and outputs, valid declared storage, mutually disjoint.
 * Failure leaves all output samples unchanged. This API has no retained state. */
int ambi_first_order_f32(const ambi_input *, size_t, const ambi_output *, size_t,
                         const ambi_options *);
int ambi_first_order_f64(const ambi_input *, size_t, const ambi_output *, size_t,
                         const ambi_options *);
#endif
