# Rebase Windows host

This WPF/.NET 10 host uses the shared Swift session for project loading, editing, undo, tempo, snapping, save, and WAV rendering, and the native WASAPI DLL for transport. The timeline and four-channel example are real project views, not a static mockup. The UI supports selection, pointer or numeric move/trim, split/delete, track gain/pan/mute/solo, volume/pan automation, undo/redo, tempo, snap, Save/Save As, WAV export, and play/pause/stop/seek with submitted-sample peaks.

The Windows host is an initial application milestone. Recording, plugins, advanced media formats, project-level CPR playback, streaming and the remaining macOS workflows are not integrated. Playback accepts a default Float32 stereo endpoint at 8–192 kHz; the native adapter explicitly converts differing snapshot rates with pinned public SoXR before playback. Source and converted snapshots are each bounded to 32 million stereo frames. This device policy is distinct from the recovered CPR conversion modes. Hardware output remains unverified. The included example opens as a separate editable copy.

Imported project packages can expose retained source events in the inspector. Attach PCM explicitly, then audition or export a checked stereo source event. This uses a distinct event-local transport, rechecks source/media every play, resume, and seek, and does not apply project timing, track effects, mixer, or automation.

File → Import CPR opens a paginated review of the recovered subset, unresolved
content and application defaults. Import Supported Data asks about unsaved
changes and creates a new project folder containing the exact source and import
report. A file changed after review is rejected. File → Import Report shows the
verified historical baseline; editing the project does not rewrite that report.
Canceling review or destination selection does not replace the current project.

Real clip waveforms come from the shared Swift source-envelope reducer. Background replies are revision/interval checked and cannot overwrite document state.

The musical ruler uses shared Swift bar/beat positions, validated against the current revision, viewport extent, and zoom. A Seconds selector is also available. Track names and mute/solo controls stay fixed during horizontal scrolling. The selected track's inspector volume, pan, mute, and solo controls use the same shared edits and undo history as the lower mixer.

Build with the pinned .NET SDK chosen by the application CI lane (10.0.402), without toolkit NuGet packages:

```powershell
dotnet build Application/Windows/RebaseWindows/RebaseWindows.csproj -c Release
dotnet run --project Application/Windows/RebaseWindows/Tests/RebaseWindows.Controls.csproj -c Release
```

The app folder must include `Rebase.exe`, the self-contained .NET desktop runtime, `rebase-session.exe` with its Swift/runtime dependencies, `RebaseWindowsAudio.dll`, and `Examples/Rebase Preview.rebaseproj`. Copy the complete published folder. Building WPF on macOS with `EnableWindowsTargeting` checks compilation only; it does not run Windows UI code.

The app launches its helper by absolute path and uses the [local protocol](../SESSION-PROTOCOL.md). SafeHandle and a serialized native-operation gate prevent destruction during an audio call. Rendering runs asynchronously while the UI remains responsive. Document mutations invalidate previously prepared audio; the frontend checks the render's revision and hash before playback.

Responses are bounded while reading, with a 60-second command deadline (120 seconds for renders, CPR inspection/report and import). A failed protocol exchange stops that helper instead of risking later replies being mistaken for another request. If an import result cannot be confirmed, check its destination after reopening the app: publication may already have completed. The host never automatically retries or overwrites that destination. Closing waits for queued edits before deciding whether to ask about unsaved changes. Normal shutdown sends EOF so the helper can remove its temporary example copy, with a bounded shutdown grace before termination.

## Windows smoke run

```powershell
Rebase.exe --smoke --smoke-json C:\evidence\window-smoke.json
```

This opens an actual WPF window, invokes its example/open and editing buttons through WPF automation peers, checks shared undo/redo, saves/reopens a temporary project, validates a shared render, probes the default endpoint without starting audio, and writes `native-app-visual.png` beside the JSON. The PNG renders the client content at 96 pixels per logical inch; it excludes the operating-system frame. Actual outer/client dimensions and display DPI are recorded in `window_bounds`. File dialogs and physical mouse/keyboard interaction need separate human or desktop-automation verification.

Follow-up smoke also drives inspector/mixer RangeValue and inspector/mixer/track Toggle automation, checks shared state and synchronized mixer controls, verifies undo/redo and focus return, and compares the example's returned bar 2 at 2.5 seconds with actual musical-ruler label placement. A zoomed horizontal scroll must move events while all track-header window coordinates remain fixed. This writes `native-timeline-scroll-visual.png` and a coordinate receipt before restoring the default view.

Exit 0 means those checks passed; 1 means a failure; 2 means invalid invocation or artifact-writing failure. The scenario has a 120-second deadline; CI should enforce an outer 180-second process timeout. Missing audio endpoints are recorded as unavailable, never playback success. Every smoke record has `playback_tested:false`. Hardware playback remains the separate explicit `rebase_wasapi_probe --allow-audio` procedure.

`Tests/RebaseWindows.Controls.csproj` exercises protocol identifiers, casing, invalid replies, stale render revisions, byte/hash checks, and malformed/nonfinite snapshot rejection. Those portable controls do not execute WPF or WASAPI. No Windows runtime or device success follows from cross-compilation or these controls alone.


## Windows interface refinement

