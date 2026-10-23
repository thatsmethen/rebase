"""Independent Fraction/IEEE controls for placed source reconstruction.

Inputs and arithmetic come from retained original instructions. No candidate C,
Swift projection, proprietary executable or sample-processing library is called.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
helper = HERE.parent / "APP010/native-rate-mode0-oracle.py"
assert hashlib.sha256(helper.read_bytes()).hexdigest() == "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
spec = importlib.util.spec_from_file_location("ieee", helper)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)
rn, bits, value = ieee.rn, ieee.bits, ieee.value
half = F(1, 2)


def word(x):
    return f"{bits(x):016x}"


def quantize(x, period):
    quotient = rn(rn(x * 1) / period)
    return int(rn(quotient + (-half if quotient < 0 else half)))


def project(start, end, offset, begin, finish, rate):
    # FCSEL max/min retain event operands on equality; signed-zero-only
    # distinctions are covered separately from this rational-value oracle.
    start, end, offset, begin, finish, rate = map(rn, [start, end, offset, begin, finish, rate])
    result = dict(event_start_bits=word(start), event_end_bits=word(end),
                  context_offset_bits=word(offset), window_start_bits=word(begin),
                  window_end_bits=word(finish), rate_bits=word(rate))
    if start >= finish or end <= begin:
        result.update(disposition=1, empty_reason=1)
        return result
    clipped_start, clipped_end = max(start, begin), min(end, finish)
    adjusted = rn(offset + rn(clipped_start - start))
    period = rn(1 / rate)
    integers = [quantize(x, period) for x in (clipped_start, clipped_end, adjusted)]
    result.update(period_bits=word(period), clipped_start_bits=word(clipped_start),
                  clipped_end_bits=word(clipped_end), clipped_offset_bits=word(adjusted),
                  start_frame=integers[0], end_frame=integers[1], offset_frame=integers[2],
                  disposition=0 if integers[1] > integers[0] else 1,
                  empty_reason=0 if integers[1] > integers[0] else 2)
    if result["disposition"]:
        return result
    restored = [rn(rn(F(i) * period) / 1) for i in integers]
    length = max(rn(restored[1] - restored[0]), F(0))
    getter_end = rn(restored[0] + length)
    result.update(start_bits=word(restored[0]), reconstructed_end_bits=word(restored[1]),
                  length_bits=word(length), offset_bits=word(restored[2]), getter_end_bits=word(getter_end))
    # The ordinary channel reader uses a different quantizer: narrow reciprocal,
    # then one fused multiply-add and signed truncation (positive half for all).
    multiplier = ieee.sample_value(ieee.f32(rn(1 / period)))
    reader = [int(rn(x * multiplier + half)) for x in (restored[0], getter_end, restored[2])]
    result.update(reader_start=reader[0], reader_end=reader[1], reader_offset=reader[2])
    wrong_direct = [int(rn(x * multiplier + half)) for x in (clipped_start, clipped_end, adjusted)]
    result["builder_reader_vs_direct_discriminator"] = reader != wrong_direct
    result["multiply_rate_discriminator"] = integers != [int(rn(rn(x * rate) + (-half if x < 0 else half))) for x in (clipped_start, clipped_end, adjusted)]
    result["collapsed_offset_discriminator"] = bits(adjusted) != bits(rn(offset + clipped_start - start))
    return result


def builder_controls():
    rows = []
    for rate in [8000, 44100, 48000, 192000]:
        p = rn(F(1, rate))
        for frames in [-F(7,2), -F(1,2), F(1,2), F(3,2), F(8193,2), F(1058401,2)]:
            center = bits(frames * p)
            for encoded in [center - 1, center, center + 1]:
                start = value(encoded)
                rows.append(project(start, rn(start + 257 * p), 19 * p,
                                    start - 1, start + 1, rate))
        for start, span, offset, begin, finish in [
            (0, 1, 0, 1, 2), (1, 2, 0, 0, 1),
            (0, p / 4, 0, -1, 1), (0, 1, 2*p, p/2, 1-p/2),
            (1, 2, p/2, 1+F(257)*p, 2),
            (-2, 4, -3*p, -1, 1), (0, 1, 0, 0, 1),
            (-10000, 20000, -10000, p, 1),
        ]:
            rows.append(project(start, start+span, offset, begin, finish, rate))
    # Search inputs only; expected values still use exact independent operations.
    seed = 0x51a7c0de
    for _ in range(2048):
        seed = (1664525 * seed + 1013904223) & 0xffffffff
        rate = [44100, 48000, 192000][seed % 3]
        p = rn(F(1, rate))
        start = value(bits(F(seed % 8000000, 2) * p) + (seed % 3 - 1))
        row = project(start, rn(start + 1023*p), F(7,3)*p, start+F(1,3)*p, start+1, rate)
        if row.get("multiply_rate_discriminator") or row.get("collapsed_offset_discriminator"):
            rows.append(row)
        if len(rows) >= 180:
            break
    return rows


def source_control(name, ticks, frames, offset):
    # Exact accepted LoFi map: (seconds0,ticks0,p=.75),
    # (seconds600,ticks384000,p=.5). At the knot inverse lookup chooses right.
    ticks, frames, offset = map(rn, [ticks, frames, offset])
    a, b, period = (F(0), F(0), F(3,4)) if ticks < 384000 else (F(600), F(384000), F(1,2))
    start = rn(a + rn(rn(rn(ticks-b) * period) / 480))
    source_period = rn(F(1,44100))
    duration = rn(rn(source_period * frames) / 1)
    # Native Offset negates before delta conversion, then negates back.
    canonical_offset = -rn(rn(source_period * -offset) / 1)
    end = rn(start + duration)
    row = project(start, end, canonical_offset, 0, 86400, 44100)
    row.update(name=name, raw_start_bits=word(ticks), raw_length_bits=word(frames),
               raw_offset_bits=word(offset), canonical_start_bits=word(start),
               canonical_duration_bits=word(duration), canonical_end_bits=word(end),
               canonical_offset_bits="8000000000000000" if offset == 0 else word(canonical_offset),
               media_frames=1058400)
    row["application_whole_frame_admitted"] = frames.denominator == 1 and offset.denominator == 1
    return row


def main():
    builders = builder_controls()
    sources = [source_control(*x) for x in [
        ("zero-origin-trim",0,8193,7),
        ("nonzero-before-jump",960,8193,441),
        ("fractional-source-length",480,F(513,2),F(15,2)),
        ("immediately-before-jump",F(1535999,4),257,19),
        ("exact-jump",384000,441,0),
        ("immediately-after-jump",F(1536001,4),257,23),
        ("after-jump",388800,8193,1001),
        ("last-source-frame",480,1,1058399),
    ]]
    output = dict(schema_version=1,scope="Independent analytical builder and source map/type10 controls, no target execution.",
                  generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),target_execution_count=0,
                  source_fixture_sha256="2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495",
                  arithmetic="Fraction/integer nearest/ties-even per original instruction; signed truncation; no candidate calls.",
                  signed_zero_scope="Rational builder rows use +0. Native context Offset zero is explicitly recorded as -0; source builder offset addition yields +0. Other signed-zero operand distinctions are separate controls.",
                  builder_vectors=builders,source_vectors=sources)
    out=HERE/'placed-source-oracle.json'
    with out.open('x') as f:json.dump(output,f,indent=2);f.write('\n')
    print(json.dumps(dict(builder_vectors=len(builders),source_vectors=len(sources),
        multiply_rate_discriminators=sum(x.get('multiply_rate_discriminator',False) for x in builders),
        collapsed_offset_discriminators=sum(x.get('collapsed_offset_discriminator',False) for x in builders),
        builder_reader_discriminators=sum(x.get('builder_reader_vs_direct_discriminator',False) for x in builders),
        sha256=hashlib.sha256(out.read_bytes()).hexdigest())))


if __name__=='__main__':main()
