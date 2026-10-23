# Rebase for Windows

This experimental x64 preview is intended for Windows 11. It includes its required runtimes and the example beat. No development SDK or separate .NET installation is needed. Microsoft's [.NET 10 support table](https://learn.microsoft.com/dotnet/core/install/windows) lists the supported Windows versions for the included runtime; that table is not evidence that Rebase has been tested on each version.

## Open the app

1. Download `Rebase-0.21.1-windows-preview.6-x64.zip` from the [Windows preview release](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-windows-preview.6).
2. Use **Extract All** to unpack the complete archive.
3. Open **Rebase.exe** inside the extracted `Rebase` folder. Keep the DLLs, notices and `Examples` folder beside the executable.
4. Choose **File → Open example**. The four-track beat opens as a separate editable copy.
5. Use **Save As** to save your project in a new `.rebaseproj` folder.

The preview is unsigned. Its release page includes the archive's SHA-256 checksum and the exact validation record.

To reopen a saved project, choose **File → Open project…**, enter its `.rebaseproj` folder, and select `Project.json`. To share a project, copy the complete project folder, including its media and compatibility data.

## Adjust the workspace

Choose **Compact** or **Normal** beside the ruler selector to change track height. **Left** shows or hides Channel/Inspector; **Mixer** shows or hides the lower mixer. Drag the divider above the mixer to resize it, or focus the divider and use Up/Down. Inspector sections can collapse independently. These layout changes preserve project state and selection.

## Edit track automation

1. Select a track, then choose **Project → Track automation…** or **Automation…** in its Inspector.
2. Choose **Volume** or **Pan**. Select a point to change its time, value or outgoing **Linear/Hold** segment, then choose **Update**. **Add** or a click on the curve inserts a point; **Delete** removes the selected point. Adding at an occupied time replaces that point.
3. Use **Read volume automation** or **Read pan automation** to enable the selected lane. Turning Read off preserves its points and uses the track's manual value.
4. Use **Undo/Redo** for successful edits. Changes apply immediately; **Close** retains them. Save the project to keep them on disk.

This editor operates on the selected track. Inline arrangement lanes and automation writing modes are not implemented yet.

## Review and import a CPR project

1. Choose **File → Import CPR…** and select the source project.
2. Review the recovered tracks, editable clips, retained source events and unsupported data. Large reports use **Previous** and **Next**; each page can also scroll vertically.
3. Choose **Import Supported Data** to accept the partial recovery. Save or explicitly discard any current unsaved changes when prompted.
4. Choose a new `.rebaseproj` folder name. Existing files and folders are never replaced.

The project keeps the original CPR file and its import report. **File → Import Report…** reopens that preserved baseline; later edits do not rewrite it. Cancel leaves the current project unchanged. Unresolved audio remains unresolved until its supported source workflow is completed; import does not restore effects, routing or other unsupported processing.

## Audio output

Current playback requires a Float32 stereo output endpoint at the same sample rate as the project. The included beat uses **48 kHz**. Rebase reports an unavailable or incompatible output instead of silently converting the audio. General device-rate conversion is still being implemented.

Source-event audition uses the saved source rate and a separate event-local position. Attach the matching PCM24 WAV explicitly before audition or export. This mode checks the retained source and attached bytes again on playback, resume and seek. It does not apply project routing, effects or automation, and it does not turn unresolved events into ordinary timeline clips.

## What has been checked

Preview.6 comes from commit `32e6d37` and [native Windows run 40040015003](../../research/publication/windows-portability/application-run-40040015003/observation.json) on a Windows Server 2025 GitHub runner. It passed 102 actual-window checks, 191 host controls and 169 packaged-helper checks. The shared Release gate executed 98 tests with one explicit opt-in skip and no failures. The [downloaded archive audit](../../research/publication/windows-portability/application-run-40040015003/candidate-review.json) verified its file manifest, runtime dependencies and unchanged example audio.

[Twelve screenshots](../screenshots/README.md) show the actual application's client area, including CPR review and minimum-size automation views with Read off and invalid input. They exclude the operating-system frame. A requested 1400-DIP main window remained constrained to 1100 DIP on the hosted display; larger-display behavior remains unverified.

Physical mouse/keyboard input, native file dialogs and sound through a real audio device still require interactive Windows verification. Recording, plugins, inline automation lanes, automation writing modes and the remaining Mac workflows are not yet integrated. The [parity ledger](../development/windows-parity.md) records those boundaries.

The existing [Mac release](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1) remains available.
