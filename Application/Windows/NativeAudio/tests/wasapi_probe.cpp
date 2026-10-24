#include "rebase_windows_audio.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <thread>
#include <vector>

namespace {
struct Destroy { void operator()(RBAudio *audio) const { rb_audio_destroy(audio); } };
struct Report {
    const char *stage = "create", *outcome = "failed";
    int result = RB_AUDIO_INTERNAL;
    bool allow_audio = false, attempted = false, verified = false;
    unsigned checks = 0;
    RBAudioDeviceFormat format{};
    RBAudioStatus status{};
    RBAudioRateInfo rate{};
    bool ok(bool condition, const char *name) {
        ++checks;
        if (!condition) { stage = name; return false; }
        return true;
    }
    bool call(int value, const char *name) { result = value; return ok(value == RB_AUDIO_OK, name); }
    void write(FILE *file) const {
        std::fprintf(file,
            "{\"schema\":1,\"suite\":\"windows-wasapi-native-probe\",\"outcome\":\"%s\","
            "\"stage\":\"%s\",\"result\":%d,\"hresult\":%d,\"checks\":%u,"
            "\"wasapi_compiled\":true,\"allow_audio\":%s,\"playback_attempted\":%s,\"playback_tested\":%s,"
            "\"audible_output_measured\":false,\"mix_sample_rate\":%u,\"mix_channels\":%u,"
            "\"mix_float32_stereo\":%s,\"final_phase\":%u,\"final_position_frames\":%llu,"
            "\"endpoint_buffer_frames\":%u,\"clock_reading_approximate\":%s,"
            "\"source_sample_rate\":%u,\"rate_conversion\":%s,\"converted_frames\":%llu}\n",
            outcome, stage, result, status.hresult, checks,
            allow_audio ? "true" : "false", attempted ? "true" : "false", verified ? "true" : "false",
            format.sample_rate, format.channels, format.float32 ? "true" : "false", status.phase,
            static_cast<unsigned long long>(status.position_frames), status.endpoint_buffer_frames,
            status.clock_reading_approximate ? "true" : "false", rate.source_rate,
            rate.converted ? "true" : "false", static_cast<unsigned long long>(rate.endpoint_frames));
    }
};
bool read(RBAudio *audio, Report &report) {
    if (!report.call(rb_audio_status(audio, &report.status), "status-query")) return false;
    if (report.status.phase == RB_AUDIO_FAULT) {
        report.stage = "device-fault"; report.result = report.status.result; return false;
    }
    return true;
}
bool wait_position(RBAudio *audio, Report &report, uint64_t after, bool finish = false) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (std::chrono::steady_clock::now() < deadline) {
        if (!read(audio, report)) return false;
        if (finish ? report.status.phase == RB_AUDIO_FINISHED : report.status.position_frames > after) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    return report.ok(false, finish ? "finish-timeout" : "clock-advance-timeout");
}
int probe(Report &report) {
    RBAudio *raw = nullptr;
    if (!report.call(rb_audio_create(&raw), "create")) return 1;
    std::unique_ptr<RBAudio, Destroy> audio(raw);
    report.result = rb_audio_default_format(raw, &report.format);
    if (report.result == RB_AUDIO_NO_ENDPOINT) {
        report.stage = "default-endpoint"; report.outcome = "unavailable-no-endpoint"; return 77;
    }
    if (!report.ok(report.result == RB_AUDIO_OK, "default-format")) return 1;
    if (!report.allow_audio) {
        report.stage = "read-only-endpoint-probe"; report.outcome = "endpoint-observed"; return 0;
    }
    if (!report.format.float32 || report.format.channels != 2 ||
        report.format.sample_rate < 8000 || report.format.sample_rate > 192000) {
        report.result = RB_AUDIO_FORMAT; report.stage = "supported-mix-format";
        report.outcome = "unavailable-unsupported-format"; return 77;
    }
    if (!report.ok(rb_audio_play(raw) == RB_AUDIO_STATE, "empty-play-rejected")) return 1;
    RBAudioStatus sentinel{}; sentinel.abi_version = 1234;
    if (!report.ok(rb_audio_status(nullptr, &sentinel) == RB_AUDIO_ARGUMENT && sentinel.abi_version == 1234,
                   "failed-output-preserved")) return 1;
    // Deliberately differ from the endpoint to exercise the explicit converter.
    const uint32_t rate = report.format.sample_rate == 44100 ? 48000u : 44100u;
    const uint64_t total = rate * 2;
    std::vector<float> pcm(static_cast<size_t>(total) * 2);
    for (uint64_t i = 0; i < total; ++i) {
        const double time = static_cast<double>(i) / rate;
        pcm[2 * i] = static_cast<float>(0.02 * std::sin(2 * 3.141592653589793 * 220 * time));
        pcm[2 * i + 1] = static_cast<float>(0.01 * std::sin(2 * 3.141592653589793 * 330 * time));
    }
    if (!report.call(rb_audio_set_source(raw, pcm.data(), total, rate), "snapshot")) {
        rb_audio_status(raw, &report.status); return 1;
    }
    if (!report.call(rb_audio_rate_info(raw, &report.rate), "rate-info") ||
        !report.ok(report.rate.abi_version == 1 && report.rate.source_rate == rate &&
            report.rate.endpoint_rate == report.format.sample_rate && report.rate.converted == 1 &&
            report.rate.soxr_recipe == 6 && report.rate.source_frames == total &&
            report.rate.endpoint_frames == static_cast<uint64_t>(report.format.sample_rate) * 2,
            "converted-snapshot-rates")) return 1;
    std::fill(pcm.begin(), pcm.end(), 0); // Backend must own an independent snapshot.
    pcm.clear(); pcm.shrink_to_fit();
    if (!report.ok(rb_audio_set_source(raw, nullptr, total, rate) == RB_AUDIO_ARGUMENT,
                   "invalid-snapshot-rejected")) return 1;
    if (!read(raw, report) || !report.ok(report.status.phase == RB_AUDIO_READY && report.status.total_frames == total,
                                       "invalid-snapshot-preserves-source")) return 1;
    report.attempted = true;
    if (!report.call(rb_audio_play(raw), "play") || !wait_position(raw, report, 0)) return 1;
    if (!report.ok(report.status.submitted_peak_left > 0 && report.status.submitted_peak_left <= 0.021f &&
                   report.status.submitted_peak_right > 0 && report.status.submitted_peak_right <= 0.011f,
                   "copied-source-meters")) return 1;
    if (!report.call(rb_audio_pause(raw), "pause") || !read(raw, report) ||
        !report.ok(report.status.phase == RB_AUDIO_PAUSED, "paused-phase")) return 1;
    const uint64_t paused = report.status.position_frames;
    std::this_thread::sleep_for(std::chrono::milliseconds(120));
    if (!read(raw, report) || !report.ok(report.status.position_frames == paused, "paused-clock-frozen")) return 1;
    if (!report.call(rb_audio_play(raw), "resume") || !wait_position(raw, report, paused)) return 1;
    if (!report.call(rb_audio_seek(raw, rate), "seek-playing") || !read(raw, report) ||
        !report.ok(report.status.phase == RB_AUDIO_PLAYING && report.status.position_frames >= rate,
                   "seek-playing-position")) return 1;
    if (!report.call(rb_audio_stop(raw), "stop") || !read(raw, report) ||
        !report.ok(report.status.phase == RB_AUDIO_READY && report.status.position_frames == 0 &&
                   report.status.submitted_frames == 0, "stop-rewinds-flushes")) return 1;
    if (!report.call(rb_audio_seek(raw, total), "seek-end") || !read(raw, report) ||
        !report.ok(report.status.phase == RB_AUDIO_FINISHED && report.status.position_frames == total,
                   "seek-end-finishes")) return 1;
    if (!report.ok(rb_audio_play(raw) == RB_AUDIO_STATE, "finished-play-rejected")) return 1;
    if (!report.call(rb_audio_seek(raw, total - rate / 4), "seek-tail") ||
        !report.call(rb_audio_play(raw), "play-tail") || !wait_position(raw, report, 0, true) ||
        !report.ok(report.status.position_frames == total, "clock-reaches-end")) return 1;
    if (!report.call(rb_audio_stop(raw), "stop-after-end") ||
        !report.call(rb_audio_play(raw), "play-before-destroy") || !wait_position(raw, report, 0)) return 1;
    audio.reset(); // Destruction while active must signal the worker and join it.
    report.result = RB_AUDIO_OK; report.verified = true; report.outcome = "device-lifecycle-verified";
    report.stage = "destroy-active-completed"; return 0;
}
}
int main(int argc, char **argv) {
    Report report;
    const char *json_path = nullptr;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--allow-audio") == 0) report.allow_audio = true;
        else if (std::strcmp(argv[i], "--json") == 0 && i + 1 < argc) json_path = argv[++i];
        else return 2;
    }
    int result;
    try { result = probe(report); }
    catch (...) { report.stage = "probe-exception"; report.result = RB_AUDIO_INTERNAL; result = 1; }
    report.write(stdout);
    if (json_path) {
        FILE *file = std::fopen(json_path, "wb");
        if (!file) return 2;
        report.write(file);
        const bool bad = std::ferror(file) != 0;
        if (std::fclose(file) != 0 || bad) return 2;
    }
    return result;
}
