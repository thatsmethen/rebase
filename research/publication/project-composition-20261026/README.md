# Counted project structure and output routing

This continuation uses static REA/Ghidra observations of the retained macOS reference image, SHA-256 `dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb` (85,691,328 bytes). No proprietary reference program was executed. Windows checks concern the independently implemented shared decoder and application, not a Windows reference executable.

## Implemented saved-structure boundary

The [decoder handoff](decoder-handoff-20261026.md) describes counted project order, null and repeated identities, common track-resource associations, typed audio resources, raw saved numeric representations and bounded bus descriptions. The implementation retains unknown objects and opaque tails. It does not interpret a saved Volume as application gain, equate a saved bus ID with an active route, or authorize whole-project mixing.

The [independent source review](peer-review-example-payload-01.json) found two declaration-order defects. The corrected decoder reads each resource at its serialized position and captures its version context before later objects can supply declarations. The [private applicability receipt](private-applicability-verified-03.json) records ten unchanged retained templates, 145 counted entries, 17 common resource associations and five typed audio resources, with 1,140 independent source-byte assertions. Those templates are not distributed here.

The application integration presents a fresh read-only snapshot alongside the unchanged historical import report. The complete canonical JSON is bounded to 8 MiB and paged by bytes through revision-bound tokens. Application test and native-window results are separate evidence; these static records do not establish that an interface, audio device or full project mix worked.

## Subsequent static routing work

The following records extend the research beyond the initial saved-binding implementation. Their findings are not silently attributed to that earlier decoder:

- [Provider receiver and output registry](receiver-output-registry-addendum.md): the saved provider index selects a factory kind; the concrete audio-channel receiver and separate Devices/VST Mixer output-channel registry are traced. Five saved selector values match output-row own-input bus IDs. This remains saved identity evidence.
- [Processing state](processing-state-boundary-addendum.md): constructor-created filters, panners, folders and component state prevent assuming neutral processing from empty insert lists or absent fields.
- [Mapping lifetime](mapping-lifetime-boundary-addendum.md): nested restoration scopes and registered mapping callbacks constrain when saved IDs become runtime IDs.
- [Studio device restoration](studio-device-restoration-addendum.md): the Devices section reaches eligible named device receivers; missing names and inactive devices are not replaced with invented defaults.
- [Route application](route-application-boundary-addendum.md): selection includes eligibility, current-route retention and conditional fallbacks before destination membership changes. Pointer-vector membership does not establish floating-point accumulation order.

The latest [static verification](verification-route-application-01.json) covers 246 derived intervals and 240 distinct REA analyses/readbacks. Its [independent anchor receipt](verification-route-application-anchors-01.json) checks 83 anchors comprising 1,961 original bytes. Counts are evidence coverage, not independent runtime experiments or a completeness score. Later incomplete traversal work remains explicitly [paused and unanalysed](activation-expansion-paused-01.json).

## Corrections and provenance

Earlier notes remain unchanged. Read [Child Bus receiver correction](child-bus-receiver-correction.md), [provider option review](peer-provider-options-review-01.json) and [route evidence-directory correction](route-application-correction-01.json) with the records they qualify. The ordinary route restore does not always take the nonzero-value precheck; the corrected conditional path is in the provider addendum. Retained failed verification attempts are observations, not successful results.

[publication-manifest.json](publication-manifest.json) records original and published hashes and sizes. Derivatives replace local private paths and omit raw target-byte fields; addresses, span lengths, hashes, authored reasoning, corrections and limitations remain. Full proprietary binaries, disassembly/provider bodies and private project sources remain outside the public repository. The receipts alone cannot independently reproduce checks that require those omitted inputs. Original records have not been modified.

Effective processing, arrangement changes, activation order, automation and cross-track sample accumulation remain unresolved. Neither these records nor the saved-structure inspector establish full Cubase or macOS/Windows parity.
