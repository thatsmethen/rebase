# Native project composition: root order, channel ownership and route identity

Status: bounded static semantics recovered. No reference program was executed. These findings can drive a shared structural/ownership decoder and native bus-ID resolver; they do not yet admit a faithful full-project audio mix.

The pinned arm64 image is SHA256 `dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb` (85,691,328 bytes). REA 6.7.0 with Ghidra 12.1.4 inspected 58 original-address instruction derivatives (24,024 bytes), in 14 closed sessions. All 58 readbacks match original bytes. The independent check also binds 21 shared iterator slots and 572 reused original instruction words. See `verification-final.json`, `custody-final.json` and `intake.json`. Source hashes, exact requests/responses, decompiler warnings and two instrument failures are retained. Raw-slice analysis omits globals/RTTI/imports/unwind; exact original bytes and explicit original-image pointer/string cells resolve the relationships used below. Nothing here constitutes observed playback or a cross-platform reference comparison.

## 1. Fresh root iteration now has a concrete order

`MTrackList` primary vtable `0x104678ea8` selects reader `0x101759190`, writer `0x1017591f4`, and iterator factory `0x101758eec`. The reader calls the existing counted-object reader `0x101716008`; it consumes but does not locally branch on its compatibility word. The shared app can retain its stricter zero-word policy without pretending this is a universal native restriction.

The factory allocates 56 bytes, invokes base constructor `0x101716448`, then installs primary `0x104679050` and secondary `0x1046791f8`. Base initialization starts at the list head `list+0xb0`. Twenty-one traversal/control slots equal the corresponding `MListNode` accessor slots byte for byte. Specifically, +0xd0 selects done `0x101715bac`, +0xd8 selects forward next `0x101715bbc`, and +0xf8 selects reset `0x101715c20`. Forward next returns current and advances via node+0x10, skipping subsequent filter failures when a filter exists. Secondary forward reset also starts at +0xb0; reverse reset starts at +0xb8 and follows +0x18.

Admissible result: for a fresh ordinary forward accessor over the restored, unmutated list under the same filter context, counted child order is preserved. The distinct root accessor factory is no longer sufficient reason to exclude that structural order. Retain every child identity and ordinal, including non-audio/unknown objects. This does not establish engine collection order, which subset it selects, or floating-point bus summation order. The root accessor has extra mutation methods; +0x188/+0x190 must not be compared to metadata after the base table ends at +0x180.

## 2. Saved track association has explicit tags and restoration variants

`MAudioTrack` returns its association descriptor at owner+0x90 (`0x1001fd4d4`). The MTrack reader `0x101744d58` reads u16 tag, native string into owner+0x98, then a signed index into +0xc8 (32-bit for MTrack version >=1, sign-extended 16-bit for older versions). Original jump-table bytes at `0x103a85581` prove these continuation classes:

| Tags | Read continuation |
|---|---|
| 1, 8 | version 1 uses `0x101744f7c`; other versions use `0x10174503c` |
| 3 | reads a second string at owner+0xb0 |
| 5, 6 | reads an auxiliary representation, converts the name; tag5 becomes0 and tag6 becomes7 |
| 2, 4, 7, other | no additional branch in this function before status/remap registration |

This is not permission to accept every tag: the runtime binding paths differ. `0x101742f20`, called before audio-provider registration, dispatches tag0 through a named provider lookup (+0x160 then fallback +0x168), tag1 to `0x10174354c`, and tag8 to `0x101743998`. The other/general path can report success without establishing a channel; tags4/5 have an explicit failure branch. On the captured MAudioTrack class, the tag3 callback +0x108 returns null. Track-registration success therefore cannot be used as a channel-proof flag.

Tag1 looks up the provider by saved name, queries IID `0x10500dbd0`, obtains a channel through interface+0x18 with the saved index, and restores retained state or retained serialized data before assigning owner+0xd8. Tag8 resolves a parsed name through the registry at `0x10501a6a0`, checks `PDeviceNode`, assigns +0xd8, and restores retained +0xe0 state through +0xb0. These are conditional concrete paths, not guarantees that an arbitrary source association becomes VSTAudioChannel.

