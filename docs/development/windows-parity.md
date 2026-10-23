# Windows parity

The comparison baseline is the macOS **0.21.1** application, including its bundled example beat. A Windows application has not been released yet. The first native WPF host is implemented and undergoing package/runtime checks. Work is additive: the public repository, research export, and existing Mac downloads remain available.

## Shared implementation

Windows and macOS use the same authored Swift project/CPR models and C DSP sources. The portable Swift target selects those source files directly; it does not translate the engine into another language. PCM ownership, file decoding, device output, filesystem operations, and presentation are explicit boundaries.

The shared renderer extracts ordinary clip preparation and Float32 accumulation into `PCMRenderer`. macOS now calls that implementation through its AVFoundation decoder. The portable WAV adapter reads bounded mono/stereo PCM16/24/32 and float32/64 RIFF files. It does not support compressed, extensible, big-endian, or RF64 inputs yet. Native CPR streams, provenance checks, and their distinct reconstructed rate-conversion policies remain separate.

Document commands, selection, snapping and bounded undo/redo now share `ProjectEditing` and `ProjectEditHistory`; the Mac session uses those same sources. Windows presentation and file operations remain separate integration work.

The x64 lane explicitly qualifies the floating-point environment before enabling six previously arm64-only kernels. Independent numerical controls and altered-environment rejection tests exercise the extension. Passing these controls demonstrates reconstructed-code portability within the tested domain; it is not evidence from a proprietary Windows reference executable.

## Acceptance ledger

| Area | Required Windows acceptance | Current scope |
| --- | --- | --- |
| Project/CPR models | Same validation, decoding, opaque preservation, recovery profiles and report re-verification | Shared-source component tests and inspection CLI |
| Ordinary audio | Same trim, automation, pan, interpolation, mute/solo and accumulation; compare bundled example PCM on both architectures | Shared renderer, WAV adapter and comparison checks |
| Native DSP | Same accepted domains, exact independent controls, explicit environment rejection | Windows x64 Debug/Release passed 5,442 cases and 18,380 checks each; see the [retained run](../../research/publication/windows-portability/run-39915872920/observation.json) |
| Project files | Load/save/reopen across OS; source checks, containment, junction/drive/UNC/ADS handling and atomic replacement | Shared store and bounded snapshot copying implemented; local checks pass; native Windows filesystem checks pending |
| Editing | Move/trim/split/delete, snap, undo/redo, tempo/signature and preserved-clock conversion | Shared commands integrated into macOS and the Windows session protocol; Windows Debug component checks pass; host integration awaiting native CI |
| Timeline/mixer | Four-track example, waveforms, automation, gain/pan, keyboard access and dirty-project prompts | WPF timeline and mixer implemented; window checks pending; waveform and automation editing parity remain open |
| Native playback | Play/pause/seek/stop, meters, completion, cancellation and supported device formats through WASAPI | Windows Debug/Release DLL compilation and 89 lifecycle controls each passed; hosted endpoints unavailable; real playback verification pending |
| CPR workflows | Review, attachment, source inspection, every current audition mode and overlap-track playback | Full Windows integration pending |
| Interchange | Audio formats, DAWproject import/export and 64-bit ambisonic export | Windows adapters pending |
| Distribution | Runtime dependencies, icon, bundled example, clean-machine launch and downloadable Windows app | Self-contained package workflow implemented, including dependency closure, app-local module checks and example; native execution pending |

Hosted Windows builds can establish compilation, deterministic processing, and the specific WPF window operations exercised by automation. They do not establish physical input, file-dialog behavior, or output through a real audio endpoint. Those checks require an interactive Windows environment.

The [retained Windows component run](../../research/publication/windows-portability/run-39920053417/observation.json) includes a successful SoXR DLL/API probe and exact example exports. The overall run failed because its Release Swift test runner discovered zero tests. A test-link diagnostic is pending verification; a successful render does not substitute for executed tests.

The [Windows host](../../Application/Windows/RebaseWindows/README.md) sends versioned commands to the shared Swift session, then verifies rendered snapshot metadata and bytes before loading the native adapter. Its current playback requires an endpoint at the exact project rate. It does not yet expose all Mac workflows; the ledger remains open.

## Parallel development gate

Changes to shared semantics must run the macOS and Windows conformance lanes. Record exact toolchain, architecture, configuration, test counts and observed output. Keep static reference evidence, independent numerical controls, reconstructed application behavior, and hardware observations distinct. Preserve original research seals and private fixture boundaries.

Do not declare parity from a successful component build. The next integration order is: portable project store; shared renderer/ABI; native Windows window and WASAPI integration; complete the ledger above; then continue new REA behavior work on both platforms together.

## Primary documentation

- [Swift on Windows](https://www.swift.org/install/windows/manual/)
- [Windows runner inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)
- [Swift C export proposal](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0495-cdecl.md)
- [WinUI 3](https://learn.microsoft.com/en-us/windows/apps/winui/winui3/)
- [WASAPI](https://learn.microsoft.com/en-us/windows/win32/coreaudio/wasapi)
- [WAVEFORMATEX](https://learn.microsoft.com/en-us/windows/win32/api/mmreg/ns-mmreg-waveformatex)

Build commands and pinned toolchain details are in [WINDOWS-CI.md](../../Application/WINDOWS-CI.md).
