"""Independent value controls for the native ordinary timeline reader.

Original instructions, not a candidate kernel, define the arithmetic below.
The public input domain and output records will be checked separately by tests.
All expected floating operations use exact Fraction/integer IEEE rounding.
"""
from fractions import Fraction
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
helper = HERE.parent / "APP010/native-rate-mode0-oracle.py"
assert hashlib.sha256(helper.read_bytes()).hexdigest() == (
    "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
)
spec = importlib.util.spec_from_file_location("ieee", helper)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)
HALF = Fraction(1, 2)
I64_MIN, I64_MAX = -(1 << 63), (1 << 63) - 1
I32_MIN, I32_MAX = -(1 << 31), (1 << 31) - 1


def encoded(value):
    return f"{ieee.bits(value):016x}"


def multiplier(period_bits):
    """101d3ebdc..ec18: FDIV, FCVT S,D, FCVT D,S."""
    period = ieee.value(period_bits)
    reciprocal = ieee.rn(1 / period)
    narrowed_bits = ieee.f32(reciprocal)
    return ieee.sample_value(narrowed_bits), narrowed_bits


def quantized(period_bits, coordinate_bits):
    """101d3ed4c/edcc/ede8: FMADD coordinate, multiplier, 0.5; FCVTZS."""
    coordinate = ieee.value(coordinate_bits)
    scale, scale_bits = multiplier(period_bits)
    fused = ieee.rn(coordinate * scale + HALF)
    result = int(fused)
    split = int(ieee.rn(ieee.rn(coordinate * scale) + HALF))
    wide = int(ieee.rn(coordinate * ieee.rn(1 / ieee.value(period_bits)) + HALF))
    return dict(
        period_bits=f"{period_bits:016x}",
        coordinate_bits=f"{coordinate_bits:016x}",
        multiplier_f32_bits=f"{scale_bits:08x}",
        fused_bits=encoded(fused),
        expected=result,
        signed64_representable=I64_MIN <= result <= I64_MAX,
        split_result=split,
        nonnarrowed_result=wide,
        fma_discriminator=split != result,
        narrowing_discriminator=wide != result,
    )


def partition(start_bits, end_bits, remaining, flags):
    """101d3e888..8bc, with flags-bit2 silence at 8b4/958.

    Start is rounded independently with a sign-dependent half. Span length is
    RN64(RN64(end-start)+0.5), capped against the signed32 remaining count,
    then truncated; it is not roundedEnd-roundedStart.
    """
    start, end = ieee.value(start_bits), ieee.value(end_bits)
    begin = int(ieee.rn(start + (-HALF if start < 0 else HALF)))
    length = int(min(ieee.rn(ieee.rn(end - start) + HALF), Fraction(remaining)))
    return dict(
        start_bits=f"{start_bits:016x}", end_bits=f"{end_bits:016x}",
        remaining=remaining, flags=flags,
        start=begin, frames=length, end=begin + length,
        silence=bool(flags & 4),
        separate_endpoint_difference=(
            int(ieee.rn(end + (-HALF if end < 0 else HALF))) - begin != length
        ),
    )


def quantizer_vectors():
    result = []
    for rate in [1, 8000, 44100, 48000, 192000,
                 Fraction(441000003, 10000), Fraction(95999999, 2000)]:
        period = ieee.bits(1 / Fraction(rate))
        scale, _ = multiplier(period)
        for frames in [-257, Fraction(-5, 2), Fraction(-3, 2), -1,
                       Fraction(-1, 2), 0, Fraction(1, 2), 1,
                       Fraction(3, 2), Fraction(5, 2), 257, 1058400]:
            center = ieee.bits(Fraction(frames) / scale)
            neighbors = {center}
            if center & 0x7fffffffffffffff:
                neighbors.update([center - 1, center + 1])
            for word in sorted(neighbors):
                result.append(quantized(period, word))
    # The independent APP013 callback search supplies coordinates, not outputs.
    # Re-derive every expected operation with the narrowed reciprocal here.
    random = 0x5a17c9e3
    discriminators = []
    for _ in range(10000):
        random = (1664525 * random + 1013904223) & 0xffffffff
        word = 0x4270000000000000 | (random << 10)
        row = quantized(ieee.bits(Fraction(1, 44100)), word)
        if row["fma_discriminator"]:
            discriminators.append(row)
            if len(discriminators) == 12:
                break
    result.extend(discriminators)
    for period, coordinate in [
        (1, I64_MIN), (1, 1 << 63),
        (Fraction(1, 2), I64_MIN), (Fraction(1, 2), 1 << 62),
    ]:
        result.append(quantized(ieee.bits(period), ieee.bits(coordinate)))
    assert any(row["fma_discriminator"] for row in result)
    assert any(row["narrowing_discriminator"] for row in result)
    return result


