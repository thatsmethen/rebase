# Rebase screenshots

## macOS 0.21.0

Actual window captures from the arm64 release build, version 0.21.0 (21), on 2026-10-23. The arrangement contains four tracks and eleven clips of newly synthesized audio in a native Rebase project. It demonstrates the ordinary arrangement and automation interface, not imported reference-project fidelity.

- `arrangement.jpg`: the eight-bar, 96 BPM session with track waveforms, inspector and mixer.
- `automation.jpg`: the pad track's volume automation editor.
- `about.jpg`: application icon and version panel.

No personal documents, local filesystem dialogs or desktop content are included. Ancillary image metadata was removed without recompressing the captured image. The release executable SHA-256 is `6f22e14e301d15a6c3c418c828b9a791d41bb2330aec727f6c6b46808af2bd13`.

## Windows 0.21.1 development preview 5

Actual WPF client-area renders from the opened application at commit `5dd3beb2538024a85143af984105fe6d2daea943`, captured by [native run 40033023717](https://github.com/thatsmethen/rebase/actions/runs/40033023717). The seven main-window images are 1084 × 749 pixels. CPR review is 814 × 611; its minimum-size error state is 634 × 441. All captures use 96 DPI and exclude the operating-system frame.

- `windows-arrangement.png`: the four-track, eleven-clip example in Compact density with real waveforms, Channel/Inspector, musical ruler, mixer and transport.
- `windows-workspace-normal.png`: the same example in Normal density; all four rows fit.
- `windows-workspace-expanded.png`: the arrangement after hiding the left panels and lower mixer.
- `windows-source.png`: the canonical authored single-source fixture after PCM24 attachment and checked export.
- `windows-scrolled.png`: the example at 100 pixels per second, horizontally scrolled 368 pixels. Track headers and ruler corner remain fixed.
- `windows-long-names.png`: long authored project/event names retain their allocated fields.
- `windows-resize-request.png`: the same scenario after a wider-window request constrained by the hosted display.
- `windows-cpr-review.png`: authored CPR review with preserved-source identity and complete navigation/import controls.
- `windows-cpr-review-error.png`: minimum-size review with the observed error message and all four footer controls visible.

These are byte-exact copies of the [retained CI images](../../research/publication/windows-portability/application-run-40033023717/observation.json) and preview.5 assets. No editing or recompression was applied. Both CPR PNGs have minimum alpha 254 and no pixels below 254; their independently recounted distributions match the retained diagnostics.

Root and independent review accepted the scoped workspace and demonstrated actions. The interface remains substantially incomplete relative to the Windows reference. The compact top-row stack and expanded row dividers are covered by this slice. Both long-name captures are 1084 × 749: the requested wider window was constrained by the hosted display, so wider-desktop geometry remains unverified. A mistaken root reading of the scrolled corner label was [explicitly corrected](../../research/publication/windows-portability/application-run-40021483751/root-visual-review-correction.json); the original image and review remain preserved.

Source/CPR inputs are authored controls excluded from the download. These images do not verify physical input, native dialogs, the operating-system frame or device audio. The native review contains one page; pagination is checked separately. Its observed error fits without scrolling. Prior preview captures remain in their immutable research records and release assets.

| File | Pixels | SHA-256 |
| --- | --- | --- |
| windows-arrangement.png | 1084 × 749 | `e291059861ed8a5bb4839fe10b3f3bbf1c758e89ca987fab9de6ca982d6d7865` |
| windows-cpr-review-error.png | 634 × 441 | `4262f6bbe96ace30489893b705f4a82f28f01251535f790ff9409f9759e39b54` |
| windows-cpr-review.png | 814 × 611 | `e0a3943d8698f6132b752149f5fdfda7778e2d66a1925e31239943c510403ca0` |
| windows-long-names.png | 1084 × 749 | `f80127e7a04c8e22ec98a918e7055ff9a79cbdc50f3eb7850504f876c4a3cc02` |
| windows-resize-request.png | 1084 × 749 | `f80127e7a04c8e22ec98a918e7055ff9a79cbdc50f3eb7850504f876c4a3cc02` |
| windows-scrolled.png | 1084 × 749 | `38cc43a487102cd0dae0d475a073dcdb04c8aa815216d7abc2b50e68016001cb` |
| windows-source.png | 1084 × 749 | `76df2fbbd5f2c1ef3ab5cad61bc6d34963152e54733333c8d4c80ff2012e63d0` |
| windows-workspace-expanded.png | 1084 × 749 | `0e484275d8ba289c6c8b877ee4bc017b2b33ad7bc4ec29a98c8ef607ee921c55` |
| windows-workspace-normal.png | 1084 × 749 | `4b6351290af963424e9147762c4aea02d6a5d3c6cd2ead51304704f25a17bbca` |
