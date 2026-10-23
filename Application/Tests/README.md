# Running the tests

On macOS, from the repository root:

```sh
sh Application/Tests/run-tests.sh
```

This runs the self-contained project, parser, rendering, stream, and DSP tests.
Tests that need private source files or retained research oracles are reported as
disabled by Swift Testing, with an explicit reason. They are not counted as
successful fixture comparisons. The default wrapper clears any inherited private
fixture setting. Additional Swift test options, such as `--filter`, are passed
through to `Application/test-app.sh`.

The application and self-contained tests do not require a research checkout.
The platform toolchain and third-party build requirements are the same in both
test lanes.

## Optional private fixture lane

Researchers who already have the required inputs can keep them outside this
checkout and run:

```sh
sh Application/Tests/run-tests.sh --with-research /absolute/external/fixtures
```

Equivalently, the original test runner accepts the environment setting:

```sh
REBASE_RESEARCH_ROOT=/absolute/external/fixtures sh Application/test-app.sh
```

The root must be an existing absolute directory outside the source checkout,
including after resolving symlinks. An invalid explicit setting fails the
configuration test. A configured directory enables every fixture test; a missing
file, changed digest, or incompatible record then fails the relevant test. This
prevents an incomplete private run from silently becoming a successful public
run. The schema comparison additionally reports an explicit disabled test when
the system `xmllint` executable is unavailable.

The fixture root uses these neutral paths:

| Path | Required inputs |
| --- | --- |
| `templates/` | The ten pinned `.cpr` templates referenced by the inventory checks; original filenames and bytes |
| `evidence/cpr-static/cpr-container-001/` | `inventory.json` |
| `evidence/cpr-static/cpr-signature-001/fixtures/` | `finding-v1.json` |
| `evidence/cpr-static/cpr-audio-timing-001/` | `reviewer-template-state.json`, `reviewer-fixed-clock-vectors.json` |
| `evidence/cpr-static/cpr-map-clock-001/oracle-iterator/` | `map-clock-goldens.json` |
| `evidence/cpr-static/cpr-audio-events-001/autofade-source/` | `source-forward-probe.json` |
| `evidence/cpr-static/cpr-audio-events-001/segment-consumer/` | `interval-and-rate-vectors.json` |
| `evidence/cpr-static/cpr-audio-events-001/rate-converter/` | `finding.json`, `count_oracle.py`, `analytical-count-controls.json` |
| `evidence/cpr-static/cpr-objects-001/fixtures/` | The ten pinned `*-v09.json` inventory records |
| `evidence/application/APP003/` | Retained schema-one project packages |
| `evidence/application/APP004/` | Retained schema-two packages and signature controls |
| `evidence/application/APP010/` | Mode-zero and ring oracle JSON and generator files |
| `evidence/application/APP011/` | Downsampling oracle JSON and generator file |
| `evidence/application/APP012/` | Mode-two wrapper, public-backend oracles, and generator file |
| `evidence/application/APP013/` | Mode-one and callback-adapter oracle JSON and generator files |
| `evidence/application/APP014/` | Timeline-reader oracle JSON and generator file; `LoFi Native Timeline QA.rebaseproj/Project.json` for the historical zero-origin placement descriptor |
| `evidence/application/APP015/` | `placed-source-oracle.json` |
| `evidence/application/APP016/` | `accessor-state-oracle.json` |
| `evidence/application/APP017/` | `gain-order-stage-oracle.json`, `accessor-gain-oracle.json` |
| `evidence/application/APP019/` | `Historical V4 QA.rebaseproj`, `Saved V5 QA.rebaseproj` |
| `evidence/application/APP020/` | `track-controls-01/`, `track-controls-saved32k/`, `Two Track QA.rebaseproj` |
| `evidence/application/APP021/overlap-controls-01/` | Ten pinned symbolic `.cpr` controls and four `Overlap Signal 0.wav` through `Overlap Signal 3.wav` integer PCM assets |
| `references/dawproject/` | `Project.xsd` and its referenced schema dependencies |

The tests retain the existing digest and semantic assertions. Recorded template
source paths are resolved by filename into `templates/`; their original machine
prefix cannot redirect reads. Evidence files are read without rewriting their
contents. The optional lane neither downloads these inputs nor executes a
reference application. Passing it establishes the assertions in these tests,
not complete project or runtime equivalence.

Do not copy private fixtures into this repository. An external fixture view may
use symlinks to an existing private archive while preserving its original bytes.
