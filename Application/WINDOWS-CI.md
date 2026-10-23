# Portable component CI

The active workflow is `.github/workflows/portable-conformance.yml`. Read the results for the specific commit before treating a lane as verified.

The `Portable component conformance` GitHub Actions workflow builds and executes authored C kernels and shared Swift model tests on Windows x64 and macOS arm64, in Debug and Release configurations. It also retains the existing public macOS application test lane, builds the public SoXR library on Windows, and builds the Windows native audio adapter with read-only endpoint discovery. These checks do not provide a Windows desktop application, audio-device playback, or equivalence to a reference application's runtime.

The workflow uses standard hosted runners, which are free for public repositories. The `windows-2025` and `macos-15` images receive updates; their image versions and actual compiler versions are recorded with each run. The macOS job selects Xcode 26.1.1 (Swift 6.2.1) explicitly. The Windows Swift job selects the official Swift 6.4.1 release. Python 3.10.11, CMake 3.31.6, Ninja 1.11.1.4, and top-level action commits are pinned. The Swift setup action has an upstream floating artifact-upload action in its installer-failure path; its cache and SDK-module mutation paths are disabled.

Every native command is checked for failure. A lane also requires at least one executed test and no test failures. Each Swift lane renders the shipped example through `rebase-inspect`, verifies its WAV format and 20-second duration, and records SHA-256 hashes of the actual PCM data chunk and WAV file. It requires a regular file rather than a symbolic link, then verifies that a repeated render refuses to overwrite it and preserves every byte. The hashes must match the predeclared macOS Release hashes in `scripts/example-render-lock.json`, without tolerance. A final job also requires the hashes to match across Windows/macOS and Debug/Release. The uploaded artifacts contain JSON conformance records, test XML, and logs, not application downloads or unsigned Windows builds. A failed or absent run is not successful Windows validation.

## Run the portable targets

From a developer environment with Clang, CMake, Ninja, Python, and Swift installed:

```sh
python Application/scripts/run-portable-ci.py c --configuration Release --output /tmp/rebase-c-evidence
python Application/scripts/run-portable-ci.py swift --configuration Release --output /tmp/rebase-swift-evidence
```

On Windows, choose writable Windows paths for `--output`. The Swift runner sets `REBASE_PORTABLE_ONLY=1`, which excludes the macOS app, AVFoundation, and ZIPFoundation. Neither private research fixtures nor installed proprietary binaries are used.

On a Mac with only Command Line Tools selected, the driver applies the same Swift Testing framework/plugin flags as `test-app.sh`. Full-Xcode hosted runners use their normal test invocation. SwiftPM may emit `tests-swift-testing.xml` alongside or instead of the requested `tests.xml`; the driver sanitizes and reads both known reports, records skipped and executed counts, and requires at least one executed test with no failures. The portable driver restores the application's existing `Package.resolved` after execution because the dependency-free portable package can otherwise remove it.

Swift 6.4.1 on Windows produced a zero-test Release runner even with both `--disable-dead-strip` and explicit `/OPT:NOREF`; Debug executed its suite. Swift Build generates an empty public anchor function and calls it from the runner to load the test DLL. The next diagnostic disables cross-module optimization for the test build with `-Xswiftc -disable-cmo`, while retaining Release `-O` within modules, the explicit linker retention flag, and the nonzero executed-test requirement. This tests whether optimization removes the DLL-loading anchor; it is a hypothesis until native evidence establishes the cause. Generated source, PE headers/imports, verbose compiler output, and a discovery listing are retained. Production inspector and session-helper builds use their normal compiler/link flags and must independently pass the locked render and interactive protocol checks.

## Windows application development package

The separate `.github/workflows/windows-application.yml` builds the WPF host with .NET SDK 10.0.402 and the self-contained .NET/Windows Desktop 10.0.13 runtime. It uses the same Swift 6.4.1 release and an independently built Release session helper, the native audio DLL, and the exact manifest-listed authored example. The published directory is untrimmed, with separate DLLs/helper and no PDBs. Source prefix maps use `/_/Rebase`.

```powershell
python Application/scripts/build-windows-app.py --output "$env:TEMP/rebase-windows-application"
```

The packager checks native and managed PE architecture and recursively resolves static and delayed imports. Runtime files come only from the selected Swift runtime component and the Visual C++ x64 CRT redistributable directory; Windows API contracts/system DLLs remain operating-system dependencies. ICU runtime components are included for dynamic loading. Hash-pinned upstream license/notices are retained in the package with their source URLs. The resulting package manifest records every other shipped file's SHA-256.

