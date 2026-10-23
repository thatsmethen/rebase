# Rebase screenshots

## macOS 0.21.0

Actual window captures from the arm64 release build, version 0.21.0 (21), on 2026-10-23. The arrangement contains four tracks and eleven clips of newly synthesized audio in a native Rebase project. It demonstrates the ordinary arrangement and automation interface, not imported reference-project fidelity.

- `arrangement.jpg`: the eight-bar, 96 BPM session with track waveforms, inspector and mixer.
- `automation.jpg`: the pad track's volume automation editor.
- `about.jpg`: application icon and version panel.

No personal documents, local filesystem dialogs or desktop content are included. Ancillary image metadata was removed without recompressing the captured image. The release executable SHA-256 is `6f22e14e301d15a6c3c418c828b9a791d41bb2330aec727f6c6b46808af2bd13`.

## Windows 0.21.1 development preview 3

Actual WPF client-area renders from the opened application at commit `aaa7c3c6c88cdaacf029d136f654b1f81bfec201`, captured by [native run 39966842279](https://github.com/thatsmethen/rebase/actions/runs/39966842279). The main, source and scroll images are 1084 × 749 pixels. CPR review is 814 × 611; its minimum-size error state is 634 × 441. All captures use 96 DPI and exclude the operating-system frame.

- `windows-arrangement.png`: the four-track, eleven-clip example with real waveforms, Channel/Inspector, compact controls, shared bars/beats ruler, mixer and bottom transport.
- `windows-source.png`: the authored source-event fixture after explicit PCM24 attachment and checked export.
- `windows-scrolled.png`: the example at 100 pixels per second, horizontally scrolled 368 pixels. Track headers remain fixed while the events and ruler move.
- `windows-cpr-review.png`: the authored CPR review with recovered data, preserved-source identity and complete navigation/import controls.
- `windows-cpr-review-error.png`: the review at minimum window size with the observed error message and all four footer controls visible.

These are byte-exact copies of the [retained CI images](../../research/publication/windows-portability/application-run-39966842279/observation.json) and preview.3 release assets. No image editing or recompression was applied. Both CPR PNGs have minimum alpha 254 and no pixels below 254; their independently recounted distributions and PNG hashes match the retained diagnostics.

Root and independent visual review accepted the scoped readability and demonstrated actions. The window still differs substantially from the reference layout. The two source/CPR fixtures are authored controls and are not included in the download. These captures do not verify physical input, native file dialogs, the operating-system frame or audio-device playback. The native review contains one page; longer-page and bounds controls are recorded separately. The observed minimum-size error fits without scrolling; this run did not exercise error scrolling.

| File | Pixels | SHA-256 |
| --- | --- | --- |
| windows-arrangement.png | 1084 × 749 | `8845bf6b3ad845c64987243f0c6683f4da9d89850b4e259c0034a8b8e48c34ff` |
| windows-source.png | 1084 × 749 | `0429783bac6bb03d825b7ebbce0c47d259ca3f25868ba6fdbeedc4be89d1d6d3` |
| windows-scrolled.png | 1084 × 749 | `3d51582ab3fab7767952fe2632e3aeb50049c8a8c914e7bea113c827c27cf9d7` |
| windows-cpr-review.png | 814 × 611 | `e0a3943d8698f6132b752149f5fdfda7778e2d66a1925e31239943c510403ca0` |
| windows-cpr-review-error.png | 634 × 441 | `4262f6bbe96ace30489893b705f4a82f28f01251535f790ff9409f9759e39b54` |
