# Rebase for Windows

This experimental x64 preview is intended for Windows 11. It includes its required runtimes and the example beat. No development SDK or separate .NET installation is needed. Microsoft's [.NET 10 support table](https://learn.microsoft.com/dotnet/core/install/windows) lists the supported Windows versions for the included runtime; that table is not evidence that Rebase has been tested on each version.

## Open the app

1. Download `Rebase-0.21.1-structure-preview.1-windows-x64.zip` from the [Windows preview release](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-structure-preview.1).
2. Use **Extract All** to unpack the complete archive.
3. Open **Rebase.exe** inside the extracted `Rebase` folder. Keep the DLLs, notices and `Examples` folder beside the executable.
4. Choose **File → Open example**. The four-track beat opens as a separate editable copy.
5. Use **Save As** to save your project in a new `.rebaseproj` folder.

The preview is unsigned. The archive is 100,149,693 bytes; its SHA-256 is `ae8fef10e7d9f23f9747ad82504a229dcd05330222106312609f38646e216cdd`. The release page includes the checksum and exact validation record.

To reopen a saved project, choose **File → Open project…**, enter its `.rebaseproj` folder, and select `Project.json`. To share a project, copy the complete project folder, including its media and compatibility data.

## Create a project and import audio

Choose **File → New project** (Ctrl+N), then **File → Import audio…** (Ctrl+I). Select 1–32 supported mono/stereo PCM WAV files. Rebase copies their bytes into the project and imports the batch as one undoable edit at the playhead, using the current snap setting. Invalid batches leave the project unchanged. **Save** on a new project asks for its permanent location; **Save As** preserves the original project.

The Windows importer currently accepts PCM16/24/32 and float32/64 WAV at 8–192 kHz, up to 256 MiB per batch and 16 million frames per file. Compressed audio, extensible WAV, RF64 and the broader Mac format range remain unsupported.

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

## Inspect preserved project structure

Choose **Project → Saved Project Structure** after opening an imported CPR project. The five sections show the counted hierarchy, audio-resource bindings, unresolved conditions and complete JSON. Inspection preserves edits, selection and Undo. The complete report is verified before display and remains read-only; it describes the preserved source, excluding later Rebase edits. Raw bus and Volume values do not establish working routing or processing.

## Audio output

Playback accepts Float32 stereo output devices from **8 to 192 kHz**. The included beat uses **48 kHz**. When the device rate differs, Rebase prepares a converted snapshot before playback and shows the source and output rates in the status line. Transport positions remain in project/source time. Pause reads the frozen source position before resume; a seek that rounds to the end finishes without trying to restart beyond it.

Ordinary-project source and converted snapshots are limited to **32 million frames**. Supported CPR source auditions now use a separate shared streaming worker and bounded source/device queues; source WAV exports retain their snapshot limit. Unsupported formats and unavailable devices produce an error. Device conversion does not change the saved project or exported render.

Select a retained source event and attach its matching PCM24 WAV, then choose **Source audio…**. Choose an available mode and use **Play** or **Export WAV…**. The eight choices cover original rate, source/current/saved timeline clocks, complete saved-clock track and conversion modes 0/1/2. The dialog explains the selected clock; unconverted clock changes can alter speed and pitch.

Each play, resume, seek and export checks the source and required attachments again. Complete-track checks include covered events. Export also writes a `.source-audition.json` proof beside the WAV and preserves existing files. These modes bypass project routing, mixer, effects and automation, and leave unresolved events unresolved. Availability is a preparation check; device output is checked when playback starts.

## What has been checked

The saved-structure preview comes from commit `bbc16cf2d19fc1e7cf31bd8edec816d99b7fc50a` and [native Windows run 40275372541](../../research/publication/windows-portability/application-run-40275372541) on a Windows Server 2025 GitHub runner. It passed 179 actual-window checks, 646 host controls, 853 streaming-helper checks across 85 scenarios, 425 source-mode checks across 48 scenarios and the existing 169-check helper suite. The shared Windows Release gate executed 168 tests with four explicit skips. The [component run](../../research/publication/windows-portability/run-40275372542) passed all 13 jobs and compared authored output/provenance across Windows/macOS Debug/Release.

The independent downloaded-package review checked all 444 files, dependency closure, app-local loaded modules, notices and seven unchanged example files. [Nineteen screenshots](../../research/publication/windows-portability/application-run-40275372541/README.md) show the actual client area, including New/import, streaming source audition and the saved-structure inspector. Both reviewers inspected every image. The hosted display constrained the wider-window request; larger-display behavior remains unverified.

The hosted runner had no playback endpoint. Conversion and pause/seek controls passed, but they do not establish sound through a real device. Physical mouse/keyboard input, native file dialogs and device audio still require interactive Windows verification. Recording, plugins, inline automation lanes, automation writing modes and the remaining Mac workflows are not yet integrated. The [parity ledger](../development/windows-parity.md) records those boundaries.

The existing [Mac release](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1) remains available.
