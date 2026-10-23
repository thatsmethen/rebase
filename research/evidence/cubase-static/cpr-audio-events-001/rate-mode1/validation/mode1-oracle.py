"""Independent native-instruction mode1 oracle; never loads candidate code.

Coefficient construction follows retained 10030a974 using Python binary64
operations and the host libSystem sin/sqrt primitives. This primitive choice
does not certify a historical/vendor libm. Tap FMAs and final Float32 rounding
are independently evaluated by exact Fraction/integer IEEE rounding.
"""
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import ctypes
import hashlib
import importlib.util
import json
import math
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
helper = HERE.parent / "APP010/native-rate-mode0-oracle.py"
assert hashlib.sha256(helper.read_bytes()).hexdigest() == "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
spec = importlib.util.spec_from_file_location("ieee", helper)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)
lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
lib.sin.argtypes = [ctypes.c_double]
lib.sin.restype = ctypes.c_double
lib.sqrt.argtypes = [ctypes.c_double]
lib.sqrt.restype = ctypes.c_double
lib.fma.argtypes = [ctypes.c_double] * 3
lib.fma.restype = ctypes.c_double


def raw(value):
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def double(bits):
    return struct.unpack("<d", struct.pack("<Q", bits))[0]


def encoded32(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def float32(bits):
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def digest64(values):
    return hashlib.sha256(b"".join(struct.pack("<d", x) for x in values)).hexdigest()


def exact_fma(x, y, z):
    # Pure exact arithmetic followed by precisely one nearest/ties-even round.
    return double(ieee.bits(Fraction(x) * Fraction(y) + Fraction(z)))


def i0_series(half_argument):
    term = total = order = 1.0
    epsilon = double(0x3B92E3B40A0E9B4F)
    while True:
        divisor = half_argument / order
        order = order + 1.0
        square = divisor * divisor
        term = term * square
        total = total + term
        if term < total * epsilon:
            return total


@lru_cache(None)
def tables(source_rate, output_rate):
    ratio = float(output_rate) / float(source_rate)
    cutoff = ratio * 0.5 if ratio < 1 else 0.5
    scale = ((cutoff + cutoff) * double(0x400921FB54442D18)) * double(0x3F60000000000000)
    inverse_i0 = 1.0 / i0_series(double(0x4011EB851EB851EC))
    beta = double(0x4021EB851EB851EC)
    table = [1.0]
    for index in range(1, 32769):
        argument = scale * float(index)
        sinc = lib.sin(argument) / argument
        radius = (1.0 / 32768.0) * float(index)
        root = lib.sqrt(lib.fma(-radius, radius, 1.0))
        window = i0_series((root * beta) * 0.5) * inverse_i0
        table.append(sinc * window)
    total = 0.0
    # Native unroll preserves this sequential sum of the 64 integer taps.
    for index in range(512, 32769, 512):
        total = total + table[index]
    normalization = 1.0 / lib.fma(total, 2.0, 1.0)
    table = [x * normalization for x in table]
    difference = [b - a for a, b in zip(table, table[1:])] + [-table[-1]]
    return table, difference


class Model:
    def __init__(self, source, output, channels, samples=True):
        self.ratio = float(output) / float(source)
        self.step = 512.0 / self.ratio
        self.phase = 0.0
        self.channels = channels
        self.capacity = 65536
        self.storage = [[0.0] * (self.capacity + 129) for _ in range(channels)] if samples else None
        self.fresh = True
        self.total_input = self.generated = self.returned = 0
        self.coefficients, self.differences = tables(source, output) if samples else (None, None)

    def reset(self):
        self.phase = 0.0
        self.fresh = True
        self.total_input = self.generated = self.returned = 0

    def snapshot(self):
        return dict(ratio_bits=f"{raw(self.ratio):016x}", step_bits=f"{raw(self.step):016x}",
                    phase_bits=f"{raw(self.phase):016x}", cumulative_input=self.total_input,
                    cumulative_generated=self.generated, total_returned=self.returned,
                    input_capacity=self.capacity, fresh=int(self.fresh))

    def process(self, frames, final, encoded=None):
        if frames > self.capacity:
            self.capacity = frames + 1024
            if self.storage is not None:
                self.storage = [[0.0] * (self.capacity + 129) for _ in range(self.channels)]
        beginning = 64 if self.fresh else 128
        if beginning + frames + (64 if final else 0) > self.capacity + 129:
            raise ValueError("native_write_bound")
        if self.storage is not None:
            assert encoded is not None and len(encoded) == frames * self.channels
            for channel, memory in enumerate(self.storage):
                if self.fresh:
                    first = float32(encoded[channel]) if frames else 0.0
                    memory[:64] = [first] * 64
                values = [float32(encoded[index * self.channels + channel]) for index in range(frames)]
                memory[beginning:beginning + frames] = values
                if final:
                    tail = values[-1] if values else 0.0
                    memory[beginning + frames:beginning + frames + 64] = [tail] * 64
        self.total_input += frames
        index = 64 if self.fresh else 0
        self.fresh = False
        limit = frames + (64 if final else 0)
        center = 64
        output = []
        generated = 0
        while True:
            while int(self.phase) >= 512 and index < limit:
                self.phase = self.phase + (-512.0)
                center += 1
                index += 1
            if index >= limit:
                break
            if self.storage is not None:
                if center - 63 < 0 or center + 64 >= self.capacity + 129:
                    raise ValueError("native_tap_bound")
                left = int(self.phase)
                fraction = self.phase - float(left)
                complement = 512.0 - self.phase
                right = int(complement)
                remainder = complement - float(right)
                for memory in self.storage:
                    accumulation = 0.0
                    for tap in range(64):
                        at = left + tap * 512
                        weight = exact_fma(fraction, self.differences[at], self.coefficients[at])
                        accumulation = exact_fma(memory[center - tap], weight, accumulation)
                    for tap in range(64):
                        at = right + tap * 512
                        weight = exact_fma(remainder, self.differences[at], self.coefficients[at])
                        accumulation = exact_fma(memory[center + tap + 1], weight, accumulation)
                    output.append(ieee.f32(Fraction(accumulation)))
            generated += 1
            self.phase = self.phase + self.step
        if self.storage is not None:
            # Native moves 128 doubles from current center−64 to storage0.
            for memory in self.storage:
                source = center - 64
                if source + 128 > len(memory):
                    raise ValueError("native_history_bound")
                memory[:128] = memory[source:source + 128]
        self.generated += generated
        returned = generated
        if final:
            ideal = int(float(self.total_input) * self.ratio)
            if ideal < self.generated:
                returned = max(0, generated + ideal - self.generated)
        self.returned += returned
        return dict(input_frames=frames, final=final, generated_frames=generated,
                    returned_frames=returned, output_f32_bits=[f"{x:08x}" for x in output[:returned * self.channels]],
                    snapshot=self.snapshot(),
                    storage_prefix_f64_bits=[[f"{raw(x):016x}" for x in channel[:256]] for channel in self.storage]
                    if self.storage is not None else [])


def pattern(count, channels, kind):
    result = []
    state = 0x5A17C9E3
    for frame in range(count):
        for channel in range(channels):
            state = (1664525 * state + 1013904223) & 0xffffffff
            if kind == "impulse":
                value = (1 if channel == 0 else -0.5) if frame in (0, 63, 64, count - 1) else 0
            elif kind == "ramp":
                value = ((frame * 7 + channel * 13) % 257 - 128) / 512
            elif kind == "alternate":
                value = (0.25 if (frame + channel) % 2 == 0 else -0.25)
            else:
                value = ((state >> 8) - (1 << 23)) / (1 << 24)
            result.append(encoded32(value))
    return result


def main():
    vectors = []
    scenarios = [
        (44100, 48000, 2, [129], "impulse", "positive"),
        (48000, 44100, 2, [129], "ramp", "positive"),
        (44100, 16000, 1, [193], "noise", "positive"),
        (44100, 44100, 2, [193], "impulse", "positive"),
        (8000, 192000, 1, [1], "alternate", "positive"),
        (192000, 8000, 2, [129], "ramp", "positive"),
        (44100, 48000, 1, [64, 65], "noise", "positive"),
        (44100, 48000, 1, [63, 66], "noise", "positive"),
        (44100, 48000, 1, [1, 128], "noise", "positive"),
        (44100, 48000, 1, [129], "noise", "null"),
        (48000, 44100, 2, [64, 0, 65], "alternate", "null"),
        (44100, 48000, 1, [0, 129], "ramp", "positive"),
        (44100, 48000, 1, [0], "noise", "positive"),
        (44100, 48000, 1, [193, -1, 1], "noise", "positive"),
    ]
    for number, (source, output, channels, partitions, kind, terminal) in enumerate(scenarios):
        model = Model(source, output, channels)
        values = pattern(sum(n for n in partitions if n > 0), channels, kind)
        position, calls = 0, []
        for index, count in enumerate(partitions):
            if count == -1:
                model.reset()
                calls.append(dict(reset=True, snapshot=model.snapshot()))
                continue
            data = values[position * channels:(position + count) * channels]
            position += count
            final = terminal == "positive" and index == len(partitions) - 1
            calls.append(dict(input_f32_bits=[f"{x:08x}" for x in data], **model.process(count, final, data)))
        if terminal == "null":
            calls.append(dict(input_f32_bits=[], **model.process(0, True, [])))
        vectors.append(dict(name=f"{number:02}-{source}-{output}-{channels}-{kind}-{terminal}",
                            source_rate=source, output_rate=output, channels=channels, calls=calls))
        print(f"completed {vectors[-1]['name']}", file=sys.stderr, flush=True)
    table_records = []
    for rates in sorted({(v["source_rate"], v["output_rate"]) for v in vectors}):
        coefficients, differences = tables(*rates)
        indices = sorted({0, 1, 2, 511, 512, 513, 1024, 8191, 16384, 32767, 32768})
        table_records.append(dict(source_rate=rates[0], output_rate=rates[1],
            coefficient_sha256_le=digest64(coefficients), difference_sha256_le=digest64(differences),
            indices=indices, coefficient_bits=[f"{raw(coefficients[i]):016x}" for i in indices],
            difference_bits=[f"{raw(differences[i]):016x}" for i in indices]))
    counts = []
    for output in [48000, 32000, 16000, 44100]:
        model = Model(44100, output, 2, samples=False)
        remaining, calls = 1058400, []
        while remaining:
            n = min(remaining, 8192)
            remaining -= n
            calls.append(model.process(n, not remaining))
        counts.append(dict(source_rate=44100, output_rate=output, source_frames=1058400,
                           block_frames=8192, total_returned=model.returned, calls=calls))
    result = dict(schema_version=1, scope="Independent instruction-ordered mathematical reconstruction, not target execution.",
        arithmetic="Binary64 operation order from original words; host libSystem sin/sqrt for coefficient primitives, exact Fraction/integer IEEE nearest-even tap FMA and Float32 narrowing.",
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
        vectors=vectors, tables=table_records, full_source_counts=counts,
        limitations=["No candidate library or proprietary executable is loaded.",
                     "Host libm coefficient primitive identity is an explicit context, not proof of vendor execution.",
                     "No mathematical ideal low-pass or partition invariance assumption; native history gaps/reset retention are retained.",
                     "Only visible returned samples are compared; native writes in discarded output tail are outside the candidate API."])
    (HERE / "mode1-oracle.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
