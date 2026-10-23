# Windows parity

The behavior comparison baseline is the macOS **0.21.1** application, including its bundled example beat. The visual target is the [Cubase Pro 15.0.30 Windows interface](windows-ui-fidelity.md). The [Windows development preview](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-windows-preview.6) includes the native WPF package, compact/normal track rows, adjustable panels, shared waveforms, musical ruler, volume/pan automation editor, reviewed partial CPR import and bounded source-event journey. The captured selector/header defects have been corrected; exact reference fidelity remains open. The public repository, research export, and existing Mac downloads remain available.

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
| Timeline/mixer | Four-track example, waveforms, automation, gain/pan, keyboard access and dirty-project prompts | Native checks cover the editable inspector, mixer controls, shared bars/beats ruler, 11 real waveforms, four visible rows and fixed headers during scrolling. Twelve actual client-area captures were visually reviewed, including CPR review and the automation editor at minimum size. Physical gestures and full reference layout/control fidelity remain open. |
| Automation | Shared volume/pan point identity, interpolation, Read state, undo/redo and rendered samples | The selected-track editor passed native point/curve/parameter/Read/error/history checks; helper and cross-platform lanes match edited/restored audio. Edits commit immediately, while the Mac editor uses Apply/Cancel. Inline lanes, writing modes and reference presentation remain open. |
| Native playback | Play/pause/seek/stop, meters, completion, cancellation and supported device formats through WASAPI | Windows Debug/Release DLL compilation and 89 lifecycle controls each passed; hosted endpoints unavailable; real playback verification pending |
| CPR workflows | Review, attachment, source inspection, every current audition mode and overlap-track playback | Reviewed partial CPR import and historical-report retrieval passed through the shared helper and native window. Shared strict stereo PCM24 source attachment/export and event-local audition are implemented; attachment, undo/redo, export and provenance checks passed with authored input. Device audition is unverified. Native conversion, placed-clock and overlap-track modes remain unintegrated. |
| Interchange | Audio formats, DAWproject import/export and 64-bit ambisonic export | Windows adapters pending |
| Distribution | Runtime dependencies, icon, bundled example, clean-machine launch and downloadable Windows app | Preview package passed dependency closure, app-local loaded-module checks, native window smoke, manifest/example checks and archive privacy review. Download and extraction instructions are in the [Windows installation guide](../install/windows.md). Interactive Windows 11 launch remains unverified. |

Hosted Windows builds can establish compilation, deterministic processing, and the specific WPF window operations exercised by automation. They do not establish physical input, file-dialog behavior, or output through a real audio endpoint. Those checks require an interactive Windows environment.

The [latest retained component run](../../research/publication/windows-portability/run-40040015052/observation.json) passed all 13 jobs. Windows Swift executed 98 tests in each configuration with one opt-in skip; portable macOS executed 100 per configuration with one skip. The public Mac application suite executed 266 tests with 117 explicit private-fixture/generator skips. The four portable lanes include eight automation tests alongside the existing CPR review/import controls. Each production helper passed 169 checks, including all 16 CPR import gates. Ordinary example PCM, source-event output, source/report hashes, waveform peaks, ruler results and edited/restored automation audio matched across platforms and configurations.

The [preview.6 application run](../../research/publication/windows-portability/application-run-40040015003/observation.json), from `32e6d37`, passed 169 packaged-helper checks, 191 host controls and 102 actual-window checks. Its twelve native client images passed root and independent review for the demonstrated states. Three automation captures at 664 × 521 show restored five-point Volume, rejected nonfinite input and Read-off/manual-value behavior. Native edits exercise Volume, Pan, parameter switching, curve insertion, deletion and shared undo/redo; undo restores the exact original WAV. Native device playback was not tested; prepared-audio invalidation has separate portable fake-audio controls.

CPR review preserves its complete footer at 814 × 611 and at the 634 × 441 minimum-size error state. The [independent downloaded-package audit](../../research/publication/windows-portability/application-run-40040015003/candidate-review.json) verified the archive digest, file manifest, committed example and runtime closure. All eight measured workspace states preserve the session and selection, with no unnecessary vertical scrolling. Compact/normal rows, pane toggles, bounded splitter and fader geometry pass their native checks. The top-row stack is 107 DIP, returning 19 DIP to the arrangement. Long-name fields, source-only unavailable timing and full-width row dividers pass their scoped checks. The requested 1400-DIP window remained at 1100 DIP on the hosted display, so wider-desktop geometry remains unverified. These results establish the exercised scope; full parity and reference fidelity remain open.

