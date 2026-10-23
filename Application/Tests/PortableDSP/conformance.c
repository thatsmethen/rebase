#include <fenv.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(__APPLE__)
#include <sys/sysctl.h>
#endif
#include "ambi_first_order.h"
#include "ambi_processor.h"
#include "cpr_accessor_format.h"
#include "cpr_accessor_seek.h"
#include "cpr_event_pcm.h"
#include "cpr_live_stereo_ring.h"
#include "cpr_timeline_builder.h"
#include "cpr_timeline_reader.h"
#include "cpr_track_overlap.h"
#include "native_callback_adapter.h"
#include "native_rate_mode0.h"
#include "native_tempo.h"
#include "rebase_fp_environment.h"
#include "controls.h"

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF

#define LENGTH(a) (sizeof(a) / sizeof((a)[0]))
typedef struct { const char *name; size_t cases, checks, failed; } Group;
static Group groups[] = {{"accessor-seek"}, {"accessor-format"}, {"timeline-builder"},
    {"timeline-reader"}, {"callback-adapter"}, {"track-overlap"},
    {"existing-dsp-and-ring"}, {"floating-point-environment"}};
static Group *group;
static size_t hardware_modes_tested, hardware_modes_unavailable;
static void check(int good, const char *expression, int line) {
    ++group->checks;
    if (!good) {
        ++group->failed;
        fprintf(stderr, "%s case %zu line %d: %s\n", group->name, group->cases, line, expression);
    }
}
#define CHECK(expression) check(!!(expression), #expression, __LINE__)
static double f64(uint64_t bits) { double value; memcpy(&value, &bits, 8); return value; }
static float f32(uint32_t bits) { float value; memcpy(&value, &bits, 4); return value; }
static uint64_t b64(double value) { uint64_t bits; memcpy(&bits, &value, 8); return bits; }
static uint32_t b32(float value) { uint32_t bits; memcpy(&bits, &value, 4); return bits; }

static void test_seek(void) {
    group = &groups[0];
    for (size_t i = 0; i < LENGTH(seek_controls); ++i) {
        ++group->cases;
        const seek_controls_row *c = &seek_controls[i];
        RBAccessorSeek result = {0};
        CHECK(rb_cpr_accessor_seek(c->source, c->output, c->requested, &result) == 0);
        CHECK(result.sourceFrame == c->source_frame);
        CHECK(result.returnedOutputFrame == c->returned);
        CHECK(result.sourcePerOutputBits == c->ratio);
        CHECK(result.sourceProductBits == c->product);
        CHECK(result.outputQuotientBits == c->quotient);
    }
    ++group->cases;
    RBAccessorSeek result, before;
    memset(&result, 0xa5, sizeof(result)); memcpy(&before, &result, sizeof(result));
    CHECK(rb_cpr_accessor_seek(UINT32_C(0x472c4400), UINT32_C(0x473b8000), -1, &result) == 1);
    CHECK(memcmp(&result, &before, sizeof(result)) == 0);
}

static void test_format(void) {
    group = &groups[1];
    for (size_t i = 0; i < LENGTH(pcm24_controls); ++i) {
        ++group->cases;
        const pcm24_controls_row *c = &pcm24_controls[i];
        float value = f32(c->input);
        int status = rb_cpr_accessor_pcm24_roundtrip(&value, 1);
        CHECK(status == (c->accepted ? 0 : 1));
        CHECK(b32(value) == (c->accepted ? c->output : c->input));
    }
    for (size_t i = 0; i < LENGTH(gain_controls); ++i) {
        ++group->cases;
        const gain_controls_row *c = &gain_controls[i];
        float value = f32(c->input);
        CHECK(rb_cpr_accessor_gain_f32(&value, 1, c->gain) == 0);
        CHECK(b32(value) == c->output);
    }
    ++group->cases;
    float values[] = {0.5f, f32(UINT32_C(0x7f800000))}, before[2];
    memcpy(before, values, sizeof(values));
    CHECK(rb_cpr_accessor_pcm24_roundtrip(values, 2) == 1);
    CHECK(memcmp(before, values, sizeof(values)) == 0);
    CHECK(rb_cpr_accessor_gain_f32(values, 2, UINT32_C(0x40000000)) == 1);
    CHECK(memcmp(before, values, sizeof(values)) == 0);
}

