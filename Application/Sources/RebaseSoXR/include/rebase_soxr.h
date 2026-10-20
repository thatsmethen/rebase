#ifndef REBASE_SOXR_H
#define REBASE_SOXR_H
#include <stddef.h>
#include <stdint.h>
#include "native_rate_mode2.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Public SoXR 0.1.3 build, not Reference's bundled library.
 * Callbacks for the separately recovered native mode-2 wrapper.
 * Successful calls preserve actual library consumed/produced counts.
 * NULL input signals EOF; a non-NULL zero-frame input does not.
 * No retry, artificial padding, carry management, or gain occurs here. */
enum { RB_SOXR_OK = 0, RB_SOXR_INVALID_ARGUMENT = 1,
       RB_SOXR_CREATE_FAILED = 2, RB_SOXR_PROCESS_FAILED = 3,
       RB_SOXR_ROUNDING_MODE = 4 };
int rb_soxr_create(void *context, double source_rate, double output_rate,
                   uint32_t channels, void **handle);
int rb_soxr_process(void *handle, const float *input, size_t input_frames,
                    size_t *input_used, float *output, size_t output_capacity,
                    size_t *output_produced);
void rb_soxr_destroy(void *handle);
const char *rb_soxr_version(void);
const char *rb_soxr_error(void *handle);
const char *rb_soxr_engine(void *handle);
RBMode2Backend rb_public_soxr_backend(void);
#ifdef __cplusplus
}
#endif
#endif
