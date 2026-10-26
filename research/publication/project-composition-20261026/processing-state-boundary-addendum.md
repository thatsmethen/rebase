# Processing graph and saved component-state boundary

This is an additive continuation of `receiver-output-registry-addendum.md`; neither that note nor earlier observations are replaced. It is static evidence from the pinned arm64 image SHA-256 `dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb`. REA raw slices retain their original addresses, complete readbacks, original-image disassembly and warnings. No reference code or plugin was executed. A constructor path is not proof that a particular runtime load traversed it.

## Channel-to-graph inputs are explicit

The shared channel constructor helper `0x101d67ef0` builds processors and folders before saved restoration. At `0x101d68878` it queries the panner wrapper at channel `+0x1578` through virtual `+0x550`; the corresponding query for input-filter wrapper `+0x1590` was made at `0x101d67fa0`. These are engine receiver pointers, not saved `Volume` scalars.

For the general graph branch, `0x101d68900..0x101d68934` passes the following arguments through wrapper `0x101f37910` to constructor `0x101f3672c`. The constructor stores them at the listed offsets. The folder names come from the original literal references where the channel fields are constructed, not from inferred graph labels.

| Channel member / role | Constructor argument | Graph member |
| --- | --- | --- |
| `+0x1540`, Modulators | x2 | `+0x270` |
| `+0x1548`, Inserts | x3 | `+0x278` |
| `+0x1550`, Strips | x4 | `+0x280` |
| `+0x1558`, Sends | x5 | `+0x288` |
| `+0x1560`, Outputs | caller stack +8 | `+0x290` |
| `+0x1568`, Foldbacks | caller stack +16 | `+0x298` |
| `+0x1570`, DirectRouting | caller stack +24 | `+0x2a0` |
| input-filter engine receiver | x6 | supplied to `0x101f37474` |
| panner engine receiver | x7 | retained and supplied to a graph stage |

Setup byte `+0x2a` gates graph construction; byte `+0x27` selects an alternate constructor `0x101f3f970 -> 0x101f3f6ec`. The alternate constructor calls the general constructor with a narrower set of folder inputs and installs a derived table. In both branches the resulting graph is stored at channel `+0x14c8` and registered with the engine collection (`0x101d6896c..0x101d68980`). This is a conditional construction/registration chain, not a declaration of the setup bytes during an observed project load.

`0x101f3672c` creates explicit stages and patchers in addition to folder items. Original UTF-16 labels include `pre listen patcher`, `post listen patcher`, `recording from buses patcher`, `input splitter`, `input splitter patcher`, `pre splitter`, and `pre splitter patcher`. The alternate constructor adds `listen/talkback merger` and `merger patcher`. Exact literal bytes are in `processing-stage-label-anchors.json`. These labels identify objects, not an independently recovered floating-point evaluation order.

## Selection and rewiring are state-dependent

The graph's `+0x178` and `+0x180` virtual methods select concrete stage receivers rather than returning a scalar neutral flag. `0x101f3f010` and `0x101f3f268` consult folder entries, `APluginSlot` type checks, item stage `+0x260`, stage `+0x190`, graph flag `+0x2af`, and fallback stages. Empty plugin lists do not eliminate the input splitter, input-filter or panner stages by themselves.

`0x101f375bc` constructs a selected effect-interface list at graph `+0x198` with count `+0x1a8`. It includes a specific stage and qualifying Inserts/Strips entries, checks `VstOpEffect`, and checks plugin-slot predicates. This is not proof of the complete render chain or root-track accumulation order. Likewise graph virtual `+0x130` (`0x101f3ec98`) calculates guarded numeric state across stage links; its numeric meaning has not been assigned from a guessed name.

`0x101f3b3c8` rewires stage neighbors and port maps. The original instructions reject null/equal receivers, call neighbor setters `+0x1a0/+0x1a8`, transfer per-port entries via `+0x170/+0x178/+0x180`, and notify the engine of changed stages. It is not a sample-processing loop. `0x101f3c9d0` changes graph flag `+0x2af` and walks Strips entries, calling that splice helper for qualifying stages. Consequently, counted saved folder order alone does not prove effective graph order.

## The panner and input filter are plugin-state consumers

The panner wrapper constructor is `0x101cb9c70 -> 0x101cb86fc`; its primary table is `0x104797978`. It initializes a typed device object, queries a plugin factory, and uses global/default properties as well as a local fallback. It does not consist solely of a pan multiplier. The input-filter wrapper constructor is `0x101cb286c -> 0x101cb20d4`, table `0x104795cb8`.

