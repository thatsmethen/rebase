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
| `attachSourceMedia` | Preserved event `clipID` and explicitly selected PCM file `path`; validates and copies matching media, records undo, and selects the event. |
| `renderSourceEvent` | Preserved event `clipID` and a new WAV `path` outside the source package. |
| `waveform` | Ordinary `clipID`; a read-only source-envelope request. |

Quarter/eighth/sixteenth snapping is 1, 0.5, and 0.25 quarter notes. Bar snapping uses the shared signature map. The helper derives trim limits from checked media and generates split identifiers. The frontend sends proposed seconds from pointer geometry, leaving all snapping and edit rules to Swift.

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
