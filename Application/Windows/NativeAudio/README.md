# Native Windows audio foundation

This is the Windows 10+ output adapter for the shared Rebase rendering work. It is a standalone C ABI and WASAPI shared-mode backend, not yet a Windows application, project renderer, or full device-support claim. The public header is `include/rebase_windows_audio.h`.

The caller supplies a complete, pre-rendered, interleaved Float32 stereo snapshot. The adapter validates all samples, copies the snapshot during `rb_audio_set_source`, then owns the copy. The caller must keep the input memory stable until that call returns and may release it afterward. Accepted source lengths are 1–32,000,000 frames; accepted integral rates are 8,000–192,000 Hz. This bounded snapshot design consumes memory proportional to project length. Streaming from disk remains separate work.

## Rate and format boundary

`rb_audio_default_format` discovers the default multimedia render endpoint's mix rate and channel count. Its `float32` flag means that the mix is specifically Float32 **stereo** with either the conventional left/right channel mask or no mask. Discovery exposes no endpoint name, device identifier, or personal machine information.

The snapshot must already have that exact mix rate and stereo layout. Source-rate conversion belongs upstream in the shared rendering layer. This adapter does not enable `AUTOCONVERTPCM`, select an implicit rate-conversion algorithm, or downmix multichannel audio. An unsupported endpoint or mismatched rate returns `RB_AUDIO_FORMAT`. Windows shared-mode processing and device effects can still affect output; this API does not claim bit-identical DAC output.

## Ownership and lifecycle

One MTA worker owns every COM audio object, snapshot, clock observation, and transport state. All public operations run synchronously through a serialized command queue. Callers may submit operations from different threads, but must not destroy a handle concurrently with another call. They must not call the API from an audio callback. Destruction signals the command loop, stops the stream, releases COM objects on their owning thread, and joins the worker. It does not promise to interrupt a blocking operating-system/driver call.

The worker waits for WASAPI's event notification. Its data path consists of bounded copies, zero-filling the final buffer, and peak scans. It performs no file I/O, IPC, allocation, Swift callback, or managed-runtime callback in that data path. Source replacement may allocate and close/open a device as a control operation. Signalled output events are serviced between commands so sustained UI polling does not starve rendering. No hard real-time scheduling or low-latency guarantee is claimed in this foundation.

| Operation | Result |
| --- | --- |
| Create | Empty handle; no device opened or sound played. |
| Set source | Validate and copy input; stop previous stream; open default endpoint; enter ready. Invalid input preserves the previous source; an open failure enters fault. |
| Play | Prime a ready stream or resume a paused stream. Repeated play is harmless. A finished stream needs a seek or stop first. |
| Pause | Stop the device clock and retain queued audio. Repeated pause is harmless. |
| Stop | Stop and reset WASAPI; flush queue; rewind to frame zero; enter ready. |
| Seek | Stop/reset/flush, set a new source position and clock origin, then resume if previously playing. Seek to end enters finished. Seeking while paused enters ready. |
| Status | Observe the device clock. Position remains bounded and monotonic within the current generation. It is not merely the count enqueued. |
| Device error | Enter fault, preserve the error and HRESULT, close the stream. Setting a new valid source is the recovery boundary. |

Stop, seek, source replacement, and fault each advance `generation`, allowing a host to discard obsolete UI observations. Clock progress beyond submitted source frames before the final buffer is an underrun fault; inserted silence must not be reported as delivered source audio. At the tail, position is capped at the final source frame. `submitted_peak_left/right` describe the last submitted source block before Windows processing, not a speaker measurement. Paused, finished, and fault states clear these meters. `clock_reading_approximate` exposes `IAudioClock::GetPosition` returning `S_FALSE`.

Output structs are written only when the public operation succeeds. A successful status query can report a fault state; inspect `phase`, `result`, and `hresult`. Format discovery is rejected while playing. Default-device changes are not followed automatically; an invalidated device faults and a source reload can reopen the new default. Recording, device selection, exclusive mode, ASIO, disk streaming, and frontend integration are outside this adapter.

## Build and verification

```sh
cmake -S Application/Windows/NativeAudio -B build-native-audio -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-native-audio
ctest --test-dir build-native-audio --output-on-failure --output-junit lifecycle.xml
```

Use a Visual Studio developer environment with the Windows SDK on Windows. The CMake target builds `RebaseWindowsAudio.dll` and `rebase_wasapi_probe.exe` there; keep them together. On other platforms only the portable transport model and its tests build. On macOS without Ninja, use `-G "Unix Makefiles"`.

The default CTest suite exercises the portable transport model, not WASAPI. Its assertions remain enabled in Release. `rebase_audio_lifecycle_tests --json lifecycle.json` emits machine-readable results, with `playback_tested:false`.

Hosted Windows CI should then run the read-only probe and retain its JSON and exit code:

```powershell
& ./build-native-audio/rebase_wasapi_probe.exe --json native-audio-endpoint.json
$probeExit = $LASTEXITCODE
# 0: endpoint observed; 77: no endpoint; any other code: probe failure.
# Neither 0 nor 77 from this command establishes playback.
```

On an explicitly selected machine with an output endpoint, opt in to a quiet tone and native lifecycle test:

```powershell
& ./build-native-audio/rebase_wasapi_probe.exe --allow-audio --json native-audio-device.json
```

The device test checks snapshot-copy ownership through submitted meters, real device-clock advance, pause/resume, active seek, stop/flush/rewind, seek-to-end, natural completion, and active destruction. A successful run reports `playback_tested:true` and `device-lifecycle-verified`; it still reports `audible_output_measured:false`. It does not record loopback or measure the DAC. Missing endpoints and unsupported mix formats return 77 with explicit unavailable results. Other failures return 1, invalid arguments/artifact output failures return 2. `-DREBASE_RUN_AUDIO_DEVICE_TESTS=ON` adds this opt-in test to CTest, where 77 is a skip rather than audio success.

Local portable evidence is in `evidence/2026-10-23`. Windows compilation, endpoint behavior, frontend integration, and hardware output need their own evidence; local portable success establishes none of them.

## Public implementation references

- [IAudioClient::Initialize](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient-initialize): shared-mode event initialization, duration/periodicity, and event-handle requirements.
- [IAudioClock::GetPosition](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclock-getposition): device clock units, approximate readings, and stop/reset semantics.
- [IAudioClient::Reset](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient-reset): flushing requires a stopped stream.
- [Low-latency audio](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/low-latency-audio): device-dependent periods and scheduling considerations for later latency work.

The implementation uses public Windows APIs and independently authored lifecycle controls. It does not execute the proprietary reference or establish reference-application equivalence.
