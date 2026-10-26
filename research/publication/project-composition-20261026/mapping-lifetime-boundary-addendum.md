# Saved bus-ID mapping lifetime — additive static continuation

This extends the frozen receiver/output-registry and processing-state notes. It does not change their original records. The reference-image pin remains `dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb`; no reference program or proprietary plugin was executed. REA/Ghidra analysis and complete byte readback for passes53–61 are retained. The cumulative verifier passes190 derivative intervals,185 unique analysis/readback pairs and the original21 iterator slots. A separate verifier rereads106 selected anchors,1570 bytes, directly from the original Mach-O.

## What was closed

The bus-ID map is an explicitly registered lifetime listener, rather than a permanently active lookup inferred from its singleton allocation. The named mapping scope nests across channel restores. An MRoot activation method creates an outer scope before its retained-state restoration calls and root traversal. This supplies concrete static conditions for considering saved selector-to-bus matches as candidates for a common restoration transaction. It does not establish that the required runtime host/provider is present, that a saved child survives compatibility checks, or that its processing is neutral.

## Listener registration has a real image initializer

Mach-O `__DATA_CONST,__mod_init_func` cell `0x10440e628` contains `0x101f04f80`. That entry creates two24-byte records at globals `0x105011500` and `0x105011518`, using string `VstOpBusIDMapping` at `0x1038f12b2`, callback functions `0x101f0143c` and `0x101f015f4`, phase flags1 and0 respectively, and numeric field50. The common record constructor is `0x1022192d8` → `0x102219030`. It stores the name at+0, numeric field at+8 and callback at+0x10, then inserts the record into one of two phase-selected collections. Calling the numeric field a priority would require the separate dispatch/sorting implementation; this note does not assign that meaning.

`0x101f0143c` calls previously retained registration function `0x101f01458`; `0x101f015f4` calls unregister `0x101f0160c`. Registration initializes the listener registry and the map singleton, requires global `0x10501cac0` to exist with virtual+0xd8 returning false, locks the registry, and inserts the map pointer using `0x1008235d8`. That insertion checks pointer identity and refuses duplicates. Unregister removes the same pointer under the same context and lock. These are possible initialization/termination paths in the pinned image, not a runtime observation that the callbacks ran.

The initializer entry is important evidence of a boundary limitation. `LC_FUNCTION_STARTS` omits `0x101f04f80` and groups its bytes into the preceding interval beginning `0x101f049c0`, which also contains other disconnected routines. Pass59 retains that whole interval; pass60 separately analyzes the actual initializer entry identified by `__mod_init_func`, ending at the next declared boundary. The earlier interval is not presented as one reachable function.

## Nested lifetime and exact notifications

The scope vtable is `0x1044f05d8`; RTTI names `Steinberg::ChangeFollower::ObjectIDMappingLifeTimeScope`. Constructor `0x100823360` atomically adds1 to global `0x104f86ba0`. Only an old value of0 calls the begin dispatcher `0x100823450`. Destructor target `0x100827120` atomically subtracts1 and calls finish dispatcher `0x1008271e4` only when the old value was1. Thus an inner scope neither resets the mapping on entry nor finishes it on exit while an outer scope remains active. This is a static counter/control-flow observation, not a concurrency or lifetime correctness test.

Both dispatchers first apply the same global-host/nonzero and virtual+0xd8-false condition. They lock listener registry `0x104f86ba8`, temporarily move its pointer vector out, call each listener in vector order, reinsert those listener pointers through the uniqueness helper, free the old vector, and unlock. Begin uses listener virtual+0; finish uses virtual+8.

The bus map vtable `0x10458c9f8` has exactly those two slots: begin `0x100dd07a4`, finish `0x100dd0940`. Its RTTI is `TObjectIDMappingWithOneIDSpace<AudioEngine::VstOpBusIDMappingSetup>`, with `ObjectIDMappingBase` and `IObjectIDMappingLifeTimeListener` base identities. Begin clears the maps and sets map+0x68. Finish, if active, drains deferred work via `0x100dd0ba0`, clears map+0x68, and unlocks; the drain also clears both mapping trees. If inactive it follows a distinct direct-clear path. No permanent saved-ID mapping is implied after the outermost scope ends.

The previously decoded saved-ID setter `0x100dbf31c` and deferred-registration helper `0x101d16bb4` independently require that active flag and the host-context condition. The scope therefore closes a real admission prerequisite that the earlier map-setter analysis left open. It does not remove those guards.

## Root and channel scope placement

