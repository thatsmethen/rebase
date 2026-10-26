# Conditional saved Devices restoration into the studio and mixer

This is a new static-only addendum to `mapping-lifetime-boundary-addendum.md`, `receiver-output-registry-addendum.md` and `processing-state-boundary-addendum.md`. It preserves those frozen records. The original arm64 target SHA-256 remains `dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb` (85,691,328 bytes). No target code was executed, no private fixture was edited, and no production source was changed. REA analyses and full readbacks are retained in passes 62–73, with original-address native disassembly and original-image hash-bound derivatives. LC_FUNCTION_STARTS intervals are not a claim that every contained instruction is reachable from their first entry.

The new result closes a conditional receiver chain: a typed saved `Devices` attribute object is retained on MRoot, its activation method supplies it to the resolved IStudio service, and the fallback PStudio implementation restores only eligible registered devices using attributes under each device's actual name. A known initialization path registers the VST Mixer owner that has the previously recovered Output Channels reader. This is stronger than a name-only correspondence, but it does not establish that the fallback service or mixer exists in any particular runtime.

## File object to MRoot storage

The routine beginning `0x1009b97ec` receives the source-container object and an output project object. At `0x1009b9a98..0x1009b9ae4` it requests the exact key `Devices` (`0x103890ec3`) with type `FAttributes` (`0x1038911f2`), then independently invokes the returned object's type query before accepting it. At `0x1009b9ae8..0x1009b9af4`, the object from the output project's `+0x108` field and the accepted attributes are supplied to `0x10171dbc4`. That setter releases the previous pointer and stores the new pointer at receiver `+0x148`. The caller then increments the accepted object's reference count. The setter alone does not establish the concrete caller receiver; its direct call and the earlier MRoot layout/activation evidence supply that relationship.

If typed attribute retrieval fails, `0x1009b9b10..0x1009b9b94` tries the same `Devices` key as `FMemoryStream` (`0x10389a4c6`), type-checks it, invokes its preparation routine `0x1031823e4`, and calls `0x10171d934`, which stores it at receiver `+0x140`. These are separate saved-state representations. No equality of their serialized payload formats is claimed.

The previously retained MRoot activation routine `0x10171cab4` gives `+0x140` precedence: it wraps that stream and calls resolved studio slot `+0x218`, then releases/clears it. Otherwise it calls slot `+0x208` with `+0x148`, then releases/clears it. If neither exists, it calls slot `+0x220` with argument 1. All these calls are inside the previously recovered ObjectIDMappingLifeTimeScope. The standalone MRoot attribute reader `0x101722ca0` and stream reader `0x101722120` did not establish these stores; those inspected negative paths remain retained. A separate path `0x10171d550` captures current studio attributes through `+0x200` and stores them at `+0x148`; it is not the file-section admission path.

The selected-reference search is limited to direct branches and adjacent ADRP+ADD pairs. The bounded MRoot store search inspected aligned instructions only between `0x101710000` and `0x101730000`, without receiver tracking. Its candidates were used to locate the setters, not treated as proof of their receiver types.

## Resolving the service receiver

`0x1005bff7c` obtains or supplies a fallback `Lego::IComponents` object with table `0x1044aced8`; `0x1005c002c` publishes the host and resolved component into the structure at `0x104feeee0`. The table's `+0x38` entry is `0x1005c0784`, which returns the field at context `+0x30`. The table's `+0x10` initializer `0x1005c033c` supplies that field's address to `0x1005c0d60`, which resolves the exact `IStudio` component. This connects the same `0x1005bff70 → virtual +0x38` used by MRoot and the track binding path to the studio interface when this Context implementation is in use.

The component setup path `0x1005ca934` invokes `0x1005cad48`. That function first looks up `IStudio` (`0x104f86448`); only if absent does it allocate `0x180` bytes, construct through `0x101a95318 → 0x101a9500c`, and register the object. Its primary table is `0x1046df3c0`, whose RTTI names `Steinberg::PStudio`. Existing replacement components are not overwritten by this fallback path. Neither the presence of this code nor the resolved table in static data proves the runtime selected it.

Relevant PStudio slots are independently read back:

| Slot | Target | Observed role |
| --- | --- | --- |
| `+0x120` | `0x101a960e8` | Device registration |
| `+0x160` | `0x101a95dcc` | Named PDeviceNode lookup used by the track-provider path |
| `+0x200` | `0x101a9785c` | Attribute capture invoked by MRoot's separate capture path; body not newly analyzed |
| `+0x208` | `0x101a97b88` | Saved attribute restoration |
| `+0x218` | `0x101a98320` | Saved stream restoration |
| `+0x220` | `0x101a977a0` | No-state/reset operation |
| `+0x258` | `0x101a9b7b4` | Returns PStudio's registry at `+0x20` |

PStudio's constructor creates that registry through `0x101a0bd4c → 0x101a0bc74`. The registry constructs a PDeviceNode named `Device Root` at its `+0x10`. Registration forwards to that node's `+0x110` collection method via `0x101a0be38`. Attribute restoration visits the same registry/node through its count `+0x100` and index `+0x108` methods. This establishes shared collection identity, not a mixer accumulation order.

