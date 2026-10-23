# Local automation implementation controls

These records cover shared volume/pan editing and its Windows host integration
before native Windows execution. They do not establish Windows appearance,
device playback, reference-application fidelity or native CPR automation support.

| Record | Observed result | Evidence boundary |
| --- | --- | --- |
| `shared/observation.json` and XML | 8 new tests and 18 session/edit regressions passed | Portable shared target, executed on macOS ARM64 |
| `shared/mac-core-observation.json` and XML | 3 shared rendering tests passed | Normal macOS `RebaseCore` target; GUI and device audio were not exercised |
| `protocol/helper-protocol-01.json` and validation | 169 checks passed, including 78 automation checks | Actual ordinary Release helper on macOS ARM64; existing example/source locks retained |
| `host/observation.json` and logs | Windows cross-build and 191 host controls passed | macOS cross-compilation and authored host controls, including a fake audio adapter |
| `protocol-gate/` | 84 controls passed; byte-exact reproduction | One actual helper receipt accepted and 83 altered receipts rejected |
| `native-gate/` | 86 controls passed; portable derivative reproduces all outcomes | Two authored receipts accepted and 84 altered receipts rejected; no native window was executed |

The native-window gate harness generates flat-colour PNG controls with valid
headers. They are **not screenshots** and are deliberately excluded here.
Its recorded booleans, geometry and hashes are authored instrument inputs, not
evidence of native UI behavior. The protocol helper report is an actual process
observation; its separate gate controls mutate copies of that report.

`provenance.json` records every copied file's original and published hashes,
the limited derivative transforms, and hashes of private raw logs. Raw records
remain unchanged in ignored local storage. Passed XML files contain no absolute
workspace/toolchain paths and are copied byte-for-byte. The host cross-build
log replaces one absolute checkout prefix with `<workspace>`; its observation
continues to identify the original private log hash. Initial shared test build
failures are listed in the original summary and hashed in provenance.

The native harness derivative changes only invocation and output handling:
it requires a fresh destination instead of overwriting files beside the harness.
Its reproduced control outcomes match the original 86 outcomes exactly. This
folder omits cross-platform comparison controls, which were not ready when the
folder was assembled.

Run the published instruments from the repository root, selecting fresh ignored
output directories:

```sh
python3 research/publication/windows-portability/automation-local-20261024/protocol-gate/check-protocol-gate.py --receipt research/publication/windows-portability/automation-local-20261024/protocol/helper-protocol-01.json --output .local/work/automation-protocol-gate-recheck
python3 research/publication/windows-portability/automation-local-20261024/native-gate/run-native-gate-controls.py --output .local/work/automation-native-gate-recheck
```

These commands validate the current gate source. Compare its recorded hash with
the original observations before attributing a result to the same implementation.
Source-file hashes identify the tested versions even when they were not yet
committed. Native CI and image review belong in a separate subsequent record.
