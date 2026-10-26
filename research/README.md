# Research guide

This is the research behind Rebase: a static investigation of Cubase Pro 15.0.30.287 for macOS, using [morluto/rea](https://github.com/morluto/rea), with independently implemented application code and analytical controls. The proprietary reference has not been executed. **Reference runtime comparisons remain zero; full application equivalence is unestablished.**

## Start here

- [Study and evidence definitions](study.json): target identity, tools, hypotheses, acceptance rules and findings.
- [Coverage ledger](coverage.json): what has been investigated, admitted, rejected or left unresolved.
- [Research steering](rea-steering.json): investigation priorities, constraints and retained decisions.
- [Counted project structure and output routing](publication/project-composition-20261026/README.md): later REA findings, corrected binding decoder boundaries, provider/device restoration and unresolved processing. The associated [saved-structure inspector](../docs/development/saved-project-structure.md) has separate application validation.
- [Development overview at APP020](development-overview-APP020.md): the detailed application and research narrative before the current overlap implementation.
- [Experiment protocols](protocols/) and [research instruments](../scripts/): acquisition, byte verification, project inspection and deterministic audio checks.
- [Candidate DSP experiments](../candidate/): scoped implementations and their controls.
- [Publication manifest](publication/research-export-manifest.json): hashes of included records and an inventory of omitted local artifacts.

## Current application evidence

**APP020 is the latest sealed application milestone.** Its [acceptance record](evidence/application/APP020/application-validation.json) covers 301 tests in 47 suites, six bounded GUI groups and 20 unchanged QA package files. It admits complete direct-track source audition for supported chronological, disjoint events.

**APP021 implements overlapping source-track events.** The [full test record](evidence/application/APP021/core-test-run.json) covers 322 tests in 50 suites in the original research checkout. The [release build record](evidence/application/APP021/release-build.json) records a successful build. The [independent implementation review](evidence/application/APP021/overlap-application-independent-review/review.json) and [compiled kernel checks](evidence/application/APP021/overlap-kernel-check/result.json) provide additional scoped evidence. Four GUI input packages were prepared; final APP021 GUI acceptance and milestone sealing are pending. A successful build or synthetic check does not complete that acceptance.

The public application's neutral terminology, legacy contract decoding and optional external fixture configuration are subsequent publication changes. Its earlier validation is recorded separately in [publication validation](publication/application-validation.json). The downloadable privacy-cleaned build has a separate [0.21.0 release validation](publication/release-0.21.0/validation.json), including current tests, source identities, archive hashes and a launch/About-panel smoke check. Historical source hashes describe the preserved research checkout, not these later edits.

## Follow the object and audio work

- [CPR container](evidence/cubase-static/cpr-container-001/finding.json) and [native object readers](evidence/cubase-static/cpr-objects-001/native/finding.json).
- [Fixed clock](evidence/cubase-static/cpr-audio-timing-001/finding-v1.json) and [jump-map clock](evidence/cubase-static/cpr-map-clock-001/finding.json).
- [Event segment rendering](evidence/cubase-static/cpr-audio-events-001/event-rendering/finalization-finding.json), [timeline selection](evidence/cubase-static/cpr-audio-events-001/timeline-playback/finding.json), and [rate conversion](evidence/cubase-static/cpr-audio-events-001/rate-converter/finding.json).
- [Counted track contributors](evidence/cubase-static/cpr-audio-events-001/track-contributors/finding.json) and [overlap semantics](evidence/cubase-static/cpr-audio-events-001/track-overlaps/finding.json).
- [Explicit fade investigation](evidence/cubase-static/cpr-audio-events-001/explicit-event-fades/progress-01.json): unfinished, unsealed work. It does not enable fades in the application.

## Reading and reproducing the evidence

The research is published as a mixture of unchanged records and explicitly identified privacy-redacted derivatives. Personal author details, local home and temporary paths, and unrelated personal links are replaced. Six raw captures containing local filesystem or process details are omitted; the authored observations and findings remain. Target names, technical identifiers, failures, revisions, limitations and third-party attribution are retained. The study and coverage ledgers still reflect the latest sealed APP020 milestone.

The publication manifest records both each private original digest (`original_sha256`) and its distributed digest (`sha256`). Historical internal hashes and seals continue to identify the private original archive; they do not certify modified public copies. See the [privacy publication policy](publication/PRIVACY.md).

The publication includes the authored research and its compact evidence, not the full local acquisition and build archive. Hash manifests may refer to unavailable proprietary inputs, raw native slices or provider captures. Those references identify evidence; they do not mean that the referenced bytes are distributed here. Full recursive seal verification requires the original local archive. A public checkout must not be presented as independently verifying every retained claim.

Verify the 4,347 published records with `python3 research/publication/verify_research_export.py`. This checks their sizes and SHA-256 hashes. It does not verify the 20,432 omitted local acquisition, capture, fixture and build artifacts listed in the manifest.

Use the self-contained test lane described in the root README. Reference-dependent application tests require the external layout in [the test guide](../Application/Tests/README.md). Research scripts may additionally require their recorded target paths and pinned REA/Ghidra tools. They are preserved research instruments rather than portable one-command reproductions.

Source audition is bounded. Project mixer state, routing, effects, automation, fades, nested contributors, arbitrary source order and other unresolved processing are not restored by the current compatibility implementation. The application keeps unsupported state explicit.
