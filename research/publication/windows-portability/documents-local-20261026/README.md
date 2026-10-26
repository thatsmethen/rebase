# New Project and audio import: local candidate

The Windows candidate adds File → New Project (Ctrl+N) and Import Audio (Ctrl+I). Imported files are copied byte-for-byte into one newly published media directory, placed on separate tracks at the retained ordinary-project insertion time, selected, and recorded as one undoable batch. New/Import refuse queued intents after the project or revision changes. A failed native stop/cancel prevents the document mutation. Save As publishes an editable package; cancellation and invalid inputs preserve the document.

The initial Windows domain is 1–32 mono/stereo PCM WAV files, 8–192 kHz, at most 16 million frames per file and 256 MiB per batch. The shared package bounds remain 512 MiB and 10,000 entries. This does not match all Mac import formats or sizes: the existing Mac interface keeps its broader importer. The new Mac adapter passed bounded WAV and AIFF controls but has not replaced that interface.

## Observed local validation

- Shared portable controls: 36 executed, no failures or skips. Normal Mac controls: 15 executed, no failures or skips. These include the new workflow and relevant existing document controls; they are not whole-suite totals.
- Managed host controls: 574 passed. WPF Release cross-build: zero warnings/errors. Cross-building on macOS does not execute a Windows window.
- Documents receipt gate: 92 authored cases (4 accepted, 88 rejected), all as expected. These validate the receipt/image instrument; they do not demonstrate native UI behavior.
- The implemented native journey adds 15 window checks to the prior 150, including New, multi-file import, one-step undo/redo, failed batch, cancellation, Save As, clean New, reopen, copied hashes and real waveforms. Its actual Windows execution is pending. File paths and dialog decisions are injected through the real WPF File-menu journey; physical dialogs, input and audio output are not claimed.

## Preserved application failure and capture correction

Application run [40260074474](https://github.com/thatsmethen/rebase/actions/runs/40260074474), at source `0df898f443feace27ea888904d74f7d6cc747457`, remains failed. Native/helper gates and all 150 WPF interaction checks passed, but the package validator rejected the source-stream PNG for alpha values below 255. The unchanged 724 × 501 image contains 361,359 pixels at 255, 1,365 at 254, and none below 254. Visual review found complete content.

New captures record the root brush alpha and exact raster histogram before validation. The validator independently decodes PNG alpha, checks CRC/size/DPI/geometry and requires exact agreement with the recorded histogram, an opaque root brush, and no pixels below 254. Alpha-254 pixels remain explicitly counted; they are not relabeled opaque. The stream gate passed 115 controls and three bounded actual helper workers. Sixteen additional controls over the retained raster use explicitly authored/derived root metadata; they cannot retroactively accept the original failed run.

Original failure records, earlier local tests and source hashes remain preserved. New source still requires native Windows execution, the cross-platform lanes, final package/privacy audit and actual-image review before a downloadable release is accepted. The released preview remains available. No proprietary reference executable was run.
