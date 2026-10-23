"""Independent exact-rational callback arithmetic and bit-operation controls.

Derived from original 101f2c440 and bound Float32 adapter/helper instructions.
No candidate or proprietary executable is loaded.
"""
from fractions import Fraction
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
helper = HERE.parent / "APP010/native-rate-mode0-oracle.py"
assert hashlib.sha256(helper.read_bytes()).hexdigest() == "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
spec = importlib.util.spec_from_file_location("ieee", helper)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)


def raw64(value):
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def window(position, offset_bits, rate_bits, frames):
    offset, rate = ieee.value(offset_bits), ieee.value(rate_bits)
    rounded = ieee.rn(offset * rate + Fraction(1, 2))
    adjustment = int(rounded)  # Fraction int truncates toward zero.
    start = position + adjustment
    end = start + frames
    split = int(ieee.rn(ieee.rn(offset * rate) + Fraction(1, 2)))
    valid = all(-(1 << 63) <= x < (1 << 63) for x in (adjustment, start, end))
    return dict(position=position, offset_bits=f"{offset_bits:016x}", rate_bits=f"{rate_bits:016x}",
                frames=frames, valid=valid, adjustment=adjustment, start=start, end=end,
                split_adjustment=split, fma_discriminator=adjustment != split)


def postprocess(planes, frames, offset, prefix):
    sentinel = planes[0][frames - 1]
    exponent = sentinel & 0x7f800000
    action = 1 if exponent == 0 and sentinel & 0x7fffffff else (2 if exponent == 0x7f800000 else 0)
    output = [list(channel) for channel in planes]
    if action == 1:
        if any(bits & 0x7f800000 == 0x7f800000 for channel in planes for bits in channel[:frames]):
            return dict(valid=False, action=action)
        amplitude = ieee.sample_value(0x2edbe6ff)
        for channel in output:
            for index in range(frames):
                channel[index] = ieee.f32(ieee.sample_value(channel[index]) + (amplitude if index % 2 == 0 else -amplitude))
    elif action == 2:
        for channel in output:
            channel[:frames] = [0] * frames
    for channel in output:
        channel[offset:offset + prefix] = [0] * prefix
    return dict(valid=True, action=action, output_bits=[[f"{bits:08x}" for bits in p] for p in output])


def main():
    windows = []
    for rate in [1, 8000, 44100, 48000, 192000]:
        for product in [Fraction(-5, 2), Fraction(-3, 2), Fraction(-1, 2), Fraction(0),
                        Fraction(1, 2), Fraction(3, 2), Fraction(5, 2), Fraction(1023, 2)]:
            center = ieee.bits(product / rate)
            # Neighboring encodings expose the one-sided negative conversion.
            for encoded in sorted({center, center - 1 if center & 0x7fffffffffffffff else center,
                                   center + 1 if center & 0x7fffffffffffffff else center}):
                windows.append(window(12345, encoded, ieee.bits(rate), 257))
    random = 0x5a17c9e3
    discriminators = []
    for _ in range(10000):
        random = (1664525 * random + 1013904223) & 0xffffffff
        x = 0x4270000000000000 | (random << 10)
        row = window(0, x, ieee.bits(44100), 1)
        if row["fma_discriminator"]:
            discriminators.append(row)
            if len(discriminators) == 12:
                break
    assert discriminators
    windows.extend(discriminators)
    for position, offset, rate, frames in [
        ((1 << 63) - 2, 1, 1, 2), (-(1 << 63), -2, 1, 1),
        (0, 1 << 63, 1, 1), (0, -(1 << 63), 1, 1),
    ]:
        windows.append(window(position, ieee.bits(offset), ieee.bits(rate), frames))
    offsets = []
    for rate in [1, 8000, 44100, 48000, 192000]:
        for frame in [-(1 << 31), -129, -2, -1, 0, 1, 2, 129, (1 << 31) - 1]:
            reciprocal = ieee.rn(Fraction(1, rate))
            expected = ieee.rn(Fraction(frame) * reciprocal)
            offsets.append(dict(frames=frame, rate_bits=f"{ieee.bits(rate):016x}",
                                expected_bits=f"{ieee.bits(expected):016x}"))
    post = []
    sentinels = [0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x807fffff,
                 0x00800000, 0x3e800000, 0x7f800000, 0xff800000, 0x7fc12345, 0xff812345]
    for frames in [1, 2, 3, 15, 16, 17, 32, 33]:
        for sentinel in sentinels:
            channels = 2 if frames % 2 else 3
            planes = []
            for channel in range(channels):
                values = [ieee.f32(Fraction(((i * 17 + channel * 7) % 31) - 15, 64)) for i in range(frames)]
                planes.append(values + [0x3f123456] * 4)
            planes[0][frames - 1] = sentinel
            if sentinel in (0, 0x80000000, 0x00800000):
                # Nonfinite in another plane must not trigger first-plane gate.
                planes[-1][0] = 0x7fc31415
            offset, prefix = (frames - 1, 1) if frames % 2 else (1, min(frames, 3))
            post.append(dict(name=f"{frames}-{sentinel:08x}", frames=frames, capacity=frames + 4,
                offset=offset, prefix=prefix, input_bits=[[f"{bits:08x}" for bits in p] for p in planes],
                **postprocess(planes, frames, offset, prefix)))
    # The correction branch cannot safely accept NaN/Inf elsewhere.
    planes = [[0x3e800000, 1, 0x3f123456], [0x7fc31415, 0, 0x3f123456]]
    post.append(dict(name="dither-nonfinite-other-plane", frames=2, capacity=3, offset=0, prefix=0,
        input_bits=[[f"{bits:08x}" for bits in p] for p in planes], **postprocess(planes, 2, 0, 0)))
    prefix = []
    for transport in [0, 1, 2, -1]:
        for whole in [0, 1]:
            for boundary in [-99, 100, 101, 115, 116, 999]:
                expected = 0 if transport == 0 else (16 if whole else min(16, max(0, boundary - 100)))
                prefix.append(dict(start=100, end=116, transport=transport, whole=whole,
                                   boundary=boundary, expected=expected))
    output = dict(schema_version=1,
        source_scope="101f2c440 window/admission/postprocess with bound Float32 adapters and both alternating helper bodies; explicit supplied context only.",
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        arithmetic="Exact Fraction operations plus independent integer IEEE nearest/ties-even rounding; no candidate loaded.",
        windows=windows, offsets=offsets, postprocess=post, prefixes=prefix,
        limits=["No native scheduling, block partition, latency, device transport or source-event placement inferred.",
                "NaN payloads are retained only through bit-copy branches; correction with nonfinite other samples is a defensive unsupported domain.",
                "Overflow rejects rather than emulating saturation/wrap."])
    (HERE / "callback-adapter-oracle.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(dict(windows=len(windows), fma_discriminators=len(discriminators),
                          offsets=len(offsets), postprocess=len(post), prefixes=len(prefix))))


if __name__ == "__main__":
    main()
