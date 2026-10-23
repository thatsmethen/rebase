# Rebase for Windows

This experimental x64 preview is intended for Windows 11. It includes its required runtimes and the example beat. No development SDK or separate .NET installation is needed. Microsoft's [.NET 10 support table](https://learn.microsoft.com/dotnet/core/install/windows) lists the supported Windows versions for the included runtime; that table is not evidence that Rebase has been tested on each version.

## Open the app

1. Download `Rebase-0.21.1-windows-x64.zip` from the [Windows preview release](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-windows-preview.1).
2. Use **Extract All** to unpack the complete archive.
3. Open **Rebase.exe** inside the extracted `Rebase` folder. Keep the DLLs, notices and `Examples` folder beside the executable.
4. Choose **File → Open example**. The four-track beat opens as a separate editable copy.
5. Use **Save As** to save your project in a new `.rebaseproj` folder.

The preview is unsigned. Its release page includes the archive's SHA-256 checksum and the exact validation record.

To reopen a saved project, choose **File → Open project…**, enter its `.rebaseproj` folder, and select `Project.json`. To share a project, copy the complete project folder, including its media and compatibility data.

## Audio output

Current playback requires a Float32 stereo output endpoint at the same sample rate as the project. The included beat uses **48 kHz**. Rebase reports an unavailable or incompatible output instead of silently converting the audio. General device-rate conversion is still being implemented.

Source-event audition uses the saved source rate and a separate event-local position. Attach the matching PCM24 WAV explicitly before audition or export. This mode checks the retained source and attached bytes again on playback, resume and seek. It does not apply project routing, effects or automation, and it does not turn unresolved events into ordinary timeline clips.

## What has been checked

The release's Windows build runs on a Windows Server 2025 GitHub runner. It checks the shared project/audio code, the opened WPF application's exercised controls, the packaged runtime dependencies and the unchanged example audio. Screenshots render the actual application's client area and exclude the operating-system frame.

Physical mouse/keyboard input, native file dialogs and sound through a real audio device still require interactive Windows verification. Recording, plugins, automation editing and the remaining Mac workflows are not yet integrated. The [parity ledger](../development/windows-parity.md) records those boundaries.

The existing [Mac release](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1) remains available.
