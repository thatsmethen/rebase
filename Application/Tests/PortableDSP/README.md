# Portable C arithmetic conformance

This lane compiles the existing authored C DSP kernels on qualified ARM64 and
x86-64 hosts. It is a portability check of bounded reconstructed value semantics.
It does not execute proprietary code, establish Windows target equivalence,
build the desktop application, or test an audio device.

## Build and run

Clang (including AppleClang), CMake 3.21 or later, and a C11 platform SDK are
required. Use Ninja on Windows from a configured Visual Studio developer shell:

```sh
cmake -S Application -B build-portable -G Ninja -DCMAKE_C_COMPILER=clang -DCMAKE_BUILD_TYPE=Release
cmake --build build-portable
ctest --test-dir build-portable --output-on-failure
build-portable/rebase_portable_dsp_tests --json portable-dsp-result.json
python3 Application/Tests/PortableDSP/generate_controls.py --check
```

The runner writes the same JSON to standard output and the optional `--json`
file. A failed assertion or an unsupported initial arithmetic environment causes
a nonzero exit. Debug and Release should both be exercised. The CMake targets
are `RebaseDSP`, `RebaseAmbiDSP`, `RebaseTimingDSP`, and
`rebase_portable_dsp_tests`. `REBASE_BUILD_SOXR=ON` additionally compiles the wrapper
against an existing pinned library supplied as `REBASE_SOXR_LIBRARY`; SoXR is off
by default because its separate build and dynamic-loading verification has its
own dependency requirements.

## Independent expectations

`controls.h` contains 5,422 numeric vectors projected from the published authored
analytical oracles. These include exact IEEE bit patterns, fused-operation and
Float32-narrowing discriminators, saturation/tie cases, overlap thresholds,
signed priorities, and invalid numerical domains. The original oracle authors
used independent integer/Fraction arithmetic or separate analytical models;
the portable generator does not call the implementation or recompute expected
arithmetic. It only selects numeric fields and serializes them.

`controls-manifest.json` pins the public source copies, generator, generated
header, and per-table counts. The public research records are preserved in place.
Regeneration is explicit; `--check` never writes files. Hand-computable controls
also cover existing tempo, PCM24, linear upsampling, ambisonic conversion/state,
and the serialized stereo ring. Those are bounded smoke controls, not exhaustive
qualification of every function in the compiled libraries.

## Floating-point admission

Six previously ARM64-only domains now use `rebase_fp_environment.h`: accessor
seek, accessor PCM24/gain, timeline builder, timeline reader, callback adaptation,
and track overlap normalization. Their numerical input bounds and operation
order are unchanged. Admission requires declared binary32/binary64 precision,
nearest/even rounding and gradual underflow. ARM64 additionally excludes
FZ/DN/AH/FIZ and enabled traps; x86-64 checks MXCSR rounding, FTZ, DAZ and all SSE
exception masks directly, independently of the C runtime's rounding query.
Unsupported states are rejected without repairing the caller's environment.

The runner changes each wrong rounding mode and individual hardware control in
turn, verifies rejection and byte-preserved outputs, then restores the original
environment. An unavailable hardware feature bit is counted explicitly rather
than treated as a passed rejection. For example, Rosetta can keep exception
traps masked after an attempted unmask; that test is unavailable there. A
translated macOS x86-64 result is explicitly recorded as translated and cannot
replace a native Windows result.

Strict compilation disables fast math and implicit FP contraction and enables
rounding-mode access. Explicit `fma` operations remain fused. Windows x64 builds
must exercise these same vectors and controls before the Windows lane is
qualified; compiling alone is insufficient.