For the modern retained-state continuation `0x10174503c`: signed marker -88888 creates and reads FAttributes; marker -77777 reads an object plus u16, retaining that object at descriptor+0x40 (owner+0xd0); positive size reads a bounded opaque stream and extracts FAttributes through the existing archive mechanism. Nonpositive unrecognized markers do not establish a state object. Exact object/frame boundary and failure status must be preserved by a new decoder.

Correction to an initial hypothesis: `0x101a0a000` only swaps/refcounts descriptor+0x40. It does not clear the tag or name. The later MAudioTrack reader’s ASpeakerArrangement object supplements this descriptor; it does not overwrite the saved association kind. `0x101744218` stores the receiver at owner+0xd8; its PMixerChannel test controls conditional registration callbacks, not universal type rejection.

## 3. Concrete VSTAudioChannel state connects to saved output bus identifiers

The previously sealed successful audio-provider binding remains conditional on the VSTAudioChannel receiver. Reused constructor `0x101d3b918` installs primary `0x1047ac688`; this tranche verifies its base-constructor call to `0x101d65f68`. The base constructor establishes:

| Channel offset | Concrete initialization | Saved-state key/restore target |
|---|---|---|
| +0x940 | `0x101d067b4`, VSTVolumeValue | `Volume` |
| +0x9c0 | `0x101d5e61c` → `0x101d5e528`, VSTBusValue | `OutputBusValue` |
| +0xa68 | same VSTBusValue constructor | `InputBusValue` |

VSTAudioChannel +0xb0 points to `0x101d75844`: constructs restoration options through `0x101d758b4`, then calls virtual+0x530. The concrete +0x530 is `0x101d41dcc`, which invokes `0x101d75bcc` before audio-specific RecordDir/InputBusArrangementType handling. The base restore independently consumes `Volume`, `Panner`, `InputFilter`/legacy `InputGain` and `InputPhase`, `Solo`, `SoloFlag`, `Monitor`, `InsertFolder`, `ModulatorsFolder`, `StripFolder`/legacy `EQ`, `SendFolder`, `foldbackSendFolder`, `directRoutingFolder`, `outputBusEnable`, `OutputBusValue`, `OutputBus`, `RecorderBus`, and other controls. Exact string addresses and hashes are in `channel-state-property-anchors.json`.

The generic nested-object restore `0x1031a07d8` verifies the attribute object is FAttributes, then invokes the destination’s +0xb0. This closes the receiver link from OutputBusValue at channel+0x9c0 to VSTBusValue attribute reader `0x101d5f974`, rather than relying on the key’s name alone.

VSTBusValue vtable `0x1047af310`:

- Attribute reader `0x101d5f974` first clears current integer at +0x3c, reads integer key `Value`, and returns the read result. Missing and explicit zero both leave local storage zero, but differ in success status. They must remain distinguishable in admission.
- A successful nonzero value is stored and passed to restoration map `0x104f9bef0` through `0x101d5fb24`. That registry can immediately invoke or retain an update callback; callback `0x101d62c14` writes the mapped integer to the same +0x3c.
- Serialized reader `0x101d5f368` directly reads one 32-bit value to +0x3c. It does not locally execute the attribute-reader’s remap registration. Preserve which representation supplied the route.
- Registry lookup `0x101d4d748` scans each registry top-level object: compare its virtual+0x1b8 ID, then each direct child (+0x180 count, +0x188 access) ID, then advance to the next top-level object. It returns first match or null. This is a one-level child search, not recursive arbitrary nesting or a root-track ordinal lookup.
- Setter `0x101d5eeb8` has channel-type and compatibility restrictions and can refuse/alter an assignment. Import restoration and interactive routing changes are not interchangeable.

Admissible result: retain raw saved bus IDs plus their representation and unresolved/remapped status. A resolver can implement the proven ordered top-level/direct-child ID search when the actual bus registry is recovered. Do not substitute the root track order, the selected anchor, the first bus, the app’s main output, or the text "Stereo Out". Duplicate-ID admission should remain unsupported until identity-uniqueness rules are established; native first-match behavior alone is not evidence that duplicates are valid input.

