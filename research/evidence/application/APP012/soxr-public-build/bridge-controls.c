/* Independent public API versus callback-bridge checks, never vendor code. */
#include "rebase_soxr.h"
#include "soxr.h"
#include <assert.h>
#include <fenv.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static size_t compare(double source, double target, unsigned channels) {
    RBMode2Backend backend = rb_public_soxr_backend();
    void *wrapped = NULL;
    assert(backend.create(backend.context, source, target, channels, &wrapped) == 0);
    soxr_io_spec_t io = soxr_io_spec(SOXR_FLOAT32_I, SOXR_FLOAT32_I);
    soxr_quality_spec_t quality = soxr_quality_spec(SOXR_VHQ, 0);
    soxr_runtime_spec_t runtime = soxr_runtime_spec(0);
    assert(SOXR_VHQ == 6 && quality.precision == 28);
    soxr_error_t error = NULL;
    soxr_t direct = soxr_create(source, target, channels, &error,
                                &io, &quality, &runtime);
    assert(direct && !error);
    assert(strcmp(rb_soxr_engine(wrapped), "cr64") == 0);
    float input[8192 * 2], a[257 * 2], b[257 * 2];
    for (size_t i = 0; i < 8192; ++i) {
        input[i * channels] = i == 0 ? 0.75f : (float)((int)(i % 31) - 15) / 32;
        if (channels == 2)
            input[i * channels + 1] = i == 8191 ? -0.5f : (float)(i % 19) / 32;
    }
    size_t position = 0, total = 0, calls = 0;
    while (position < 8192) {
        size_t count = 8192 - position;
        if (count > 113) count = 113;
        size_t used_a = 777, used_b = 888, made_a = 777, made_b = 888;
        assert(backend.process(wrapped, input + position * channels, count,
                               &used_a, a, 257, &made_a) == 0);
        assert(!soxr_process(direct, input + position * channels, count,
                             &used_b, b, 257, &made_b));
        assert(used_a == used_b && made_a == made_b && used_a <= count && made_a <= 257);
        assert(!memcmp(a, b, made_a * channels * sizeof(float)));
        assert(used_a || made_a);
        position += used_a;
        total += made_a;
        assert(++calls < 1000);
    }
    for (;;) {
        size_t used_a = 777, used_b = 888, made_a = 777, made_b = 888;
        assert(backend.process(wrapped, NULL, 0, &used_a, a, 257, &made_a) == 0);
        assert(!soxr_process(direct, NULL, 0, &used_b, b, 257, &made_b));
        assert(used_a == used_b && made_a == made_b && made_a <= 257);
        assert(!memcmp(a, b, made_a * channels * sizeof(float)));
        total += made_a;
        assert(++calls < 1000);
        if (!made_a) break;
    }
    assert(!rb_soxr_error(wrapped));
    backend.destroy(wrapped);
    soxr_delete(direct);
    return total;
}

int main(void) {
    assert(strcmp(rb_soxr_version(), "libsoxr-0.1.3") == 0);
    void *sentinel = (void *)0x1234;
    assert(rb_soxr_create(NULL, NAN, 48000, 2, &sentinel) == RB_SOXR_INVALID_ARGUMENT);
    assert(sentinel == (void *)0x1234);
    assert(rb_soxr_create(NULL, 44100.5, 48000, 2, &sentinel) == RB_SOXR_INVALID_ARGUMENT);
    assert(rb_soxr_create(NULL, 44100, 48000, 3, &sentinel) == RB_SOXR_INVALID_ARGUMENT);
    assert(rb_soxr_create(NULL, 7999, 48000, 2, &sentinel) == RB_SOXR_INVALID_ARGUMENT);
    assert(rb_soxr_create(NULL, 44100, 192001, 2, &sentinel) == RB_SOXR_INVALID_ARGUMENT);
    assert(fesetround(FE_DOWNWARD) == 0);
    assert(rb_soxr_create(NULL, 44100, 48000, 2, &sentinel) == RB_SOXR_ROUNDING_MODE);
    assert(fesetround(FE_TONEAREST) == 0);
    size_t used = 123, made = 456;
    assert(rb_soxr_process(NULL, NULL, 0, &used, NULL, 0, &made) == RB_SOXR_INVALID_ARGUMENT);
    assert(used == 123 && made == 456);
    rb_soxr_destroy(NULL);
    size_t totals[8];
    const double rates[][2] = {{44100,48000},{48000,44100},{44100,16000},{44100,44100}};
    for (unsigned i = 0; i < 4; ++i)
        for (unsigned c = 1; c <= 2; ++c)
            totals[i*2+c-1] = compare(rates[i][0], rates[i][1], c);
    printf("{\"status\":\"passed\",\"version\":\"%s\",\"engine\":\"cr64\","
           "\"comparisons\":8,\"all_consumed_produced_and_sample_bits_match\":true,"
           "\"output_totals\":[%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu],"
           "\"scope\":\"Our bridge versus direct calls to same public library; no native wrapper or vendor equivalence\"}\n",
           rb_soxr_version(),totals[0],totals[1],totals[2],totals[3],totals[4],totals[5],totals[6],totals[7]);
}