The exact staged helper must pass the interactive session protocol checks, including its predeclared example render. An actual WPF window must then complete its automation-peer smoke scenario and emit a visual-tree PNG. This image is not a desktop screenshot; file dialogs and physical input remain untested. Both processes run with compiler/runtime installation directories removed from PATH, and their observed module lists must locate app runtimes inside the package and OS modules inside Windows. Headless endpoint absence remains explicitly unavailable; the scenario does not play audio.

The mandatory shared Release test/render gate runs after the window diagnostic and before ZIP creation, so a zero-test runner or other failure still prevents a download. Only a fully passing job uploads an unsigned **development build**, retained for seven days. Failure uploads sanitized evidence only. This workflow does not create a GitHub release, sign an executable, establish hardware playback, or establish application parity. Read the actual run for the chosen commit before treating the package as verified.

## Windows SoXR build

In an x64 Visual Studio developer environment with `clang.exe` available:

```powershell
python Application/scripts/build-windows-soxr.py --output "$env:TEMP/rebase-soxr-evidence"
```

The script verifies the pinned SoXR 0.1.3 source manifest. Git's exact link-text representation is accepted for its noncompiled symlink wrapper on Windows. All compiled source bytes must match. CR32, CR64, and the high-precision clock remain enabled; OpenMP, SIMD variants, VR32, LSR bindings, PFFFT, AVFFT, examples, upstream tests, and developer tracing remain disabled, matching the macOS build's feature selection. Optimization remains `-O3 -DNDEBUG`, with fast math and floating-point contraction disabled. It selects CMake's `RelWithDebInfo` configuration with those explicit flags to avoid upstream's Unix-only `-s` shared-linker option in `Release`.

The Windows build explicitly enables `SOXR_DLL` exports because upstream enables that macro automatically only for MSVC's frontend. The probe uses `clang-cl /MD` to select the dynamic C runtime consistently. It loads the built library, checks its version, converts an authored stereo impulse from 48 kHz to 44.1 kHz, flushes the converter, and verifies frame count, finite output, and channel relationship. This is an API plumbing check. It does not establish matching impulse responses or project playback between platforms.

## Windows native audio foundation

Two separate Windows x64 jobs build `Windows/NativeAudio` in Debug and Release with `clang-cl`, Ninja, and the Visual Studio SDK environment. The DLL and probe use CMake's dynamic MSVC runtime selection, including the Debug runtime in Debug builds. Each job requires an executed, passing lifecycle CTest case in XML and a nonzero passing assertion count from the portable transport model.

```powershell
python Application/scripts/run-windows-native-audio-ci.py --configuration Release --output "$env:TEMP/rebase-native-audio-evidence"
```

The runner then invokes `rebase_wasapi_probe` without `--allow-audio`. Exit 0 means an endpoint was observed; exit 77 is recorded as `unavailable-no-endpoint`. Both remain `playback_tested:false`, and neither establishes playback. Exit 1, inconsistent JSON, a timeout, or any other unexpected exit fails the lane. Hosted runners are not assumed to have an audio device. Audio-device lifecycle testing remains an explicit, separate opt-in described in `Windows/NativeAudio/README.md`.

Only sanitized JSON, XML, and logs are uploaded. The manifest records DLL/probe hashes, but no DLL, executable, Windows application, or audio download is published by this workflow. For local script validation on a non-Windows machine, `--portable-lifecycle-only` builds and runs only the portable transport model; its report explicitly marks the native library and endpoint probe as untested. This flag is absent from the Windows jobs.

ZIPFoundation 0.9.20 and the macOS audio adapters remain outside the Windows model lane. ZIPFoundation's pinned CI supports macOS/Linux and its filesystem operations depend on POSIX APIs; a Windows archive adapter needs its own implementation and tests.

References: [Swift Windows prerequisites](https://www.swift.org/install/windows/manual/), [runner image labels](https://github.com/actions/runner-images), [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [pinned Swift setup action](https://github.com/compnerd/gha-setup-swift/blob/775d3f4111c5be58a0f62f2efdd353bb8fac15c7/action.yml), [SoXR 0.1.3 build definitions](https://github.com/chirlu/soxr/blob/0.1.3/CMakeLists.txt), and [ZIPFoundation 0.9.20 CI](https://github.com/weichsel/ZIPFoundation/blob/0.9.20/.github/workflows/CI.yml).
