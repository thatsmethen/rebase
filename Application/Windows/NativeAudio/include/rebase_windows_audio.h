#ifndef REBASE_WINDOWS_AUDIO_H
#define REBASE_WINDOWS_AUDIO_H
#include <stdint.h>
#if defined(_WIN32) && defined(REBASE_AUDIO_BUILD)
#define RB_AUDIO_API __declspec(dllexport)
#elif defined(_WIN32)
#define RB_AUDIO_API __declspec(dllimport)
#else
#define RB_AUDIO_API
#endif
#ifdef __cplusplus
extern "C" {
#endif
typedef struct RBAudio RBAudio;
enum RBAudioResult {
    RB_AUDIO_OK = 0, RB_AUDIO_ARGUMENT = 1, RB_AUDIO_STATE = 2,
    RB_AUDIO_NO_ENDPOINT = 3, RB_AUDIO_FORMAT = 4, RB_AUDIO_DEVICE = 5,
    RB_AUDIO_MEMORY = 6, RB_AUDIO_INTERNAL = 7, RB_AUDIO_UNDERRUN = 8
};
enum RBAudioPhase {
    RB_AUDIO_EMPTY = 0, RB_AUDIO_READY = 1, RB_AUDIO_PLAYING = 2,
    RB_AUDIO_PAUSED = 3, RB_AUDIO_FINISHED = 4, RB_AUDIO_FAULT = 5
};
typedef struct RBAudioDeviceFormat {
    uint32_t sample_rate, channels, float32;
} RBAudioDeviceFormat;
typedef struct RBAudioStatus {
    uint32_t abi_version, phase, sample_rate, endpoint_buffer_frames;
    uint64_t total_frames, position_frames, submitted_frames, generation;
    float submitted_peak_left, submitted_peak_right;
    int32_t result, hresult;
    uint32_t clock_reading_approximate, reserved;
} RBAudioStatus;

/* Native Windows 10+ backend. Opaque handles never cross process boundaries.
   Calls are synchronous and serialized per handle; never call from an audio
   callback. Destroy must be exclusive with all other calls on that handle. */
RB_AUDIO_API int32_t rb_audio_create(RBAudio **output);
RB_AUDIO_API void rb_audio_destroy(RBAudio *audio);
/* Read-only discovery, with no device names/IDs exposed. No endpoint is a
   distinct failure, never successful playback or an emulated output device.
   Discovery is rejected while PLAYING; source setup is the format boundary. */
RB_AUDIO_API int32_t rb_audio_default_format(RBAudio *audio, RBAudioDeviceFormat *output);
/* Snapshot is interleaved Float32 stereo, finite samples, 1..32M frames,
   integral 8..192kHz. It must remain unchanged until this call returns. It is
   copied during this call and may be freed on return.
   No reader, Swift, managed-runtime, or caller callback runs on the device
   thread. A valid replacement stops the old stream; an endpoint/open failure
   leaves FAULT. Invalid input is rejected before changing the old stream.
   The endpoint must already mix at the exact rate in Float32 stereo. This
   layer never resamples/downmixes and never enables AUTOCONVERTPCM. */
RB_AUDIO_API int32_t rb_audio_set_source(RBAudio *audio, const float *interleaved,
                                        uint64_t frames, uint32_t sample_rate);
/* Play READY/PAUSED; repeated PLAYING is harmless. FINISHED requires a seek.
   Pause retains queued audio and the device clock. Stop flushes and rewinds.
   Seek flushes/re-primes; playing stays playing, other valid states stay ready.
   Seek to total_frames produces FINISHED without starting an empty stream. */
RB_AUDIO_API int32_t rb_audio_play(RBAudio *audio);
RB_AUDIO_API int32_t rb_audio_pause(RBAudio *audio);
RB_AUDIO_API int32_t rb_audio_stop(RBAudio *audio);
RB_AUDIO_API int32_t rb_audio_seek(RBAudio *audio, uint64_t frame);
/* Samples the device clock on its owning thread. Position is a bounded
   stream-clock observation, not wall time or samples merely enqueued. Peaks
   describe the last block submitted to WASAPI, before Windows processing;
   they do not measure the DAC. Failed calls preserve caller output structs. */
RB_AUDIO_API int32_t rb_audio_status(RBAudio *audio, RBAudioStatus *output);
#ifdef __cplusplus
}
#endif
#endif