For both wrappers:

- virtual `+0x550` is `0x100dcac7c`, returning member `+0x5b8`;
- ordinary `+0xb0` tail-dispatches virtual `+0x368` with mode zero;
- plugin selection `+0x4a0` dispatches `+0x6e8` with x3 zero and w4 -1; the concrete `+0x6e8` is `0x100daa63c`.

Panner `+0x368` is `0x101cc05f0`. Its mode-zero path includes compatibility/default UID handling, the common plugin reader, parent-channel type checks, and `PannerType` handling. Input-filter `+0x368` is `0x101cb4dd8`: it calls common reader `0x100dbe6d4`, then invokes `+0x508` with one. The latter (`0x100dbfa64`) updates a bit-dependent device state and recalculates another property. It must not be silently identified with the separate saved `Active` property without following its notification semantics.

The common reader `0x100dbe6d4` has an `Unload Attributes` branch. When that nested field is absent it tail-calls existing captured function `0x100dadac0`. The latter resolves saved `Plugin UID` through a plugin registry, consumes audio input/output arrangements, and obtains `audioComponent` and `editController` as typed `FMemoryStream` objects. At `0x100dae64c..0x100dae738`, a nonempty component stream is reset/wrapped and passed through `0x100da3978` to the selected component's virtual `+0x60`. That wrapper treats component return codes 0 or 3 as success; the caller here does not branch on the returned boolean. A valid serialized field therefore does not establish that the processor accepted or applied the state. `0x100decbac` separately forwards component state to the selected controller through `+0x28`, accepting return zero.

The common reader also consumes saved `Active` at `0x100daea40..0x100daea60` into the device property at `+0x2d8`. That property, wrapper activation, plugin availability, component-state acceptance and DSP-neutrality are separate facts. The 140 opaque fields described below are not decoded by this tranche.

## Actual saved output processing coverage

`private-output-processing-coverage-01.json` is derived from the unchanged exact-end `private-devices-fields-01.json`, whose original bytes were independently checked by `private-devices-readback-01.json` (33,752 checks, 8,734 fields, ten fixtures). It records hashes/spans and scalar bits, never string values or copied component payloads.

All ten observed output-channel records contain `InputFilter`, `InputGain`, `InputPhase`, `Volume`, `InsertFolder`, `hasAudioStrips`, `StripFolder`, `ChannelStripsPreInserts`, `EQ`, `Panner`, `Monitor`, `foldbackSendFolder`, `clickEnable`, `clickVolume`, and `clickPan`. The selected section set contains 140 compound-type-7 opaque field envelopes, including both audio-component and controller state. All ten save `InputFilter/Active = 1` and `Panner/Active = 1`; their insert/strip folder `Bypass` scalars are zero. These are saved values, not measured enabled DSP or proof of an audible change. An empty insert slot list would not dispose of the independent opaque input-filter/panner state.

The selected `ModulatorFolder` and `DirectRouting` keys are absent in these output rows. The observation is exact key absence in these files, not proof that native construction omitted corresponding stages or that other spellings/roles are equivalent.

## Implementation consequence and next closure

A useful bounded next implementation remains an ordered saved output-registry report: preserve each raw output-channel receiver envelope and identity, every bus role and child identity, exact cross-section saved-ID candidates, and a processing-coverage object identifying explicit controls and opaque spans. The registry joins can be exposed now with effective routing unresolved. They must not turn on a project mix merely because an ID uniquely matches.

A faithful playback admission rule still needs these independently closed prerequisites:

1. Establish the actual load/remap context, registry construction options, provider availability and unique receiver ownership; retained saved IDs are not runtime IDs.
2. Resolve channel layout and every effective output edge, including child-bus, monitor/listen/foldback and default-output policies without inventing a master route.
3. Resolve the selected processor identities and accepted state. For an explicit neutral subset, prove neutral behavior from each processor's actual supported state, not missing keys, `Active`, `Bypass`, `PannerType`, or empty slots alone.
4. Recover graph traversal, clock/automation applicability, summing order and arithmetic for the admitted topology. Constructor and accessor order do not certify sample accumulation order.

The next narrow static target is the selected component identity/state contract reached through the verified `Plugin UID -> +0x6e8 -> component +0x60` chain, with exact component custody before analyzing another image. In parallel, the whole-project remap begin/end caller scope remains necessary. This tranche does not claim any whole-project neutral/audio-fidelity domain has been certified.