def partition_vectors():
    result = []
    for start in [Fraction(-7, 2), Fraction(-5, 4), Fraction(-1, 2),
                  Fraction(-1, 4), 0, Fraction(1, 4), Fraction(1, 2),
                  Fraction(3, 4), Fraction(5, 4), 2047]:
        for span in [0, Fraction(1, 4), HALF, Fraction(3, 4),
                     1, Fraction(3, 2), 257]:
            for remaining in [1, 257]:
                for flags in [0, 1, 4, 5]:
                    result.append(partition(ieee.bits(start), ieee.bits(start + span),
                                            remaining, flags))
    assert any(row["separate_endpoint_difference"] for row in result)
    return result


def window(begin, end, cursor, descriptor):
    """Independent integer interval specification after the native quantizer.

    Fields omitted from expected are not semantically published by that branch.
    A gap can be filled before an empty intersection, as the instruction order
    (rather than a generic interval intersection) requires.
    """
    row = dict(request_start=begin, request_end=end, cursor=cursor,
               descriptor=descriptor)
    expected = dict(action=0, fields=0, stop=1, next=cursor,
                    silence_frames=0, read_frames=0)
    row["expected"] = expected
    if cursor == end:
        return row
    if descriptor is None:
        expected.update(action=3, next=end, silence_offset=cursor-begin,
                        silence_frames=end-cursor)
        return row
    a, b, offset = descriptor
    expected.update(fields=1, segment_start=a)
    if a > end:
        expected.update(action=3, next=end, silence_offset=cursor-begin,
                        silence_frames=end-cursor)
        return row
    expected.update(fields=3, segment_end=b, stop=0)
    if a >= b:
        expected.update(action=1, skip=1)
        return row
    if b < begin:
        expected.update(action=1, skip=2)
        return row
    expected.update(fields=7, segment_offset=offset)
    first = max(cursor, a)
    last = min(end, b)
    if cursor < a:
        expected.update(next=a, silence_offset=cursor-begin, silence_frames=a-cursor)
    if first >= last:
        expected.update(action=3 if cursor < a else 1, skip=3,
                        stop=int(first == end))
        return row
    expected.update(action=2, next=last, stop=int(last == end),
                    read_offset=first-begin, read_begin=first,
                    read_frames=last-first, source_seek=offset+first-a,
                    retry=int(first == a))
    return row


def window_vectors():
    # Integer source descriptors are encoded as (integer-.5) for negatives
    # so FMADD+.5/FCVTZS yields exactly the intended signed integer.
    result = []
    for begin, end in [(-10, 10), (0, 10), (100, 110), (0, 0)]:
        cursors = sorted({begin, (begin+end)//2, end})
        descriptors = [None, (begin, end, 0), (begin-5, end+5, 7),
                       (end, end+5, 11), (end+1, end+5, 0),
                       (begin-10, begin-1, 0), (begin-10, begin, 0),
                       (begin+2, begin+5, 19), (begin, begin, 0),
                       (begin+5, begin+4, 0), (begin-5, begin+2, -3)]
        for cursor in cursors:
            for descriptor in descriptors:
                row = window(begin, end, cursor, descriptor)
                if descriptor is not None:
                    row["descriptor_bits"] = [
                        encoded(Fraction(value) - HALF if value < 0 else Fraction(value))
                        for value in descriptor
                    ]
                result.append(row)
    return result


def read_vectors():
    result = []
    for request in [1, 257, 16000000]:
        for begin, segment in [(0, 0), (5, 0), (-5, -5)]:
            for retried in [0, 1]:
                for returned in [request, 0, request-1, request+1,
                                 -2147483645, -2147483648, -1]:
                    action = 0 if returned == request else (
                        1 if returned == -2147483645 and begin == segment and not retried else 2)
                    native = returned if returned < 0 or action == 0 else I32_MIN
                    result.append(dict(request=request, begin=begin, segment=segment,
                                       retried=retried, returned=returned,
                                       action=action, native=native))
    return result


if __name__ == "__main__":
    document = dict(
        schema_version=1,
        scope="Original-instruction value controls only; provider, source units, "
              "host scheduling and ordinary project fidelity are separate gates.",
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        arithmetic="Exact rational operations and independent IEEE nearest/ties-even rounding.",
        quantizers=quantizer_vectors(), partitions=partition_vectors(),
        windows=window_vectors(), reads=read_vectors(),
        target_execution_count=0,
    )
    destination = HERE / "timeline-reader-oracle.json"
    with destination.open("x") as output:
        json.dump(document, output, indent=2)
        output.write("\n")
    print(json.dumps(dict(
        quantizers=len(document["quantizers"]),
        fma_discriminators=sum(row["fma_discriminator"] for row in document["quantizers"]),
        narrowing_discriminators=sum(row["narrowing_discriminator"] for row in document["quantizers"]),
        partitions=len(document["partitions"]),
        windows=len(document["windows"]), reads=len(document["reads"]),
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
    )))
