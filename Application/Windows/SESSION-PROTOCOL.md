# Local Windows session protocol 1

`Rebase.exe` launches its bundled `rebase-session.exe --stdio` directly, without a shell. This is a local child process, not a network listener. Each request and reply is one UTF-8 JSON line. Standard output is protocol only; diagnostics use standard error. Requests are limited to 64 KiB. The frontend checks protocol version, ordered response identifier, and a 16 MiB response limit. Requests are serialized; their positive unsigned 64-bit identifiers strictly increase even after operation failures.

```json
{"protocol":1,"id":1,"command":"open","expectedRevision":0,"path":"C:\\Projects\\Song.rebaseproj","discardChanges":false,"asCopy":false}
```

Every command except `state` includes the current `expectedRevision`. The helper owns the full project, selection, validation, edit history, media checks, persistence, and rendering. The frontend owns display geometry, dialogs, view zoom, and native transport. It never reconstructs project edits from a returned DTO or writes project JSON itself.

| Command | Additional fields |
| --- | --- |
| `state` | None. |
| `open` | `path`: package directory or its `Project.json`; `discardChanges:true` only after the user elects to discard; `asCopy:true` for the included example. |
| `inspectCPR` | `path`: raw CPR file. Creates one reviewed snapshot without changing the active document. |
| `cprReviewPage` | `reviewID`, `reviewOffset`: next or previously visited item offset within that snapshot. |
| `cancelCPRReview` | `reviewID`: discard that snapshot without changing the active document. |
| `importCPR` | `reviewID`, `sourceSHA256`, `allowPartial:true`, `path`: new `.rebaseproj` destination. `discardChanges:true` only after explicit choice. |
| `cprImportReport` | Revalidate and review the current package's historical import report, read-only. |
| `selectClip`, `selectTrack` | `clipID` or `trackID` UUID string. |
| `moveClip`, `trimClip`, `splitClip` | `clipID`, finite `value` in seconds; trim uses absolute end time. Optional `snap`: `off`, `quarter`, `eighth`, `sixteenth`, `bar`. |
| `deleteEvent` | `clipID`. |
| `setGain`, `setPan` | `trackID`, finite `value` in dB or −1…1 pan. |
| `toggleMute`, `toggleSolo` | `trackID`. |
| `upsertAutomationPoint` | `trackID`, `parameter`: `gainDB` or `pan`, `time`: absolute project seconds, `value`. Optional existing `pointID`; omit to insert a new identity. Optional `interpolation`: `linear` (default) or `step`. |
| `removeAutomationPoint` | `trackID`, `parameter`, existing `pointID`. |
| `setAutomationRead` | `trackID`, `parameter`, required Boolean `enabled`. |
| `setTempo` | Finite `value` in BPM. |
| `undo`, `redo`, `save` | None. |
| `saveAs` | `path`: a new, nonexistent `.rebaseproj` directory with an existing parent. |
| `render` | `path`: a new WAV outside the source package. |
| `attachSourceMedia` | `clipID`: retained event; `path`: explicitly selected matching PCM24 WAV. Shared history records the association and selects the event. |
| `inspectSourceEvent` | `clipID`: retained event. Read-only preparation availability for all eight source modes. |
| `renderSourceEvent` | `clipID`: retained event; `path`: a new WAV outside the package. Optional `mode` (default `sourceRate`), `startSeconds` (default 0), `rewindAtEnd` (default false). |
| `waveform` | `clipID`: ordinary clip. Read-only source envelope, no revision change. |
| `ruler` | Required finite `value`: pixels per second in 4…420. Optional finite `duration`: extent in seconds in 0…86,400. Read-only musical ticks, no revision change. |

Quarter/eighth/sixteenth snapping is 1, 0.5, and 0.25 quarter notes. Bar snapping uses the shared signature map. The helper derives trim limits from checked media and generates split identifiers. The frontend sends proposed seconds from pointer geometry, leaving all snapping and edit rules to Swift.

Automation commands use the shared lane model and edit history. Times must be
finite and within 0…86,400 seconds, volume values within −96…24 dB, and pan
within −1…1. These commands do not snap or clamp values. Interpolation belongs
to the point's outgoing segment. Linear volume interpolation is in dB; step
holds until the next point's exact time. Automation replaces the manual value;
Read off or an empty lane uses the manual track value. Rendering evaluates the
lane at absolute project-frame time, independently of clip source offset.

