# Rebase Preview example beat

A 20-second, 96 BPM example with four tracks and eleven clips: rhythm, warm pad, round bass, and glass melody. All four stereo WAV files are synthesized at 48 kHz, 16-bit PCM. This is the same arrangement and audio shown in the release screenshots.

In the macOS app, choose **File → Open Example Beat** to open an editable copy. The project package also works with **File → Open**.

## Audio permission and provenance

The example music, arrangement, and audio were newly authored for Rebase using the included synthesizer script. They use oscillators and seeded noise, with no sampled recordings or external media. The example is included for playback, editing and experimentation in Rebase. It does not change the licenses or permissions for application code, dependencies, or research records.

`example.json` records the exact shipped project file hashes, WAV properties, and clip-bound validation. The shipped files are byte-identical to the original screenshot example.

## Re-create the example

Python 3 and its standard library are sufficient:

```sh
python3 Application/Examples/generate_demo.py /tmp/Rebase-Preview-copy.rebaseproj
```

The output directory must not already exist. The seed and UUID namespace are fixed, and WAV samples are written explicitly in little-endian order. The original math and arrangement are preserved. A `demo-validation.json` file is written next to the generated project; compare its file hashes with `example.json` to verify a re-creation on your Python and platform.
