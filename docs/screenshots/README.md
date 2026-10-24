# Rebase screenshots

## macOS 0.21.0

Actual window captures from the arm64 release build, version 0.21.0 (21), on 2026-10-23. The arrangement contains four tracks and eleven clips of newly synthesized audio in a native Rebase project. It demonstrates the ordinary arrangement and automation interface, not imported reference-project fidelity.

- `arrangement.jpg`: the eight-bar, 96 BPM session with track waveforms, inspector and mixer.
- `automation.jpg`: the pad track's volume automation editor.
- `about.jpg`: application icon and version panel.

No personal documents, local filesystem dialogs or desktop content are included. Ancillary image metadata was removed without recompressing the captured image. The release executable SHA-256 is `6f22e14e301d15a6c3c418c828b9a791d41bb2330aec727f6c6b46808af2bd13`.

## Windows 0.21.1 development preview 7

Actual WPF client-area renders from the opened application at commit `53cb669f0e2bbf28003c79a355e7de526aeeef9b`, captured by [native run 40045765975](https://github.com/thatsmethen/rebase/actions/runs/40045765975). The seven main-window images are 1084 × 749 pixels. CPR review is 814 × 611; its minimum-size error state is 634 × 441. The three minimum-size automation editor images are 664 × 521. All captures use 96 DPI and exclude the operating-system frame.

- `windows-arrangement.png`: the four-track, eleven-clip example in Compact density with real waveforms, Channel/Inspector, musical ruler, mixer and transport.
- `windows-workspace-normal.png`: the same example in Normal density; all four rows fit.
- `windows-workspace-expanded.png`: the arrangement after hiding the left panels and lower mixer.
- `windows-source.png`: the canonical authored single-source fixture after PCM24 attachment and checked export.
- `windows-scrolled.png`: the example at 100 pixels per second, horizontally scrolled 368 pixels. Track headers and ruler corner remain fixed.
- `windows-long-names.png`: long authored project/event names retain their allocated fields.
- `windows-resize-request.png`: the same scenario after a wider-window request constrained by the hosted display.
- `windows-cpr-review.png`: authored CPR review with preserved-source identity and complete navigation/import controls.
- `windows-cpr-review-error.png`: minimum-size review with the observed error message and all four footer controls visible.
- `windows-automation.png`: restored five-point Volume automation, real curve, point list and editing/footer controls at the editor's minimum size.
- `windows-automation-invalid.png`: the invalid numeric draft remains visible with finite-value guidance; the document and points remain unchanged.
- `windows-automation-read-off.png`: the edited Hold point and retained curve with Read off and the manual-volume reference visible.

These are byte-exact copies of the [retained CI images](../../research/publication/windows-portability/application-run-40045765975/observation.json), selected for the preview.7 release. No editing or recompression was applied. Eleven images are byte-identical to preview.6; the automation editor's minimum-size capture differs only within the focused time-entry field. Both CPR PNGs have minimum alpha 254 and no pixels below 254; their independently recounted distributions match the retained diagnostics.

An independent peer reviewed all twelve images; the [root review](../../research/publication/windows-portability/application-run-40045765975/root-visual-review.json) spot-checked four actual states. These reviews accepted the scoped workspace and demonstrated actions. The interface remains substantially incomplete relative to the Windows reference. The automation editor is a separate selected-track window; it does not establish inline-lane or writing-mode fidelity. Both long-name captures are 1084 × 749: the requested 1400-DIP window remained constrained to 1100 DIP, so wider-desktop geometry remains unverified. A mistaken earlier root reading of the scrolled corner label was [explicitly corrected](../../research/publication/windows-portability/application-run-40021483751/root-visual-review-correction.json); the original image and review remain preserved.

Source/CPR inputs are authored controls excluded from the download. These images do not verify physical input, native dialogs, the operating-system frame or device audio. The hosted endpoint was unavailable, so they do not show the new rate-conversion status during playback. The native review contains one page; pagination is checked separately. Its observed error fits without scrolling. Prior preview captures remain in their immutable research records and release assets.

| File | Pixels | SHA-256 |
| --- | --- | --- |
| windows-arrangement.png | 1084 × 749 | `92837bc71574a1b95e4114e05f545fea9e38897ad25dcc095ea864f1c7885d7f` |
| windows-automation-invalid.png | 664 × 521 | `5408fd5a73fcc13cfebaebd8b422a8deb3e4b7968d9ad084d2b4755fdbb6d16f` |
| windows-automation-read-off.png | 664 × 521 | `7574078f4c9f7b99551202ec4cf43cabfc1274c9ab0c97e7b6e9bd8dfd06726d` |
| windows-automation.png | 664 × 521 | `cb15520067bed02bf435470857f4103aeac46941b30bc35dc0e5f578f3a96769` |
| windows-cpr-review-error.png | 634 × 441 | `4262f6bbe96ace30489893b705f4a82f28f01251535f790ff9409f9759e39b54` |
| windows-cpr-review.png | 814 × 611 | `e0a3943d8698f6132b752149f5fdfda7778e2d66a1925e31239943c510403ca0` |
| windows-long-names.png | 1084 × 749 | `386098c635f898c16dd14c34dabd1dd37fa32c9a95f5ea6dc4e593df11e223cb` |
| windows-resize-request.png | 1084 × 749 | `386098c635f898c16dd14c34dabd1dd37fa32c9a95f5ea6dc4e593df11e223cb` |
| windows-scrolled.png | 1084 × 749 | `f81d162a9a99b537d973d355c3445d5739c9806be3eaad16a97938907d471f07` |
| windows-source.png | 1084 × 749 | `8f46fd96682f1184139ae372443599eca8d585a8c67011b6ca8ac8c7a4eaaa69` |
| windows-workspace-expanded.png | 1084 × 749 | `fe749e25219e7d03aaa5839b5d927bb199f3f3889148a67f2c261ddab4ab7b09` |
| windows-workspace-normal.png | 1084 × 749 | `d6f02ff5491ec7cc2aac96b35544d45d44c2facfdba9c0dc8652a3134857bfd3` |
