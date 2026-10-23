/* Authored public-SoXR plumbing check, not a reference audio fidelity test. */
#include "soxr.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    const size_t input_frames = 4800, output_capacity = 16384;
    float *input = calloc(input_frames * 2, sizeof(float));
    float *output = calloc(output_capacity * 2, sizeof(float));
    if (!input || !output) return 2;
    input[0] = 1; input[1] = -0.5f;
    soxr_io_spec_t io = soxr_io_spec(SOXR_FLOAT32_I, SOXR_FLOAT32_I);
    soxr_quality_spec_t quality = soxr_quality_spec(6, 0);
    soxr_runtime_spec_t runtime = soxr_runtime_spec(0);
    soxr_error_t error = NULL;
    soxr_t state = soxr_create(48000, 44100, 2, &error, &io, &quality, &runtime);
    if (!state || error) { fprintf(stderr, "SoXR creation failed\n"); return 3; }
    size_t used = 0, produced = 0, tail = 0;
    error = soxr_process(state, input, input_frames, &used, output, output_capacity, &produced);
    if (error || used != input_frames) { fprintf(stderr, "SoXR input was not consumed\n"); return 4; }
    error = soxr_process(state, NULL, 0, NULL, output + produced * 2, output_capacity - produced, &tail);
    produced += tail;
    if (error || produced != 4410) { fprintf(stderr, "Unexpected flushed frame count\n"); return 5; }
    double energy = 0, peak = 0, channel_error = 0;
    for (size_t i = 0; i < produced; ++i) {
        double left = output[2*i], right = output[2*i+1];
        if (!isfinite(left) || !isfinite(right)) return 6;
        energy += left * left;
        if (fabs(left) > peak) peak = fabs(left);
        if (fabs(right + 0.5 * left) > channel_error) channel_error = fabs(right + 0.5 * left);
    }
    if (!(energy > 0 && peak <= 2 && channel_error < 1e-6)) return 7;
    if (!strstr(soxr_version(), "0.1.3")) return 8;
    printf("{\"schema\":\"rebase.soxr-plumbing.v1\",\"status\":\"passed\","
           "\"scope\":\"Public SoXR API plumbing, not reference-runtime fidelity\","
           "\"source_rate\":48000,\"output_rate\":44100,\"channels\":2,"
           "\"input_frames\":%zu,\"output_frames\":%zu,\"finite\":true,"
           "\"peak\":%.17g,\"energy\":%.17g,\"maximum_channel_error\":%.17g}\n",
           used, produced, peak, energy, channel_error);
    soxr_delete(state); free(input); free(output);
    return 0;
}
