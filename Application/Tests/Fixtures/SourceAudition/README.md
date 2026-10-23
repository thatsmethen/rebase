# Authored source-audition control

This small fixture exercises explicit media attachment, retained CPR provenance,
and original-rate source-event audition in the Windows window smoke test. Every
archive and audio byte was authored by this repository's test generator. It
contains no captured project, reference program output, personal metadata, or
third-party audio. It is a synthetic implementation control, not evidence of
reference-runtime equivalence or general project playback.

- `AuthoredSource.rebaseproj/` is an unattached project with one retained source
  event, the generated original archive, and its replayable import report.
- `SelectedSource.wav` is the separately selected PCM24 stereo source: 44,100
  frames at 44,100 Hz. The project uses its explicit 48,000 Hz application
  default. Audition must retain the source rate.
- `expected.json` records stable event identity, input/source/report/manifest
  hashes, generator hashes, and independently calculated output/PCM hashes.

The source uses the repeating signed integer markers in
[`CPRAudioControl.swift`](../../SharedCPRAudioTests/CPRAudioControl.swift).
The event gain is exactly `0.0625`; full-scale markers therefore produce a peak
of `0.0625`. These are test tones, not a musical example. The expected samples
are computed independently of the C decoder as
`Float32((Double(marker) / 8388608) * 0.0625)`. The expected output is an
IEEE-float WAVEFORMATEX file with a `fact` frame count, 352,858 bytes including
its header. No expected render is checked into the repository.

Generation is implemented in
[`SourceAuditionFixtureGenerator.swift`](../../SharedCPRAudioTests/SourceAuditionFixtureGenerator.swift)
using `CPRAudioControl`. It refuses an existing destination, writes sorted JSON,
verifies attachment/save/reopen through `ProjectStore`, and checks the renderer's
entire output against the independently calculated bytes before publishing the
fixture. Source and event identities derive from the generated archive bytes;
the report contains no timestamps or machine paths. The sole absolute-looking
archive path, `/unresolved/authored/`, is an intentionally fictitious unresolved
source location. Tests require explicit selection of the supplied WAV.

To regenerate into a **new** directory on macOS, from the repository root:

```sh
REBASE_GENERATE_SOURCE_AUDITION_FIXTURE=/tmp/rebase-authored-source-control \
  sh Application/Tests/run-tests.sh \
  --filter SourceAuditionFixtureTests.generateAuthoredFixtureAtExplicitNewDestination
```

The generation test is disabled unless that environment variable is set. The
normal `checkedInAuthoredFixtureAttachesRendersAndReopensWithoutChangingOriginal`
test runs on both shared-core targets and verifies the checked-in files, exact
render hashes, save/reopen, no overwrite, unresolved-project barrier, and original
package preservation. It also removes the copied empty `Media` directory to
match a fresh Git checkout; media storage is created only during attachment.

The Windows smoke inputs are `--smoke-source-project <path-to-AuthoredSource.rebaseproj>`
and `--smoke-source-media <path-to-SelectedSource.wav>`. The packager passes these
only to its test run. This fixture is not the bundled user example and must not
be added to the release archive.
