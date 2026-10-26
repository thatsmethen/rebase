# Saved selector to conditional runtime bus connection

This is a new additive static tranche (passes74–80), following the frozen studio-device and mapping-lifetime notes. Original target SHA-256 remains `dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb`. No proprietary reference ran. All derivatives retain original addresses, REA analyses, complete raw readbacks and original-image disassembly. No tracked application source changed.

## A selector value is not its effective connection

The already recovered saved-ID callback `0x101d62c14` only writes selector `+0x3c`. The newly inspected lookup `0x101d5f240` reads that value, requires it to be nonzero and the global mixer owner to exist, then passes the selector's captured collection `+0x68` and ID to `0x101d4d748`. That collection searches parent then direct child IDs; it does not resolve by track index or label. A missing runtime ID returns null.

The common channel reconciliation method is `0x101d6cc88`, at virtual `+0x4f8` of the known audio-channel table `0x1047ac688`. Its output selector is channel `+0x9c0`, independently confirmed by `OutputBusValue` restore at `0x101d766f8`. Unless the selector's role field at channel `+0xa58` equals1, reconciliation performs this decision sequence:

1. Resolve the selector to a bus using `0x101d5f240`.
2. If a bus resolves, ask the channel's virtual `+0x620` predicate whether it is acceptable. If lookup returns null but the raw selector value is zero, still call that predicate with null.
3. If accepted, call channel `+0x4c0` with that selected bus, including an explicitly accepted null bus.
4. Otherwise test the channel's current destination at `+0x14d8` with the same predicate. If acceptable, obtain its runtime ID through `+0x1b8` and submit it to the selector setter. If not, call selector fallback `0x101d5f0d8`.
5. Resolve the possibly changed selector again, then call channel `+0x4c0`.

This is an observed state-dependent policy. In particular, saved zero, unresolved nonzero, an inadmissible resolved bus and an existing acceptable route are distinct cases. Nothing here authorizes treating every unresolved route as master/stereo/unity.

## Audio-channel destination admission

For the concrete audio channel, `+0x620 → 0x101d6cb18`. Null is accepted. Non-null candidates are rejected if their type query accepts any of the exact strings `VstOpBaiosInputBus`, `VstOpBaiosOutputBus`, or `VstOpRecorder`. If the channel has an engine wrapper at `+0x14c8`, the predicate obtains the candidate's containing process unit through `0x101f170cc` and rejects a positive `0x101f435c8(channelWrapper, candidateProcessUnit)` result.

The latter helper performs recursive pointer identity reachability, not speaker-arrangement comparison: null target returnsfalse; identical root/target returnstrue; otherwise it iterates receiver virtual `+0xf8` count and `+0x100` indexed process-unit relationships and recurses. For the known wrapper table `0x1047e8d48`, those methods are `0x101f3e934` and `0x101f3ea2c`. They enumerate relationships through the wrapper's source/operator path, with a mode flag at `+0x2ae` and associated operator/folder paths. This supports a containment/cycle guard in that observed direction; a fully reconstructed generic routing graph has not been proved.

`0x101f170cc` follows parent `+0x38` while the parent is a `VstOperator`, then requires a `VstProcessUnit`. These are exact type literals. The output-channel subclass predicate (`0x1047be9e0 +0x620 → 0x101dee3dc`) first accepts the common predicate's success, but on failure can additionally accept one exact pointer reached through its own `+0x15f0 → +0xe8`. That subclass path cannot be applied to ordinary audio channels.

## Concrete connection and membership operations

Audio-channel `+0x4c0` is `0x101d72c78`. Its body includes old/new bus-type-dependent relationship updates, then at `0x101d72e38..0x101d72e5c`, when an engine wrapper exists, invokes `0x101f398f0(wrapper,newBus)` under a scoped operation and stores the destination at channel `+0x14d8`. The method also invokes graph/update/notification paths. Those updates are not reduced to a pure pointer assignment by this note.

`0x101f398f0` passes the new destination into `0x101f270d8` with receiver `wrapper+0x248`, then invokes additional graph update functions. The wrapper constructor previously captured in pass47 installs this output-stage object through `0x101f289c0` at `0x101f36cb0..0x101f36cb8`; its graph is not inferred from a UI route label.

`0x101f270d8` performs the actual observed edge mutation:

- If the output-stage receiver's old destination at `+0x230` exists, call old destination virtual `+0x170` with this output-stage receiver.
- Store the new destination at `+0x230`.
- If new destination exists, call its virtual `+0x168` with this output-stage receiver.
- Obtain a destination-dependent configuration (or a different receiver when destination is null) and call `0x101f273c4` before returning.

For the concrete native bus table `0x1047e3768`, attach `+0x168` resolves to `0x101f022c0`, and detach `+0x170` to `0x101f02560`. Attach scans the pointer vector at bus `+0xf8..+0x100` for identity and only inserts if absent, then calls `0x101f02414`. Detach scans/removes the matching pointer with element movement and invokes the same update method. The insertion helper's growth/order and the update method's complete effects have not been reconstructed. Neither identity membership nor the saved root order establishes floating-point summation order.

## Selector-specific fallback is observed, not assumed

The audio-channel constructor at `0x101d3bdf8..0x101d3be04` supplies role10004 (`0x2714`) and the channel pointer for its output selector. `0x101d5eea4` stores the role at selector `+0x98` and channel pointer at `+0x60`, then invokes a virtual setup method. The inspected fallback `0x101d5f0d8` uses a role switch;10004 enters the branch that calls mixer `0x101dc97e4` with argument0 and submits the selected bus's runtime ID, or0, to virtual selector `+0xe8`.

`0x101dc97e4` immediately uses cached mixer `+0x9c8` if non-null. Otherwise it iterates the output collection at `+0xac8` with the stored bound at `+0xae0`, checks `VSTOutputChannel`, initially retains a bus from channel `+0x568`, and can prefer another using channel `+0x580` plus configuration helper `0x10035f868`. The exact meaning of the constructed configuration value1 and that comparison is not established here. The argument0 in this path prevents the later branch that can create an output when none was found. It finally writes the result through the previously retained default-output setter `0x101dc9c20`.

Consequently a fallback is real, but its outcome depends on the current cached default, actual restored output collection, supported arrangement behavior and the selector's setter checks. It must not be invented from absence of saved attributes. Current-route preservation and role-specific fallback also mean that source bytes alone do not yet define every runtime route outcome.

## What this enables next

A shared composition planner can now distinguish: saved selector candidate, saved-to-runtime identity remap, registry lookup, recipient eligibility, retained-current-route fallback, default-selection fallback and output membership mutation. These should be separate evidence fields/states. The first implementation remains the saved registry/processing inventory under the verified Devices receiver, followed by a route evaluator only for explicitly reconstructed receiver/graph/default states. It must preserve unknowns and reject unsupported playback instead of guessing.

The unresolved work is concrete: establish the root/track activation visitor's ordering of channel reconciliation against the mapping lifetime; close configuration/arrangement updates, direct-routing/send variants and subclass behavior; interpret supported processor state or establish actual neutral processing; and recover scheduling plus float32 accumulation order. Other inspected paths in pass74 (`0x101d6d118`, `0x101d73d0c`) include migration/serialized state work and are retained as context, not claimed as the authoritative graph connection operation.

`route-application-anchors-01.json` and `verification-route-application-anchors-01.json` independently bind the new cells, strings, instruction sequences and selected call references to original bytes. `verification-route-application-01.json` repeats full derivative/readback custody validation across the complete retained static set. No external peer has reviewed this new tranche; prior provider/options peer review does not cover it. All earlier observations and notes remain unchanged.
