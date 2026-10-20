#ifndef REBASE_CPR_EVENT_PCM_H
#define REBASE_CPR_EVENT_PCM_H
#include <stddef.h>
#include <stdint.h>

/* Packed signed little-endian PCM24 to Float32, then one event-gain multiply.
   Distinct nonoverlapping buffers must hold sample_count*3 and *4 bytes.
   Bounded to normal-or-zero arithmetic and round-to-nearest. No resampling.
   Returns 0 on success; invalid inputs are rejected before writing output. */
int rb_cpr_event_pcm24_f32(const uint8_t *input, float *output,
                         size_t sample_count, uint32_t gain_bits);
/* Separate binary32 event gain after rate conversion. In-place, finite
   normal-or-zero samples/results only. Failure leaves samples unchanged. */
int rb_cpr_event_gain_f32(float *samples, size_t sample_count, uint32_t gain_bits);
#endif
