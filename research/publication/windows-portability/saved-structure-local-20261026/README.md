# Saved-structure local integration

This record concerns the shared CPR binding decoder, complete snapshot protocol, Mac inspector and Windows managed client. Native Windows acceptance and a downloadable inspector build remain pending. The already published Windows preview 9 is unchanged.

The initial full portable run executed 172 tests with three explicit generator skips. After the import-report byte-custody correction and new fixture generator, the final full normal Mac run executed 312 tests with 120 explicit skips and no failures. The final focused portable run executed six tests, covering the deterministic fixture exporter, exact report-byte custody and all four protocol tests. XML and source-hashed receipts are retained; earlier full runs are not presented as having tested later changes.

The [first integration review](structure-independent-review-01.json) found a Mac lifecycle gap: identical project reopen or edit/Undo could allow a stale inspection to publish. The [correction review](structure-independent-review-02.json) verifies generation invalidation and records 18 native executable checks of the current actual app code. Those checks combine bounded one-second observation with source review; discarded detached tasks are not directly joined. They do not constitute a new pixel or reference-runtime comparison.

The earlier [Mac UI review](mac-structure-ui-review-01.json) visited all five sections, read the complete JSON, scrolled to its end and preserved a dirty edit through inspection and Undo. Its exact build and source hashes precede the lifecycle correction. The view source itself is unchanged. Two original captures are included: [overview](mac-structure-overview.png) and [saved bindings](mac-structure-bindings.png). Original failed tab-layout capture, remaining images and raw accessibility records remain in private local custody, identified by the review receipt; none were repaired or substituted.

Windows [local controls](windows-structure/observation-01.json) passed 646 host checks, including 72 new saved-structure cases, a Release crossbuild and a real managed-client/shared-helper journey. These are macOS-hosted checks and do not establish WPF rendering on Windows.

The [final fixture/client correction](structure-fixtures-final-observation-01.json) binds both small and large managed-client journeys to the current helper and unchanged fixture files. The [native smoke preparation](windows-structure-smoke/observation-01.json) adds 14 future Windows checks and two capture requirements. Its receipt gate passed 130 authored controls. Independent review found and closed a tab-geometry acceptance hole; the [eight focused regression controls](structure-window-independent-geometry-probe-02.json) and [source review](structure-window-independent-review-01.json) remain distinct from native WPF execution. The earlier gate, its 124-control result and the failed crossbuild are retained.

## Fixture corrections

The first two fixture-export attempts failed the required multi-page size assertion. The second diagnosis showed that the authored writer did not mark its non-ASCII string encoding; the existing decoder correctly retained those bytes as opaque. The correction uses explicit ASCII authored text without broadening the decoder. The third run produced identical repeated exports: a 10,681-byte small report and a 102,898-byte large report spanning two pages. It also refused an existing export destination. Failed logs and XML are retained alongside the successful run.

The packages are authored historical replay controls, not vendor-authored or reference-accepted projects. Their generator is committed in the shared tests, and native CI generates them outside the downloadable application. The original source and frozen import report are never rewritten by inspection.

[publication-manifest.json](publication-manifest.json) identifies original and distributed hashes and every text-path redaction. All captures retain their original bytes. These checks do not establish effective routing, processing, reference equivalence, device output or complete platform parity.
