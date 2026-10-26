# Provider receiver and saved output-channel registry

This is an additive static continuation. Earlier records, including failed probes and the overly broad OutputBusValue precheck wording in `bus-identity-addendum.md`, remain unchanged. No proprietary program was executed and no effective project mix has been admitted.

Target SHA256: dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb (85,691,328 bytes). Exact original instructions, derived slices, REA results, complete byte readbacks and losses are retained in passes30–43. `verification-output-registry-01.json` verifies135 derived intervals,131 unique function/hash analyses and readbacks, and21 shared counted-iterator slots. Repeated intervals are not extra independent functions.

## Conditional provider receiver is now concrete

All five retained audio associations are tag1, named provider `VST Multitrack`, saved index1. Constructor101d99034 passes that literal1038a19cf to its base and installs table1047b70b0. Query101d9e88c compares the same IID storage10500dbd0 used by MTrack binder10174354c, returning provider+2f8. This interface table1047b7a78 has+18=101d9bff0, which adjusts by-2f8 then branches101d9bef0.

The saved index is a factory-kind selector, not an existing-channel ordinal. 101d9bef0 admits indices1,4,5,7,8,9,10,11 and maps them to kinds1,2,6,3,4,19,20,21. Index1 calls101dcf544 with kind1. Its explicit table branch allocates0x1aa8 and calls101d3c1fc→101d3b918. This constructor installs known audio-channel table1047ac688 and base channel kind+58c=1. The factory adds the object to owner+a00. The audio receiver's+b0 is101d75844 and+530 is101d41dcc, reaching101d75bcc.

Provider initializer101d983c0 does register the newly constructed provider through the same manager access path used by the MTrack binder, but only after two host-availability checks and through an unresolved manager virtual+120. Name lookup uniqueness, successful installation and actual project load context are still conditions; static factory closure is not evidence that the reference application ran or selected this provider. The IID storage is in zero-fill `__common`; the retained unmapped observation is not replaced with invented IID bytes.

## Correction to ordinary route restoration

The earlier statement that OutputBusValue restore always requires a successful nonzero Value precheck is wrong. Ordinary channel+b0 zero-initializes its options object, so mode0 reaches101d758b4. This yields option+17=true and+19=false. At101d76550 the latter branches directly101d766f8, which calls generic nested restore1031a07d8 at101d76708. The nonzero/compatibility precheck101d766c8–766f4 belongs to a different option branch (mode4), not this ordinary path. The independent peer reviewed this exact correction in `peer-provider-options-review-01.json`.

Generic nested restoration still distinguishes absent field, wrong receiver/type, nested Value absent, explicit zero and nonzero saved selector. VSTBusValue restoration clears its selector before reading; nonzero saved values register remapping. This correction does not turn raw candidates into effective routes. Channel kind1 also does not enter the OutputBus object branch controlled by mask0x19780; OwnInputBus is a different role.

## Saved registry and native receiver

A new bounded structural walk of the Devices root section found CmObject0/FAttributes0 envelopes in all ten unchanged private fixtures. Each VST Mixer dictionary contains Output Channels as subtype5/FSubList. There is one ordered output-channel row per fixture. The inventory records8734 field spans, types and hashes; string values are hashed rather than copied. `private-devices-readback-01.json` independently rechecks33752 original-byte assertions, ten source hashes and five cross-section joins.

Owner constructor101dc760c uses literal VST Mixer1038b157d and table1047bca48. Table+a8=101dd8f04 writes this saved scope; table+b0=101dd94a4 reads it. The reader counts Output Channels using1031a0e1c. When owner+d35 is false, it loops the list, allocates0x1640, calls101dedb78→101ded558 with kind8 and flag7=0, adds the channel to owner+ac8, and consumes the next saved FSubList row through1031a0c94. That helper checks the FSubList member via1031a0ce8, then invokes the created receiver+b0. This is typed contextual restoration, not a label-based guess.

The output constructor installs1047be9e0, whose+b0 is the same101d75844 and+530 is101dedb7c→101d75bcc. Saved Type8 matches all ten observed rows, but the creation call itself supplies kind8; a conflicting saved Type must not silently select another constructor in a decoder.

