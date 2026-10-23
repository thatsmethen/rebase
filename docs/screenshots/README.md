# Rebase screenshots

## macOS 0.21.0

Actual window captures from the arm64 release build, version 0.21.0 (21), on 2026-10-23. The arrangement contains four tracks and eleven clips of newly synthesized audio in a native Rebase project. It demonstrates the ordinary arrangement and automation interface, not imported reference-project fidelity.

- `arrangement.jpg`: the eight-bar, 96 BPM session with track waveforms, inspector and mixer.
- `automation.jpg`: the pad track's volume automation editor.
- `about.jpg`: application icon and version panel.

No personal documents, local filesystem dialogs or desktop content are included. Ancillary image metadata was removed without recompressing the captured image. The release executable SHA-256 is `6f22e14e301d15a6c3c418c828b9a791d41bb2330aec727f6c6b46808af2bd13`.


## Windows 0.21.1 development preview 1

Actual WPF client-area renders from the opened Windows application at commit `6a6f4d4077fd817574d7f2756e3f060d693f35b5`, captured by [native run 39939758507](https://github.com/thatsmethen/rebase/actions/runs/39939758507) on 2026-10-23. Each image is 1084 × 749 pixels at 96 DPI. The application window's outer bounds were 1100 × 788; the PNGs exclude the operating-system frame.

- `windows-arrangement.png`: four tracks and eleven example clips with source waveforms, an editable inspector, the shared bars/beats ruler, mixer and bottom transport.
- `windows-source.png`: the authored source-event fixture after explicit PCM24 attachment and checked export. This synthetic fixture validates the implemented path; it is not a reference-project capture and is not shipped in the download.
- `windows-scrolled.png`: the example at 100 pixels per second, horizontally scrolled 358 pixels. Track headers remain fixed while events and ruler move.

These are byte-exact copies of the retained [CI image artifacts](../../research/publication/windows-portability/application-run-39939758507/observation.json), with no image editing. Root and independent visual review found the captured states readable and the previously observed selector/header defects corrected. They do not establish pixel-identical reference fidelity, physical input, native dialogs or audio-device playback.

| File | SHA-256 |
| --- | --- |
| windows-arrangement.png | `ee2cbbd9b28353161061669ae8531e4151f9c53708948e02594bf599b081f382` |
| windows-source.png | `b9e36fe83733476faf1f980bf5588b7572b377f728b96c96a03d6898bf0a3d93` |
| windows-scrolled.png | `cebafe0a54dfd53f50cdb2c9062f4fbf12394bd3dc465e6f47e2cae7cc66d304` |
