"""Independent exact-rational interpretation of the retained ARM64 downsample code.

This does not call the candidate, target executable, or a resampling library.
Each instruction's IEEE nearest/even rounding is performed with integer arithmetic.
Native out-of-block source accesses are rejected, never supplied invented padding.
"""
from fractions import Fraction
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / "APP010/native-rate-mode0-oracle.py"
HELPER_SHA = "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == HELPER_SHA
spec = importlib.util.spec_from_file_location("ieee_fraction", HELPER)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)
rn, bits, f32, val = ieee.rn, ieee.bits, ieee.f32, ieee.sample_value


class SourceBounds(Exception):
    pass


def state(source, output, channels):
    return dict(step=rn(val(source) / val(output)), phase=Fraction(1),
                history=[Fraction(0)] * channels, pending=False)


def encode_state(s):
    return dict(step_f64_bits=f"{bits(s['step']):016x}",
                phase_f64_bits=f"{bits(s['phase']):016x}",
                history_f64_bits=[f"{bits(x):016x}" for x in s["history"]],
                pending=s["pending"])


def process(s, encoded, channels, layout="above", variant="native"):
    """Return new state and bits for one block; source state is never changed.

    layout is the two disjoint address orderings at the native terminal compare.
    `variant` is only for negative arithmetic controls, never native expectations.
    """
    s = dict(s, history=list(s["history"]))
    if not encoded:
        return s, []
    assert len(encoded) % channels == 0
    samples = [[val(x) for x in encoded[i:i + channels]]
               for i in range(0, len(encoded), channels)]
    n = len(samples)
    out = []

    def read(i):
        if i < 0 or i >= n:
            raise SourceBounds(f"source frame {i} outside 0..{n - 1}")
        return samples[i]

    def emit(values):
        out.extend(f32(x) for x in values)

    def mix(old, new, phase):
        a = rn(1 - phase)
        result = []
        for x, y in zip(old, new):
            product = rn(phase * y)
            if variant == "unfused":
                result.append(rn(rn(a * x) + product))
            elif variant == "distributed":
                result.append(rn(x + rn(phase * rn(y - x))))
            else:
                result.append(rn(a * x + product))
        return result

    p = s["phase"]
    if s["step"] >= 2:
        if p < 0 and s["pending"]:
            old = [val(f32(x)) for x in s["history"]]
            current = read(0)
            if channels == 1:
                weight = rn(p + 1)
                # FMSUB is one rounding of product - phase*previous.
                mixed = [rn(rn(weight * current[0]) - p * old[0])]
            else:
                a = rn(1 - rn(p + 1))
                b = rn(1 - a)
                mixed = [rn(a * x + rn(b * y)) for x, y in zip(old, current)]
            emit(mixed)
            p = rn(s["step"] + p)
        index = p.numerator // p.denominator  # FCVTMS, not truncation
        while n - 1 > index:
            fraction = rn(p - index)
            emit(mix(read(index), read(index + 1), fraction))
            p = rn(s["step"] + p)
            index = p.numerator // p.denominator
        p = rn(p - n)
        s.update(phase=p, pending=p < 0, history=read(n - 1))
        return s, out

    delta = rn(s["step"] - 1)
    # Logical frame immediately before the next old sample. The assembly uses
    # input-4 for both channels; stereo then advances in eight-byte increments.
    cursor = -1
    remaining_input = n
    pending = False
    if p < 1 and s["pending"]:
        old = [val(f32(x)) for x in s["history"]]
        s["history"] = [val(f32(x)) for x in mix(old, read(0), p)]
        p = rn(p + delta)
        if p < 1:
            pending = True
        else:
            emit(s["history"])
            p = rn(p - 1)
            cursor = 0
            remaining_input -= 1
    last_skip = False
    if remaining_input >= 2:
        remaining_pairs = remaining_input - 1
        while True:
            if p < 1:
                while True:
                    mixed = mix(read(cursor + 1), read(cursor + 2), p)
                    if pending:
                        emit(s["history"])
                        s["history"] = mixed  # No intervening Float32 store.
                    else:
                        emit(mixed)
                    p = rn(delta + p)
                    cursor += 1
                    remaining_pairs -= 1
                    if p >= 1 or remaining_pairs == 0:
                        break
            last_skip = p >= 1
            if last_skip:
                p = rn(p - 1)
                cursor += 1
                remaining_pairs -= 1
                if pending:
                    emit(s["history"])
                    pending = False
            if remaining_pairs <= 0:
                break
    # For disjoint buffers, BELOW always passes and ABOVE always fails the
    # unsigned destination-cursor <= source-cursor comparison.
    if pending and layout == "below":
        emit(s["history"])
    if not last_skip:
        s["history"] = read(cursor + 1)
    s.update(phase=p, pending=not last_skip)
    return s, out