## 4. Volume is not the app’s gainDB field

`VSTVolumeValue` is identified by its original class string at `0x103899f19` and primary table `0x1047a4d38`. Constructor `0x101d067b4` supplies Float32 values 0,32767,1 to its base constructor. Attribute restore `0x101d077d0` reads Float32 key `Value`, invokes +0x358 (`0x10315cc4c`), and that function normalizes through +0x370 (`0x10315ca9c`) before storing at +0x50. Serialized restore `0x101d07568` reads a Float32 and two further numeric fields, then uses the same setter. The normalizer has both cyclic and clamp branches based on receiver state.

This establishes a separate raw native control representation. It does not establish a dB conversion, channel DSP multiplication, unity of the whole processing chain, panning law, automation interpolation, or the meaning of absent nested controls. In particular, 0 app dB cannot be inserted as a missing native Value, nor can a constructor default prove that a restored channel has no additional processing.

## Executable next milestone

Implement `CPRNativeProjectBindings.read(container:)` as a shared, read-only, source-bound decoder, followed by a separate admission assessment:

1. Enumerate every counted root child in the now-proven structural order; bind identity/object offset, root ordinal, native class/version and supported/unsupported role. Keep unknowns, references, nesting and non-audio tracks visible. Do not flatten track event priority across tracks.
2. Decode MTrack association tag/name/index and exact continuation representation for explicitly tested class versions. Preserve the full opaque state span/hash and state-object identity. Tags/versions and malformed or ambiguous states outside this recovered domain remain explicit unresolved entries.
3. Decode nested FAttributes OutputBusValue/Value and Volume/Value without rewriting the original. Preserve field presence, numeric bits, raw ID, retained source span and representation. Keep channel-local selectors separate from physical output setup and bus definitions.
4. After the actual project bus registry decoder exists, resolve bus IDs with the captured parent-then-direct-child search, recording every candidate identity and the chosen match/remap evidence. Unknown/duplicate/unresolved identities block full project audio, not structural inspection.
5. Attach original source/report/current-project/clock/media hashes and all root contributors; editing app mixer values must not silently become native controls. Use explicit `structureRecovered`, `channelAssociationRecovered`, `routeResolved`, `processingVerified` statuses. Only complete proof can enable native project playback.

Author controls should cover empty/multiple/interleaved root children, direct versus reference identity, unsupported/duplicate/cyclic roots, both MTrack index widths, all tag branches, markers -88888/-77777/positive/invalid, missing versus zero route Value, remapped IDs, child-before-next-parent resolution, missing/duplicate destinations, exact Float32 Volume bits and nonfinite controls, stale source/report/media, and preservation through save/reopen. These controls validate our implementation/instrument; they do not measure reference runtime.

## Proof still required before a full native project mix

The final audio path cannot yet be admitted, including apparently neutral stereo projects. Remaining concrete proof domains are: locating/restoring the project’s actual bus registry and remap producer; proving each saved track association’s concrete channel receiver (rather than the conditional path alone); channel mute/solo/monitor and automation state; panner representation and law; empty/bypassed inserts/strip/sends/direct routing; gain unit and arithmetic; destination output enable, layout and speaker map; group/bus cycle handling; and engine traversal/mix accumulation order. Unknown root objects cannot be treated as inaudible.

The strongest immediate static continuation is the route setup path after `0x101d75bcc`: `0x101d694a8` and the bus registry population/remap producers feeding `0x101d4d748`, followed by concrete channel processing construction. This is preferable to implementing a sum of the eight pre-mixer source audition modes and calling that the source project mix. The existing eight modes remain unchanged and useful as independently verified source contributors.

All original sealed records remain untouched. This note supersedes only the earlier assumption that MTrackList’s different iterator factory, by itself, prevents structural root-order recovery. It does not rewrite the prior exclusion or extend its old evidence claim retroactively.
