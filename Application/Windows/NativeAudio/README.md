# Native Windows audio

This Windows 10+ C ABI supplies the WPF host's WASAPI shared-mode output through either a copied snapshot or the additive bounded source-stream interface below. For the snapshot interface, the caller supplies a complete, pre-rendered, interleaved Float32 stereo snapshot. It is copied during `rb_audio_set_source`; the caller must keep its memory stable until that call returns and may release it afterward. No reader, Swift, managed-runtime or caller callback runs on the device thread.

Accepted snapshots contain 1–32,000,000 frames at integral rates from 8,000 to 192,000 Hz. The converted snapshot has a separate 32,000,000-frame limit. Memory and preparation time therefore scale with project length. File-backed source storage, recording, device selection, exclusive mode and ASIO remain separate work.

## Explicit device-rate conversion

`rb_audio_default_format` discovers the default multimedia render endpoint's mix rate and channel count. Its `float32` flag means Float32 **stereo** with the conventional left/right mask or no mask. No device name or identifier is exposed. Other channel layouts, sample types and rates outside 8–192 kHz are rejected.

At equal rates the adapter moves its copied snapshot directly into playback storage, preserving every Float32 word, including signed zero and subnormal samples. At different rates it uses the pinned public **SoXR 0.1.3** library with an explicit application profile: interleaved Float32 stereo, VHQ recipe 6, linear phase, default quality flags and one runtime thread. This device adapter is independently authored. It does not reuse the recovered CPR mode-2 wrapper's carry/EOF policy and does not claim reference-library or AVAudioEngine output equivalence.

Conversion completes during source setup before READY. It consumes actual backend counts, signals EOF with NULL input and drains all returned frames. The upper allocation bound is `ceil(sourceFrames * endpointRate / sourceRate)`; bounds above 32 million endpoint frames fail before allocation. Actual output may be shorter because of final sample-count rounding. A downsampled source that produces zero frames is rejected explicitly. No artificial tail, padding or truncated converter output is installed. A spare single-frame sink detects unexpected output beyond the allocated bound. Destination storage is allocated once and shrunk in place after draining; it is not repeatedly copied while growing.

Conversion requires nearest rounding, preserved denormals and masked floating-point traps on qualified x64/arm64 environments. Unsupported environments fail without changing their controls. Converter creation/process errors, nonfinite output and nonprogress are rejected. Equal-rate copying needs no floating arithmetic and bypasses converter qualification. The public source validator classifies sample bits before arithmetic, including rejection of signaling NaNs.

This adapter never enables `AUTOCONVERTPCM` or `SRC_DEFAULT_QUALITY`. WASAPI is initialized at the discovered endpoint mix rate. Shared-mode processing, Windows effects and the device can still change output; this is not a bit-identical DAC claim.

## Clock and frame units

The existing 72-byte `RBAudioStatus` and seek ABI remain in **source frames**: `sample_rate`, `total_frames`, `position_frames` and `submitted_frames` describe the supplied project or source-event snapshot. `endpoint_buffer_frames` is explicitly in endpoint frames. Peaks measure the most recently submitted endpoint-rate PCM block before Windows processing, not speakers or the DAC.

The additive `rb_audio_rate_info` returns the 56-byte `RBAudioRateInfo`: ABI version 1, source/endpoint rates, conversion flag, original frame count, actual converted frame count, endpoint position/submitted counters, recipe 6 for conversion (0 for identity), and reserved zero. Before any successful source configuration the rates and frame counts are zero. A fault may retain the last configured metadata; inspect the status phase and accept a new rate receipt only after successful source setup. Failed API calls preserve caller output structures.

Transport runs internally in endpoint frames. Seeking maps a source frame to the nearest frame in the **same fully converted snapshot**, with integer half-up rounding; exact source end maps to exact endpoint end. Resampling is never restarted from the seek offset, so conversion phase and surrounding filter context are preserved. Quantization is at most half an endpoint frame. A near-end seek that rounds to endpoint end finishes at exact source end.

Within a seek generation, the public position is the requested source-frame origin plus `floor(endpointClockElapsed * sourceRate / endpointRate)`, bounded to the source. A stale clock cannot move it backward. Natural completion waits for all real converted endpoint frames to be consumed, then sets exact source end. An enqueued count is not a playback position. At the tail, zero-fill used to complete a WASAPI buffer does not extend the source duration. Clock progress beyond submitted endpoint audio before that tail is an underrun fault.

## Ownership and lifecycle

One MTA worker owns every COM audio object, snapshot, clock observation and transport state. Calls run synchronously through a serialized queue. Callers may submit from different threads but must not destroy a handle concurrently with another call or call from an audio callback. Shutdown stops the stream, releases COM objects on their owner and joins the worker. It cannot interrupt a blocking driver call or an in-progress source conversion.

