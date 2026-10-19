# AmbiConverter processing subset

This original C implementation follows reviewed static contracts AMBI-DSP-002,
AMBI-DSP-003 and AMBI-STATE-004. It is not a VST3 implementation and has not been
compared with an executing Reference component. The target code is never loaded.

The source is the arm64 slice with SHA-256
`e8341c6b31ac6b65cf7e8c18bdfbaa18ac24b20160b4287dc385b202eb29b883` under
`research/evidence/cpr-static/ambisonic`. The 388-byte table region at virtual
address `0x18d15c` has SHA-256
`c49accecf95f469477a7f57bcc31e6e35ff5d51ee1ff63479b9268bb5a3fc874`.
`first-order-finding.json`, `higher-order-finding.json`,
`higher-order-table-contract.json`, and `state-contract-finding.json` in that
directory, and the three corresponding review directories, contain derivations.

## Implemented contract

Configuration is 4, 9, or 16 planar channels, binary32 or binary64, one input bus
and one equal-sized output bus. Conversion scatters source channels through the
selected table, then multiplies each destination by its exact recovered gain.
Binary32 gains are explicit nearest-even narrowing of the recovered binary64
bits. In particular the reverse W binary64 gain is `0x3fe6a09e667f3bcc`, not the
usual rounded square root of one half. Higher-order directions are not assumed
to be mathematical inverses; the tests retain the observed nonidentity example.

Recognized parameter queues consume only the last point when its read succeeds:
ID 1 selects bypass for values greater than 0.5; ID 2 selects table B for values
greater than or equal to 0.5. Sample offsets are ignored by this recovered path.
Updates persist on zero-frame/no-input calls. Fresh local initialization uses
table A and bypass off; serialized target state is not implemented.

Bypass copies corresponding channels without arithmetic. Otherwise, any nonzero
input silence mask skips conversion and leaves output samples untouched. The
full input mask is copied unchanged on positive audio calls. High mask bits
model the observed branch, not a claim that such masks are valid host inputs.
Flagged input planes must contain only signed zero. The caller must interpret
`AMBIP_SILENCE_SKIPPED`; this kernel does not silently clear output buffers.

Exactly corresponding input/output plane aliases stage all inputs before
conversion. Cross-channel, partial, duplicate, and scratch overlaps are rejected.
Caller storage must be valid for every declared extent. Metadata cannot overlap
sample storage. Processing allocates nothing; configuration and scratch allocation
belong outside an audio callback. A state instance must not be used concurrently.

## Candidate restrictions

Normal conversion accepts signed zero or finite magnitudes between 8 times the
minimum normal and one eighth of the maximum finite value, inclusive, in the
selected precision. This conservative domain keeps all products normal/finite.
Normal conversion requires round-to-nearest-even and arm64 FPCR exactly zero,
or x86-64 default MXCSR controls (sticky exception flags ignored). Other host
architectures fail closed. These are explicit candidate restrictions, not
recovered Reference environment guarantees. Bypass/skip accept every finite bit
pattern, including subnormals, because they perform no sample arithmetic.

NaN/infinity, nonnormalized parameter values, empty recognized queues, unsupported
shapes, and unsupported aliases are rejected. Errors leave state, output samples,
flags and report unchanged. This safe rejection policy is original application
behavior; it is not a claim about the target's errors or malformed inputs.

## Verification

Run `python3 candidate/ambiconverter_processor/test_processor.py`. Add
`--output-dir NEW_DIRECTORY` to retain source snapshots, hashes and results.
The oracle independently reads the pinned Mach-O tables as data, then uses exact
rational products and IEEE nearest-even rounding. Tests cover basis vectors,
rounding/signs, all configurations, threshold neighbors, queue retention,
silence/bypass precedence, in-place staging, overlap rejection, domain endpoints,
and floating-point controls. Passing proves candidate agreement with this static
contract inside the declared domain, not native runtime parity.

## Application integration and remaining architecture

The file converter uses this implementation in blocks, supplies a direction
queue, disables bypass and supplies zero silence flags. It preserves stored
channel count and sample rate, uses binary64 for binary64 PCM sources and
binary32 for other decoded sources, and writes floating-point WAV. It does not
claim to preserve arbitrary container metadata or speaker-layout tags.
The output encoder writes IEEE-float RIFF bytes explicitly: a measured Core
Audio WAV write narrowed requested binary64 output to binary32. The integration
tests compare raw output bytes and reopen them through Core Audio. An integer
WAV sample rate and a conservative RIFF size limit are required before processing.

A future live insert needs an explicit channel-bus layout/precision descriptor,
an ordered insert chain before stereo monitoring, allocation during preparation,
and a policy for output-buffer initialization on silence skips. The current
stereo track renderer has none of that routing. This pass does not add it.

Known native anchors include process thunk `0x154464`, body `0x153d98`, parameter
consumer `0x1520d0`, bus arrangements `0x152824`, activation `0x153ba0`, and
binary32/binary64 normal routines `0x154d4c`/`0x154a8c`. Missing contracts include
serialized state and controller restoration, complete setup/latency/tail lifecycle,
meter publication (`0x15414c`/`0x1542d0` only partially understood), actual host
bus ordering and buffer initialization, target floating-point control state,
and dynamically bound DSP behavior. No unsupported native entrypoint is inferred
from a suggestive vtable position or filename.