A provided point identifier must exist in the selected parameter's lane;
otherwise the command fails without changing state. A new point gets a helper
UUID. An insertion at an occupied timestamp replaces that point, and moving an
existing identity to an occupied timestamp removes the displaced point. The
result remains sorted by time. Existing lane identity, Read state, other lanes
and other tracks are retained. New lanes default to Read on; `setAutomationRead`
can create an empty lane with the requested Read state. Removing the final
point retains the empty lane and its identity. An unchanged existing point or
Read value succeeds without advancing revision or clearing redo history; the
revision check still precedes that no-op. Missing removal targets fail.

Session edits may grow a lane to 4,096 points. Beyond that, an edit which would
increase the count fails with `automationLimit`. Existing larger lanes remain
loadable, editable and reducible without truncation. The limit does not change
the project format. The authoritative projection remains the complete
`state.project.tracks[].automation` array, including every point and identity.

CPR inspection and historical report review return `cprReview` with a UUID
`reviewID`, `sourceName`, `sourceSHA256`, `sourceByteCount`,
`interpretationProfile`, `historical`, `canImport`, `recoveredTrackCount`,
`recoveredClipCount`, `unresolvedEventCount`, `totalItems`, `offset`, optional
`nextOffset`, and `items:[{section,label,detail}]`. Section keys are `recovered`,
`tracks`, `unresolved`, `defaults`, and `metadata`. Each encoded page is at most
128 KiB and 32 items; an individual item that cannot fit rejects the review
instead of silently truncating it. The report is bounded to 8 MiB. The full
report and recovered project are not duplicated into the review response.

Only one review token is current. A new inspection/report supersedes the old
token. The host validates page identity and progression, exposes every page,
and submits the reviewed token and exact source digest on confirmation.
Inspection, pagination and cancellation leave the active project, revision,
selection and history unchanged. A historical report is replayed using its
frozen interpretation and cannot be imported through its review token.

Import requires explicit partial acceptance even when the supported subset is
small. It preserves dirty-project protection and rejects a source changed since
review. The core creates a new package with the original bytes and report,
verifies it before publication, and refuses existing destinations. Only a
validated published package replaces the session, resets history and advances
the revision. If publication succeeded but a subsequent read failed, or the
helper stopped before its reply arrived, the destination may already exist.
The host reports that uncertainty and never automatically retries or overwrites
it. Review does not attach media or make unresolved native events playable.

`ruler` returns `ruler:{revision,duration,pixelsPerSecond,ticks:[{seconds,bar,label}]}`.
`bar` is a Boolean marking a bar boundary, and `label` is the one-based bar
number as ASCII decimal digits (at most 10 characters), including on minor
ticks. At 96 BPM in 4/4 with 100 pixels per second, the first five ticks are
`0, 0.625, 1.25, 1.875, 2.5` seconds, with bar flags
`true, false, false, false, true` and labels `1, 1, 1, 1, 2`.

The omitted extent defaults to `min(86400, max(30, arrangementDuration + 8))`.
An explicit extent outside 0…86,400 or scale outside 4…420 is rejected; neither
is silently clamped. Valid projections start at `{seconds:0,bar:true,label:"1"}`
even for zero extent. Later seconds strictly increase and never exceed the
accepted extent. At most the first 8,192 ticks are returned; the host must leave
any remaining span unlabeled rather than invent timing. Zoom chooses visual
density using the existing Mac 12-pixel target: denominator beats when they fit,
otherwise whole-bar strides. Hosts may suppress overlapping bar labels (the Mac
uses 55 pixels between labels), without changing tick positions or snap rules.

Both hosts use the same shared tempo/signature projection, including checked
native clock arithmetic when present. Bar numbering and density remain
application display policy, not verified reference display behavior. This does
not convert a native clock, attach media, resolve source events, or enable project
playback. The command rejects stale revisions and external manifest changes and
leaves project, selection, dirty state and history unchanged. A frontend must
match revision, requested extent and scale before drawing a reply; background
ruler requests must not replace its current document state.

Every reply includes the full state, including failures:

```json
{"protocol":1,"id":1,"ok":true,"state":{"revision":1,"dirty":false,"needsSaveAs":false,"path":"C:\\Projects\\Song.rebaseproj","project":{},"selection":{},"canUndo":false,"canRedo":false}}
```

Here `project` is the ordinary serialized shared `Project` model (the empty object above abbreviates it). Before opening a project, it is absent or null. Selection has optional `trackID` and `clipID`. Failure replies set `ok:false` and add `error:{"code":"...","message":"..."}`; the current state remains authoritative. A malformed request can have no reply identifier and is treated as a failed protocol exchange by the host.

