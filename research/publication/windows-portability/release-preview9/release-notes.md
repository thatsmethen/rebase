Rebase for Windows now streams supported CPR source auditions through bounded queues and adds **New project** and **Import audio**. Create a project with Ctrl+N, import a batch of PCM WAV files with Ctrl+I, then edit, undo/redo, Save As and reopen it.

**[Download the Windows x64 app](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-windows-preview.9/Rebase-0.21.1-windows-preview.9-x64.zip)** · [Installation guide](https://github.com/thatsmethen/rebase/blob/main/docs/install/windows.md) · [macOS app](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1)

Extract the complete ZIP and run `Rebase.exe` inside the Rebase folder. The runtimes, app icon, editable example beat and public SoXR source/notices are included. No separate Swift or .NET installation is needed. This is an unsigned Windows x64 development preview.

Audio import copies 1–32 supported mono/stereo PCM WAV files into the project as one undoable batch. Invalid batches leave the project unchanged, and source files stay untouched. The Windows importer currently accepts PCM16/24/32 and float32/64 at 8–192 kHz, with explicit file/frame limits; broader Mac audio formats remain a parity task.

![New project and audio import](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-windows-preview.9/windows-new-import.png)

Source audition uses a shared streaming worker and bounded native source/device queues, including long sparse timelines, complete supported overlap tracks and explicit conversion modes. Playback preparation, seek, cancellation and provenance checks retain their tested source semantics. Ordinary-project playback and WAV exports retain their snapshot limits. Source audition still bypasses whole-project routing, mixer, effects and automation.

![Streaming source audition](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-windows-preview.9/windows-source-stream.png)

![Windows arrangement](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-windows-preview.9/windows-arrangement.png)

This build passed **165 native window checks, 574 host controls, 853 streaming-helper checks across 85 scenarios, 425 source-mode checks across 48 scenarios, and the existing 169-check helper suite**. All 13 component jobs passed, with exact authored PCM/provenance comparisons across Windows/macOS Debug/Release. The normal Mac suite executed 288 tests with 119 explicit skips. Seventeen actual client screenshots are attached and were independently reviewed.

The downloaded ZIP passed exact archive/file-hash coverage, runtime dependency and app-local module checks, unchanged example verification and the reviewed private-pattern scan. Earlier failed observations and their corrections are retained. [Application/package evidence](https://github.com/thatsmethen/rebase/tree/main/research/publication/windows-portability/application-run-40265349968) · [Component evidence](https://github.com/thatsmethen/rebase/tree/main/research/publication/windows-portability/run-40265350027).

The hosted Windows runner had no audio endpoint. These results do not establish hardware output, physical input, native file-picker behavior, reference sample equivalence or full application parity. Whole imported-project playback, recording, plugins, interchange and remaining interface fidelity are still under development. The new saved-structure inspector is separate development work and is not included in this ZIP.

Source: [`2934b9a`](https://github.com/thatsmethen/rebase/commit/2934b9a0b6e96a5b3bd654a3e6a4fb00abe64e31). ZIP: **99,930,466 bytes**. SHA-256: `fc1d90aaff8f5179cef008b12bb3b3b55fce45e6dde480b2a0aaa2a4160fb6c4`. `SHA256SUMS.txt` covers the ZIP and attached screenshots. Existing releases remain available.
