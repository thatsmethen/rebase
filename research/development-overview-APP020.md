# Cubase macOS research

Private development repository: [`repository-owner/rebase`](https://github.com/thatsmethen/rebase).
Source control includes the Rebase application, tests, research instruments,
compact findings and analytical controls. The official reference downloads,
extracted Cubase installation, native code slices, large REA provider captures,
media, screenshots and built application bundles remain in the local research
workspace. Retained manifests identify those local artifacts by hash; a manifest
entry does not mean the artifact is distributed in this repository.

Build on macOS 14 or later with `sh Application/build-app.sh`. The full
`sh Application/test-app.sh` suite requires the locally acquired reference
templates and historical evidence packages at their recorded paths. A source
checkout does not include those proprietary fixtures. Analytical controls are
included; reference-dependent tests must not be reported as passing without
their inputs. REA setup and static-only acquisition commands are documented below.

The latest packaged application is **Rebase 0.20.0**. Complete source-track
audition now includes every supported event on a direct audio track, in its saved
order, with gaps and exact source offsets. It uses the saved CPR clock while each
file keeps its own rate. Every counted contributor and media binding must pass;
unknown, missing, removed or overlapping contributors cannot silently disappear.

The admitted track has chronological, disjoint ranges, supported plain events
and no active fades. A fresh default filtering context is explicitly reconstructed;
live Cubase state is not restored. Project effects, mixer, routing and automation
remain outside this source audition. Historical reports and current projects are
not rewritten, and ordinary project playback remains guarded.

All **301 tests in 47 suites** pass. Final acceptance records **6 bounded
GUI groups** and **20 unchanged QA package files**. The signed release,
source and fixed test binaries have preserved identities.
See [APP020 validation](research/evidence/application/APP020/application-validation.json).

The multi-event controls test app parsing and exact sample composition; their
minimal ancillary objects are not proved native-valid CPR data. Overlap priority,
fades, hosted filtering, channel routing and full project playback remain unfinished.
**Cubase runtime comparisons remain zero; full reconstruction is not established.**

An active scientific investigation of **Cubase Pro 15.0.30**, directed with
[`morluto/rea`](https://github.com/morluto/rea), begun 19 October 2026.
This repository contains a native macOS application under `Application/`,
actual static reverse engineering of the official macOS executable and selected
bundled components, retained REA/Ghidra evidence, and instruments for subsequent
controlled experiments. **Full Cubase
reconstruction remains unestablished. No Cubase runtime behavior or candidate
conformance against a running reference has been measured.** Runtime work is
deferred at the user's instruction to proceed with static analysis first.
That deferral concerns the Cubase reference; the independently authored Rebase
application is built and executed for its own implementation checks. The goal
remains a complete native application reconstruction across editing, timing,
MIDI, mixing, plug-in hosting, persistence and interaction. The current app is
an early, incomplete implementation of that goal.

## Native application

The locally built application is `Application/dist/Rebase.app`. Build it with
`sh Application/build-app.sh`; run its tests with `sh Application/test-app.sh`.
The build uses SwiftPM, SwiftUI/AppKit, AVFoundation and reviewed
C conversion kernels. It targets macOS 14 or later and is signed locally for
development. No Cubase executable or proprietary library is linked into it.

Implemented workflows include self-contained projects with copied media,
mono/stereo audio import, actual waveform display, multitrack playback, seeking,
clip movement/end trimming/splitting/deletion, undo/redo, gain, pan, mute/solo,
project save/open and stereo float32 WAV mixdown. Stereo output meters use
actual audio-engine buffers. Named projects save
explicitly; New, Open and Quit protect unsaved edits, and Save As writes an
independent package. Scratch sessions retain a recovery copy.
`scripts/create_app_demo.py` creates an explicit, self-authored example project
for verification; a new application session starts empty.

The native app now includes jump-only tempo maps, signature changes at bar
boundaries, a bars/beats ruler, bar/beat/quantize snapping and relative dragging.
Track timebase can be seconds or musical: tempo edits move musical clip starts
while preserving source offsets and audio durations. Tempo ramps are explicitly
rejected because their reference interpolation domain remains unresolved.
Editable gain and pan automation supports outgoing hold/linear segments and a
Read gate; playback and export evaluate it at absolute sample times. Automation
writing and Cubase's named writer modes are not implemented. The musical model
and read curves are independently defined application behavior informed by the
documented contracts. CPR imports can additionally retain the separately bounded
native fixed and bounded jump-map clocks described below. Their recovered
arithmetic is separate from the application's general timing model; native
mixing algorithms remain unresolved.

DAWproject 1.0 import/export supports a strict, flat audio subset: seconds-based
mono/stereo clips with embedded media, jump tempo/signature maps, and explicitly
interpolated gain/pan automation. Source media must have an integral sample rate
from 8–192 kHz. Unsupported musical anchors, disabled automation, complex routing,
plug-ins and other unsupported content are rejected rather than silently lost.
Schema checks and local roundtrips do not establish exchange with Cubase.
A native **Import Cubase Project** command now inspects CPR object archives and
offers a reviewed partial import. It follows counted track hierarchies and
archive identities to recover ordered audio-track names, source-backed unresolved
audio events, plus a fixed clock or a supported serialized jump map when the
structurally bound native mode selects it.
For example, the shipped Classic House template restores its Bongos track and
126.5 BPM; Stereo Mastering restores its two audio-track names. The review
identifies unsupported tracks, events and linked missing VSTsound sources,
and separates descriptive metadata from active project settings.

Profile-v3 imports retain the native fixed clock's float32 period and exact
binary64 operation order, with 480 native ticks per quarter note. The input domain
is nonnegative, finite normal-or-zero values within application bounds, in
round-to-nearest mode. The clock must belong to
consistent verified tempo/signature interface pairs in the counted hierarchy.
An origin meter is recovered only when one compact record at zero agrees with
one supported typed Bar-0 signature. Conflicting representations remain
unsupported because native compatibility selection is unresolved.

V3 also recovers one- or two-point jump maps with the exact supported attribute
and variation states. Original float32 periods and float64 anchors are retained;
the saved anchors must match the native cache recurrence bit for bit. LoFi Hip
Hop restores 80 BPM at beat zero and 120 BPM at beat 800. Six pinned templates
now recover map clocks, while four fixed-clock results remain unchanged. Maps
with more points, ramps, unknown attributes or noncanonical anchors remain
unsupported. These are interpretations of preserved source records using
recovered native calculations. The default local construction path is traced,
but replaceable host providers and observers leave effective runtime clock
equivalence unverified.

Profile V4 adds counted MAudioEvent/PAudioClip objects and linked media/segment
records, including shared-object identity caches. LoFi Hip Hop restores a source
event at zero with a 24-second saved duration under the bounded type-10 scalar
contract. Classic House retains its musical event without assigning unverified
seconds. These are unresolved events, with explicit media and processing status,
not playable clips. The arrangement and inspector expose them; removal supports
Undo/Redo. Playback, mixdown and DAWproject export refuse to silently omit them.
Relinking to playable audio still needs the remaining event-rendering and
backend contracts. Raw values, object offsets, payload hashes and declared
media information remain attached to the original source interpretation.

Rebase 0.7 adds explicit **Attach Media** and **Replace Attached Media** actions.
A selected PCM file is copied into the project, checked against the saved frame
count, rate, channels, bit depth and frame size, and bound to the original CPR
SHA and AudioFile identity with its own SHA-256. The recovered integer segment
mapping checks source bounds for every event sharing that file before accepting
the association. Failed attachment leaves the manifest unchanged and removes
the attempted copy. The current gate supports one file and one segment per
linked event, mono/stereo PCM, at most 256 MiB and 16 million frames.
Attachments support Undo/Redo, removal, save/reopen and Save As. They remain
separate from frozen V4 import reports. Matching metadata does not prove that a
chosen file is the missing original. Attachment alone does not enable ordinary
project playback. The bounded source-rendering and explicit event-audition
operations below remain separate from full project transport.

Rebase 0.8 adds **Inspect Source Audio** and **Render Source Event**. The inspector
replays the preserved CPR and shows saved gain, inversion, explicit fade objects,
warp state and the effective project/track automatic-fade setting. Native
restoration ownership connects a null track override to the saved project
setting; neither null alone nor matching media metadata implies disabled fades.
The research renderer accepts a narrow direct-track, zero-origin, complete
PCM24 mono/stereo segment with explicit zero automatic-fade flags and no
unsupported fade, inversion, warp, pitch-child or lane state. It converts signed
PCM24 exactly by 2^23 and applies a separate Float32 event-gain multiply, then
exports Float32 WAV at the original source rate. It reconstructs fresh source
state without external pitch context; track effects, mixer and automation are
outside this operation. Source/report and attachment hashes are checked before
atomic publication outside the project. The unresolved event remains intact.
An eligible source can still have missing, changed or unsupported attached media;
the renderer validates the actual bytes before writing.

Rebase 0.9 adds **Play Event on Timeline** for an eligible attached stereo source.
It uses the same verified source samples and saved event gain at the source rate,
with Play/Pause, seek, return-to-start and end handling. A persistent **Source
Event Audition** banner identifies the event and provides **Exit Audition**.
Project effects, mixer, routing and automation are bypassed. Resume and seek
recheck the preserved source/report and actual media; changing the project,
attachment or selection stops and leaves the mode. The event is never promoted
to a normal clip, and ordinary Play, mixdown and exchange keep their existing
unresolved-content barriers.

The native segment selector is reconstructed as a bounded, unit-agnostic value
operation: generation changes reset scanning, an existing cursor follows its
successor, and scanning compares the segment end inclusively. The current
operation supplies a separately verified zero-origin source descriptor; this
does not establish the coordinate units of every native timeline builder.
Rebase's frame quantization and half-open sample intervals are explicit host
policies. AVAudioEngine schedules the samples; completion waits for the nominal
timeline and all `dataPlayedBack` callbacks so elapsed wall time alone does not
cut off the final buffer. This is an application delivery implementation, not
measured Cubase device-output behavior.

The separately tested native source-frame rate budget models request counts,
including the bounded initial-allowance branch and reverse correction. It does
not produce resampled audio. Rebase 0.10 adds a separate, explicit **Project rate ·
native linear mode 0** option for eligible stereo source events. The original
source-rate path remains the default. The new branch upsamples to a higher
integral project rate between 8 and 192 kHz, preserving the native binary64
phase/history recurrence and fused interpolation before one Float32 store.
Saved event gain is applied afterward. The first input frame becomes history;
EOF adds no repeated sample or padding. Thus the 24-second LoFi input produces
1,151,999 output frames at 48 kHz, rather than forcing 1,152,000.

Verified source PCM stays immutable and resident. Conversion advances in 8192-input
blocks, with four output buffers queued for AVAudioEngine. Each cursor transfers
stereo output through the recovered 32768-frame ring operations in chunks of at
most 8192 output frames, including blocks larger than the ring. Seeking resets
and discards preroll from the source origin, retaining the crossing-block suffix.
These chunk sizes, queue depth, serialized ring access and seek policy are
application choices. Through 0.12, refill depended on the main actor; 0.13 moves
refill to a serial worker. Neither queue establishes hard-real-time operation or
Cubase's complete live callback graph. Native ring stop/drain/underrun value
operations are tested separately;
ordinary transfer uses the sufficient-data branch.

Rebase 0.11 also supports explicit mode0 downsampling. Its small-ratio branch
retains deferred interpolation and depends on source/output address order and
block boundaries. Rebase puts output after input in one allocation, processes
8192-input blocks, and uses 8191 plus 2 frames instead of a final 8192 plus 1
to avoid a native one-frame lookahead path. Unsupported lookahead rejects before
writing. Both ratio branches retain their distinct rounding order; flush does
not append a tail. The LoFi-sized source produces 767,967 frames at 32 kHz and
384,000 at 16 kHz under this explicit policy. The captured equal-rate mode0
branch is not a transparent copy, so matching rates use original-rate audition.

The two inspected native AXt/offline construction paths select mode2 when
available and successfully created, otherwise mode1. Successful Float32 mode2
uses SoXR recipe 6/flags0 (VHQ). Mode0 remains a forced research choice; these
traces do not identify a global or observed runtime default.

Rebase 0.12 adds an explicit **Project rate · SoXR mode2** option for eligible
stereo source events, including higher, lower and equal project rates. The
reconstructed wrapper preserves rounded requested-frame counts, drift correction,
initial zero storage and discard, partial backend consumption/production,
compaction, and the final padding/drain rules. Positive EOF repeats the last
input frame; a separate null EOF supplies zero padding. Exactly one terminal
call is admitted. Returned wrapper frames are distinct from samples produced
by the backend. The application uses 8192-source-frame calls with the last
positive call final; the LoFi-sized source returns 1,152,000/768,000/384,000 frames
at 48/32/16kHz and 1,058,400 at its original 44.1kHz.

The filter is a pinned public SoXR0.1.3 scalar build, using Float32 interleaved
I/O, quality recipe 6/flags0 (VHQ) and runtime 0. Two independent build directories
produce an identical library. This is a public-source substitute with a recovered
wrapper, not a claim that the bundled vendor library or Cubase runtime produces
those samples. Gain remains after conversion; fresh source/media proof,
reset-and-preroll seeks and bounded ring transfer remain in place. Original-rate
audition remains the default. Backend failures are explicit; no mode0 or system
conversion fallback is silently substituted. Build provenance and license
notices accompany the public library; the build record is
`research/evidence/application/APP012/soxr-public-build/finding.json`.
The sealed native wrapper finding is
`research/evidence/cubase-static/cpr-audio-events-001/rate-mode2/finding.json`.

Rebase 0.13 adds explicit **Project rate · native sinc mode 1** audition for higher,
lower and equal rates. It reconstructs the coefficient/difference tables,
128-double channel history, ordered fused coefficient/tap calculations and
phase/count/final-trim rules. Equal-rate mode1 still filters; it is not a copy.
The application uses 8192-source-frame blocks with the last positive block final,
then applies event gain. Seeking creates a fresh kernel and repeats the same
source-origin preroll because native reset retains stored samples. Short initial
blocks can change results, so arbitrary partition invariance is not claimed.
Coefficient generation uses the traced beta bits for 8.96 and host libSystem
sin/sqrt; matching this construction does not establish vendor runtime identity.
The exact contract and storage/domain limits are retained in
`research/evidence/cubase-static/cpr-audio-events-001/rate-mode1/finding.json`.

Static callback ownership now connects the source-event audition producer to a
Float32 VstOpTrack adapter. After ring transfer, converted app buffers apply its
terminal-sample output stage with explicit zero prefix/offset and Rebase's block
partitions. A nonzero subnormal at the end of the first plane selects alternating
Float32 correction; an exponent-all-ones sentinel selects block clearing. This
is not a scan of every sample. Window, offset and transport-prefix arithmetic
are tested separately with explicit inputs; native transport context is not
inferred. The retained connection and remaining ordinary-channel provider edge
are in `research/evidence/cubase-static/cpr-audio-events-001/live-binding/finding.json`.

A serial worker now owns conversion and the four-buffer refill queue. Player
completions enqueue work; cancellation waits for producer serialization before
stop/detach. The source stays resident, and initial priming/seek preroll remain
synchronous. This removes main-actor refill dependence without proving realtime
deadlines or the absence of all underruns. The UI playhead remains host-time based.
Original-rate audition remains the default; all three converter choices are
explicit. Automatic native fallback, vendor library/runtime equivalence, general
event placement, inversion/fades/looping and complete scheduling remain open.
No frozen CPR profile, source report or original project is rewritten.

Rebase 0.15 extends **Native timeline reader · original rate** to supported
nonzero source events. Saved Start is interpreted through the containing track's
preserved native clock; Length and Offset use the clip's type10 sample datum.
The native builder snaps each coordinate separately before the reader applies
its own distinct quantizer. Whole-frame trims and offsets are checked against
the complete attached stereo PCM24 source. Leading silence is streamed, allowing
absolute positions up to 24 hours without allocating a whole silent arrangement.

The inspector exposes source start, duration and media offset. During audition,
the timeline shows this ephemeral range; the frozen V4 import remains unchanged.
The operation replays the original source clock even after the user explicitly
edits application timing. It requires zero saved track delay and reconstructs
fresh resource state without later host callback mutations. Its source-rate
builder context is explicit, not inferred as the hosted default. At APP015, nonzero events at differing output rates remained gated. APP018 adds
explicit unconverted project-clock playback; zero-origin mode0/1/2 conversion
keeps its separate contracts.

APP015 passes 258 tests in 40 suites, including 180 independent exact builder
controls and seven source-derived placement/trim/offset cases around the original
600-second tempo change. Eight final-release GUI groups cover placement, prefix
silence, live output, seek/pause/end, source tampering, project barriers and all
three converted audition modes. These use synthetic PCM and own-engine telemetry.
The acceptance record is `research/evidence/application/APP015/application-validation.json`;
full Cubase runtime equivalence remains unestablished.

Each imported project retains the exact original CPR and a versioned compatibility
report. Frozen v1, v2, v3 and v4 interpretations reopen earlier reports unchanged.
Reports replay their versioned source interpretation; loading or saving an active
native clock or unresolved event requires an exact match to that verified evidence.
Save As retains both files, while edits change the independent Rebase project.
Changing native timing or exporting it to DAWproject requires the explicit
**Use Rebase Timing** conversion, which retains musical anchors and recalculates
their seconds positions. Full CPR audio-track playback, MIDI, instrument and mixer state, broader
native tempo maps, signature changes and display state are not yet converted.
The 48 kHz application default remains explicit for historical profiles and
new imports without an admitted saved setup; V5 otherwise uses the recovered
base rate with factor +1. Unsupported-map 120 BPM and unrecovered 4/4 defaults
remain explicit. No compatible CPR writing or Cubase roundtrip is claimed.

A separate Convert Ambisonics command handles 4, 9 or 16 stored channels in
float32 or float64 using the reviewed static-derived processor. Its explicit
IEEE-float WAV writer preserves tested sample precision and channel order;
arbitrary source metadata and speaker labels are not preserved. This is file
conversion, with no live multichannel insert or track-bus integration.

The ordinary project audio engine uses linear sample-rate conversion and its own stated
mono pan/stereo balance rules. Edits during playback rebuild prepared buffers
and restart at the current position; this is not yet a continuous realtime
mix engine. The `.rebaseproj` format is an independently defined project bundle.
Recording, MIDI editing, VST hosting, plug-in delay compensation, complete mixer
routing, automation writing, audio time stretching, full CPR project compatibility,
the remaining DSP library and complete Cubase interaction fidelity remain
unimplemented or unverified. Implementation progress and reference conformance
are tracked separately; **the Cubase runtime comparison count remains zero**.

Rebase **0.13.0** passes **238 tests in 36 suites**, retained in
`research/evidence/application/APP013/core-tests-first.log`. Six independent
mode1 tests compare 2084 exact output samples, six complete coefficient/difference
table pairs, short-block/history/reset cases and four full-source count ledgers.
Four callback tests cover 316 independent numerical/plane/prefix cases, including
16 fused-operation discriminators. Eight queue tests cover ordered refill,
cancellation/failures and offline AV playback while the main actor is blocked.
These are implementation and analytical checks, not vendor output comparisons.
UBSan authored controls passed. ASan failed during host sanitizer initialization
before candidate main; the retained failure is not an ASan pass.

Eight final-release GUI groups cover mode1 up/down/equal admission and transport,
media tampering, edit/Undo exits, ordinary-project barriers, mode2 regression and
original-rate regression. Independent review checked 41 retained records
(35 accessibility states, one screenshot and five JSON records), 15 unchanged
package files and 23 source/test pins. It did not replay the UI or capture DAC
output. The acceptance is
`research/evidence/application/APP013/application-validation.json`, alongside
`research/evidence/application/APP013/gui-independent-check.json` and a 250-entry
source snapshot. The final 0.13.0 build 13 executable is 4,912,720 bytes, SHA-256
`6ac7a0a8940f273d19b8ff415dbaadc820980fafe2345d30cd681b340607036d`.
Module-cache/test corrections are retained. Exact source inventory and recursively
pinned prior/native evidence are checked again at sealing. Cubase executions and
runtime comparisons remain zero.

Earlier Rebase **0.12.0** passed **212 tests in 31 suites**, retained in
`research/evidence/application/APP012/core-tests-first.log`. Seven focused tests
cover 47 original-instruction spy cases, four full-source count ledgers and 27
separate public-SoXR wrapper cases, checking 561,454 returned Float32 sample bits.
Exact drift 1, discard boundaries, compaction, requested-versus-produced counts,
positive/null EOF, singleton high ratios and alias/capacity/backend failures are
covered. The public sample oracle calls the same pinned library directly through
an independently authored wrapper; it does not independently verify the filter
or bundled library. Actual cursors, gain/ring transfer, seek suffixes and CPR
custody are checked separately. The independent review is
`research/evidence/application/APP012/mode2-independent-review.json`.
Eight final-release Rebase GUI groups cover mode2 up/down/equal-rate admission,
transport/seek/end, media tampering, edit/Undo exits, ordinary-project barriers
and original-rate regression. Independent review checked 36 retained records
(30 accessibility states, one screenshot and five JSON custody/identity records)
and 15 unchanged files across three QA packages. It also verified the bundled
public library loaded by the running application. The reviewer did not replay
the UI or capture physical audio output.

The accepted record is
`research/evidence/application/APP012/application-validation.json`, with
`research/evidence/application/APP012/gui-independent-check.json` and a 238-entry
source snapshot that includes 138 upstream source/license entries. The final
0.12.0 build 12 executable is 4,878,128 bytes with SHA-256
`3cb6b102a31314d7bd05d38c72f5bb7dcc54c9c6af19863e44029609ca154d87`.
Module-cache and packaging corrections are retained. The initial independent
five-test run succeeded; the later run expanded it to seven tests. No Cubase
runtime comparison has been performed.

Earlier Rebase **0.11.0** passed **200 tests in 29 suites**, retained in
`research/evidence/application/APP011/core-tests-first.log`. Independent exact
arithmetic controls cover 105 sample/state vectors, 18 large partition cases,
fused-operation and mono/stereo carry discriminators, both address layouts,
ignored flush, lookahead rejection and transactional errors. Actual planar
cursor buffers and seek suffixes match independently generated sample hashes.
The full-source 32/16 kHz counts are checked separately, and offline AVAudioEngine
checks cover three rates and a 257-frame silent tail. Eight final-release GUI
groups cover lower-rate admission and transport, media tampering, edit/Undo
exits, ordinary-project barriers, equal-rate rejection and original-rate
regression. Independent review of retained states and fresh hashes confirms
15 unchanged files across three QA packages; it did not independently replay
the UI or capture DAC output. The accepted record is
`research/evidence/application/APP011/application-validation.json`, with
`research/evidence/application/APP011/gui-independent-check.json` and an
88-file source snapshot. Earlier runner, test-expression and generated-module
cache failures are retained. These checks establish neither a global Cubase
backend default nor target runtime conformance.

Earlier Rebase **0.10.0** passed **191 tests in 28 suites**, retained in
`research/evidence/application/APP010/core-tests-final.log`. New controls cover
exact-rational interpolation bits and state across input partitions, reset/preroll
seek suffixes, transactional sample/rate rejection, ring wrapping and
stop/drain/underrun distinctions. A high-ratio control checks all 393,314 Float32
output samples by exact-byte digest while a converted block crosses the entire ring capacity.
The initial full-suite compile failure from a test expression is retained;
the corrected full suite passes. Eight final-release GUI groups cover inspection
and mode choice, converted transport/end bounds, media tampering, edit/Undo
exits, ordinary-project barriers, original-rate regression, explicit exits and
equal-rate rejection. Independent inspection of 29 retained accessibility records
and fresh hashes confirms ten unchanged files across the two QA packages. The
reviewer did not independently replay the UI, and output peaks do not measure
DAC sample equivalence. The accepted record is
`research/evidence/application/APP010/application-validation.json`; the independent
GUI check is `research/evidence/application/APP010/gui-independent-check.json`.
These are analytical and application checks, with zero Cubase runtime comparisons.

Earlier Rebase **0.9.0** passed **171 tests in 25 suites**, retained in
`research/evidence/application/APP009/core-tests-release.log`. New controls cover
native segment selection separately from host frame scheduling, exact stereo
sample copying across seek boundaries, source/media/report changes and an
offline AVAudioEngine unity-route tail check. Seven bounded native GUI groups
passed on the final release: Open/inspect,
play/pause/seek/end, restart/stop/bounds, changed-media rejection/restoration,
project playback/export barriers, edit/Undo exits and explicit Exit Audition.
Independent accessibility-record and hash review supports those outcomes and
five unchanged package files. All seven groups were repeated after correcting
shared error wording and the stale status label on edit exit. The acceptance
record is `research/evidence/application/APP009/application-validation.json`.
These checks do not establish physical device output or Cubase runtime conformance.

Earlier Rebase **0.8.0** passed **158 tests in 23 suites**, retained in
`research/evidence/application/APP008/core-tests-source-render-final.log`.
Controls cover forward automatic-fade object semantics, typed ownership,
malformed source state, exact PCM/gain arithmetic, bounded WAV parsing,
source/media tampering and unchanged project custody. Native GUI checks exercise
source inspection, separate WAV export, cancellation/reopening and the continued
project-playback refusal. These are application and analytical checks using
self-authored PCM, with zero Cubase runtime comparisons. The retained APP008
validation distinguishes those checks from open compatibility work.

Earlier Rebase **0.7.0** passed **138 tests in 20 suites**, retained in
`research/evidence/application/APP007/core-tests-final.log`. The added controls
cover integer segment arithmetic, explicit media associations, shared-file
transactions, format and source-proof rejection, changed/missing assets, package
persistence and unresolved-processing barriers. Ten native GUI groups check
backward opening, rejected media, attachment, replacement, Undo/Redo, removal,
save/reopen, Save As and checksum rejection. Self-authored PCM validates these
workflows; it is not reference audio. APP005 and APP006 artifacts remain intact.
The full-fidelity objective remains incomplete; native timeline rendering and
the remaining event-processing states are the next compatibility targets.

Earlier Rebase **0.6.0** passed **124 tests in 18 suites**, retained in
`research/evidence/application/APP006/core-tests-final.log`. New checks cover
shared source objects, exact LoFi placement, rejected coordinate/rate/rounding
variants, source replay, package forgery rejection and unresolved playback/export
barriers. Ten bounded native GUI groups check LoFi and Classic import, source-event
inspection, removal/Undo/Redo, playback/export refusal, save/reopen, Save As and
frozen V3 reopening. The source studies and application checks do not establish
Cubase runtime fidelity.

The earlier Rebase **0.5.0** passed **108 tests in 16 suites**, retained in
`research/evidence/application/APP005/core-tests-final.log`. The new map kernel
matches 105 independent analytical vectors, with separate quantizer, fused
operation, rejection and fixed-clock regression controls. Ten bounded native
GUI groups check import, protected timing, conversion, cancellation, Undo/Redo,
save/reopen, export and a deliberately altered anchor. Two saved packages and a
converted DAWproject were independently inspected. All 107 APP004 evidence files
and 18 historical package files remain unchanged. APP005 retains the final
source and binary snapshots, strict local signature verification and
`application-validation.json`. These checks establish this application slice;
Cubase runtime comparisons remain zero.

The earlier Rebase **0.4.0** passed **92 tests in 13 suites**, retained in
`research/evidence/application/APP004/core-tests-final.log`. The new timing,
signature, profile-replay and provenance checks include ten pinned factory
templates, concordant/conflicting signature controls and forged-clock rejection.
The optimized fixed-clock kernel matches 36 independent analytical bit-pattern
vectors, including seven operation-order discriminators. The 0.4.0 build passes
strict local signature verification and twelve bounded native GUI check groups.
Three saved packages and a converted DAWproject export were independently
inspected; all nine historical APP003 package files remain unchanged.
`APP004/application-validation.json`, `gui-observations.json` and
`final-source-snapshot/` pin the checked build, workflows and sources. These
checks do not establish Cubase runtime conformance. APP004 retains the integration report,
its additive role-validation correction and `cpr-v2-integration-review.json`,
which independently accepts the final bounded integration.

The earlier Rebase **0.3.0** passed **68 tests in 11 suites**, including 13 CPR tests, retained
in `research/evidence/application/APP003/core-tests-final.log`. APP003 records
native GUI import, report, Save As, reopen, cancellation and malformed-input
checks. Independent comparisons verify the original CPR bytes, archive object
ranges and recovered subset in three saved packages. Its
`application-validation.json` and `final-source-snapshot/` pin the checked build
and source. These checks cover a partial importer, not full project fidelity.

The earlier APP002 iteration passed 55 tests in 10 suites. It retains builds,
integration reviews, exchange fixtures and
`gui-automation-comparison.json`: the tested 648,000-frame stereo GUI export
matches an independently calculated application payload exactly. The ambisonic
integration report and wrapper review cover all 12 channel/precision/direction
combinations, chunk tails, float64 readback and failed-conversion preservation.
The native DAWproject export/import retained supported project semantics and
produced a byte-identical WAV; `gui-exchange-comparison.json` records the
independent manifest, XML, schema, media and sample checks. The native converter's
9-channel float64 output also matched the independent expected sample payload
(`gui-ambisonic-comparison.json`). `application-validation.json` records build
hashes, observed UI workflows, retained failures and limits, with the final
sources preserved in `final-source-snapshot/`.
These are application checks, not target conformance or whole-product completion.

Earlier native GUI checks and the three-source mixdown comparison remain in
`research/evidence/application/APP001/`. Its `application-validation.json` records
observations against build hashes and `shell-review.json` records source review.
Reproduce that earlier bounded mixdown comparison with
`scripts/verify_app_demo_export.py`; its report is
`research/evidence/application/APP001/gui-export-final-comparison.json`.

The target is the current build listed on the [official download page](https://o.steinberg.net/index.php?L=1&id=15431)
at study start. One installer serves several editions; a running Pro licence
must establish the reference edition. The complete universal executable has
SHA-256 `29586308db2731c26aa846bf7cfd6455b351da8be0f52109394c54a9294757e0`.
Its exact arm64 slice has SHA-256
`dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb`.
The complete extracted application identifies itself as **15.0.30.287**, build
`287`, identifier `com.steinberg.cubase15`. The full installer SHA-256 is
`0548f5c5fb0a024f6bfc5e10d58449c2916b277af326ba5c185b40e4463eb0a1`.
This host reports macOS 27.0/arm64;
Steinberg's listed supported versions are 14, 15 and 26. Runtime observations
here require replication on a supported configuration.

## Research record

- `research/evidence/cubase-static/`: actual native target observations, function dossiers, and retained queries.
- `research/evidence/cubase-static/ambisonic/`: AmbiConverter parameter and first-order DSP traces.
- `candidate/ambiconverter_first_order/`: a restricted C reconstruction of the traced float32/float64 conversion path, with exact coefficient bits and synthetic checks.
- `research/evidence/cubase-static/ambisonic-review/review.json`: independent byte, contract and implementation review, including ten additional check groups.
- `research/evidence/cubase-static/ambisonic/higher-order-finding.json`: separately reviewed 9/16-channel operators and exact gains; runtime comparison remains pending.
- `research/evidence/cubase-static/ambisonic/state-contract-finding.json`: independently reviewed parameter, zero-frame, bypass, silence and corresponding-buffer alias branches for both precisions.
- `candidate/ambiconverter_processor/`: bounded 4/9/16-channel float32/float64 processor reconstruction, including reviewed state branches and synthetic tests; integrated into standalone file conversion.
- `research/evidence/application/APP002/ambisonic-integration/integration-report.json` and `ambisonic-wrapper-review.json` in APP002: file-format, sample-byte and independent wrapper checks, including the retained initial float64 encoder failure.
- `research/evidence/cubase-static/musical-time-001/`: shipped timing presets, API declarations, official ruler/snap/timebase documentation and independent jump-map application validation. These earlier observations are distinct from the later native clock traces.
- `research/evidence/cubase-static/automation-001/`: bounded native recorder flags/callback traces and separately defined application curve tests; the connection to named automation writer modes remains unresolved.
- `research/evidence/cubase-static/dawproject-001/native-finding.json`: native parser/writer observations for tempo and parameter fields; host units, DSP transforms and actual emitted XML remain bounded by untraced calls.
- `research/evidence/application/APP002/automation-integration-review-final.json`: track timebase, sample-timed read automation and strict exchange integration review, including corrected source-format rejection tests.
- `research/evidence/cubase-static/cpr-container-001/`: ten shipped Pro templates with a verified RIFF/NUND envelope, alternating ROOT/ARCH chunks and root names.
- `research/evidence/cubase-static/cpr-objects-001/`: native archive dispatch/identity, counted track hierarchy, fixed-tempo selection, audio descriptor/path relationships and independent fixture decoding. The app implements a reviewed partial importer; playable events, complete state and CPR writing remain unresolved.
- `research/evidence/cubase-static/cpr-audio-timing-001/`: native clock interface consumers and fixed arithmetic, initial map investigations and independent analytical bit vectors. AudioCluster event/source binding remains pending.
- `research/evidence/cubase-static/cpr-map-clock-001/`: one/two-point jump-map attribute, iterator, default lifecycle and canonical-cache findings; analytical oracle and optimized kernel checks. The stronger whole-host lifecycle gate remains open.
- `research/evidence/cubase-static/cpr-signature-001/correction-v2.json`: correction to the earlier unconditional typed-signature interpretation; the implemented origin subset requires compact/typed agreement.
- `research/evidence/application/APP004/`: frozen-v1/profile-v2 replay, fixed-clock and origin-signature integration, independent reviews, negative controls and the 92-test application suite. Twelve native GUI check groups and independent package/export checks are recorded in application-validation.json.
- `research/evidence/application/APP005/`: frozen-v1/v2 replay plus profile-v3 map recovery, 108 tests, ten native GUI groups, independent package/export checks and source/binary snapshots. `next-cpr-audio-event-slice.json` defines the next event-placement and source-interval questions.
- `research/evidence/application/APP006/`: frozen-v3/profile-v4 replay, source-backed unresolved events, bounded LoFi placement, 124 tests and ten native GUI groups.
- `research/evidence/application/APP007/`: checked segment intervals, explicit PCM attachments, 138 tests, ten native GUI groups, independent source/media custody checks and release snapshots.
- `research/evidence/cubase-static/cpr-audio-events-001/`: source timebase, cluster fields, audible state, segment read mapping, conditional stream selection and rate-converter count traces. These static findings do not establish final rendered sample parity.
- `research/evidence/cubase-static/cpr-audio-events-001/rate-samples/finding.json`: explicit mode0 upsampling sample/state arithmetic, reset and no-tail behavior; independent Fraction controls and optimized candidate checks.
- `research/evidence/cubase-static/cpr-audio-events-001/live-consumer/finding.json`: bounded stereo ring transfer and stop/drain/underrun contracts. It also corrects the earlier interpretation of literal 5 as a format: that argument is flags. Full callback routing remains unresolved.
- `research/evidence/application/APP010/`: 191 tests in 28 suites, exact sample and ring controls, eight accepted GUI groups and independent preservation checks for ten QA package files. Historical and superseded test snapshots are distinguished from final release acceptance.
- `research/evidence/cubase-static/main-reference-review/finding.json`: main-executable interpolation and pan-law parameter-display helpers, verified against original instruction bytes. Their connection to an audio panning path remains unproven.
- `research/evidence/cubase-static/main-function-slices/raw-slice-analysis.json`: five bounded REA/Ghidra function dossiers, independently checked against the original bytes; missing import/global/exception context is explicit.
- `research/evidence/cubase-static/main-analysis-strategy.json`: whole-image provider failures and the separately scoped successful method. No whole-image analysis completion is claimed.
- `research/evidence/cubase-static/graphics/findings.json`: bounded image-generator factory and graphics-library relationship.
- `research/evidence/cubase-static/bundle-manifest/findings.json`: 2,204 declared bundle paths and a comparison against recovered files.
- `research/evidence/cubase-static/midi-remote/finding.json`: three sealed source files, a concrete controller mapping, and the boundary between API stubs and unresolved native host behavior.
- `research/evidence/acquisition/full-reference-2026-10-19/summary.json`: complete reference verification, actual bundle identity and reconciliation with earlier partial evidence.
- `research/study.json`: target selection, evidence classes and current acceptance state.
- `research/rea-steering.json`: the staged REA investigation and claim requirements.
- `research/coverage.json`: initial decomposition into 25 research domains. It is not an exhaustive feature denominator.
- `research/protocols/E001-audio-export.json`: first preregistered export experiment, still unrun.
- `research/protocols/E002-ambiconverter-disconfirmation.json`: prospective channel, parameter-queue and higher-order composition probes; no target captures performed.
- `research/sources.json`: official source links and the claims each supports.
- `research/evidence/tooling/`: instrument verification, exact outputs and provider calibration. Synthetic controls are explicitly labelled.
- `research/targets/`: local reference downloads/extractions, excluded from source control.

The complete application intake records 2,200 regular files, eight symlinks and
538 directories. The earlier immutable snapshot, `partial-components-04`,
contains 803 complete regular files and remains preserved. The plug-in-set inventory includes 535 controller
XML representations declaring 100 distinct class IDs; these are declarations,
not a complete count of Cubase functionality. Its complete bundle metadata
declares `15.0.30.131`, distinct from the outer application build `15.0.30.287`.

## Acquisition and integrity boundary

The complete official installer contains 1,226,998,651 bytes. Independent checks
match all 69 recorded HTTP segments and the final SHA-256; native `hdiutil`
verification passes. All 49 XAR data checksums and 11 gzip streams pass. Native
`pkgutil` validates the Steinberg installer signature and reports Apple notary
trust. The SHA-256 is a locally computed fingerprint, not a comparison with a
published vendor digest; fresh online certificate revocation was not separately
checked.

The package was expanded without installation or target execution. Native strict,
deep signature verification across both architectures passes for the complete
application, with eight additional explicit VST3 bundle checks. The read-only
disk-image mount has been detached; the extracted application remains available
under `research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/`.

Earlier component recovery used journal-verified HTTP ranges and UDIF, HFS+, XAR
and bounded CPIO decoding. Against the native full extraction, 802 of 803 regular
paths match exactly. The remaining AppleDouble sidecar is recovered verbatim
from the complete CPIO payload; its four attributes match the native extended
attributes. The native extraction was not altered to manufacture a regular-path
match. All earlier snapshots and their derivations remain preserved.

For the main executable, all 48,024 embedded code-page hashes match across both
architectures and both embedded CMS signatures verify mathematically. That early
page check alone did not establish outer bundle integrity; the later complete
native bundle verification is retained separately with its exact scope.

Analysis uses REA 6.7.0 and Ghidra 12.1.4. Universal binaries remain unchanged;
Ghidra receives exact, separately hashed arm64 byte slices. Decompiled text is
an analysis artifact, not recovered original source. Unresolved indirect calls
and uncertain ABI types remain explicit in the dossiers.

## Local instruments

Run from this directory. Python tools require Python 3.10 or later; REA uses the
installed Node 24.14.0. No global MCP registration is required for these commands.

```sh
# Recreate the pinned local REA package if absent.
npm install --prefix .tools/rea --no-audit --no-fund --ignore-scripts --save-exact rea-agents@6.7.0

# REA uses a local Ghidra installation when present. Inspect the actual result.
sh scripts/rea --help

# Test the research instruments with synthetic controls.
python3 -m unittest discover -s tests -v

# Create a new deterministic six-second stereo PCM24/48 kHz stimulus corpus.
python3 scripts/audio_probe.py generate research/fixtures/new-run

# Compare original stored sample positions. Both tolerances default to zero.
python3 scripts/audio_probe.py compare /absolute/reference.wav /absolute/candidate.wav

# Inventory an explicitly selected, extracted .app without executing or copying it.
python3 scripts/intake_target.py '/absolute/Cubase.app' --out research/evidence/new-target --inspect-file
```

The comparison supports RIFF PCM16/24/32 and IEEE float32/64, including full-width
extensible formats. It rejects unsupported/malformed inputs and nonfinite samples.
Exit codes are 0 for a passing sample comparison, 1 for mismatch and 2 for invalid
input. A sample pass does **not** validate export format, speaker layout, routing,
provenance or product equivalence; E001 requires those checks separately. The
tool performs no time alignment, cropping, gain fitting, resampling or channel
reordering. It is intended for short controlled captures, not whole sessions.

The initial E001 corpus is preserved in `research/fixtures/E001`. Its manifest
identifies the exact generator source archived in the tooling evidence directory.
Use fresh output paths; existing evidence is not overwritten.

The initial Python instrument suite passed 40 synthetic controls, with output
retained in `research/evidence/tooling/instrument-suite-2026-10-19.txt`. The
restricted first-order C candidate has eight author test methods and ten
independent check groups recorded separately. The later 4/9/16-channel processor
has 13 passing author methods recorded in the APP002 integration report. None of
these counts is a target-conformance count.

## Remaining experimental boundary

The next application research priority is the finite event-rendering consumer:
gain, fades, looping, stream cache selection and actual backend format/rate
behavior. Checked segment intervals and explicit source-media attachment are
implemented, while playable imported events still require these rendering
bindings. Continue broader coordinate/variable-map contracts, MIDI event/time
contracts, mixer routing and
latency compensation, plug-in hosting, and automation write-mode transitions.
The current importer covers a bounded subset of CPR state; the container and
clock findings do not establish complete project compatibility.
Extend static traces around explicit questions and implement the resulting
bounded application workflows; do not reduce the full application goal to DSP.
The current state contract includes a strict `p > 0.5` bypass threshold, distinct
from direction's `p >= 0.5` high branch; parameter consumption before a zero-frame
return; bypass priority over the silence test; and corresponding-buffer staging.
Meter publication and wider lifecycle behavior remain unresolved. Independently
implemented static-derived candidates must retain their exact assumptions and
must not be promoted to measured target conformance. When runtime research is
resumed, qualify the identified Pro reference with repeated captures, then use
negative controls and held-out compound scenarios. Preserve raw exports,
project files, configuration, action histories, failures and uncertainties.
Passing a function reconstruction or these instruments does not establish full
Cubase fidelity.
