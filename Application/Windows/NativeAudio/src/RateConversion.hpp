#pragma once
#include "rebase_windows_audio.h"
#include "soxr.h"
#include <cstddef>
#include <vector>

namespace rebase {
/* Explicit application device profile, independent of recovered CPR wrappers:
   Float32 interleaved stereo, SoXR VHQ(6), linear phase, one worker. */
bool conversion_environment_valid();
struct ConversionServices {
    soxr_t (*create)(double, double, unsigned, soxr_error_t *, const soxr_io_spec_t *,
                     const soxr_quality_spec_t *, const soxr_runtime_spec_t *);
    soxr_error_t (*process)(soxr_t, soxr_in_t, size_t, size_t *, soxr_out_t, size_t, size_t *);
    void (*destroy)(soxr_t);
    std::vector<float> (*allocate)(size_t);
};
/* On any failure output remains unchanged. The internal service seam permits
   allocation/backend-failure controls without changing the public ABI. */
int convert_snapshot(const float *input, uint64_t frames, uint32_t source_rate,
                     uint32_t endpoint_rate, std::vector<float> &output,
                     const ConversionServices *services = nullptr);
}