static void test_builder(void) {
    group = &groups[2];
    for (size_t i = 0; i < LENGTH(builder_controls); ++i) {
        ++group->cases;
        const builder_controls_row *c = &builder_controls[i];
        RBTimelineBuilderProjection r;
        memset(&r, 0xa5, sizeof(r));
        CHECK(rb_cpr_timeline_builder_project(f64(c->input[0]), f64(c->input[1]),
            f64(c->input[2]), f64(c->input[3]), f64(c->input[4]), f64(c->input[5]), &r) == RB_TIMELINE_BUILDER_OK);
        CHECK(r.disposition == c->disposition && r.emptyReason == c->empty_reason);
        CHECK(r.startFrame == c->start && r.endFrame == c->end && r.offsetFrame == c->offset);
        double output[] = {r.period, r.clippedStart, r.clippedEnd, r.clippedSourceOffset,
            r.start, r.reconstructedEnd, r.length, r.sourceOffset, r.getterEnd};
        for (size_t j = 0; j < LENGTH(output); ++j) CHECK(b64(output[j]) == c->output[j]);
    }
    ++group->cases;
    RBTimelineBuilderProjection r;
    CHECK(rb_cpr_timeline_builder_project(-0.0, 1, 0, 0, 1, 8192, &r) == 0);
    CHECK(b64(r.clippedStart) == UINT64_C(0x8000000000000000));
    CHECK(b64(r.start) == 0 && r.startFrame == 0);
}

static void test_reader(void) {
    group = &groups[3];
    for (size_t i = 0; i < LENGTH(reader_quantizers); ++i) {
        ++group->cases;
        const reader_quantizers_row *c = &reader_quantizers[i];
        int64_t result = 77;
        int status = rb_cpr_timeline_quantize(f64(c->period), f64(c->coordinate), &result);
        CHECK(status == (c->valid ? RB_TIMELINE_OK : RB_TIMELINE_RANGE));
        CHECK(result == (c->valid ? c->expected : 77));
    }
    for (size_t i = 0; i < LENGTH(reader_partitions); ++i) {
        ++group->cases;
        const reader_partitions_row *c = &reader_partitions[i];
        RBTimelinePartition result = {0};
        CHECK(rb_cpr_timeline_partition(f64(c->start), f64(c->end), c->remaining, c->flags, &result) == 0);
        CHECK(result.frames == c->frames && result.silence == c->silence);
        if (!c->silence) CHECK(result.startFrame == c->expected_start && result.endFrame == c->expected_end);
    }
    for (size_t i = 0; i < LENGTH(reader_results); ++i) {
        ++group->cases;
        const reader_results_row *c = &reader_results[i];
        RBTimelineReadDecision result = {0};
        CHECK(rb_cpr_timeline_read_result(c->request, c->begin, c->segment, c->retried, c->returned, &result) == 0);
        CHECK(result.action == c->action && result.nativeResult == c->native_result);
    }
    ++group->cases;
    RBTimelineSegment segment = {1.0, 2.0, 0.5};
    RBTimelinePlan plan = {0};
    CHECK(rb_cpr_timeline_plan(0, 16384, 0, 0x1p-13, &segment, &plan) == 0);
    CHECK(plan.action == RB_TIMELINE_READ && plan.segmentStart == 8192 && plan.segmentEnd == 16384);
    CHECK(plan.silenceFrames == 8192 && plan.readFrames == 8192 && plan.sourceSeek == 4096);
    CHECK(plan.readOffset == 8192 && plan.nextCursor == 16384);
}