The current layout uses the implemented portions of the Windows project window described in the [official Cubase Pro 15.0.30 Operation Manual](https://www.steinberg.help/api/khub/documents/O4PvzgK5U8lOyn4ANi_gKg/content), pages 12 (Windows screenshot provenance), 54 (project window), 76 (track inspector), 306 (integrated transport), and 434–435 (lower-zone mixer). Authored controls use compact top rows, a gray event canvas, a narrow inspector, lower-zone channel strips, and bottom transport. Unsupported reference controls are not represented as working controls. This is a bounded application implementation, not an exact or complete interface recreation. Vendor screenshots and manual bytes are not included in this repository.

DWM dark-caption opt-in follows [Microsoft's documented API](https://learn.microsoft.com/windows/apps/desktop/modernize/apply-windows-themes). Its HRESULT is recorded by smoke; the WPF visual-tree PNG does not capture or validate the operating-system frame.

For the optional authored source-event smoke, append `--smoke-source-project ABSOLUTE_PACKAGE --smoke-source-media ABSOLUTE_WAV`. Both paths are required together and stay outside the shipped app. The scenario opens a scratch copy, selects the source-event UI item, attaches media through the actual button handler with a supplied path, checks undo/redo, and exports through the actual button handler. File dialogs remain untested. It records provenance/output hashes and `native-source-visual.png`, then returns to the bundled beat, waits for all real waveform geometry, checks that all four rows fit, and captures `native-app-visual.png`. The same authored input also drives reviewed CPR import: cancel, changed-source rejection, dirty protection, destination cancellation, publication and historical-report retrieval. It writes `native-cpr-review-visual.png`, `native-cpr-review-minimum-error-visual.png` and matching alpha diagnostics, while checking footer geometry and available review space. The extended scenario allows 180 seconds; the outer process timeout is 240 seconds. It never starts audio.

[Windows preview 6](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-windows-preview.6), built from `32e6d37`, passed [102 actual-window checks, 191 host controls and 169 helper checks](../../../research/publication/windows-portability/application-run-40040015003/observation.json). The shared Release gate executed 98 tests with one explicit opt-in skip and no failures. All 16 CPR process gates passed, preserving the authored source/report and exact audio locks. The [independent archive audit](../../../research/publication/windows-portability/application-run-40040015003/candidate-review.json) checks the downloaded bytes, file manifest, committed example and runtime closure.

Twelve reviewed native captures show the arrangement, source attachment/export, anchored track headers, CPR review, workspace states, long names and the automation editor. Three 664 × 521 automation client captures retain the full curve, point list, fields and footer in restored, invalid-input and Read-off states. Both CPR review captures retain the complete footer and observed message. The original rejected capture and failed strict-alpha run remain in the research record. The wider-window request remained constrained to 1100 DIP. Native pointer drag, physical keyboard interaction, file dialogs and hardware audition need further desktop/device verification. Full feature and reference fidelity remain ongoing work.


The workspace defaults to 44-DIP Compact rows and offers 68-DIP Normal rows. Left/Mixer toggles return their space to the arrangement; the lower-zone divider supports bounded pointer and keyboard resizing. Faders adapt to the mixer height, Inspector sections collapse, and ordinary clip editing stays disabled for retained source events. Native checks record actual content viewports, extent/scroll relationships, state hashes, hit targets, splitter limits and source-selection transitions. The separate selection-control scratch project preserves its original source/report sidecars and is never packaged. Physical gestures remain unverified.

## Automation editing

`Project → Track automation…` and the selected-track Inspector open a volume/pan editor. Select a point to change its time, value or outgoing Linear/Hold segment; Add or a curve click creates a point. Read controls whether the lane affects rendering without deleting its points. Edits enter the shared project undo history immediately, and Close retains successful edits. The macOS editor currently uses an Apply/Cancel transaction instead.

The shared helper checks the project revision, parameter bounds and point identity before each edit. Numeric drafts keep their original revision and are rejected if the project changes. Unchanged edits preserve redo history. Existing larger lanes remain readable and editable, although session commands cannot grow a lane beyond 4,096 points; curves over 16,384 points explicitly report that drawing is unavailable.

Native checks exercise the opened editor through automation peers, injected keyboard events and the production curve-coordinate callback. They verify Volume and Pan edits, parameter switching, Read-off point preservation, invalid/stale draft rejection, deletion, undo/redo and unchanged selection. Undo restores the locked original WAV; four portable lanes match edited/restored audio. These are programmatic UI journeys, not physical input or device playback. Prepared playback invalidation is covered separately with portable fake-audio controls. This is authored application behavior; inline arrangement lanes, write/touch/latch modes and reference-equivalent presentation remain separate work.

## Source Audio integration

Select a retained event and choose **Source audio…** to inspect eight shared modes: original rate, three placed clocks, complete saved-clock track, and conversion modes 0/1/2. Availability describes preparation only. Each export, play, resume or seek rechecks the preserved source and required attachments; complete-track checks include covered contributors. Exports write an adjacent `.source-audition.json` proof. Existing outputs are never replaced.

Playback and export are bounded to 32 million stereo frames. The unconverted clock modes can change speed and pitch; explicit source conversion and output-device adaptation are separate stages. Source modes bypass project routing, mixer, effects and automation. This integration does not establish complete CPR playback, reference sample equivalence or physical Windows output.