def vector(name, source, output, channels, values, partitions, layout="above",
           starting_state=None):
    encoded = [f32(x) for x in values]
    s = starting_state or state(f32(source), f32(output), channels)
    initial = encode_state(s)
    outputs = []
    calls = []
    at = 0
    for count in partitions:
        block = encoded[at * channels:(at + count) * channels]
        assert len(block) == count * channels
        try:
            after, result = process(s, block, channels, layout)
        except SourceBounds as error:
            calls.append(dict(input_frames=count, rejected_source_bounds=str(error),
                              state_before=encode_state(s)))
            break
        calls.append(dict(input_frames=count, output_frames=len(result) // channels,
                          state_after=encode_state(after)))
        outputs.extend(result)
        s = after
        at += count
    else:
        assert at * channels == len(encoded)
    return dict(name=name, source_rate_f32_bits=f"{f32(source):08x}",
                output_rate_f32_bits=f"{f32(output):08x}", channels=channels,
                layout=layout, initial_state=initial,
                input_f32_bits=[f"{x:08x}" for x in encoded], calls=calls,
                output_f32_bits=[f"{x:08x}" for x in outputs],
                final_state=encode_state(s))


def main():
    ramp = [Fraction((i * 17) % 97 - 48, 64) for i in range(256)]
    stereo = [x for a in ramp for x in (a, -a / 2)]
    vectors = []
    for source, output in [(48000, 44100), (88200, 48000), (48000, 48000),
                           (96000, 48000), (192000, 44100), (192000, 8000)]:
        for channels in [1, 2]:
            values = ramp[:35] if channels == 1 else stereo[:70]
            for partitions in [[35], [7] * 5, [2, 3, 5, 11, 14], [1] * 35]:
                for layout in ["above", "below"]:
                    name = f"{source}-{output}-c{channels}-{layout}-" + "-".join(map(str, partitions))
                    vectors.append(vector(name, source, output, channels, values, partitions, layout))
    for channels in [1, 2]:
        source, output = 88200, 48000
        s = state(f32(source), f32(output), channels)
        s.update(phase=Fraction(3, 4), pending=True,
                 history=[Fraction(-1, 2)] * channels)
        vectors.append(vector(f"pending-one-frame-lookahead-c{channels}", source, output,
                              channels, [Fraction(1, 4)] * channels, [1], starting_state=s))
        vectors.append(vector(f"zero-input-preserves-pending-c{channels}", source, output,
                              channels, [], [0], starting_state=s))
    # Integer rates represented by adjacent Float32 mantissas test exact ratio.
    adjacent = val(f32(48000) + 1)
    vectors.append(vector("adjacent-rate-boundary-stereo", adjacent, 44100, 2,
                          stereo, [31, 17, 0, 91, 117]))
    for channels in [1, 2]:
        s = state(f32(48000), f32(44100), channels)
        s.update(phase=rn(Fraction(147, 160)), pending=True,
                 history=[Fraction(-147, 256)] * channels)
        vectors.append(vector(f"fused-pending-cancellation-c{channels}", 48000, 44100,
                              channels, [Fraction(13, 256)] * channels * 2, [2],
                              starting_state=s))
        s = state(f32(192000), f32(44100), channels)
        s.update(phase=-Fraction(1, 1 << 54), pending=True,
                 history=[Fraction(1)] * channels)
        vectors.append(vector(f"mono-stereo-carry-rounding-c{channels}", 192000, 44100,
                              channels, [Fraction(0)] * channels * 2, [2],
                              starting_state=s))
    differences = []
    for v in vectors:
        if not v["name"].startswith("fused-pending"):
            continue
        initial = v["initial_state"]
        s = dict(step=ieee.value(int(initial["step_f64_bits"], 16)),
                 phase=ieee.value(int(initial["phase_f64_bits"], 16)),
                 history=[ieee.value(int(x, 16)) for x in initial["history_f64_bits"]],
                 pending=initial["pending"])
        source = [int(x, 16) for x in v["input_f32_bits"]]
        for variant in ["unfused", "distributed"]:
            _, wrong = process(s, source, v["channels"], v["layout"], variant)
            for i, (correct, bad) in enumerate(zip(v["output_f32_bits"], wrong)):
                if int(correct, 16) != bad:
                    differences.append(dict(vector=v["name"], variant=variant, index=i,
                                            correct=correct, wrong=f"{bad:08x}"))
    assert len(differences) >= 4
    large = []
    for source, output in [(48000, 44100), (48000, 32000), (96000, 44100)]:
        for n in [8193, 16385, 24577]:
            values = [x for i in range(n)
                      for x in (Fraction(i % 127 - 63, 128),
                                Fraction((i * 17) % 131 - 65, 256))]
            conventional = [8192] * (n // 8192) + [n % 8192]
            safe, remaining = [], n
            while remaining:
                take = 8191 if remaining == 8193 else min(remaining, 8192)
                safe.append(take)
                remaining -= take
            for label, partitions in [("fixed8192", conventional), ("avoid-singleton", safe)]:
                v = vector(f"{source}-{output}-{n}-{label}", source, output, 2,
                           values, partitions)
                input_bytes = b"".join(int(x, 16).to_bytes(4, "little") for x in v.pop("input_f32_bits"))
                output_bits = v.pop("output_f32_bits")
                output_bytes = b"".join(int(x, 16).to_bytes(4, "little") for x in output_bits)
                v.update(input_frames=n, output_frames=len(output_bits) // 2,
                         pattern="L=(i%127-63)/128,R=((i*17)%131-65)/256",
                         input_f32le_sha256=hashlib.sha256(input_bytes).hexdigest(),
                         output_f32le_sha256=hashlib.sha256(output_bytes).hexdigest(),
                         suffix_f32le_sha256={str(k): hashlib.sha256(output_bytes[k * 8:]).hexdigest()
                                              for k in sorted({0, 1, len(output_bits) // 4,
                                                               max(0, len(output_bits) // 2 - 1),
                                                               len(output_bits) // 2})})
                large.append(v)
    doc = dict(schema_version=1, generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               arithmetic_helper=dict(path=str(HELPER.relative_to(HERE.parent.parent.parent.parent)),
                                      sha256=HELPER_SHA),
               scope="Original-instruction analytical downsample/equal-rate controls, not target runtime comparison.",
               zero_sign_limit="Fraction controls use positive exact zero; signed-zero preservation is tested separately if asserted.",
               flush="W4 is unreferenced on the captured mono/stereo paths; zero input returns before state mutation.",
               source_bounds="Out-of-block reads are unsupported; no lookahead or final padding is fabricated.",
               target_execution_count=0, arithmetic_discriminators=differences,
               vectors=vectors, large_partition_vectors=large)
    destination = HERE / "native-rate-down-oracle.json"
    with destination.open("x") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print(json.dumps(dict(vectors=len(vectors),
                          rejected=sum(any("rejected_source_bounds" in c for c in v["calls"]) for v in vectors),
                          sha256=hashlib.sha256(destination.read_bytes()).hexdigest())))


if __name__ == "__main__":
    main()