The event-driven data path performs bounded copies, final-buffer zero fill and peak scans. It performs no conversion, file I/O, IPC or allocation. Source setup is a control operation and may allocate, convert and open a device. Audio events are serviced between commands so sustained UI polling does not starve rendering. No hard real-time or low-latency guarantee is claimed.

| Operation | Result |
| --- | --- |
| Create | Empty handle; no endpoint opened or sound played. |
| Set source | Validate/copy input, stop the old stream, open the endpoint and prepare its rate snapshot. Invalid input preserves the old source. Endpoint, allocation or conversion failure after replacement begins enters fault; no partial new source is installed. |
| Play | Prime READY or resume PAUSED. Repeated PLAYING is harmless. FINISHED requires seek or stop. |
| Pause | Stop the device clock and retain converted data already queued. Repeated pause is harmless. |
| Stop | Stop/reset WASAPI, flush the queue and rewind both clocks to zero; enter READY. |
| Seek | Stop/reset/flush, map the source position to the converted snapshot, then resume only if previously playing. Seeking while paused enters READY. |
| Status/rate info | Observe the owning device clock, preserving source-unit and endpoint-unit diagnostics separately. |
| Device/converter failure | Enter FAULT and close the stream. A new valid source configuration is the recovery boundary. |

Stop, seek, source replacement and fault each advance `generation`. `clock_reading_approximate` exposes `IAudioClock::GetPosition` returning `S_FALSE`. Pause, completion and fault clear peaks. Endpoint changes are not followed automatically; invalidation faults, and source reload can open the new default.

Error codes retain the original values 0–8 and add 9 (conversion failure), 10 (converted snapshot capacity), 11 (unsupported floating-point environment) and 12 (downsampling produced no endpoint frames).

## Bounded source stream ABI

`rb_audio_stream_begin` accepts the 48-byte `RBAudioStreamDescriptor` (ABI 1, Float32 stereo, 8–192kHz). Its nonzero UInt64 `source_frames` describes a freshly prepared suffix, independently from queue storage. The host owns the absolute source origin and issues a strictly increasing nonzero generation. Begin consumes a generation even if endpoint opening fails, but transfers ownership only on success: failed producer startup is joined and discarded before returning. Zero-length validated suffixes remain a host EOF result without opening a device.

The source and endpoint queues each hold 4096–262144 frames; `max_block_frames` is 1–65536 and no greater than source capacity. `prime_endpoint_frames=0` selects `max(4096, 2 × actual WASAPI buffer frames)`, checked against endpoint capacity. Explicit thresholds must cover the actual device buffer. Prime makes Play available; a short, nonempty fully drained stream can prime below that threshold.

`rb_audio_stream_submit` checks generation, consecutive sequence (starting 0), exact relative start, whole-block bounds and finite Float32 words. It copies the entire block into native ownership on success. Result 13 is explicit no-consumption backpressure; the caller may retry those same bytes without holding a device control lock. Result 14 rejects stale generations and 15 rejects sequence/start/EOF mismatches. `rb_audio_stream_finish` requires the exact next sequence and declared accepted count. A full input count, an empty converter output block or a closed process pipe never substitutes for this EOF.

One dedicated native producer owns the converter. Incoming transport pieces refill a sliding 4096-frame source window and a bounded 4096-frame pending output window, matching the existing snapshot converter's exact process-call input/output capacities even after partial input consumption. The public SoXR profile and FP qualification are unchanged. Output can be appended to the fixed endpoint ring in partial writes; it never needs one output ring slot large enough for a 24× input block. Final NULL-input drain establishes the actual endpoint total. Equal-rate PCM remains a copied bit-exact path. The maximum explicit native PCM storage at the API capacity limits is 4,259,840 bytes: two 262144-frame stereo rings plus the two 4096-frame windows. This excludes SoXR's rate-dependent internal workspace, thread stacks and object metadata; it does not describe shared source-file storage or the managed transport queue.

The 160-byte `RBAudioStreamStatus` exposes source accepted/consumed/played counts, endpoint produced/submitted/played counts, queue use and peaks, priming, EOF and final-total flags, the actual buffer/rates and error metadata. `endpoint_total` stays 0 until `endpoint_total_final=1`. Release-published completion flags precede the monotonic counters they certify in each snapshot. Overflow-checked quotient/remainder mapping keeps source positions below source end until explicit EOF, final conversion drain and device-clock completion agree. Source-relative frame counts do not include the host's absolute suffix origin.

