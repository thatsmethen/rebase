# Rebase

<img src="Application/Assets/Rebase.png" alt="Rebase app icon" width="96">

Rebase is an experimental audio workstation with a macOS app and a Windows development preview. The apps share Swift project/audio code and C DSP implementations; Windows uses a native WPF interface. Both apps support audio arrangement, basic mixing, volume/pan automation editing and musical timing. Both now expose eight shared source-audio audition modes; the Mac app retains broader project exchange workflows.

The compatibility and DSP modules include implementations reconstructed through static interoperability research. This repository includes the application, research instruments, findings, analytical controls, and validation records. Start with the [research guide](research/README.md) to follow the investigation and its evidence.

The research identifies its reference software and retains its original terminology. Acquired proprietary software, copied reference projects and media, raw provider captures, and generated build products are kept in ignored local storage and excluded from published Git content. The publication manifest identifies included research and omitted local artifacts. Public copies have been checked for personal information; privacy-redacted derivatives are [explicitly identified](research/publication/PRIVACY.md).

[Contributor guide](CONTRIBUTING.md) · [Test guide](Application/Tests/README.md) · [Research guide](research/README.md)

Windows development follows the [Windows reference interface](docs/development/windows-ui-fidelity.md). The [parity ledger](docs/development/windows-parity.md) tracks implemented behavior and remaining work; [component and application checks](Application/WINDOWS-CI.md) cover the native Windows host and its package. Full reference fidelity and Mac feature parity remain ongoing work.

## Release

**[Download Windows x64](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-structure-preview.1/Rebase-0.21.1-structure-preview.1-windows-x64.zip)** · **[Download macOS Apple Silicon](https://github.com/thatsmethen/rebase/releases/download/v0.21.1-structure-preview.1/Rebase-0.21.1-structure-preview.1-macos-arm64.zip)**

The **saved-structure preview** builds both apps from the same source revision. Open an imported CPR project, then choose **Project → Saved Project Structure** on Windows or **File → Saved Project Structure** on Mac. The read-only inspector shows counted track order, saved resource bindings, unresolved conditions and complete source-bound JSON while preserving project edits and Undo. Saved values do not establish effective routing or processing.

Both downloads include the editable example beat and app icon. The Windows archive includes its runtimes; extract the complete ZIP and run `Rebase.exe`. It retains New Project, PCM WAV batch import, streaming source auditions, volume/pan automation and adjustable panels. This unsigned x64 preview targets Windows 11; native automated checks ran on Windows Server 2025, with physical input and device audio still awaiting interactive verification. The Mac app requires **Apple Silicon and macOS 14 or later**, is ad-hoc signed and is not notarized.

[Release page, screenshots and checksums](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-structure-preview.1) · [Windows installation](docs/install/windows.md) · [Mac installation](Application/INSTALL.md) · [Previous Mac release](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1)

The Mac app includes the [example beat](Application/Examples/README.md) shown below. Choose **File → Open Example Beat**, then press Space. Save keeps an editable copy in your chosen location.

## Screenshots

The Windows preview, showing the included four-track beat, real waveforms, separate Channel and Inspector, compact controls, musical ruler and mixer. This is the actual opened application's client-area render from the native Windows validation run.

![Rebase Windows arrangement, inspector and mixer](docs/screenshots/windows-arrangement.png)

[New project and audio import](docs/screenshots/windows-new-import.png) · [Streaming source audition](docs/screenshots/windows-source-stream.png) · [Source Audio modes](docs/screenshots/windows-source-modes.png) · [Complete source track](docs/screenshots/windows-source-track.png) · [Windows automation editor](docs/screenshots/windows-automation.png) · [Normal track density](docs/screenshots/windows-workspace-normal.png) · [Expanded arrangement](docs/screenshots/windows-workspace-expanded.png) · [Windows source-event view](docs/screenshots/windows-source.png) · [Windows zoom and scrolling](docs/screenshots/windows-scrolled.png) · [CPR import review](docs/screenshots/windows-cpr-review.png)

The Mac app, showing the same eight-bar session of synthesized audio.

![Rebase arrangement, inspector and mixer](docs/screenshots/arrangement.jpg)

[Mac automation editor](docs/screenshots/automation.jpg) · [App icon and version](docs/screenshots/about.jpg) · [Capture details](docs/screenshots/README.md)

## Build

Requires macOS 14 or later, Apple's command-line developer tools, and CMake. The build downloads the pinned Swift package dependency and builds the included SoXR source.

```sh
sh Application/build-app.sh
open Application/dist/Rebase.app
```

## Test

```sh
sh Application/Tests/run-tests.sh --public
```

The public lane runs self-contained tests and explicitly skips tests requiring private reference inputs. See [test documentation](Application/Tests/README.md) for the optional private fixture configuration. Skipped tests do not establish compatibility.

## Compatibility scope

Imported CPR projects retain the original file and an interpretation report. Supported source-event and complete direct-track auditions use explicit clock and processing modes. Complete-track audition verifies every counted contributor and attached media file, resolves signed event priorities and overlapping ranges, and derives each surviving fragment from its original source timing. Inputs must already be chronological. The implementation supports up to 4,096 contributors and 8,192 fragments within explicit media and processing limits.

The application does not claim full project fidelity or equivalence with a reference application's runtime. Source audition does not restore mixer state, routing, effects, automation, fades, nested containers or other unsupported processing. Unsupported events remain unresolved and block whole-project playback and export.

## Third-party code

Required notices and source licenses are retained in `Application/ThirdParty` and the research reference directories. Packaging also includes ZIPFoundation's license. These licenses apply to their respective components; there is no additional project-wide license grant.
