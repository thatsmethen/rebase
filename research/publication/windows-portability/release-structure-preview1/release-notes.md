Rebase now includes **Saved Project Structure** on both macOS and Windows. Inspect the preserved CPR track hierarchy, audio-resource bindings, raw saved values, unresolved conditions and complete JSON without changing the project or its undo history.

**[Download macOS Apple Silicon](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-structure-preview.1/Rebase-0.21.1-structure-preview.1-macos-arm64.zip)** · **[Download Windows x64](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-structure-preview.1/Rebase-0.21.1-structure-preview.1-windows-x64.zip)**

Both apps include the editable example beat, icon and required notices. The Windows ZIP includes its Swift/.NET runtimes: extract the complete archive and run `Rebase.exe` inside the Rebase folder. For macOS 14 or later on Apple Silicon, extract `Rebase.app` and follow the [Mac installation guide](https://github.com/thatsmethen/rebase/blob/main/Application/INSTALL.md). The Mac app is ad-hoc signed and not notarized; the Windows app is unsigned. [Windows installation guide](https://github.com/thatsmethen/rebase/blob/main/docs/install/windows.md).

Open an imported CPR project, then choose **File → Saved Project Structure** on Mac or **Project → Saved Project Structure** on Windows. The view describes the preserved source, including repeated references, empty slots and unknown objects. Complete reports are verified against source, project-manifest and historical-import-report hashes; oversized or changed reports fail explicitly.

![macOS saved project structure](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-structure-preview.1/macos-saved-structure.png)

![Windows saved project structure at its minimum client size](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-structure-preview.1/windows-saved-structure.png)

![Saved audio bindings on macOS](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-structure-preview.1/macos-saved-bindings.png)

![Windows arrangement](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-structure-preview.1/windows-arrangement.png)

The Windows package passed **179 native window checks and 646 host controls**, plus the existing **853 streaming checks across 85 scenarios**, **425 source-mode checks across 48 scenarios**, and **169 helper checks**. All 13 component jobs passed. The shared suites executed 168 tests on Windows and 172 on portable macOS, each with 4 explicit skips; the normal Mac suite executed 312 tests with 120 explicit skips. Nineteen actual Windows client screenshots were independently reviewed. The actual Mac Release app was checked through all five inspector sections, exact complete-JSON comparison, scrolling to the end, and edit → inspect → Close → Undo.

Both archives passed file and privacy checks, with the example preserved. Windows additionally passed exact manifest coverage and PE/runtime dependency verification. [Windows app and package evidence](https://github.com/thatsmethen/rebase/tree/main/research/publication/windows-portability/application-run-40275372541) · [Cross-platform component evidence](https://github.com/thatsmethen/rebase/tree/main/research/publication/windows-portability/run-40275372542) · [Mac Release evidence](https://github.com/thatsmethen/rebase/tree/main/research/publication/windows-portability/macos-inspector-bbc16cf) · [Research](https://github.com/thatsmethen/rebase/tree/main/research/publication/project-composition-20261026).

This is a development preview from the same source revision on both platforms; internal app versions remain 0.21.1. The inspector does not apply saved values as effective routing, gain or processing. Output-registry decoding is subsequent development and is not included in these archives. The Windows runner had no audio endpoint: these checks do not establish physical audio output, physical input, native file-picker behavior, full project playback or full application parity. No proprietary reference was executed.

Source: [`bbc16cf`](https://github.com/thatsmethen/rebase/commit/bbc16cf2d19fc1e7cf31bd8edec816d99b7fc50a). `SHA256SUMS.txt` covers both downloads and all five attached screenshots. Existing releases remain available.
