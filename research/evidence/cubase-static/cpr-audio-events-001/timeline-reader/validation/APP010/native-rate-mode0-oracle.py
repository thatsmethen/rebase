"""Independent integer/Fraction oracle for the bounded native mode0 recurrence.

No candidate kernel, target executable, host floating arithmetic, or resampling
library is used to compute expected bits. Each IEEE operation is rounded
separately to nearest/ties-even, with one rounding for the binary64 FMA.
"""
from fractions import Fraction
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent


def value(bits, precision=53, exponent_bits=11):
    fraction_bits = precision - 1
    sign = -1 if bits >> (fraction_bits + exponent_bits) else 1
    exponent = (bits >> fraction_bits) & ((1 << exponent_bits) - 1)
    fraction = bits & ((1 << fraction_bits) - 1)
    assert exponent != (1 << exponent_bits) - 1
    bias = (1 << (exponent_bits - 1)) - 1
    significand = fraction if exponent == 0 else fraction + (1 << fraction_bits)
    power = (1 - bias if exponent == 0 else exponent - bias) - fraction_bits
    return sign * Fraction(significand) * power_of_two(power)


def power_of_two(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def nearest_integer(number):
    whole, remainder = divmod(number.numerator, number.denominator)
    twice = remainder * 2
    return whole + int(twice > number.denominator or
                       (twice == number.denominator and whole & 1))


def bits(number, precision=53, exponent_bits=11):
    number = Fraction(number)
    if number == 0:
        return 0  # These controls do not require a negative-zero operation.
    negative = number < 0
    number = abs(number)
    exponent = number.numerator.bit_length() - number.denominator.bit_length()
    if number < power_of_two(exponent):
        exponent -= 1
    bias = (1 << (exponent_bits - 1)) - 1
    minimum = 1 - bias
    quantum = max(exponent, minimum) - (precision - 1)
    significand = nearest_integer(number / power_of_two(quantum))
    if significand == 1 << precision:
        significand >>= 1
        exponent += 1
    if significand < 1 << (precision - 1):
        encoded_exponent = 0
        fraction = significand
    else:
        encoded_exponent = max(exponent, minimum) + bias
        fraction = significand - (1 << (precision - 1))
    assert encoded_exponent < (1 << exponent_bits) - 1
    return ((int(negative) << (precision - 1 + exponent_bits)) |
            (encoded_exponent << (precision - 1)) | fraction)


def rn(number):
    return value(bits(number))


def f32(number):
    return bits(number, 24, 8)


def sample_value(encoded):
    return value(encoded, 24, 8)


def calculate(source_bits, output_bits, channels, samples):
    step = rn(sample_value(source_bits) / sample_value(output_bits))
    phase = Fraction(1)
    previous = [Fraction(0)] * channels
    output, unfused, distributed = [], [], []
    for index in range(0, len(samples), channels):
        current = [sample_value(x) for x in samples[index:index + channels]]
        while phase < 1:
            complement = rn(1 - phase)
            for old, new in zip(previous, current):
                product = rn(phase * new)
                output.append(f32(rn(complement * old + product)))
                # Deliberately incorrect alternatives challenge operation order.
                unfused.append(f32(rn(rn(complement * old) + product)))
                distributed.append(f32(rn(old + rn(phase * rn(new - old)))))
            phase = rn(step + phase)
        phase = rn(phase - 1)
        previous = current
    return dict(
        step_f64_bits=f"{bits(step):016x}",
        final_phase_f64_bits=f"{bits(phase):016x}",
        final_previous_f64_bits=[f"{bits(x):016x}" for x in previous],
        output_f32_bits=[f"{x:08x}" for x in output],
        output_frames=len(output) // channels,
        unfused_difference_indices=[i for i, (a, b) in enumerate(zip(output, unfused)) if a != b],
        distributed_difference_indices=[i for i, (a, b) in enumerate(zip(output, distributed)) if a != b],
        first_unfused_differences=[
            dict(index=i, correct=f"{output[i]:08x}", wrong=f"{unfused[i]:08x}")
            for i in range(len(output)) if output[i] != unfused[i]][:8],
        first_distributed_differences=[
            dict(index=i, correct=f"{output[i]:08x}", wrong=f"{distributed[i]:08x}")
            for i in range(len(output)) if output[i] != distributed[i]][:8])


def vector(name, source, output, channels, samples):
    encoded = [f32(x) for x in samples]
    return dict(name=name, source_rate_f32_bits=f"{f32(source):08x}",
                output_rate_f32_bits=f"{f32(output):08x}", channels=channels,
                input_f32_bits=[f"{x:08x}" for x in encoded],
                **calculate(f32(source), f32(output), channels, encoded))


def main():
    # Local rounding controls include ties, subnormals and significand carry.
    assert f32(1 + Fraction(1, 1 << 24)) == 0x3f800000
    assert f32(1 + Fraction(3, 1 << 24)) == 0x3f800002
    assert f32(Fraction(1, 1 << 150)) == 0
    assert f32(Fraction(3, 1 << 150)) == 2
    assert f32(2 - Fraction(1, 1 << 24)) == 0x40000000
    state = 0x5a17c9e3
    noise = []
    for _ in range(257 * 2):
        state = (1664525 * state + 1013904223) & 0xffffffff
        noise.append(Fraction((state >> 8) - (1 << 23), 1 << 24))
    boundary = []
    for frame in range(8195):
        boundary.extend([
            Fraction(1, 2) if frame in [0, 1, 8191, 8192, 8194] else Fraction(0),
            Fraction(-1, 4) if frame in [2, 8190, 8193] else Fraction(0)])
    vectors = [
        vector("empty", 44100, 48000, 2, []),
        vector("one-frame-is-history-only", 44100, 48000, 2, [Fraction(1, 2), Fraction(-1, 4)]),
        vector("two-frame-stereo-fma-cancellation", 44100, 48000, 2,
               [Fraction(-147, 256), Fraction(147, 512), Fraction(13, 256), Fraction(-13, 512)]),
        vector("stereo-channel-distinct-ramp", 44100, 48000, 2,
               [x for i in range(35) for x in (Fraction(i - 17, 64), Fraction(17 - 2 * i, 128))]),
        vector("mono-half-rate", 48000, 96000, 1, [Fraction((i % 5) - 2, 8) for i in range(39)]),
        vector("maximum-allowed-upsampling", 8000, 192000, 2,
               [x for i in range(11) for x in (Fraction(i, 32), Fraction(-i, 64))]),
        vector("adjacent-f32-rate-mantissa", sample_value(f32(44100) + 1), 48000, 2, noise),
        vector("seeded-noise-stereo", 44100, 48000, 2, noise),
        vector("8192-input-boundary-impulses", 44100, 48000, 2, boundary),
    ]
    assert any(v["unfused_difference_indices"] for v in vectors)
    assert any(v["distributed_difference_indices"] for v in vectors)
    document = dict(
        schema_version=1,
        scope="Exact analytical IEEE sample controls for the explicitly selected mode0 upsample recurrence; no target execution or runtime conformance.",
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        arithmetic="Float32 rates widened exactly; RN64 division; reset phase1/history0; RN64 complement/product then binary64 fused multiply-add, one Float32 store; separately rounded phase add/subtract.",
        zero_policy="Positive zero analytical controls only; no assertion about negative-zero preservation outside individually tested IEEE operations.",
        target_execution_count=0, vectors=vectors)
    destination = HERE / "native-rate-mode0-oracle.json"
    with destination.open("x") as stream:
        json.dump(document, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(vectors=len(vectors), output_samples=sum(len(v["output_f32_bits"]) for v in vectors),
                          fma_discriminators=sum(len(v["unfused_difference_indices"]) for v in vectors),
                          distributed_discriminators=sum(len(v["distributed_difference_indices"]) for v in vectors),
                          sha256=hashlib.sha256(destination.read_bytes()).hexdigest())))


if __name__ == "__main__":
    main()
