# Rebase Windows host

This WPF/.NET 10 host uses the shared Swift session for project loading, editing, undo, tempo, snapping, save, and WAV rendering, and the native WASAPI DLL for transport. The timeline and four-channel example are real project views, not a static mockup. The UI supports selection, pointer or numeric move/trim, split/delete, track gain/pan/mute/solo, undo/redo, tempo, snap, Save/Save As, WAV export, and play/pause/stop/seek with submitted-sample peaks.

The Windows host is an initial application milestone. Recording, plugins, advanced media formats, native CPR playback, general device-rate adaptation, and the remaining macOS workflows are not integrated. Playback currently requires a Float32 stereo endpoint at the project sample rate. The included example opens as a separate editable copy.

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