static void test_callback(void) {
    group = &groups[4];
    for (size_t i = 0; i < LENGTH(callback_windows); ++i) {
        ++group->cases;
        const callback_windows_row *c = &callback_windows[i];
        RBCallbackWindow result = {71, 72};
        CHECK(rb_native_callback_window(c->position, f64(c->offset), f64(c->rate), c->frames, &result) ==
            (c->valid ? RB_NATIVE_CALLBACK_OK : RB_NATIVE_CALLBACK_RANGE));
        CHECK(result.startFrame == (c->valid ? c->start : 71));
        CHECK(result.endFrame == (c->valid ? c->end : 72));
    }
    for (size_t i = 0; i < LENGTH(callback_offsets); ++i) {
        ++group->cases;
        double result;
        const callback_offsets_row *c = &callback_offsets[i];
        CHECK(rb_native_callback_offset_from_frames(c->frames, f64(c->rate), &result) == 0);
        CHECK(b64(result) == c->output);
    }
    for (size_t i = 0; i < LENGTH(callback_prefixes); ++i) {
        ++group->cases;
        const callback_prefixes_row *c = &callback_prefixes[i];
        RBCallbackWindow window = {c->start, c->end};
        int32_t result = 77;
        CHECK(rb_native_callback_prefix(&window, c->transport, c->whole, c->boundary, &result) == 0);
        CHECK(result == c->expected);
    }
    for (size_t i = 0; i < LENGTH(callback_samples); ++i) {
        ++group->cases;
        const callback_samples_row *c = &callback_samples[i];
        float storage[CONTROL_CALLBACK_CHANNELS][CONTROL_CALLBACK_CAPACITY];
        float *planes[CONTROL_CALLBACK_CHANNELS];
        for (int j = 0; j < c->channels; ++j) {
            planes[j] = storage[j];
            for (int k = 0; k < c->capacity; ++k) storage[j][k] = f32(c->input[j][k]);
        }
        RBCallbackPostResult result = {71, 72};
        int status = rb_native_callback_postprocess_f32(planes, c->channels, c->frames, c->capacity, c->offset, c->prefix, &result);
        CHECK(c->valid ? status == 0 : status != 0);
        CHECK(result.action == (c->valid ? c->action : 71));
        CHECK(result.prefixFrames == (c->valid ? c->prefix : 72));
        for (int j = 0; j < c->channels; ++j)
            for (int k = 0; k < c->capacity; ++k) CHECK(b32(storage[j][k]) == c->output[j][k]);
    }
    ++group->cases;
    CHECK(rb_native_callback_enabled(1, 2, 0) == 0);
    CHECK(rb_native_callback_enabled(1, 1, 0) == 1);
    CHECK(rb_native_callback_enabled(0, 1, 1) == 0);
}

static void test_overlap(void) {
    group = &groups[5];
    for (size_t i = 0; i < LENGTH(overlap_controls); ++i) {
        ++group->cases;
        const overlap_controls_row *c = &overlap_controls[i];
        RBTrackOverlapRange input[CONTROL_OVERLAP_INPUTS], output[CONTROL_OVERLAP_OUTPUTS];
        int32_t count = 77;
        for (int j = 0; j < c->inputs; ++j) input[j] = (RBTrackOverlapRange){
            c->input[j].index, c->input[j].ordinal, c->input[j].priority, f64(c->input[j].start), f64(c->input[j].end)};
        CHECK(rb_cpr_track_overlap_normalize(input, c->inputs, output, CONTROL_OVERLAP_OUTPUTS, &count) == 0);
        CHECK(count == c->outputs);
        for (int j = 0; j < count && j < c->outputs; ++j) {
            CHECK(output[j].sourceIndex == c->output[j].index && output[j].ordinal == c->output[j].ordinal);
            CHECK(output[j].priority == c->output[j].priority);
            CHECK(b64(output[j].start) == c->output[j].start && b64(output[j].end) == c->output[j].end);
        }
    }
}