The `MRoot` RTTI/vtable identity is independently anchored at `0x104671b38` / `0x104671208`. Its virtual+0x130 points to `0x10171cab4`. That method creates a mapping scope at `0x10171cae0`, before several restoration paths through the same global service used by MTrack's provider binder (`0x1005bff70` → global `0x104feeee0`, then virtual+0x38). One path builds a stream wrapper around root+0x140 and calls the returned service's virtual+0x218; alternate paths use+0x208 or+0x220. The concrete implementation of those three service methods has not been closed in this tranche, so their successful restoration of the complete Devices dictionary is not assumed.

Still inside the scope, `0x10171cd50..0x10171cd68` invokes root virtual+0x588 with a visitor and arguments0,1. The exact MRoot table entry is `0x10171f76c`: it traverses the selected root container through `0x10175c6f0`, then additional collected containers via `0x10175c80c`. The caller subsequently sends the observed `Before Activate` message, performs more activation work, and ends the mapping scope at `0x10171cecc`. The concrete visitor's entire effect and every activation branch remain separate work. This is stronger than an unplaced generic scope, but not a claim of complete root/device restoration order or floating-point mixing order.

Common channel restoration `0x101d75bcc` independently opens a nested scope at `0x101d75c3c`. The input/output selectors and own buses restored inside it can therefore share an already active outer transaction. If called with no outer scope, it starts and finishes its own mapping lifetime. The saved-ID joins in the previous registry note must not be treated as durable runtime IDs or root ordinals.

Other observed callers include a Modulators service at `0x100815920` and a track-preset-related path at `0x100933f60`. They are retained as additional scope use, not mislabeled as project-file loaders. The bounded reference scan found18 direct calls to the scope constructor; this is not a complete dynamic caller inventory.

## A distinct deferred attribute-rewrite path

The finish queue dispatches each callback at virtual+0x30. The previously captured callback installed by `0x101d169cc` has table `0x1047a7a60` and+0x30 target `0x101d18958`. It passes retained attributes to `0x101d16068` with mapping callback `0x1047a7ad0`.

`0x101d16068` recursively handles named `Synth Slot` / `Output Channels` / `Output Channel` attribute scopes, then handles `InputBusValue`, `OutputBusValue`, `SendFolder` and `directRoutingFolder`. Its selector helper `0x101d1618c` requires an existing nested selector, a successful Value read, and a nonzero value; on successful callback lookup it writes the mapped value through `0x101d5fed4`. Other paths collect unresolved values. The callback+0x30 (`0x101d18b08`) passes the saved signed32 value to lookup `0x101d18c34`. The latter helper and full send/direct-routing branches are not yet analyzed here. This is attribute-remapping evidence, not an audio-connect or summation operation, and it must not be confused with the direct live VSTBusValue callback `0x101d62c14` already retained.

## Executable scope and next dependencies

The next safe report extension remains a source-bound typed saved output registry, with ordered rows, exact IDs/spans/hashes, role-separated child buses, processing-field coverage and cross-section saved-ID matches. A transaction model can explicitly record these conditions: initializer/listener path present in the image; host context unresolved; outer scope path identified; selected provider/factory path conditional; bus restore compatibility unresolved; saved match unique, duplicate or absent; processing state explicit/opaque/unsupported. None of these fields alone should set an effective-route or playback-admission flag.

The strongest next static target is the concrete global-service virtual+0x218/+0x208/+0x220 receiver used by MRoot, followed by the root traversal visitor and selector connection callback. Closing those would tie saved Devices restoration to the same active transaction as track-channel restoration. Whole-project rendering additionally requires supported InputFilter/Panner/component state interpretation, effective mute/solo/monitor/automation and routing topology, plus an observed accumulation/clock policy. The ten retained output rows already contain active filter/panner and opaque component state; their absence from Rebase's ordinary mixer is not evidence of native unity processing.

## Preserved limits and verification

- `verification-mapping-lifetime-01.json`:190 intervals,185 unique analysis/readback pairs,21 iterator cells.
- `verification-mapping-lifetime-anchors-01.json`:106 original-byte anchors,1570 bytes. It does not certify semantic interpretation.
- `mapping-lifetime-anchors-01.json`, `map-lifetime-scope-anchors-01.json`, `map-typeinfo-anchors-01.json`: exact cells/literals/instructions.
- `selected-static-refs-12.json` / `13.json`: only direct B/BL and adjacent ADRP+ADD scans. No claim of exhaustive references.
- `map-materialization-candidates-01.json` retained a broader lookahead scan without register-clobber tracking. Its extra candidates are not adopted as confirmed uses.
- `map-registration-pointer-candidates-01.json` found no exact absolute pointer to the two registration thunks. The later positive initializer evidence is not a rewrite of that limited negative observation.
- This new lifetime chain has not yet received the peer review that covered the earlier provider/options chain. That prior peer review must not be extended to these results.
