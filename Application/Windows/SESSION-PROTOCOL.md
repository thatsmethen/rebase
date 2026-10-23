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

Quarter/eighth/sixteenth snapping is 1, 0.5, and 0.25 quarter notes. Bar snapping uses the shared signature map. The helper derives trim limits from checked media and generates split identifiers. The frontend sends proposed seconds from pointer geometry, leaving all snapping and edit rules to Swift.

Every reply includes the full state, including failures:

```json
{"protocol":1,"id":1,"ok":true,"state":{"revision":1,"dirty":false,"needsSaveAs":false,"path":"C:\\Projects\\Song.rebaseproj","project":{},"selection":{},"canUndo":false,"canRedo":false}}
```

Here `project` is the ordinary serialized shared `Project` model (the empty object above abbreviates it). Before opening a project, it is absent or null. Selection has optional `trackID` and `clipID`. Failure replies set `ok:false` and add `error:{"code":"...","message":"..."}`; the current state remains authoritative. A malformed request can have no reply identifier and is treated as a failed protocol exchange by the host.

Opening, edits, undo, redo, and Save As advance the document revision when they change state. Selection and Save do not advance it. The included example is cloned into helper-owned scratch storage and reports `path:null` and `needsSaveAs:true`; its original bundled files are never the editing destination. Save verifies the previously opened manifest has not changed outside the session. Save As copies the ordinary project into a new destination, retaining checked sidecars. CPR playback remains unavailable in this Windows session.

A successful render adds:

```json
{"render":{"path":"C:\\Output\\snapshot.wav","revision":4,"sampleRate":48000,"frames":960000,"channels":2,"wavBytes":7680058,"sha256":"hex-digest-of-complete-wav"}}
```

The frontend verifies the returned path, revision, byte count, SHA-256, exact Float32 stereo WAV format, frame count, and finite samples before handing a copied snapshot to `RebaseWindowsAudio.dll`. It discards stale rendered revisions. Document changes stop and invalidate an earlier snapshot. No PCM is sent through JSON. Rendered previews are deleted after the native adapter copies their samples; explicit exports remain at the chosen destination.

The current adapter requires the default Windows endpoint to mix Float32 stereo at the project's exact sample rate. A mismatch is an explicit playback error. There is no hidden Windows resampling, alternate editing implementation, or claim of full macOS/native CPR parity in this first host.