The device thread only consumes ready endpoint PCM, copies and scans peaks. It zero-fills only a legitimate final device-buffer remainder. Starvation before final EOF is an underrun fault. Pause freezes the measured device clock while the native producer may continue filling bounded storage. Resume/seek in the host cancel the old stream and create a newly validated suffix and converter; there is no native stream seek into cached output. `rb_audio_stream_cancel` stops/resets the endpoint, joins the producer and rejects all late submissions before returning success. A Stop or Reset failure remains a fault and a retry can finish cancellation; it is never reported as a successful stop. Begin, Play, Pause, Cancel and Status use the serialized COM-owning control worker. Submit/Finish use a separate short admission lock, with no capacity wait, so cancellation never waits for a full queue to drain. Destruction remains exclusive with all API calls.

This queue, producer schedule and endpoint conversion policy are application engineering. They do not establish the reference application's scheduler, physical playback, DAC equality, or new source-file admission limits.

## Build and verification

Build and verify the pinned public library first. On Windows, from the repository root in a Visual Studio developer environment:

```powershell
python Application/scripts/build-windows-soxr.py --output .local/builds/windows-soxr
cmake -S Application/Windows/NativeAudio -B .local/builds/native-audio -G Ninja -DCMAKE_BUILD_TYPE=Release -DREBASE_SOXR_LIBRARY="$PWD/.local/builds/windows-soxr/install/lib/soxr.lib" -DREBASE_SOXR_RUNTIME="$PWD/.local/builds/windows-soxr/install/bin/soxr.dll"
cmake --build .local/builds/native-audio
ctest --test-dir .local/builds/native-audio --output-on-failure --output-junit lifecycle.xml
```

CMake copies the supplied matching `soxr.dll` beside the native DLL and conversion tests. Distribution must retain that library and its notices. The library/runtime paths must come from the same verified build. On macOS use the pinned `Application/ThirdParty/build-soxr.sh` build, pass its installed dylib as `REBASE_SOXR_LIBRARY`, and use `Unix Makefiles` if Ninja is absent. Only portable components build there; WASAPI is Windows-only.

The default CTest suite executes `native_audio_portable_lifecycle`, `native_audio_rate_conversion` and `native_audio_bounded_stream`. Their binaries accept `--json PATH`; assertions remain enabled in Release. Controls cover identity bits, 44.1/48 kHz and 8/192 kHz boundaries, fractional/short/empty results, zero/stereo isolation and a late impulse through EOF, source/endpoint clock projection, near-end seeks, pause/reset/drain, invalid configuration, fault recovery, capacity, and injected allocation/backend failures. Injection checks the production failure paths; it is not evidence of an actual memory outage or driver failure. The original two portable receipts report `playback_tested:false` and `wasapi_compiled:false`. The additive `rebase_audio_stream_tests --json PATH` receipt uses schema `rebase.native-bounded-stream-controls.v1` and `physical_playback_tested:false`. Its authored controls compare 28 incremental outputs byte-for-byte with the snapshot oracle, exercise 40 cancellation races and 300 concurrent status cycles, explicit EOF/zero-output distinctions, maximum-size copied blocks, injected converter/allocation/Stop/Reset failures, and a 32,004,240-frame bounded drain with an incremental byte hash. The 24-hour control admits duration without materializing or draining a full day. The receipt records observed queue peaks; these are synthetic controls, not endpoint scheduling measurements.

Hosted Windows CI builds the WASAPI DLL and runs this read-only endpoint probe:

```powershell
& ./.local/builds/native-audio/rebase_wasapi_probe.exe --json endpoint.json
$probeExit = $LASTEXITCODE
# 0: endpoint observed; 77: no endpoint; other codes: failure.
# Neither 0 nor 77 establishes playback.
```

On an explicitly selected machine with a real output endpoint, `--allow-audio` opts into a quiet tone and lifecycle test. It deliberately chooses a source rate different from the endpoint, checks the rate receipt, copied-snapshot meters, clock advance, pause/resume, active seek, stop/reset, exact-end completion and active destruction. Successful execution reports `playback_tested:true` but still `audible_output_measured:false`; there is no loopback or DAC measurement. Unsupported formats/missing endpoints return 77, failures return 1, and invalid invocation/artifact writing returns 2. `REBASE_RUN_AUDIO_DEVICE_TESTS=ON` adds this opt-in test to CTest.

Historical local evidence under `evidence/2026-10-23` predates rate adaptation and remains unchanged. New local portable checks do not establish Windows compilation, real device behavior or equivalence with either platform's output system.

## Public implementation references

- [IAudioClient::GetMixFormat](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient-getmixformat): shared-engine format discovery and supported initialization format.
- [IAudioClient::Initialize](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient-initialize): shared-mode event initialization and event-handle requirements.
- [IAudioClock::GetPosition](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclock-getposition): clock units/frequency, approximate readings and stream-relative time.
- [IAudioClient::Reset](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient-reset): stop before flushing/resetting the clock.
- [Pinned public SoXR API](../../ThirdParty/soxr-0.1.3/src/soxr.h): explicit profile, consumed/produced counts and NULL-input EOF.

No proprietary executable is used by this adapter or its authored controls.