Opening, edits, attachment, undo, redo, and Save As advance the document revision when they change state. Selection and Save do not advance it. The included example is cloned into helper-owned scratch storage and reports `path:null` and `needsSaveAs:true`; its original bundled files are never the editing destination. Save verifies the previously opened manifest has not changed outside the session. Save As copies the project into a new destination, retaining checked sidecars. Ordinary project rendering continues to reject unresolved CPR events and native timing.

A successful render adds:

```json
{"render":{"kind":"project","path":"C:\\Output\\snapshot.wav","revision":4,"sampleRate":48000,"frames":960000,"channels":2,"wavBytes":7680058,"sha256":"hex-digest-of-complete-wav","kind":"project"}}
```

The frontend verifies the returned path, revision, byte count, SHA-256, exact Float32 stereo WAV format, frame count, and finite samples before handing a copied snapshot to `RebaseWindowsAudio.dll`. It discards stale rendered revisions. Document changes stop and invalidate an earlier snapshot. No PCM is sent through JSON. Rendered previews are deleted after the native adapter copies their samples; explicit exports remain at the chosen destination.

`waveform` returns `waveform:{revision,clipID,sampleRate,sourceStartFrame,sourceFrames,mediaSHA256,peaks}` without changing the document or selection. The shared reducer reads at most 16 million source frames in bounded chunks and returns at most 1,600 finite nonnegative peaks across all channels. Source offset and duration truncate at the source sample rate; the interval ends at source EOF. Position, gain, pan and project rate do not alter the envelope. The digest identifies the actual WAV byte snapshot. The host rejects stale/deleted-clip replies; opening or saving under a new root clears its display cache, while trim/split require new source ranges. These peaks are display data, not evidence of device playback.

`inspectSourceEvent` returns `sourceInspection:{revision,eventID,sourceSHA256,
availabilityScope:"preparation-only",maximumFrames:32000000,modes:[...]}`. There
are exactly eight mode entries, in the order below. Each has `mode`, `available`,
and an optional refusal `reason`. Successful preparation additionally supplies
`sampleRate`, `frames`, `sourceSampleRate`, `mediaSHA256`, optional
`timelineRange` and `savedProjectAudioSetup`, `contributorCount`, and
`fragmentCount`. The complete inspection is bounded to 128 KiB; it is never
truncated. Inspection prepares each mode without draining converter output or
writing files. Availability is provisional until a fresh render succeeds; it
does not establish device playback. Missing media or an unsupported mode-specific
source shape is an explicit unavailable entry. Invalid preserved source/report
provenance fails the inspection itself.

| Mode | Clock and interpretation |
| --- | --- |
| `sourceRate` | Complete zero-origin stereo source at its saved rate, with event gain. |
| `nativeTimelineSourceRate` | Retained placement/trim/offset, source clock, no resampling. |
| `nativeTimelineProjectClock` | Retained placement using the current project clock, raw frames without resampling. |
| `nativeTimelineSavedProjectClock` | Retained placement using the explicit preserved saved setup, raw frames without resampling. |
| `nativeTrackSavedProjectClock` | Complete original source track, saved clock, normalized priority fragments with every original contributor verified. |
| `nativeMode0ProjectRate` | Existing mode-0 converter into current project rate; equal rates remain unsupported. |
| `nativeMode1ProjectRate` | Existing mode-1 converter into current project rate. |
| `nativeMode2ProjectRate` | Public SoXR 0.1.3 mode-2 path into current project rate. This does not establish reference-library equality. |

Unknown mode strings fail with `sourceMode`; an omitted mode preserves the
original `sourceRate` WAV contract. These operations use the same prepared
sources, timeline/conversion cursors and output stages as macOS. They preserve
the existing stereo, gain, fade, warp, saved-setup, contributor-membership and
priority restrictions. No event is promoted to an editable clip. Project mixer,
effects, routing and ordinary automation are outside these explicit audition
paths.

`renderSourceEvent` always replays the source/report relationship and validates
all relevant media. `startSeconds` must be finite and nonnegative. The shared
macOS scheduling function applies native event selection where applicable,
clamps to the freshly prepared duration, and rounds output frames to nearest,
ties away from zero. `rewindAtEnd:true` restarts only if that result equals the
total frame count. Each request creates a fresh cursor at the resulting frame;
the host must not substitute a slice of a previously rendered full snapshot.

