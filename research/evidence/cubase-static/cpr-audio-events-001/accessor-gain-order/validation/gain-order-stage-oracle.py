"""Independent signed Float32 gain/PCM24 stage controls, not target execution.

Exact Fraction/integer rounding models three native candidate orders. No C or
Swift implementation is imported. Equal-rate scalar/SIMD decoder agreement has
a proof-qualified domain; rows below it deliberately discriminate the paths.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IEEE = HERE.parent / "APP010/native-rate-mode0-oracle.py"
FORMAT = HERE.parent / "APP016/accessor-pcm24-oracle.py"
ieee = load("gain_ieee", IEEE)
packed = load("gain_packed", FORMAT)


def record(path):
    raw = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def multiply(a, b):
    result = ieee.f32(ieee.sample_value(a) * ieee.sample_value(b))
    if result & 0x7fffffff == 0:
        result = ((a ^ b) >> 31) << 31
    return result


def equal_paths(integer, gain):
    decoded = ieee.f32(F(integer, 1 << 23))
    scalar_scale = multiply(gain, 0x34000000)
    vector_scale = multiply(gain, 0x30000000)
    return dict(integer=integer, gain_bits=f"{gain:08x}",
                decoded_bits=f"{decoded:08x}", scalar_scale_bits=f"{scalar_scale:08x}",
                vector_scale_bits=f"{vector_scale:08x}",
                scalar_bits=f"{multiply(ieee.f32(integer), scalar_scale):08x}",
                vector_bits=f"{multiply(ieee.f32(integer << 8), vector_scale):08x}",
                separate_bits=f"{multiply(decoded, gain):08x}")


def main():
    integers = sorted(set([-8388608, -8388607, -4194305, -257, -3, -2, -1, 0,
                           1, 2, 3, 255, 257, 4194303, 4194305, 8388606, 8388607] +
                          [((n * 104729) % 16777216) - 8388608 for n in range(128)]))
    accepted_gains = [0, 0x80000000, 0x10000000, 0x10000001, 0x18012345,
                      0x3e99999a, 0x3f400000, 0x3f800000, 0x3fa66666, 0x40000000,
                      0x4b123457, 0x7f7fffff]
    accepted_gains += [g | 0x80000000 for g in accepted_gains if g & 0x7fffffff]
    equal = [equal_paths(n, g) for g in accepted_gains for n in integers]
    assert all(r["scalar_bits"] == r["vector_bits"] == r["separate_bits"] for r in equal)
    rejected = [equal_paths(n, g) for g in [0x0fffffff, 0x0ffffffe, 0x0f800001,
                0x0e123457, 0x08000001, 0x00800001] for n in integers]
    discriminators = [r for r in rejected if len({r["scalar_bits"], r["vector_bits"], r["separate_bits"]}) > 1]
    # Filter output is Float32 and need not lie on the signed24 lattice. These
    # rows isolate the post-filter Q24/gain order, not a whole resampler model.
    inputs = [0, 0x80000000, 0x33800000, 0x33c00000, 0x34200000,
              0x3eaaaaab, 0x3f000001, 0x3f7fffff, 0x3f800001,
              0xbf800001, 0xbeaaaaab, 0xb3800000]
    stage = []
    for x in inputs:
        for g in [0, 0x80000000, 0x3e99999a, 0x3f400000, 0x3fa66666,
                  0x40000000, 0xbe99999a, 0xbfa66666]:
            q = int(packed.project(x)["output_f32_bits"], 16)
            gained = multiply(x, g)
            wrong = int(packed.project(gained)["output_f32_bits"], 16)
            expected = multiply(q, g)
            stage.append(dict(filter_output_bits=f"{x:08x}", gain_bits=f"{g:08x}",
                              q24_then_gain_bits=f"{expected:08x}",
                              gain_then_q24_bits=f"{wrong:08x}",
                              gain_without_q24_bits=f"{gained:08x}"))
    report = dict(schema_version=1, target_executions=0, candidate_expected_calls=0,
        inputs=[record(Path(__file__)), record(IEEE), record(FORMAT)],
        scope="Independent stage arithmetic; no selected backend, resampler state or hosted gain inference.",
        proof=dict(domain="Gain is signed zero, or finite Float32 with magnitude >=2^-95; decoded source is an exact signed24 integer.",
            reasoning=[
                "Multiplying admitted nonzero gain by 2^-31 remains normal and exact, as does multiplication by 2^-23.",
                "Every signed24 integer and its exact left shift by8 are representable in Float32.",
                "Both paths therefore present the same exact real product integer*gain/2^23 to one Float32 rounding; decoded-Float32 then gain presents that same product.",
                "Signed zero follows XOR of operand sign bits; integer zero is positive in both decoders. The tests retain these bits.",
                "This proof excludes subnormal scaled gain, altered FP modes and other format/layout branches. Signed32 overflow is not used; integer<<8 lies in signed32 range."
            ]),
        equal_rate_vectors=equal, below_bound_discriminators=discriminators,
        downsample_stage_vectors=stage,
        counts=dict(equal_rate_vectors=len(equal), below_bound_discriminators=len(discriminators),
                    downsample_stage_vectors=len(stage),
                    q24_gain_order_discriminators=sum(r["q24_then_gain_bits"] != r["gain_then_q24_bits"] for r in stage),
                    missing_q24_discriminators=sum(r["q24_then_gain_bits"] != r["gain_without_q24_bits"] for r in stage)))
    destination = HERE / "gain-order-stage-oracle.json"
    with destination.open("x") as output:
        json.dump(report, output, indent=2); output.write("\n")
    print(json.dumps(dict(**report["counts"], output=record(destination))))


if __name__ == "__main__":
    main()