The earlier [functional candidate](../../research/publication/windows-portability/application-run-39962134728/observation.json) passed 65 native checks but its CPR image clipped the action buttons and omitted the window background. It was rejected and not released. The first [capture-correction run](../../research/publication/windows-portability/application-run-39964618757/observation.json) then stopped after 38 native checks at an exact-alpha assertion; no PNG or ZIP was produced. Both original observations remain unchanged. The successful follow-up writes PNG diagnostics before checking complete client coverage with the observed alpha 254–255 range, alongside footer geometry and viewport bounds.

The [Windows host](../../Application/Windows/RebaseWindows/README.md) sends versioned commands to the shared Swift session, then verifies rendered snapshot metadata and bytes before loading the native adapter. Its current playback requires an endpoint at the exact project rate. It does not yet expose all Mac workflows; the ledger remains open.

## Parallel development gate

The accepted automation editor exposes the shared volume/pan lane model with revision-bound point edits, Read controls, unchanged-edit preservation and undo/redo. The native run exercises the real helper and WPF editor, compares original/restored example bytes against the existing lock, and captures minimum-size Read-off, invalid-input and restored states. Four portable lanes also match edited/restored audio and saved-project roundtrips. These checks remain required when the shared behavior changes.

Windows commits each successful edit immediately and Close retains it; macOS currently defers its editor transaction until Apply. Inline automation lanes, write/touch/latch modes and reference-equivalent presentation remain open.

Changes to shared semantics must run the macOS and Windows conformance lanes. Record exact toolchain, architecture, configuration, test counts and observed output. Keep static reference evidence, independent numerical controls, reconstructed application behavior, and hardware observations distinct. Preserve original research seals and private fixture boundaries.

Do not declare parity from a successful component build. Reviewed raw CPR import now has bounded native-window evidence. The next compatibility integrations are the remaining native conversion/placed/overlap audition modes, device-rate output, interchange, inline automation and writing workflows. Continue shared REA behavior work through both platform lanes; the full ledger remains the acceptance target.

### Reviewed CPR import

The shared parser, recovery profiles, historical report replay and `CPRProject.importProject` now compile portably. The importer uses exclusive staging and the existing Windows-aware `ProjectFileIO` publication helpers; it verifies the staged model and exact original/report bytes before publishing without replacement. [Local authored controls](../../research/publication/windows-portability/cpr-import-local-20261023/observation.json) passed through both the portable and native macOS core targets. The subsequent [native cross-platform run](../../research/publication/windows-portability/run-39951105337/observation.json) executed the six Windows and seven macOS importer cases in both configurations without failures. These cover the tested publication paths; broader Windows junction/reparse and interactive dialog behavior remain open.

The Windows implementation exposes inspect → review → explicitly accepted partial import through the shared session and a native review window. Preview.3 passes that authored native journey, including cancellation, changed-source rejection, dirty protection, destination cancellation, preserved source and historical report. The [local record](../../research/publication/windows-portability/cpr-review-local-20261024/sequence.json) and separate failed native observations retain the earlier results.

Review confirmation is bound to the source path/name/hash and interpretation profile. Changed input is rejected; the full original and report are preserved in a new destination. Inspection and cancellation leave the active project/history unchanged. Import retains dirty-project protection and switches the session only after validated publication and readback. Historical reports retain their original frozen interpretation.

The helper serializes a bounded review projection with explicit counts and import eligibility: at most 32 items and 128 KiB per page, backed by an import report limited to 8 MiB. The native fixture exercises 15 items on one page; shared and host controls cover pagination and bounds separately. A published-but-unconfirmed import revokes the review and tells the user to inspect the destination before retrying; failed-save confirmation remains required even if a later state reports clean. Broader Windows reparse/containment and interactive dialog behavior remain open. No proprietary executable was used for these authored controls.

## Primary documentation

- [Swift on Windows](https://www.swift.org/install/windows/manual/)
- [Windows runner inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)
- [Swift C export proposal](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0495-cdecl.md)
- [WinUI 3](https://learn.microsoft.com/en-us/windows/apps/winui/winui3/)
- [WASAPI](https://learn.microsoft.com/en-us/windows/win32/coreaudio/wasapi)
- [WAVEFORMATEX](https://learn.microsoft.com/en-us/windows/win32/api/mmreg/ns-mmreg-waveformatex)

Build commands and pinned toolchain details are in [WINDOWS-CI.md](../../Application/WINDOWS-CI.md).