The render reply adds `kind:"sourceEvent"`, `eventID`, `sourceSHA256`,
`mediaSHA256`, `mode`, `startFrame`, `totalFrames`, `manifestPath`,
`manifestSHA256`, and `manifestBytes`. `frames` is the remaining output count,
so `startFrame + frames == totalFrames`. Exact EOF still revalidates all source
bytes and returns a valid 58-byte zero-frame Float32 stereo WAV and complete
provenance; the host marks playback finished without passing zero frames to the
native audio adapter. Source audition never reuses external-byte validation on
the strength of a revision alone. Resume and seek require fresh rendering.

Every source WAV has a companion `requested.wav.source-audition.json`. The
sidecar is compact UTF-8 JSON, encoded with sorted keys and unescaped slashes,
bounded to 8 MiB. The returned digest identifies its exact bytes; hosts verify
the digest, byte count, schema, source identities and complete contributor proof
before installing audio. `rebase.source-audition-manifest.v1` contains:

- `revision`, `eventID`, `name`, `mode`, `sourceKind` (`event` or `track`), and
  `clockRole` (`source-rate`, `source-clock-unconverted`,
  `current-project-clock-unconverted`, `saved-project-clock-unconverted`, or
  `current-project-rate-converted`).
- `projectSampleRate`, optional `currentNativeClock` and
  `preservedNativeClock` in their full existing Codable forms,
  `projectManifestSHA256` for saved bytes, `currentProjectSHA256` for the current
  encoded model, `importReportSHA256`, `sourceSHA256`, and anchor `mediaSHA256`.
- `sampleRate`, `sourceSampleRate`, `frames`, `startFrame`, `totalFrames`,
  `channels:2`, `maximumFrames:32000000`, optional `timelineRange` and
  `savedProjectAudioSetup`, and optional `sourceTrack`.
- `wavFileName`, `wavBytes`, and `wavSHA256`, binding the manifest to the output.

Ranges contain `contract`, `position`, `duration`, and `offset`. Saved audio
setup retains its existing contract, raw base-rate/factor bits, object identities
and offsets. `sourceTrack` contains `contract`, `freshRootMode`, `trackIdentity`,
`events`, `fragments`, and `snappedEmptyFragmentCount`. Every event contains
`eventID`, `eventIdentity`, `sourceOrdinal`, signed `priority`,
`sourceSampleRate`, `mediaSHA256`, `canonicalStart`, `canonicalEnd`, and optional
original `range`. Every fragment contains `eventID`, `eventIdentity`,
`sourceOrdinal`, and its projected `range`. Fully covered contributors remain in
`events` and their attached bytes are checked; the anchor digest alone is never
complete-track proof. Large proof arrays are not truncated.

All modes currently use a bounded Windows snapshot: total output above
32 million stereo frames is refused with `sourceFrameLimit` before WAV
allocation or publication, including a long silent timeline. Full admitted
macOS timeline duration requires a later streaming transport. Both outputs must
be new regular files outside the project. They are staged and checked, followed
by a fresh manifest/source/report/all-contributor-media check. The sidecar is
published first and the WAV last, with exclusive file publication. If WAV
publication fails, rollback removes the sidecar only when its identity proves
ownership. `sourcePublicationIncomplete` means an output may remain: inspect
the destination, do not silently retry or overwrite it. The two files are not
one atomic filesystem transaction.

Inspection and source rendering leave revision, dirty state, project,
selection, undo/redo and imported package bytes unchanged. Transport receives
stereo Float32 only. The explicit source-mode rate and downstream device-rate
adaptation are separate: the native adapter uses its pinned public SoXR path
when the endpoint rate differs, and does not ask Windows for hidden conversion.
Neither source conversion controls nor an unavailable CI endpoint establish
audible output or reference-runtime fidelity.

A waveform reply adds `waveform:{revision,clipID,sampleRate,sourceStartFrame,sourceFrames,mediaSHA256,peaks}`. Peaks are finite, nonnegative, source-domain maxima across channels, with at most 1,600 bins. Source start truncates `sourceOffset*sourceRate`; count truncates the bounded source duration. The frontend validates receipt identity/interval and finite limits, draws those peaks, and never synthesizes an envelope. It sends at most one background envelope request at a time, yields between requests, and never applies a background reply's document state. Open/Save As clear cached envelopes; trim, split, and deletion invalidate changed source intervals. Move/mixer/zoom changes can reuse unchanged source ranges.
