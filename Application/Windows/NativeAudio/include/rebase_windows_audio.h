#ifndef REBASE_WINDOWS_AUDIO_H
#define REBASE_WINDOWS_AUDIO_H
#include <stdint.h>
#include <stddef.h>
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
    RB_AUDIO_MEMORY = 6, RB_AUDIO_INTERNAL = 7, RB_AUDIO_UNDERRUN = 8,
    RB_AUDIO_CONVERSION = 9, RB_AUDIO_CAPACITY = 10,
    RB_AUDIO_ENVIRONMENT = 11, RB_AUDIO_RATE_EMPTY = 12,
    RB_AUDIO_BACKPRESSURE = 13, RB_AUDIO_STALE = 14, RB_AUDIO_PROTOCOL = 15
};
enum RBAudioPhase {
    RB_AUDIO_EMPTY = 0, RB_AUDIO_READY = 1, RB_AUDIO_PLAYING = 2,
    RB_AUDIO_PAUSED = 3, RB_AUDIO_FINISHED = 4, RB_AUDIO_FAULT = 5,
    RB_AUDIO_PRIMING = 6, RB_AUDIO_DRAINING = 7, RB_AUDIO_CANCELLED = 8
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
/* Additive diagnostics; existing status/seek frame units remain source frames.
   This structure is 56 bytes with the platform's usual 8-byte alignment.
   Endpoint counters refer to the complete converted snapshot, not wall time. */
typedef struct RBAudioRateInfo {
    uint32_t abi_version, source_rate, endpoint_rate, converted;
    uint64_t source_frames, endpoint_frames, endpoint_position_frames, endpoint_submitted_frames;
    uint32_t soxr_recipe, reserved;
} RBAudioRateInfo;

/* Additive bounded stream ABI, 48/160 bytes. Frame positions are relative to
   this fresh suffix; the host owns the absolute source start. Storage bounds
   are independent from the nonzero UInt64 source duration. Source/endpoint
   queue capacities: 4096..262144 frames. max_block_frames: 1..65536 and no
   greater than source capacity. prime_endpoint_frames=0 selects max(4096,
   2*device buffer), bounded by capacity; explicit values must cover the device
   buffer. Generation is nonzero and must increase for each new stream. */
typedef struct RBAudioStreamDescriptor {
    uint32_t abi_version, source_rate, channels, max_block_frames;
    uint64_t generation, source_frames;
    uint32_t source_queue_frames, endpoint_queue_frames, prime_endpoint_frames, reserved;
} RBAudioStreamDescriptor;
typedef struct RBAudioStreamStatus {
    uint32_t abi_version, phase, source_rate, endpoint_rate;
    uint64_t generation, source_frames, source_accepted, source_consumed, source_position;
    uint64_t endpoint_produced, endpoint_submitted, endpoint_position, endpoint_total;
    uint32_t source_queued, endpoint_queued, source_capacity, endpoint_capacity, source_peak, endpoint_peak;
    uint32_t primed, source_eof, endpoint_total_final, converted;
    int32_t result, hresult;
    float peak_left, peak_right;
    uint32_t endpoint_buffer_frames, clock_approximate, soxr_recipe, reserved;
} RBAudioStreamStatus;

/* Native Windows 10+ backend. Opaque handles never cross process boundaries.
   Control calls are synchronous and serialized per handle; bounded stream
   Submit/Finish have separate admission synchronization. Never call from an audio
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
   The endpoint must mix in Float32 stereo at an integral 8..192kHz. Different
   rates are explicitly converted once with pinned public SoXR before READY;
   the converted snapshot is also bounded to 32M frames. An empty downsampled
   result is rejected; no tail samples are invented. Equal-rate samples are
   copied bit exactly. This never downmixes or enables AUTOCONVERTPCM. */
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
/* Samples the device clock on its owning thread. Position/submitted/total
   remain source frames; endpoint_buffer_frames is in endpoint frames.
   Position is a bounded stream-clock observation, not wall time or samples
   merely enqueued. Peaks describe the converted block submitted to WASAPI;
   they do not measure the DAC. Failed calls preserve caller output structs. */
RB_AUDIO_API int32_t rb_audio_status(RBAudio *audio, RBAudioStatus *output);
/* Before configuration rates/counts are zero. Faults retain last configuration;
   a host accepts new rate metadata only after successful set_source. */
RB_AUDIO_API int32_t rb_audio_rate_info(RBAudio *audio, RBAudioRateInfo *output);
/* Begin opens the actual endpoint, creates bounded storage and a dedicated
   converter producer. Failed Begin closes and joins its unpublished state;
   installation ownership transfers only on success. Submit copies all finite stereo frames or returns
   BACKPRESSURE without consumption, sequence change or borrowed storage.
   Sequence starts at zero; start_frame equals source_accepted. Finish requires
   exact next sequence and declared source total. Neither queue starvation nor
   process EOF substitutes for finish. Stream calls may race cancellation;
   generation rejects late data. Destroy remains exclusive with every call.
   No queue-capacity wait holds the control lock. Conversion/allocation never
   runs in the device consumer. The endpoint total is zero until final drain.
   Play requires priming (or a completed short nonempty stream). Pause freezes
   the actual clock; cancel is a stop/reset and producer-join barrier. A device
   error remains observable and cancel can be retried; it is not Stopped.
   Zero-frame suffixes are handled by fresh host EOF without opening a device. */
RB_AUDIO_API int32_t rb_audio_stream_begin(RBAudio *audio, const RBAudioStreamDescriptor *descriptor);
RB_AUDIO_API int32_t rb_audio_stream_submit(RBAudio *audio, uint64_t generation, uint64_t sequence,
                                          uint64_t start_frame, const float *interleaved, uint32_t frames);
RB_AUDIO_API int32_t rb_audio_stream_finish(RBAudio *audio, uint64_t generation, uint64_t next_sequence,
                                          uint64_t committed_frames);
RB_AUDIO_API int32_t rb_audio_stream_play(RBAudio *audio, uint64_t generation);
RB_AUDIO_API int32_t rb_audio_stream_pause(RBAudio *audio, uint64_t generation);
RB_AUDIO_API int32_t rb_audio_stream_cancel(RBAudio *audio, uint64_t generation);
RB_AUDIO_API int32_t rb_audio_stream_status(RBAudio *audio, uint64_t generation, RBAudioStreamStatus *output);
#ifdef __cplusplus
}
static_assert(sizeof(RBAudioStreamDescriptor) == 48, "stream descriptor ABI");
static_assert(sizeof(RBAudioStreamStatus) == 160, "stream status ABI");
static_assert(offsetof(RBAudioStreamDescriptor, generation) == 16 && offsetof(RBAudioStreamDescriptor, source_queue_frames) == 32, "stream descriptor field ABI");
static_assert(offsetof(RBAudioStreamStatus, generation) == 16 && offsetof(RBAudioStreamStatus, source_queued) == 88 &&
              offsetof(RBAudioStreamStatus, result) == 128 && offsetof(RBAudioStreamStatus, endpoint_buffer_frames) == 144, "stream status field ABI");
#endif
#endif