## Saved attribute applicability is explicitly gated

`0x101a97b88` resets the supplied attribute read cursor and iterates the studio's registered collection. For each device it reads the 32-bit field at `+0x1f0` and requires:

`(deviceFlags & 0x0a00) == 0x0200`

It obtains that device's virtual `+0xd8` name and requests nested attributes of that exact name through `0x1031a08e4`. A missing nested field skips the device, without calling its reader or inferring defaults. When present, it resets that nested read cursor and dispatches the device's `+0xb0` reader; the return values are ANDed into the method's result.

An additional helper is called before that loop when studio flag `+0x140` bit 5 is clear (`0x101a7a208`). Its full effect has not been established here. Consequently the direct loop is an observed applicability rule, not an exhaustive description of all studio restoration side effects.

A precision correction to exploratory progress wording: after the registered-device loop, the method does **not** enumerate every arbitrary attribute key. It reads the explicit `StoredDevices` field (`0x1038e33c2`) using `0x10319f810`. That helper requires a compatible `FStringList` and advances its element cursor. For names from that list not already handled, the method finds their nested attributes and retains a holder containing the name and attributes at holder `+0x110`, in the studio's `+0x28` list. Thus missing receivers can have preserved saved state; an unlisted arbitrary field is not proven retained by this mechanism.

The stream reader `0x101a98320` reads a count and per-entry name/data, resolves a named `PDevice`, uses the same `0xa00/0x200` eligibility predicate and dispatches `+0x98`. Unmatched entries take a holder-retention path. Its archive encoding and that of the mixer stream reader `0x101dde5e4` remain outside this tranche; they must not be treated as equivalent to the attribute representation.

## Concrete mixer admission, still conditional

The initialization function `0x101dc6208` allocates `0xe68` bytes and invokes the known VST Mixer constructor `0x101dc760c` at `0x101dc68b4`. It stores that owner in `0x105010970`, resolves IStudio by the Context getter, and calls IStudio `+0x120` with the same owner and flags `0x302` at `0x101dc68dc..0x101dc68e4`. The owner constructor's name is the exact `VST Mixer` string. Its table `0x1047bca48` gives name `+0xd8 → 0x10000ae30` and attributes `+0xb0 → 0x101dd94a4`, the previously analyzed Output Channels reader.

PStudio registration has null, identity and name-collision paths before insertion. At `0x101a96414..0x101a9641c` it ORs the supplied flags into the device field `+0x1f0`, then inserts the same device into the registry. If studio flag `+0x140` bit 2 is set, it invokes device `+0x418`; a false result sets device bit `0x800` at `0x101a964c8..0x101a964d0`, excluding it from the later restore loop. Other paths call the device's `+0x238` and may apply retained state.

The common PDeviceNode constructor initializes `+0x1f0` to zero at `0x101a0cba0`; this is an initial value only, not a guarantee about the field by restore time. The known `0x302` registration contributes the required `0x200` without contributing `0x800`, but failed activation and other runtime state can change eligibility. A saved `VST Mixer` field alone cannot prove registration, non-replacement, successful activation or effective use.

## Implementable scope and remaining playback dependencies

This supports a separate saved-device registry decoder/report whose typed origin is `Devices/FAttributes → VST Mixer/FAttributes → Output Channels/FSubList`, using the previously established receiver-specific field schema. Preserve channel list order, named identities, exact source byte spans/hashes, Bus UID own/child relationships, default-selection candidates, explicit processing fields and unknown opaque state. Report why effective applicability remains unresolved. Do not set a runtime route-resolved flag from a saved ID join or from the fallback registration code.

The next actual routing dependency is the consumer that applies the remapped OutputBusValue to a concrete channel receiver and its bus registry, including missing/ambiguous IDs and output-child arrangement compatibility. The mapping scope and deferred saved-selector rewrite are now explicit, but a successful saved-ID equality is not the runtime connection operation. The processing dependency remains the opaque InputFilter/Panner/component/controller state and the actual insert/strip/send/routing topology; saved active and bypass flags do not certify neutrality. The clock and float32 accumulation/composition order also remain outside this receiver admission proof.

The new chain is independently byte-readback verified but **not independently peer-reviewed**: both potential reviewers are occupied with the current Windows UI/native release work. The earlier provider/options peer review remains limited to its original scope.

## Custody

`studio-device-anchors-01.json` retains exact original cells, strings and instruction sequences. `verification-studio-device-anchors-01.json` independently remaps the original Mach-O and checks these plus all selected-reference/store candidates from this continuation. `verification-studio-device-01.json` verifies every retained derived interval, its original native instruction words, each REA analysis and each complete raw readback, including all prior passes. Failed and negative exploratory observations are preserved and are not promoted into semantic claims. Privacy review covers this addendum and these reviewed relative-path summaries; raw private records remain local.