Output channel+608=101dee438 creates a bus through101f019e8→101f017e0 with parameters9 and18. The resulting own-input bus is stored at channel+1538. With the explicitly passed flag7=0,101ded8c4–8dc inserts that bus into global owner105010970+950 through101d4d84c→101d4d878. This is the same registry captured by VSTBusValue and searched by101d4d748. Ordinary common restore reads OwnInputBus through its native bus adapter; its Bus UID reader101f30b34 contributes saved→new runtime-ID mappings through100dbf31c.

The conditional collection path is therefore closed through concrete constructor, pointer field, collection insertion, attribute reader, remap producer and selector consumer. It still requires actual restore mode, enabled remap context, successful field restore and compatible bus topology.

## Five exact saved identity joins

The earlier track-only report had no saved destination matches because it only contained each track's own input bus. All five track output selectors uniquely equal the OwnInputBus/Bus UID of their fixture's Output Channels/0 row: fixture ordinals1,2,6,7,7 with values17,50,17,329,329. These identities are source-bound in `private-output-channel-id-joins-01.json`; this is saved integer equality, not a runtime-ID claim. An output channel's OwnInputBus can receive a track output; its separate OutputBus and RecorderBus cannot be substituted by role/name.

The reader also loads Default Output into a signed index, checks bounds against owner+ac8, validates the selected VSTOutputChannel receiver and gets virtual+568 before101dc9c20. Missing Default Output leaves its initialized local0, which is an observed native restore behavior; it is not permission for the research decoder to invent a saved default, a master bus or unity processing.

## Remaining effective-route conditions

- owner+d35 skips output-channel recreation. The fresh owner's constructor clears the byte within its explicit zero store at101dc7a6c–70; that alone does not establish its value at every later load. Restore-context mutation and alternative import/preserve flows remain untraced.
- The Bus UID remapper requires nonnull global10501cac0 with virtual+d8 returning false, plus its own active+68. New table10458c9f8 slots0/8 select100dd07a4/100dd0940. Slot0 clears maps and sets active; slot8 finishes/clears and deactivates. Caller scoping around an actual whole-project load remains unresolved. The selected-reference scans' missing direct calls are not proof of absent callers.
- Speaker arrangements and Child Bus compatibility can alter children after saved restoration. The primitive registry search is parent then direct children then next parent; do not flatten arbitrary descendants or use names to repair missing/duplicate IDs.
- Selector delivery is not yet proof of final audio-edge activation, cycle rules, engine accumulation order or automatic routing on zero/absent selectors. Keep raw, typed contextual and effective applicability separate.

## Processing is expressly not neutral by omission

Audio and output constructors call101d67ef0 with either a supplied setup object or configuration populated from host preferences. Its original instructions construct folders/stages named Inserts, Modulators, Strips, Sends, Outputs, Foldbacks and DirectRouting according to setup counts/flags. It also constructs a panner-like stage via virtual+618 and selects engine graph constructors101f37910 or101f3f970 under configuration flags. The REA decompiler's unresolved jump table at101d6832c is retained; no exhaustive processing interpretation is claimed.

Common saved restoration separately consumes Volume, InputFilter/InputGain/InputPhase, panner, mute/solo/monitor, insert/strip/EQ/send state and options. Absent saved attributes do not prove absent constructor-created processors. A full mix admission rule must establish constructor state plus explicit saved overrides, active/bypass states, parameter meaning, channel layout, automation and graph order. No current fixture is certified as a neutral whole-project mix.

## Next executable boundary

Extend the source-bound saved-binding report with a separate typed Devices/VST Mixer output-channel registry decoder: ordered rows, source spans/hashes, raw Type/RuntimeID/Default Output, role-separated bus trees, complete processing-field coverage/opaque hashes, and cross-section saved-ID matches. Preserve duplicates, missing IDs, malformed/wrong compound types, unknown state and restore-context conditions. This can turn the current missing-destination entries into explicit saved registry matches without changing historical import reports or enabling unproved audio.

The strongest next static processing target is101f37910 (graph constructor fed the exact folders) followed by its selected stage/accumulation dispatch, while independently closing the whole-project remap begin/end scope. Future authored tests should distinguish saved match versus effective eligibility, preserve root/output order and duplicates, cover zero/absent selector and Default Output separately, reject incompatible child layouts, and ensure every unexplained processing stage blocks whole-project playback rather than being replaced with unity.
