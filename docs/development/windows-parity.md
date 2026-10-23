# Windows parity

The behavior comparison baseline is the macOS **0.21.1** application, including its bundled example beat. The visual target is the [Cubase Pro 15.0.30 Windows interface](windows-ui-fidelity.md). The [Windows development preview](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-windows-preview.2) includes the native WPF package, shared waveforms, musical ruler and bounded source-event journey. The captured selector/header defects have been corrected; exact reference fidelity remains open. The public repository, research export, and existing Mac downloads remain available.

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
| Project files | Load/save/reopen across OS; source checks, containment, junction/drive/UNC/ADS handling and atomic replacement | Shared store and bounded snapshot copying passed Windows Debug/Release tests; the actual host saved and reopened an edited example. File-dialog interaction remains unverified. |
| Editing | Move/trim/split/delete, snap, undo/redo, tempo/signature and preserved-clock conversion | Shared commands passed Windows Debug/Release checks. The actual window exercised selection, move, undo, redo, Save As and reopen. Pointer/keyboard journeys and remaining commands require broader UI coverage. |
| Timeline/mixer | Four-track example, waveforms, automation, gain/pan, keyboard access and dirty-project prompts | Native checks cover the editable inspector, mixer controls, shared bars/beats ruler, 11 real waveforms, four visible rows and fixed headers during scrolling. Three actual client-area captures were visually reviewed. Physical gestures, automation editing and full reference layout/control fidelity remain open. |
| Native playback | Play/pause/seek/stop, meters, completion, cancellation and supported device formats through WASAPI | Windows Debug/Release DLL compilation and 89 lifecycle controls each passed; hosted endpoints unavailable; real playback verification pending |
| CPR workflows | Review, attachment, source inspection, every current audition mode and overlap-track playback | Shared strict stereo PCM24 source attachment/export and event-local audition implemented. Windows helper/window attachment, undo/redo, export and provenance checks passed with authored input. Device audition is unverified. Native conversion, placed-clock and overlap-track modes remain unintegrated. |
| Interchange | Audio formats, DAWproject import/export and 64-bit ambisonic export | Windows adapters pending |
| Distribution | Runtime dependencies, icon, bundled example, clean-machine launch and downloadable Windows app | Preview package passed dependency closure, app-local loaded-module checks, native window smoke, manifest/example checks and archive privacy review. Download and extraction instructions are in the [Windows installation guide](../install/windows.md). Interactive Windows 11 launch remains unverified. |

Hosted Windows builds can establish compilation, deterministic processing, and the specific WPF window operations exercised by automation. They do not establish physical input, file-dialog behavior, or output through a real audio endpoint. Those checks require an interactive Windows environment.

The [latest retained component run](../../research/publication/windows-portability/run-39964618713/observation.json) executed 90 Windows Swift tests in each configuration, with one opt-in generator skipped. Portable macOS executed 92 per configuration; the public Mac application suite executed 262 tests with 117 explicit private-fixture/generator skips. All four Swift lanes executed the 14 new CPR review controls plus the existing six Windows/seven macOS importer cases. Each production helper passed 91 checks and all 16 CPR import gates. Ordinary example PCM, source-event output, source/report hashes, waveform peaks and ruler results matched across platforms and configurations.

The [corresponding application run](../../research/publication/windows-portability/application-run-39962134728/observation.json) passed 91 packaged-helper checks, 155 host controls and 65 actual-window checks, including the new CPR review/import journey. Independent image review rejected its CPR capture: rendering a margin-bearing content panel clipped the action buttons and omitted the window background. The original image and functional results remain unchanged. This candidate is not released; the capture correction requires its own native run. The prior [UI milestone](../../research/publication/windows-portability/application-run-39949650116/observation.json) verifies the Channel/Inspector and corrected nameplate alignment. These checks do not establish complete parity or reference fidelity.


The first [capture-correction run](../../research/publication/windows-portability/application-run-39964618757/observation.json) stopped at a strict alpha assertion after 38 native checks. No PNG or ZIP was produced. Independent inspection of the existing accepted WPF images found alpha 254 alongside 255, so the follow-up records image diagnostics before checking the one-step coverage tolerance. Footer geometry and the opaque application background remain required; that follow-up still needs a successful native run.

The [Windows host](../../Application/Windows/RebaseWindows/README.md) sends versioned commands to the shared Swift session, then verifies rendered snapshot metadata and bytes before loading the native adapter. Its current playback requires an endpoint at the exact project rate. It does not yet expose all Mac workflows; the ledger remains open.

## Parallel development gate

Changes to shared semantics must run the macOS and Windows conformance lanes. Record exact toolchain, architecture, configuration, test counts and observed output. Keep static reference evidence, independent numerical controls, reconstructed application behavior, and hardware observations distinct. Preserve original research seals and private fixture boundaries.

Do not declare parity from a successful component build. After native verification of reviewed raw CPR import, the next compatibility integrations are the remaining native conversion/placed/overlap audition modes, device-rate output, interchange and automation workflows. Continue shared REA behavior work through both platform lanes; the full ledger remains the acceptance target.

### Reviewed CPR import

The shared parser, recovery profiles, historical report replay and `CPRProject.importProject` now compile portably. The importer uses exclusive staging and the existing Windows-aware `ProjectFileIO` publication helpers; it verifies the staged model and exact original/report bytes before publishing without replacement. [Local authored controls](../../research/publication/windows-portability/cpr-import-local-20261023/observation.json) passed through both the portable and native macOS core targets. The subsequent [native cross-platform run](../../research/publication/windows-portability/run-39951105337/observation.json) executed the six Windows and seven macOS importer cases in both configurations without failures. These cover the tested publication paths; broader Windows junction/reparse and interactive dialog behavior remain open.

The Windows implementation now exposes inspect → review → explicitly accepted partial import through the shared session and a native review window. Local checks passed through the portable engine, normal Mac importer target, production Release helper and host controller. The first native Windows run passed the functional journey but failed independent capture review, as recorded above. The [local record](../../research/publication/windows-portability/cpr-review-local-20261024/sequence.json) separates those scopes.

Bind review confirmation to the source path/name/hash and interpretation profile, reject changed input, preserve the full original and report, and never replace an existing destination. Inspection/cancellation must leave the active project/history unchanged; import must preserve dirty-project protection and only switch state after successful validated publication. Historical reports retain their original frozen interpretation.

Use a bounded review projection instead of duplicating the entire report and recovered project in the helper's response. `CPRInspection` computed counts and `canImport` need explicit serialization. Authored raw CPR and the existing source-audition fixture can exercise the shared path on both operating systems, with filename-derived metadata accounted for. Windows reparse/containment cases and uncertain publication outcomes after a helper timeout need explicit handling. No proprietary executable is required.

## Primary documentation

- [Swift on Windows](https://www.swift.org/install/windows/manual/)
- [Windows runner inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)
- [Swift C export proposal](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0495-cdecl.md)
- [WinUI 3](https://learn.microsoft.com/en-us/windows/apps/winui/winui3/)
- [WASAPI](https://learn.microsoft.com/en-us/windows/win32/coreaudio/wasapi)
- [WAVEFORMATEX](https://learn.microsoft.com/en-us/windows/win32/api/mmreg/ns-mmreg-waveformatex)

Build commands and pinned toolchain details are in [WINDOWS-CI.md](../../Application/WINDOWS-CI.md).
