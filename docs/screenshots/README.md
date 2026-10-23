# Rebase screenshots

## macOS 0.21.0

Actual window captures from the arm64 release build, version 0.21.0 (21), on 2026-10-23. The arrangement contains four tracks and eleven clips of newly synthesized audio in a native Rebase project. It demonstrates the ordinary arrangement and automation interface, not imported reference-project fidelity.

- `arrangement.jpg`: the eight-bar, 96 BPM session with track waveforms, inspector and mixer.
- `automation.jpg`: the pad track's volume automation editor.
- `about.jpg`: application icon and version panel.

No personal documents, local filesystem dialogs or desktop content are included. Ancillary image metadata was removed without recompressing the captured image. The release executable SHA-256 is `6f22e14e301d15a6c3c418c828b9a791d41bb2330aec727f6c6b46808af2bd13`.

## Windows 0.21.1 development preview 4

Actual WPF client-area renders from the opened application at commit `62893430f8394a5c1b8274d3a6273dddd4fa6653`, captured by [native run 40021483751](https://github.com/thatsmethen/rebase/actions/runs/40021483751). The five main-window images are 1084 × 749 pixels. CPR review is 814 × 611; its minimum-size error state is 634 × 441. All captures use 96 DPI and exclude the operating-system frame.

- `windows-arrangement.png`: the four-track, eleven-clip example in Compact density with real waveforms, Channel/Inspector, musical ruler, mixer and transport.
- `windows-workspace-normal.png`: the same example in Normal density; all four rows fit.
- `windows-workspace-expanded.png`: the arrangement after hiding the left panels and lower mixer.
- `windows-source.png`: the canonical authored single-source fixture after PCM24 attachment and checked export.
- `windows-scrolled.png`: the example at 100 pixels per second, horizontally scrolled 368 pixels. Track headers and ruler corner remain fixed.
- `windows-cpr-review.png`: authored CPR review with preserved-source identity and complete navigation/import controls.
- `windows-cpr-review-error.png`: minimum-size review with the observed error message and all four footer controls visible.

These are byte-exact copies of the [retained CI images](../../research/publication/windows-portability/application-run-40021483751/observation.json) and preview.4 assets. No editing or recompression was applied. Both CPR PNGs have minimum alpha 254 and no pixels below 254; their independently recounted distributions match the retained diagnostics.

Root and independent review accepted the scoped workspace and demonstrated actions. The interface remains substantially incomplete relative to the Windows reference. Expanded row-divider strokes still end at their previous canvas width, and top-row density remains follow-up work. A mistaken root reading of the scrolled corner label was [explicitly corrected](../../research/publication/windows-portability/application-run-40021483751/root-visual-review-correction.json); the original image and review remain preserved.

Source/CPR inputs are authored controls excluded from the download. These images do not verify physical input, native dialogs, the operating-system frame or device audio. The native review contains one page; pagination is checked separately. Its observed error fits without scrolling. Prior preview captures remain in their immutable research records and release assets.

| File | Pixels | SHA-256 |
| --- | --- | --- |
| windows-arrangement.png | 1084 × 749 | `5befe4b5fb241a0db1d36f68a51bcf580717b98c5b15d1ec5ac76119de3a31e1` |
| windows-source.png | 1084 × 749 | `c215374cfbb92cccf3eb758e8119d4363347d714eb8c9357dbc3faa684f4a304` |
| windows-scrolled.png | 1084 × 749 | `a9e3bada05d45877cc68ac964593ab45dae0a3404561b978758e28ec1ff6cd77` |
| windows-cpr-review.png | 814 × 611 | `e0a3943d8698f6132b752149f5fdfda7778e2d66a1925e31239943c510403ca0` |
| windows-cpr-review-error.png | 634 × 441 | `4262f6bbe96ace30489893b705f4a82f28f01251535f790ff9409f9759e39b54` |
| windows-workspace-normal.png | 1084 × 749 | `9db317443eeda033af403c9a7f94a45fe87aa3538c67fabc640708078b63c3fe` |
| windows-workspace-expanded.png | 1084 × 749 | `c637e3b40e87899b9e90458e84a79bc0073d7ab3b068e3359d2a325bfb195652` |
