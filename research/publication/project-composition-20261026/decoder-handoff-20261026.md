# Saved native project bindings: reviewed implementation boundary

The new shared decoder is ready for source-inspection integration. It preserves the counted hierarchy, typed audio resources and verified common device-resource slots, then reports saved route/Volume/bus candidates with immutable source spans. It does not resolve a runtime channel receiver, effective route or neutral processing, and it cannot authorize project mixing.

Production files are `Application/Sources/RebaseCore/CPRNativeProjectBindings.swift` and the portable source-list entry in `Application/Package.swift`. Authored controls are `Application/Tests/SharedCPRAudioTests/CPRNativeProjectBindingsTests.swift`. No existing importer, playback implementation or frozen report schema was edited.

## Observed domain

- `PArrangement v4` / `MRoot v6`, with observed root ancestry `MGroupEvent v0`, `MPartEvent v1`, `MEvent v1`; counted `MTrackList` and `MListNode v0`. Complete preorder includes null, repeated and unknown identities. List compatibility words and timing objects remain explicit saved data.
- Supported track envelopes require the observed `MEvent v1` and `MTrackEvent v2` declarations. The common `MDeviceTrackEvent v0` resource slot is decoded only through its bounded numeric attributes and object envelope; the remaining subclass tail stays opaque. These earlier slots make the actual saved `MTrack v2` declarations available without scanning opaque bytes.
- Typed `MAudioTrack v0` resources admit the verified `MTrack v0/v1/v2` prefix, association tags and exact state variants. Inline attribute parsing is bounded and must reach the trailing flags exactly before publishing parsed scalar candidates.
- Binary64 Volume bits remain raw saved representation. The observed native scalar-to-runtime conversion does not make those bits application gainDB, a unity condition or proof of an unprocessed signal path.
- Child Bus accepts the verified subtype5 FSubList of anonymous attribute dictionaries. Subtype201 FObjectList is distinct, even when its typed members happen to be FAttributes. Auxiliary numeric/string arrays and byte streams are consumed structurally but never interpreted as plugins, routing or scalar candidates.
- Conditional bus matching retains the native lookup's parent/direct-child domain. A matching saved UID is still only a saved candidate. Missing, zero, ambiguous, out-of-range and nonfinite values remain distinct.

## Declaration chronology correction

Independent source review found that decoding all audio resources after the complete root traversal could let an earlier resource borrow a later sibling's MTrack declaration. Reading tail objects before selecting the version also exposed the same hazard within one track. The decoder now parses each resource at its serialized position and snapshots its observed version context immediately after that envelope. Later conflicts invalidate the complete report. Completed bindings are ordered by their counted-entry ordinal so byte-order decoding does not change report preorder. Focused controls cover earlier/later device declarations, tail-only declarations, late conflicts and nested-track ordering.

## Evidence and limits

`decoder-tests-09` passed 20 authored shared tests. The final `decoder-full-tests-05` passed 167 reported cases: 164 executed, three explicitly disabled fixture generators, zero failures/errors. These are the portable Swift target running locally on macOS, not native Windows execution or reference application equivalence. Package.resolved was restored exactly.

`private-fixture-probe-06` applied the compiled decoder to ten unchanged retained template sources: 145 counted entries, of which 59 are root entries; 17 common resource associations; five typed audio resources. All five inline states reached their exact flags/end and yielded raw route, Volume and bus candidates. `private-applicability-verified-03.json` independently rehashed 1,140 source spans, object payloads and archive ranges, checked source identity against the earlier preserved input baseline, and checked counted order and resource extent closure. The reports still explicitly leave runtime receivers, effective routing and processing unresolved. No proprietary executable was run.

`verification-binary-state-01.json` covers 100 original function derivations, 100 REA analyses/readbacks and 21 equal traversal slots, bound to the pinned target hash. Existing raw bytes, logs and source templates remain private. `bus-identity-addendum.md`, `common-resource-addendum.md`, `child-bus-receiver-correction.md` and `auxiliary-state-boundary.md` explain the observation chains and admitted-domain changes. The Child Bus correction supersedes the earlier mistaken FObjectList interpretation; the auxiliary-state note and final probe supersede earlier subtype4/5/7 stopping boundaries. Earlier notes, rejected source observations, compile failures and successful narrower tests remain unchanged.

## Concrete app integration

Expose this as a fresh saved-binding inspection beside the frozen import report. `inspect(from:)` uses the existing bounded source intake. `inspectPreserved(in:)` first replays and verifies the complete original compatibility report, rereads the source, and binds its hash/count/sections again; it never rewrites either artifact. The protocol caller must also retain its expected revision and current application manifest/selection checks before and after the read. Inspection must preserve dirty state, revision, history, source report and original bytes.

The full report can exceed one protocol page. Publish a complete canonical bounded sidecar or page the complete report with a revision-bound token and source/report digest; do not truncate unknown identities or imply complete coverage from a short summary. The UI should distinguish saved bytes/conditional receiver evidence from effective behavior, show opaque tails and unresolved statuses, and leave project-mix controls unavailable until actual receiver/routing/processing admission is proved.

The strongest next static boundary is the MTrack tag1 provider/interface/index lookup (`101742f20`, interface identity at `10500dbd0`) through its concrete channel receiver. That must be connected to the channel restore path (`101d3b918`, `101d75844`, `101d75bcc`) and bus-registry application (`101d766c8`), preserving restoration options and missing registrations. Neutral processor state, clock compatibility and cross-track accumulation order remain separate obligations. Counted root order by itself is not mix accumulation order, and raw Volume or route IDs cannot substitute for those proofs.
