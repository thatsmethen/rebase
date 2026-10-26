# Saved field encoding and applicability correction

This additive record preserves the first 86-function study and all earlier decoder results. It concerns static readers in pinned arm64 target `dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb`; the proprietary image was not executed. `verification-field-encoding-01.json` independently verifies 91 derived functions, 91 REA analyses, 91 full-slice readbacks and 21 equal list-accessor slots. `field-encoding-custody.json` additionally verifies 1,088 instruction words in two unchanged sealed readers against that original image.

## Child Bus is a named container

Bus restoration `101f30b34` asks the named `Child Bus` field for its count using `1031a0e1c`, then retrieves members through `1031a0c94` and `1031a0ce8`. The count getter performs a single name lookup, verifies a compatible `FAttrList` object and calls its `+d0` count method. The member getter performs the same named lookup, verifies `FAttrObjectArray`, advances its stored index and calls `+110`; EOF resets the index. These are ordered members of one named container, not repeated named fields.

The saved attribute reader `1031ab5b8` branches to subtype201 at `1031aba48`. It reads a count and each member discriminator. Typed20 members call `1031ab444`; reference21 members use the deferred-identity path. A bare6 field dictionary is not an admitted object-array member. `1031ab444` reads class name, identity and field dictionary, preserving the typed wrapper. Structural parsing of a typed wrapper does not establish that its fields apply to a bus receiver.

The initial authored decoder controls used bare6 dictionaries inside subtype201. That was an instrument/domain error. The first focused12/full159 results remain as earlier outcomes and must not be cited as validating native array-member encoding. The correction requires explicit typed20 array members, changes the authored positive fixture to typed `FAttributes`, and adds negative controls for bare6 and deferred21. Deferred references remain opaque; they are not silently skipped or resolved by guessing. Duplicate named fields remain an explicit strict application policy, not a claim that all native restoration states forbid duplicates.

## Saved Volume versus runtime control precision

The numeric type jump table at `103c7a6d2` maps saved field type4 to `1031ab724`, which calls the binary64 reader and stores a Double. The Volume restoration path calls `10319e910`; that calls the numeric getter `10319e818` into a Double local, executes `fcvt s0,d0` at `10319e934`, and stores Float32. The getter also accepts selected integer/string coercions, which this first decoder does not infer as a raw float64 candidate.

Therefore preserving the saved type4 exact 64-bit payload is appropriate. It is not the runtime Float32 control, dB, normalized gain, or proof of a neutral signal path. The report exposes exact encoding/bits/span and separately marks unresolved processing.

## Actual root ancestry

The first compiled private template probe read all ten unchanged factory templates and rejected all ten at the initial root guard. These failures are retained in `private-fixture-probe-02`. The diagnostic registered-header probe in `private-header-probe-01` shows all ten roots declare `MGroupEvent v0`, `MPartEvent v1`, `MEvent v1` and `CmIDLink v0`, followed by `MRoot v6`. `MTrackEvent` is not the root's base; it is declared later at a track. No class-name scanning was used.

The existing sealed autofade-source finding binds the root call chain `101722120 -> 10170ee20 -> 10171862c -> 1017017a0` and its 26-byte event prefix. The corrected root admission requires the actual observed root bases; individual track admission still requires observed MEvent v1/MTrackEvent v2. Conflicting versions invalidate the report. The authored controls now declare MTrackEvent at the later audio-track object and include empty-root and wrong-root-base cases. This correction does not authorize full project playback.

## Inspection boundary

`inspect(from:)` uses the existing bounded source intake. `inspectPreserved(in:)` first replays and verifies the historical compatibility report, rereads the preserved source and checks exact source hash, count and sections before decoding. It does not rewrite either historical file and does not pretend that its observations describe subsequent app edits. Current app manifest/revision validation remains the responsibility of the future protocol integration.
