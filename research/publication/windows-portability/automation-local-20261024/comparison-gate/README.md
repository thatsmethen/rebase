# Automation comparison gate: authored controls

These are comparison-instrument controls, not Windows or cross-platform executions. One actual macOS arm64 Release helper receipt passed 169 interactive checks. Copies of that receipt were placed beside **authored** Windows/macOS Debug/Release metadata to test gate acceptance and rejection. The fixed original audio locks were not changed.

The initial comparator matched 35 of 44 expected outcomes and falsely accepted nine inputs: matching but incorrect original PCM/lock/frame metadata, null or malformed source identities, unsupported receipt schemas, and mismatched architecture. Those original results and source snapshots are retained. An intermediate correction matched 65 of 66 expectations because it incorrectly required unique check names; the actual CPR journey legitimately repeats descriptive checks. The corrected comparator matched all 66 controls: two valid observations and 64 rejected malformed, missing, mismatched or incomplete cases. Edited WAV and PCM divergence are checked separately.

`observations/` preserves the original comparison-result and summary JSON bytes. Each input digest inventory identifies the original generated JSON files, which remain preserved privately. `instruments/` contains the exact three comparator/gate/source-lock snapshots. `fixtures/` contains the single actual Mac helper receipt and its validation provenance plus the earlier retained render-metadata template. The template does not turn the authored comparison inputs into platform executions. `manifest.json` identifies retained file bytes; it does not replace prior provenance.

From the repository root, reproduce the expanded corrected controls with:

```sh
python3 research/publication/windows-portability/automation-local-20261024/comparison-gate/run_controls.py --output .local/work/automation-comparison-reproduction
```

The output must be a new directory under this checkout's ignored `.local/`. The harness stages the selected immutable Python instrument there, creates labelled inputs, and binds their synthetic commit metadata to the **current checkout HEAD**, because the corrected gate checks that source identity. The fixture's Mac helper identity is recorded separately; current HEAD metadata is not a new execution claim. Fresh run output is therefore a new authored observation, not a byte-for-byte rewrite of historical input files.

`--instrument initial` or `--instrument intermediate` runs the expanded controls against those earlier snapshots; rejection expectations will fail because the preserved instrument defects are still present. Historical result files are never overwritten. Corrected success validates this admission/rejection instrument only; real multi-platform CI and native application evidence remain separate.
