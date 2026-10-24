# Shared source-audio modes

The Mac scheduler and Windows helper now prepare the same eight source-audio modes through `CPRSourceAudition`. `StereoPCMBlock` owns planar Float32 samples; the Mac adapter copies those blocks into AVFoundation buffers. The portable helper writes a bounded Float32 WAV from a fresh cursor. This extraction reuses the existing static findings and reconstructed algorithms; it does not add proprietary runtime observations.

| Mode | Output clock | Placement / processing |
| --- | --- | --- |
| Original source | Attached source rate | Complete admitted event, saved gain |
| Timeline source | Attached source rate | Preserved source-clock placement and trim |
| Timeline current | Current Rebase project rate | Current-clock placement, unconverted frames |
| Timeline saved | Rate explicitly saved in the original source | Saved-clock placement, unconverted frames |
| Complete track | Saved project rate | All original direct-track contributors, signed priority and source order, audible fragments |
| Mode 0 | Current Rebase project rate | Existing reconstructed linear converter, then gain and output stages |
| Mode 1 | Current Rebase project rate | Existing reconstructed sinc converter, then gain and output stages |
| Mode 2 | Current Rebase project rate | Existing wrapper with pinned public SoXR 0.1.3, then gain and output stages |

Unconverted clock changes can alter speed and pitch. The explicit source converters remain separate from Windows output-device rate adaptation. Source modes bypass project routing, mixer, effects and automation. Full imported-project playback remains incomplete.

The existing converter input partitions, mode-0 singleton handling, gain order, stereo ring transfer and callback capacity remain shared. Seeking prepares a fresh cursor under the Mac selection/rounding policy before rendering a suffix. An EOF request still verifies provenance, produces an empty WAV with a complete manifest, and never installs an empty native source. Stop discards the installed suffix so a later status poll cannot reintroduce the old start offset.

The Windows **Source audio…** dialog exposes preparation availability, clock, duration, frames and contributor counts. Export writes a `.source-audition.json` file alongside its WAV. The helper verifies source, import report, project and required attached media before publication; complete-track proofs retain covered contributors. The host binds the returned mode, revision, identity, clock and full contributor proof to the selected project and output bytes. Existing WAVs and sidecars are preserved. Preparation availability does not establish device availability.

## Authored controls

`Application/Tests/Fixtures/SourceAuditionModes` contains two new forward-authored structural inputs: one admits all eight modes with 48 kHz source, 44.1 kHz current project and 32 kHz saved clocks; the other has three original contributors, a covered anchor, signed priorities and three audible overlap fragments. These are synthetic parser/planner controls, not reference-valid projects or reference audio.

The committed input bytes, source/report/project hashes and media hashes are fixed. Source archive and PCM generation are deterministic. The attachment API assigns new UUIDs and media filenames, so rerunning the opt-in generator does not promise identical project/manifest bytes. Generate into a new directory; never regenerate a failed comparison into the existing fixture or replace expected hashes to make a run pass.

The production-helper gate exercises all eight full renders and odd seeks, EOF, rewind, covered-media tampering, stale revisions, dirty history and exclusive output publication. Cross-platform lanes compare actual PCM and selected semantic manifests. Those comparisons establish implementation consistency within the authored cases, not sample equivalence with a reference executable.

Windows output remains a bounded snapshot: at most 32 million stereo output frames. Mac placed streams can admit longer timelines, up to the existing 24-hour guard. Streaming, physical Windows output, broader file/media support, routing and plugin behavior remain separate parity work.
