#include "PlaybackCursor.hpp"
#include <cstdio>
#include <cstring>
#include <limits>

static unsigned checks = 0, failures = 0;
#define CHECK(condition) do { ++checks; if (!(condition)) { ++failures; std::fprintf(stderr, "line %d: %s\n", __LINE__, #condition); } } while (false)

int main(int argc, char **argv) {
    const char *json_path = nullptr;
    if (argc == 3 && std::strcmp(argv[1], "--json") == 0) json_path = argv[2];
    else if (argc != 1) return 2;
    rebase::PlaybackCursor cursor;
    CHECK(cursor.status().abi_version == 1);
    CHECK(cursor.status().phase == RB_AUDIO_EMPTY);
    CHECK(cursor.play() == RB_AUDIO_STATE);
    CHECK(cursor.pause() == RB_AUDIO_STATE);
    CHECK(cursor.stop() == RB_AUDIO_STATE);
    CHECK(cursor.seek(0) == RB_AUDIO_STATE);
    CHECK(!cursor.submitted(0));
    CHECK(!cursor.submitted(1));
    CHECK(cursor.next(256) == 0);
    CHECK(!cursor.observe(999));
    CHECK(cursor.configure(0, 48000) == RB_AUDIO_ARGUMENT);
    CHECK(cursor.configure(32000001, 48000) == RB_AUDIO_ARGUMENT);
    CHECK(cursor.configure(1000, 7999) == RB_AUDIO_ARGUMENT);
    CHECK(cursor.configure(1000, 192001) == RB_AUDIO_ARGUMENT);
    CHECK(cursor.status().phase == RB_AUDIO_EMPTY);
    CHECK(cursor.configure(1000, 48000) == RB_AUDIO_OK);
    const auto ready = cursor.status();
    CHECK(ready.phase == RB_AUDIO_READY && ready.generation == 1);
    CHECK(ready.total_frames == 1000 && ready.sample_rate == 48000);
    CHECK(cursor.configure(0, 48000) == RB_AUDIO_ARGUMENT);
    CHECK(cursor.status().generation == ready.generation);
    CHECK(cursor.status().total_frames == ready.total_frames);
    CHECK(cursor.play() == RB_AUDIO_OK);
    CHECK(cursor.play() == RB_AUDIO_OK);
    CHECK(cursor.next(128) == 128);
    CHECK(cursor.submitted(128));
    CHECK(cursor.source_index() == 128);
    CHECK(cursor.status().position_frames == 0); // Enqueue is not playback.
    cursor.peaks(0.25f, 0.5f);
    CHECK(cursor.status().submitted_peak_right == 0.5f);
    CHECK(!cursor.observe(60));
    CHECK(cursor.status().position_frames == 60);
    CHECK(!cursor.observe(30));
    CHECK(cursor.status().position_frames == 60); // Clock cannot reverse.
    CHECK(cursor.pause() == RB_AUDIO_OK);
    CHECK(cursor.pause() == RB_AUDIO_OK);
    CHECK(cursor.status().submitted_peak_left == 0);
    CHECK(!cursor.observe(100));
    CHECK(cursor.status().position_frames == 60);
    CHECK(cursor.status().submitted_frames == 128); // Pause retains queue.
    CHECK(cursor.play() == RB_AUDIO_OK);
    CHECK(!cursor.observe(90));
    CHECK(cursor.status().position_frames == 90);
    CHECK(cursor.seek(1001) == RB_AUDIO_ARGUMENT);
    CHECK(cursor.status().position_frames == 90);
    CHECK(cursor.seek(500) == RB_AUDIO_OK);
    CHECK(cursor.status().phase == RB_AUDIO_PLAYING);
    CHECK(cursor.status().generation == ready.generation + 1);
    CHECK(cursor.source_index() == 500 && cursor.status().position_frames == 500);
    CHECK(cursor.next(1000) == 500);
    CHECK(!cursor.submitted(501));
    CHECK(cursor.submitted(500));
    CHECK(cursor.status().phase == RB_AUDIO_PLAYING);
    CHECK(!cursor.observe(499));
    CHECK(cursor.status().position_frames == 999);
    CHECK(cursor.observe(500));
    CHECK(cursor.status().phase == RB_AUDIO_FINISHED);
    CHECK(cursor.status().position_frames == 1000);
    CHECK(cursor.next(1) == 0);
    CHECK(cursor.play() == RB_AUDIO_STATE);
    CHECK(cursor.stop() == RB_AUDIO_OK);
    CHECK(cursor.status().position_frames == 0 && cursor.source_index() == 0);
    CHECK(cursor.status().phase == RB_AUDIO_READY);
    CHECK(cursor.seek(1000) == RB_AUDIO_OK);
    CHECK(cursor.status().phase == RB_AUDIO_FINISHED);
    CHECK(cursor.seek(250) == RB_AUDIO_OK);
    CHECK(cursor.status().phase == RB_AUDIO_READY);
    CHECK(cursor.play() == RB_AUDIO_OK);
    CHECK(cursor.submitted(10));
    CHECK(!cursor.observe(11)); // Silent underrun cannot become source time.
    CHECK(cursor.status().phase == RB_AUDIO_FAULT);
    CHECK(cursor.status().result == RB_AUDIO_UNDERRUN);
    CHECK(cursor.play() == RB_AUDIO_STATE);
    CHECK(cursor.stop() == RB_AUDIO_STATE);
    CHECK(cursor.next(10) == 0 && !cursor.submitted(0));
    CHECK(cursor.configure(1, 8000) == RB_AUDIO_OK);
    CHECK(cursor.status().result == RB_AUDIO_OK && cursor.status().hresult == 0);
    CHECK(cursor.play() == RB_AUDIO_OK && cursor.submitted(1));
    CHECK(cursor.observe(std::numeric_limits<uint64_t>::max()));
    CHECK(cursor.status().position_frames == 1); // Tail silence is bounded.
    cursor.fail(RB_AUDIO_DEVICE, -1);
    CHECK(cursor.status().phase == RB_AUDIO_FAULT && cursor.status().hresult == -1);

    float stereo[] = {0.1f, -0.2f, 0.0f, -0.0f};
    CHECK(rebase::valid_snapshot(stereo, 2, 48000));
    CHECK(rebase::valid_snapshot(stereo, 2, 192000));
    CHECK(!rebase::valid_snapshot(nullptr, 2, 48000));
    CHECK(!rebase::valid_snapshot(stereo, 0, 48000));
    CHECK(!rebase::valid_snapshot(stereo, 32000001, 48000));
    CHECK(!rebase::valid_snapshot(stereo, 2, 0));
    CHECK(!rebase::valid_snapshot(stereo, 2, 192001));
    stereo[1] = std::numeric_limits<float>::quiet_NaN();
    CHECK(!rebase::valid_snapshot(stereo, 2, 48000));
    stereo[1] = std::numeric_limits<float>::infinity();
    CHECK(!rebase::valid_snapshot(stereo, 2, 48000));
    stereo[1] = -std::numeric_limits<float>::infinity();
    CHECK(!rebase::valid_snapshot(stereo, 2, 48000));

    const char *format = "{\"schema\":1,\"suite\":\"native-audio-portable-lifecycle\",\"checks\":%u,\"failures\":%u,\"wasapi_compiled\":false,\"playback_tested\":false}\n";
    std::printf(format, checks, failures);
    if (json_path) {
        FILE *file = std::fopen(json_path, "wb");
        if (!file) return 2;
        const int written = std::fprintf(file, format, checks, failures);
        if (std::fclose(file) != 0 || written < 0) return 2;
    }
    return failures ? 1 : 0;
}
