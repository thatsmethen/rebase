# Contributing to Rebase

Rebase combines a native macOS application with a preserved interoperability research archive. A useful contribution can improve the app, reproduce a finding, add a focused control, or explain an unsupported case. The [research guide](research/README.md) identifies the current evidence and its limits.

## Build and test

Use macOS 14 or later with a Swift 6 toolchain, Apple's command-line developer tools, CMake and Python 3. Run these commands from the repository root:

```sh
sh Application/build-app.sh
open Application/dist/Rebase.app
sh Application/Tests/run-tests.sh --public
```

The build fetches the pinned Swift package dependency and compiles the included SoXR source. The public test lane needs no reference installation. It explicitly disables tests that require external research inputs; those skipped comparisons are not passes.

For a focused change, pass a Swift Testing filter through the same wrapper:

```sh
sh Application/Tests/run-tests.sh --public --filter CPRTrackOverlapNormalizerTests
```

An optional fixture lane is available for developers who already have the recorded inputs:

```sh
sh Application/Tests/run-tests.sh --with-research /absolute/external/fixtures
```

See [the test guide](Application/Tests/README.md) for the exact layout and checks. Keep these fixtures outside the checkout. A configured but incomplete fixture root fails the relevant tests; this lane neither downloads nor executes the reference application.

## Find the code

| Area | Starting points |
| --- | --- |
| App and editing state | [RebaseApp.swift](Application/Sources/Rebase/RebaseApp.swift), [StudioSession.swift](Application/Sources/Rebase/StudioSession.swift), [TimelineView.swift](Application/Sources/Rebase/TimelineView.swift) |
| Project model and persistence | [Project.swift](Application/Sources/RebaseCore/Project.swift), [ProjectStore.swift](Application/Sources/RebaseCore/ProjectStore.swift); [DAWProject.swift](Application/Sources/RebaseCore/DAWProject.swift) handles the supported exchange subset |
| Playback and export | [AudioTransportEngine.swift](Application/Sources/RebaseCore/AudioTransportEngine.swift), [CPRStreamPlaybackQueue.swift](Application/Sources/RebaseCore/CPRStreamPlaybackQueue.swift), [OfflineRenderer.swift](Application/Sources/RebaseCore/OfflineRenderer.swift) |
| Archive interpretation | [CPRProject.swift](Application/Sources/RebaseCore/CPRProject.swift), the versioned `CPRRecoveryV1`–`V5` readers, and [CPRContractMigration.swift](Application/Sources/RebaseCore/CPRContractMigration.swift) |
| Source-track audition | [CPRSourceTrackPlan.swift](Application/Sources/RebaseCore/CPRSourceTrackPlan.swift) verifies contributors and resolves overlaps; [CPRPlacedSourceEventPlan.swift](Application/Sources/RebaseCore/CPRPlacedSourceEventPlan.swift) projects original source coordinates; [CPRNativeTimelineStream.swift](Application/Sources/RebaseCore/CPRNativeTimelineStream.swift) reads the resulting windows |
| Numerical kernels | [RebaseTimingDSP](Application/Sources/RebaseTimingDSP/) contains the recovered timing, overlap and conversion operations; `RebaseDSP`, `RebaseAmbiDSP` and `RebaseSoXR` contain the other DSP modules |
| Tests and fixture selection | [RebaseCoreTests](Application/Tests/RebaseCoreTests/) and [PrivateResearchFixtures.swift](Application/Tests/RebaseCoreTests/PrivateResearchFixtures.swift) |

## Keep evidence useful

Describe the concrete behavior changed, how it was checked, and what remains unsupported. For compatibility work, link the relevant finding and identify its target build, assumptions and input domain. Separate static observations, analytical controls, application tests, GUI observations and reference runtime measurements. A passing synthetic control does not establish reference equivalence.

Preserve historical research records, manifests and their hashes. Add a new finding, review or correction that references the earlier record instead of editing a sealed result. Retain failures and explain corrections. Reference names and technical identities retain their provenance. Public records may be declared privacy-redacted derivatives, with original and distributed hashes distinguished in the [publication policy](research/publication/PRIVACY.md); do not reintroduce personal paths or raw local captures. The public application has separate publication validation.

Verify the distributed research copies with:

```sh
python3 research/publication/verify_research_export.py
```

The [publication manifest](research/publication/research-export-manifest.json) also lists omitted artifacts. This command verifies included records only; complete historical seal reproduction requires the omitted local inputs. New records can be documented separately without changing an older manifest's meaning.

Full application fidelity remains unestablished, with zero reference runtime comparisons. Current source audition does not restore project routing, mixer processing, effects, automation, fades or nested contributors. Preserve explicit unsupported-state handling when extending compatibility, and use focused regression checks for any newly admitted case. Changes to visible workflows also benefit from checking the built app; compilation alone does not verify an interaction.