static void test_existing(void) {
    group = &groups[6];
    ++group->cases;
    uint32_t period = 0;
    double seconds = 0, ticks = 0;
    CHECK(rb_native_fixed_period(UINT32_C(0x42f00000), &period) == 0);
    CHECK(period == UINT32_C(0x3f000000)); /* 60/120 = exactly one half. */
    CHECK(rb_native_fixed_seconds(UINT32_C(0x42f00000), 480, &seconds) == 0);
    CHECK(b64(seconds) == UINT64_C(0x3fe0000000000000));
    CHECK(rb_native_fixed_ticks(UINT32_C(0x42f00000), 0.5, &ticks) == 0);
    CHECK(b64(ticks) == UINT64_C(0x407e000000000000));

    ++group->cases;
    uint8_t packed[] = {0,0,0, 0xff,0xff,0x7f, 0,0,0x80, 1,0,0};
    float decoded[4] = {0};
    CHECK(rb_cpr_event_pcm24_f32(packed, decoded, 4, UINT32_C(0x3f800000)) == 0);
    CHECK(b32(decoded[0]) == 0 && b32(decoded[1]) == UINT32_C(0x3f7ffffe));
    CHECK(b32(decoded[2]) == UINT32_C(0xbf800000) && b32(decoded[3]) == UINT32_C(0x34000000));

    ++group->cases;
    RBMode0State resampler;
    CHECK(rb_native_mode0_init(24000, 48000, 1, &resampler) == RB_MODE0_OK);
    float input[] = {0, 1, 0, -1}, output[16];
    size_t produced = 0;
    CHECK(rb_native_mode0_count(&resampler, 4, &produced) == RB_MODE0_OK && produced == 6);
    CHECK(rb_native_mode0_process(&resampler, input, 4, output, 16, &produced) == RB_MODE0_OK);
    const uint32_t expected[] = {0, UINT32_C(0x3f000000), UINT32_C(0x3f800000), UINT32_C(0x3f000000), 0, UINT32_C(0xbf000000)};
    CHECK(produced == LENGTH(expected));
    for (size_t i = 0; i < LENGTH(expected); ++i) CHECK(b32(output[i]) == expected[i]);

    ++group->cases;
    float in_planes[4][2] = {{1, -0.0f}, {0.5f, -0.5f}, {0.25f, -0.25f}, {0.125f, -0.125f}};
    float out_planes[4][2] = {{0}};
    ambi_input inputs[4]; ambi_output outputs[4];
    for (int i = 0; i < 4; ++i) { inputs[i] = (ambi_input){in_planes[i], 2}; outputs[i] = (ambi_output){out_planes[i], 2}; }
    ambi_options options = {0, 1, 0, 0};
    CHECK(ambi_first_order_f32(inputs, 4, outputs, 4, &options) == AMBI_OK);
    CHECK(b32(out_planes[0][0]) == UINT32_C(0x3fb504f3) && b32(out_planes[0][1]) == UINT32_C(0x80000000));
    CHECK(out_planes[1][0] == 0.25f && out_planes[2][0] == 0.125f && out_planes[3][0] == 0.5f);

    ++group->cases;
    float scratch[8]; ambip_state ambi;
    CHECK(ambip_init(&ambi, 4, AMBIP_BINARY32, 2, scratch, sizeof(scratch)) == AMBIP_OK);
    const void *in_ptrs[4]; void *out_ptrs[4];
    for (int i = 0; i < 4; ++i) { in_ptrs[i] = in_planes[i]; out_ptrs[i] = out_planes[i]; }
    ambip_input in = {4, 2, in_ptrs, 0}; ambip_output out = {4, 2, out_ptrs, 0};
    ambip_point point = {0, 1}; ambip_queue queue = {1, 1, 0, &point}; ambip_report report;
    CHECK(ambip_process_f32(&ambi, &in, &out, 2, &queue, 1, &report) == AMBIP_OK);
    CHECK(report.disposition == AMBIP_BYPASS_COPIED && memcmp(in_planes, out_planes, sizeof(in_planes)) == 0);

    ++group->cases;
    float *left = calloc(32768, sizeof(float)), *right = calloc(32768, sizeof(float));
    CHECK(left && right);
    if (!left || !right) { free(left); free(right); return; }
    rb_cpr_live_stereo_ring ring;
    float stereo[] = {f32(UINT32_C(0x80000000)), 1, f32(UINT32_C(0x7fc12345)), -1};
    float l[4] = {7,7,7,7}, r[4] = {7,7,7,7}; rb_cpr_live_ring_result transfer;
    CHECK(rb_cpr_live_ring_init(&ring, left, right) == 0);
    CHECK(rb_cpr_live_ring_write(&ring, stereo, 2) == 0);
    CHECK(rb_cpr_live_ring_consume(&ring, l, r, 0, 4, 0, 0, &transfer) == 0);
    CHECK(transfer.copied_frames == 0 && transfer.silent_frames == 4 && ring.read_index == 0 && transfer.timeline_frames == 0);
    CHECK(rb_cpr_live_ring_consume(&ring, l, r, 0, 4, 0, 1, &transfer) == 0);
    CHECK(transfer.copied_frames == 2 && transfer.silent_frames == 2 && ring.read_index == 2 && transfer.timeline_frames == 4);
    CHECK(b32(l[0]) == UINT32_C(0x80000000) && b32(l[1]) == UINT32_C(0x7fc12345));
    CHECK(r[0] == 1 && r[1] == -1 && b32(l[2]) == 0 && b32(r[3]) == 0);
    free(left); free(right);
}

/* Every API below has valid, exactly representable inputs. Rejection must
   happen before writes, under each separately changed hardware mode. */
