Rebase for Windows now exposes the same eight source-audio modes as the Mac application. Select a retained source event and choose **Source audio…** to inspect clocks and availability, audition supported audio, or export a WAV with its complete provenance file.

**[Download the Windows x64 app](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-windows-preview.8/Rebase-0.21.1-windows-preview.8-x64.zip)** · [Installation guide](https://github.com/thatsmethen/rebase/blob/main/docs/install/windows.md) · [macOS app](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1)

Extract the complete ZIP and run `Rebase.exe`. The runtime, icon, editable example beat, public SoXR library and its source/notices are included. A separate Swift or .NET installation is not required. This is an unsigned Windows x64 development preview.

The modes include original source rate, source/current/saved timeline clocks, complete saved-clock tracks with covered contributors, and reconstructed conversion modes 0/1/2. Each playback, resume, seek and export rechecks the preserved source and required attached media. Stop returns to the beginning after a seek; EOF handling verifies the full source without installing an empty buffer. Existing WAV and provenance files are preserved.

![Source conversion controls](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-windows-preview.8/windows-source-modes.png)

![Complete source track](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-windows-preview.8/windows-source-track.png)

![Windows arrangement](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-windows-preview.8/windows-arrangement.png)

This build passed **133 native window checks, 421 host controls, 425 source-mode helper checks across 48 scenarios, and the existing 169-check helper suite**. All 13 cross-platform jobs passed; the four portable lanes produced matching source-mode PCM and provenance across Windows/macOS and Debug/Release. The normal Mac suite executed 279 tests with 118 explicit skips. Fifteen actual client screenshots are attached. The hosted Windows runner had no usable audio endpoint.

[Application/package evidence](https://github.com/thatsmethen/rebase/tree/main/research/publication/windows-portability/application-run-40051952551) · [Cross-platform evidence](https://github.com/thatsmethen/rebase/tree/main/research/publication/windows-portability/run-40051952508).

Source modes bypass project routing, mixer, effects and automation. Unconverted clock modes can change speed and pitch. Explicit source conversion and output-device adaptation are separate operations. Windows uses a bounded snapshot of at most 32 million stereo output frames; long-project streaming and full imported-project playback remain incomplete. Cross-platform authored controls establish the measured implementation behavior, not reference sample equivalence or complete application fidelity. Physical Windows input, native file pickers and hardware audio output remain unverified.

Source: [`81e96c9`](https://github.com/thatsmethen/rebase/commit/81e96c9b29b6e3d87184e067af58f4ab2973db89). [Shared mode contract](https://github.com/thatsmethen/rebase/blob/main/docs/development/source-audio-modes.md) · [Local controls and preserved failures](https://github.com/thatsmethen/rebase/tree/main/research/publication/windows-portability/source-modes-local-20261024).

ZIP SHA-256: `b8c070d7bb17e85ee38a9293af0c568730962feb842ef448522fba3ac73613d4`. `SHA256SUMS.txt` also covers the attached screenshots. Existing releases remain available.
