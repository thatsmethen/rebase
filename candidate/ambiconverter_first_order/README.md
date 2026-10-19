# First-order AmbiConverter research candidate

This small C kernel transcribes one static path observed in the arm64 slice of
Reference AmbiConverter 1.5.10.152. It has **not been compared with a running
plug-in**, and is not a VST plug-in or a Reference reconstruction. Evidence and
conditions are recorded in
[`AMBI-DSP-002`](../../research/evidence/cpr-static/ambisonic/first-order-finding.json).

For a supplied finite normalized direction `p`, four planar input channels `x`,
and each sample index, the derived equations are:

| Direction | Output channels |
|---|---|
| `0 <= p < 0.5` | `(a*x0, x2, x3, x1)` |
| `0.5 <= p <= 1` | `(b*x0, x3, x1, x2)` |

The UI choices are registered in this order as “FuMa > AmbiX” and “AmbiX > FuMa”.
Channel numbers here refer to buffer indices. Spatial labels and host routing
have not been established by target execution.

| Sample type | `a` bit pattern | `b` bit pattern |
|---|---|---|
| IEEE binary32 | `0x3fb504f3` | `0x3f3504f3` |
| IEEE binary64 | `0x3ff6a09e667f3bcd` | `0x3fe6a09e667f3bcc` |

The reverse binary64 constant is one representable value below `sqrt(0.5)`.
The binary32 path first narrows the stored binary64 constants, as observed in
the target's `FCVT S,D` instruction. Constants are copied from integer bit
patterns; no math-library approximation generates them. In this first-order
subset, channel zero maps to itself and the other gains equal one, so combining
the copy and multiplication loops preserves the derived equations.

The public API in `ambi_first_order.h` accepts only:

- Four input and four output channels with the same positive frame count, at
  most `INT32_MAX`; the caller must provide valid storage for every declared
  region and descriptor. The selected API fixes the sample type.
- Eight mutually disjoint, naturally aligned sample regions. Corresponding
  in-place buffers, cross-channel aliases, and partial overlaps are rejected.
- An explicit direction value in `[0,1]`, `direction_present=1`, `bypass=0`, and
  `input_silence_flags=0`.
- Signed zero or normal samples with `2*MIN_NORMAL <= abs(x) <= 1`, where
  `MIN_NORMAL` belongs to the sample type. Integer bit checks reject every other
  sample before writing outputs. This conservative range keeps products normal
  and finite. Output magnitudes may exceed one, so the accepted input domain is
  not closed under conversion; no general round-trip claim is made.
- The current thread's `FE_TONEAREST` rounding mode. Build with the flags below.

All failure statuses leave output sample memory unchanged. These rejections
are candidate restrictions, not claims about how the original handles those
inputs. The kernel has no retained state, activation, parameter queue, bus
negotiation, silence propagation, metering, or bypass implementation.

Static evidence shows that the processor consumes the last point in each
direction queue before processing the block and does not use that point's
sample offset. Fresh algorithm allocation writes the first table pair; absent
a successful direction update, this consumer leaves existing tables unchanged.
Saved-state and broader lifecycle defaults remain outside the proven contract.
The target's corresponding-buffer alias branch stages all inputs, but this
candidate deliberately requires disjoint buffers. The target skips normal
conversion when any input silence flag is nonzero; that path is excluded.

Run the synthetic transcription checks on macOS with a C compiler and Python:

```sh
python3 candidate/ambiconverter_first_order/test_candidate.py
```

The tests compile into a temporary directory with C11, `-O2 -fno-fast-math
-ffp-contract=off -frounding-math`, exercise each channel basis vector, exact
coefficient bits, adjacent direction values around `0.5`, multiple frames,
domain boundaries, and rejection before output writes. The numeric oracle
uses exact rational multiplication and integer ties-to-even rounding.

Passing these tests demonstrates consistency with the transcribed static
rule. Actual vDSP library resolution, target FP control state, exceptional
values, activation and routing, and target sample outputs remain unvalidated.