static void rejected_environment(void) {
    ++group->cases;
    CHECK(!rb_fp_nearest_gradual());
    RBAccessorSeek seek, saved_seek;
    memset(&seek, 0xa5, sizeof(seek)); memcpy(&saved_seek, &seek, sizeof(seek));
    CHECK(rb_cpr_accessor_seek(UINT32_C(0x472c4400), UINT32_C(0x473b8000), 1, &seek) == 2);
    CHECK(memcmp(&seek, &saved_seek, sizeof(seek)) == 0);
    float sample = 0.5f;
    CHECK(rb_cpr_accessor_pcm24_roundtrip(&sample, 1) == 2 && b32(sample) == UINT32_C(0x3f000000));
    CHECK(rb_cpr_accessor_gain_f32(&sample, 1, UINT32_C(0x40000000)) == 2 && b32(sample) == UINT32_C(0x3f000000));
    RBTimelineBuilderProjection builder, saved_builder;
    memset(&builder, 0xa5, sizeof(builder)); memcpy(&saved_builder, &builder, sizeof(builder));
    CHECK(rb_cpr_timeline_builder_project(0, 1, 0, 0, 1, 48000, &builder) == RB_TIMELINE_BUILDER_FP_ENVIRONMENT);
    CHECK(memcmp(&builder, &saved_builder, sizeof(builder)) == 0);
    int64_t quantized = 77;
    CHECK(rb_cpr_timeline_quantize(0x1p-13, 1, &quantized) == RB_TIMELINE_FP_ENVIRONMENT && quantized == 77);
    RBTimelineSegment segment = {0, 1, 0}; RBTimelinePlan plan, saved_plan;
    memset(&plan, 0xa5, sizeof(plan)); memcpy(&saved_plan, &plan, sizeof(plan));
    CHECK(rb_cpr_timeline_plan(0, 8, 0, 0x1p-13, &segment, &plan) == RB_TIMELINE_FP_ENVIRONMENT);
    CHECK(memcmp(&plan, &saved_plan, sizeof(plan)) == 0);
    RBCallbackWindow window = {71,72};
    CHECK(rb_native_callback_window(0, 0, 48000, 8, &window) == RB_NATIVE_CALLBACK_FP_ENVIRONMENT);
    CHECK(window.startFrame == 71 && window.endFrame == 72);
    double offset = 77;
    CHECK(rb_native_callback_offset_from_frames(1, 48000, &offset) == RB_NATIVE_CALLBACK_FP_ENVIRONMENT && offset == 77);
    float *planes[] = {&sample}; RBCallbackPostResult post = {71,72};
    CHECK(rb_native_callback_postprocess_f32(planes, 1, 1, 1, 0, 0, &post) == RB_NATIVE_CALLBACK_FP_ENVIRONMENT);
    CHECK(post.action == 71 && post.prefixFrames == 72 && b32(sample) == UINT32_C(0x3f000000));
    RBTrackOverlapRange source = {0,0,1,0,1}, output, saved_output;
    int32_t count = 77;
    memset(&output, 0xa5, sizeof(output)); memcpy(&saved_output, &output, sizeof(output));
    CHECK(rb_cpr_track_overlap_normalize(&source, 1, &output, 1, &count) == RB_TRACK_OVERLAP_FP_ENVIRONMENT);
    CHECK(count == 77 && memcmp(&output, &saved_output, sizeof(output)) == 0);
}

