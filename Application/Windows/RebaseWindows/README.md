# Rebase Windows host

This WPF/.NET 10 host uses the shared Swift session for project loading, editing, undo, tempo, snapping, save, and WAV rendering, and the native WASAPI DLL for transport. The timeline and four-channel example are real project views, not a static mockup. The UI supports selection, pointer or numeric move/trim, split/delete, track gain/pan/mute/solo, undo/redo, tempo, snap, Save/Save As, WAV export, and play/pause/stop/seek with submitted-sample peaks.

The Windows host is an initial application milestone. Recording, plugins, advanced media formats, project-level CPR playback, general device-rate adaptation, and the remaining macOS workflows are not integrated. Playback currently requires a Float32 stereo endpoint at the project sample rate. The included example opens as a separate editable copy.

Imported project packages can expose retained source events in the inspector. Attach PCM explicitly, then audition or export a checked stereo source event. This uses a distinct event-local transport, rechecks source/media every play, resume, and seek, and does not apply project timing, track effects, mixer, or automation.

Real clip waveforms come from the shared Swift source-envelope reducer. Background replies are revision/interval checked and cannot overwrite document state.

Build with the pinned .NET SDK chosen by the application CI lane (10.0.402), without toolkit NuGet packages:

```powershell
dotnet build Application/Windows/RebaseWindows/RebaseWindows.csproj -c Release
dotnet run --project Application/Windows/RebaseWindows/Tests/RebaseWindows.Controls.csproj -c Release
```

The app folder must include `Rebase.exe`, the self-contained .NET desktop runtime, `rebase-session.exe` with its Swift/runtime dependencies, `RebaseWindowsAudio.dll`, and `Examples/Rebase Preview.rebaseproj`. Copy the complete published folder. Building WPF on macOS with `EnableWindowsTargeting` checks compilation only; it does not run Windows UI code.

The app launches its helper by absolute path and uses the [local protocol](../SESSION-PROTOCOL.md). SafeHandle and a serialized native-operation gate prevent destruction during an audio call. Rendering runs asynchronously while the UI remains responsive. Document mutations invalidate previously prepared audio; the frontend checks the render's revision and hash before playback.

Responses are bounded while reading, with a 60-second command deadline (120 seconds for renders). A failed protocol exchange stops that helper instead of risking later replies being mistaken for another request. Closing waits for queued edits before deciding whether to ask about unsaved changes. Normal shutdown sends EOF so the helper can remove its temporary example copy, with a bounded shutdown grace before termination.

## Windows smoke run

```powershell
Rebase.exe --smoke --smoke-json C:\evidence\window-smoke.json
```

This opens an actual WPF window, invokes its example/open and editing buttons through WPF automation peers, checks shared undo/redo, saves/reopens a temporary project, validates a shared render, probes the default endpoint without starting audio, and writes `native-app-visual.png` beside the JSON. The PNG is a render of the WPF window's visual tree, not a desktop screenshot. File dialogs and physical mouse/keyboard interaction need separate human or desktop-automation verification.

Exit 0 means those checks passed; 1 means a failure; 2 means invalid invocation or artifact-writing failure. The scenario has a 120-second deadline; CI should enforce an outer 180-second process timeout. Missing audio endpoints are recorded as unavailable, never playback success. Every smoke record has `playback_tested:false`. Hardware playback remains the separate explicit `rebase_wasapi_probe --allow-audio` procedure.

`Tests/RebaseWindows.Controls.csproj` exercises protocol identifiers, casing, invalid replies, stale render revisions, byte/hash checks, and malformed/nonfinite snapshot rejection. Those portable controls do not execute WPF or WASAPI. No Windows runtime or device success follows from cross-compilation or these controls alone.


## Windows interface refinement

The current layout uses the implemented portions of the Windows project window described in the [official Cubase Pro 15.0.30 Operation Manual](https://www.steinberg.help/api/khub/documents/O4PvzgK5U8lOyn4ANi_gKg/content), pages 12 (Windows screenshot provenance), 54 (project window), 306 (integrated transport), and 434–435 (lower-zone mixer). Authored controls use compact top rows, a gray event canvas, a narrow inspector, lower-zone channel strips, and bottom transport. Unsupported reference controls are not represented as working controls. This is a bounded application implementation, not an exact or complete interface recreation. Vendor screenshots and manual bytes are not included in this repository.

DWM dark-caption opt-in follows [Microsoft's documented API](https://learn.microsoft.com/windows/apps/desktop/modernize/apply-windows-themes). Its HRESULT is recorded by smoke; the WPF visual-tree PNG does not capture or validate the operating-system frame.

For the optional authored source-event smoke, append `--smoke-source-project ABSOLUTE_PACKAGE --smoke-source-media ABSOLUTE_WAV`. Both paths are required together and stay outside the shipped app. The scenario opens a scratch copy, selects the source-event UI item, attaches media through the actual button handler with a supplied path, checks undo/redo, and exports through the actual button handler. File dialogs remain untested. It records provenance/output hashes and `native-source-visual.png`, then returns to the bundled beat, waits for all real waveform geometry, checks that all four rows fit, and captures `native-app-visual.png`. The extended scenario allows 180 seconds; the outer process timeout is 240 seconds. It never starts audio.

Journey queue: open/edit/save/export and bounded source attach/export are implemented with local controls; the redesigned shell and source window require new hosted Windows visual/runtime evidence. Native pointer drag, keyboard focus return, file dialogs, and hardware audition need further desktop/device verification. Future parity work remains separate from this UI milestone.
