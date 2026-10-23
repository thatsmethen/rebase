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
| `setTempo` | Finite `value` in BPM. |
| `undo`, `redo`, `save` | None. |
| `saveAs` | `path`: a new, nonexistent `.rebaseproj` directory with an existing parent. |
| `render` | `path`: a new WAV outside the source package. |
| `attachSourceMedia` | `clipID`: retained event; `path`: explicitly selected matching PCM24 WAV. Shared history records the association and selects the event. |
| `renderSourceEvent` | `clipID`: retained event; `path`: a new source-event WAV outside the package. |
| `waveform` | `clipID`: ordinary clip. Read-only source envelope, no revision change. |
| `ruler` | Required finite `value`: pixels per second in 4…420. Optional finite `duration`: extent in seconds in 0…86,400. Read-only musical ticks, no revision change. |

Quarter/eighth/sixteenth snapping is 1, 0.5, and 0.25 quarter notes. Bar snapping uses the shared signature map. The helper derives trim limits from checked media and generates split identifiers. The frontend sends proposed seconds from pointer geometry, leaving all snapping and edit rules to Swift.

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

`renderSourceEvent` uses the shared source-event renderer for an already-imported project. Its initial domain is a complete, zero-origin stereo PCM24 event at its saved source rate with the existing gain/fade/warp restrictions. It re-verifies preserved CPR bytes, the retained report/event relationship, and the attached media on each request. It never turns the event into an editable clip. The reply has `kind:"sourceEvent"`, `eventID`, `sourceSHA256`, and `mediaSHA256` in addition to the render fields above. The host checks those identities against the selected event and its attachment. Source audition has its own clock at the returned sample rate and must request a fresh render on resume and seek; a document revision alone does not establish unchanged external bytes. This command does not recover project mixing, effects, automation, or general native timeline playback.

The current adapter requires the default Windows endpoint to mix Float32 stereo at the rendered snapshot's exact sample rate. A mismatch is an explicit playback error. There is no hidden Windows resampling, alternate editing implementation, or claim of full macOS/native CPR parity in this host.


A source-event render uses `kind:"sourceEvent"` and includes `eventID`, `sourceSHA256`, and `mediaSHA256` in the render object. The frontend requires all three to match the selected retained event and its single user-selected media association. It uses the snapshot rate and event-local time, not the project rate. Source audition never reuses a snapshot on the strength of a document revision alone. Resume and seek render afresh. Source seek follows the existing Mac host frame policy (nearest frame, ties away from zero); seek-to-end stays at the end, while Play/resume may restart. Revision-changing edits exit audition. Native transport receives stereo Float32 only; mono expansion is not performed by the host.

A waveform reply adds `waveform:{revision,clipID,sampleRate,sourceStartFrame,sourceFrames,mediaSHA256,peaks}`. Peaks are finite, nonnegative, source-domain maxima across channels, with at most 1,600 bins. Source start truncates `sourceOffset*sourceRate`; count truncates the bounded source duration. The frontend validates receipt identity/interval and finite limits, draws those peaks, and never synthesizes an envelope. It sends at most one background envelope request at a time, yields between requests, and never applies a background reply's document state. Open/Save As clear cached envelopes; trim, split, and deletion invalidate changed source intervals. Move/mixer/zoom changes can reuse unchanged source ranges.