static void test_environment(void) {
    group = &groups[7];
    fenv_t saved;
    CHECK(fegetenv(&saved) == 0);
    const int modes[] = {FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO};
    for (size_t i = 0; i < LENGTH(modes); ++i) {
        CHECK(fesetround(modes[i]) == 0);
        rejected_environment();
        CHECK(fesetenv(&saved) == 0);
    }
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t original;
    __asm__ volatile("mrs %0, fpcr" : "=r"(original));
    const uint64_t bits[] = {UINT64_C(1)<<24, UINT64_C(1)<<25, UINT64_C(1), UINT64_C(2), UINT64_C(1)<<8};
    for (size_t i = 0; i < LENGTH(bits); ++i) {
        uint64_t changed = original | bits[i], actual;
        __asm__ volatile("msr fpcr, %0" :: "r"(changed));
        __asm__ volatile("mrs %0, fpcr" : "=r"(actual));
        if (actual & bits[i]) { ++hardware_modes_tested; rejected_environment(); }
        else ++hardware_modes_unavailable; /* Feature bits may be RES0 on this CPU. */
        __asm__ volatile("msr fpcr, %0" :: "r"(original));
    }
#elif defined(__x86_64__) || defined(_M_X64)
    const uint32_t original = (uint32_t)_mm_getcsr();
    const uint32_t bits[] = {UINT32_C(1)<<15, UINT32_C(1)<<6, UINT32_C(1)<<13, UINT32_C(2)<<13, UINT32_C(3)<<13};
    for (size_t i = 0; i < LENGTH(bits); ++i) {
        _mm_setcsr(original | bits[i]);
        ++hardware_modes_tested; rejected_environment();
        CHECK((uint32_t)_mm_getcsr() == (original | bits[i]));
        _mm_setcsr(original);
    }
    _mm_setcsr((original & ~UINT32_C(0x80)) & ~UINT32_C(0x3f));
    if (((uint32_t)_mm_getcsr() & UINT32_C(0x80)) == 0) {
        ++hardware_modes_tested; rejected_environment();
    } else ++hardware_modes_unavailable; /* Rosetta can keep traps masked. */
    _mm_setcsr(original);
#endif
    CHECK(fesetenv(&saved) == 0);
    CHECK(rb_fp_nearest_gradual());
}

static void report(FILE *stream) {
    size_t checks = 0, failures = 0, cases = 0;
    for (size_t i = 0; i < LENGTH(groups); ++i) { checks += groups[i].checks; failures += groups[i].failed; cases += groups[i].cases; }
#if defined(__aarch64__) || defined(__arm64__)
    const char *architecture = "arm64";
#elif defined(__x86_64__) || defined(_M_X64)
    const char *architecture = "x86_64";
#else
    const char *architecture = "unsupported";
#endif
    fprintf(stream, "{\n  \"schema\": \"rebase-portable-dsp-result-v1\",\n  \"architecture\": \"%s\",\n", architecture);
#if defined(__APPLE__)
    int translated = 0; size_t translated_size = sizeof(translated);
    int observed = sysctlbyname("sysctl.proc_translated", &translated, &translated_size, NULL, 0) == 0;
    fprintf(stream, "  \"host_os\": \"macOS\",\n  \"translation_observation\": \"%s\",\n", observed ? (translated ? "translated" : "native") : "unavailable");
#elif defined(_WIN32)
    fputs("  \"host_os\": \"Windows\",\n  \"translation_observation\": \"not-collected\",\n", stream);
#else
    fputs("  \"host_os\": \"other\",\n  \"translation_observation\": \"not-collected\",\n", stream);
#endif
    fprintf(stream, "  \"target_execution_count\": 0,\n  \"cases\": %zu,\n  \"checks\": %zu,\n  \"failures\": %zu,\n", cases, checks, failures);
    fprintf(stream, "  \"hardware_modes_tested\": %zu,\n  \"hardware_modes_unavailable\": %zu,\n  \"passed\": %s,\n  \"groups\": [\n", hardware_modes_tested, hardware_modes_unavailable, failures ? "false" : "true");
    for (size_t i = 0; i < LENGTH(groups); ++i)
        fprintf(stream, "    {\"name\": \"%s\", \"cases\": %zu, \"checks\": %zu, \"failures\": %zu}%s\n",
            groups[i].name, groups[i].cases, groups[i].checks, groups[i].failed, i + 1 == LENGTH(groups) ? "" : ",");
    fputs("  ]\n}\n", stream);
}

int main(int argc, char **argv) {
    const char *output = NULL;
    if (argc == 3 && strcmp(argv[1], "--json") == 0) output = argv[2];
    else if (argc != 1) { fputs("Usage: rebase_portable_dsp_tests [--json result.json]\n", stderr); return 2; }
    group = &groups[7]; CHECK(rb_fp_nearest_gradual());
    if (group->failed == 0) {
        test_seek(); test_format(); test_builder(); test_reader();
        test_callback(); test_overlap(); test_existing(); test_environment();
    }
    report(stdout);
    if (output) { FILE *file = fopen(output, "wb"); if (!file) return 2; report(file); if (fclose(file) != 0) return 2; }
    for (size_t i = 0; i < LENGTH(groups); ++i) if (groups[i].failed) return 1;
    return 0;
}
