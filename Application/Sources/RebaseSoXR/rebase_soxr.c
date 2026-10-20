#include "rebase_soxr.h"
#include "../../ThirdParty/soxr-0.1.3/src/soxr.h"
#include <fenv.h>
#include <math.h>

int rb_soxr_create(void *context, double source_rate, double output_rate,
                   uint32_t channels, void **handle) {
    (void)context;
    if (!handle || !isfinite(source_rate) || !isfinite(output_rate) ||
        source_rate < 8000 || source_rate > 192000 ||
        output_rate < 8000 || output_rate > 192000 ||
        source_rate != floor(source_rate) || output_rate != floor(output_rate) ||
        channels < 1 || channels > 2)
        return RB_SOXR_INVALID_ARGUMENT;
    if (fegetround() != FE_TONEAREST) return RB_SOXR_ROUNDING_MODE;
    soxr_io_spec_t io = soxr_io_spec(SOXR_FLOAT32_I, SOXR_FLOAT32_I);
    soxr_quality_spec_t quality = soxr_quality_spec(6, 0);
    soxr_runtime_spec_t runtime = soxr_runtime_spec(0);
    soxr_error_t error = NULL;
    soxr_t state = soxr_create(source_rate, output_rate, channels, &error,
                               &io, &quality, &runtime);
    if (!state || error) {
        if (state) soxr_delete(state);
        return RB_SOXR_CREATE_FAILED;
    }
    *handle = state;
    return RB_SOXR_OK;
}

int rb_soxr_process(void *handle, const float *input, size_t input_frames,
                    size_t *input_used, float *output, size_t output_capacity,
                    size_t *output_produced) {
    if (!handle || !input_used || !output_produced ||
        (!input && input_frames != 0) || (!output && output_capacity != 0))
        return RB_SOXR_INVALID_ARGUMENT;
    if (fegetround() != FE_TONEAREST) return RB_SOXR_ROUNDING_MODE;
    size_t used = 0, produced = 0;
    soxr_error_t error = soxr_process((soxr_t)handle, input, input_frames, &used,
                                     output, output_capacity, &produced);
    /* A library error can mutate its own state. Caller must discard the handle. */
    *input_used = used;
    *output_produced = produced;
    return error ? RB_SOXR_PROCESS_FAILED : RB_SOXR_OK;
}

void rb_soxr_destroy(void *handle) {
    if (handle) soxr_delete((soxr_t)handle);
}
const char *rb_soxr_version(void) { return soxr_version(); }
const char *rb_soxr_error(void *handle) {
    return handle ? soxr_error((soxr_t)handle) : "missing SoXR handle";
}
const char *rb_soxr_engine(void *handle) {
    return handle ? soxr_engine((soxr_t)handle) : "missing SoXR handle";
}
RBMode2Backend rb_public_soxr_backend(void) {
    RBMode2Backend backend = {NULL, rb_soxr_create, rb_soxr_process, rb_soxr_destroy};
    return backend;
}
