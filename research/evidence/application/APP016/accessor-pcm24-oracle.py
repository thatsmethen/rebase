"""Independent bit/Fraction oracle for a conditional PCM24 format roundtrip.

No candidate, target code or resampling library computes these expected values.
The native rate-conversion routine's PCM24 branch stores signed packed24 before
later conversion. Whether a particular accessor selects that branch is separate.
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
HELPER = HERE.parent / "APP010/native-rate-mode0-oracle.py"
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
spec = importlib.util.spec_from_file_location("independent_ieee", HELPER)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)
SCALE = 1 << 23


def rec(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def f32(number):
    return ieee.bits(number, 24, 8)


def value(encoded):
    return ieee.value(encoded, 24, 8)


def project(encoded):
    """Decode exact bits; multiply at binary32; round integer ties to even."""
    exponent = (encoded >> 23) & 255
    fraction = encoded & 0x7fffff
    if exponent == 255:
        return dict(accepted=False, reason="nonfinite_input")
    if exponent == 0 and fraction:
        return dict(accepted=False, reason="subnormal_input")
    exact = value(encoded)
    try:
        scaled_bits = encoded if exact == 0 else f32(exact * SCALE)
    except AssertionError:
        return dict(accepted=False, reason="scaled_float32_overflow")
    scaled = value(scaled_bits)
    if scaled >= SCALE - 1:
        integer = SCALE - 1
    elif scaled < -SCALE:
        integer = -SCALE
    else:
        # Rational nearest_integer uses floor/remainder, independent of the
        # native truncate/absolute-fraction/oddness branches.
        integer = ieee.nearest_integer(scaled)
    assert -SCALE <= integer < SCALE
    output = f32(F(integer, SCALE))
    assert value(output) == F(integer, SCALE)
    return dict(accepted=True, scaled_f32_bits=f"{scaled_bits:08x}",
                signed_pcm24=integer, packed24_le=(integer & 0xffffff).to_bytes(3, "little").hex(),
                output_f32_bits=f"{output:08x}")


def inputs():
    rows = {}

    def put(encoded, name):
        assert 0 <= encoded <= 0xffffffff
        rows.setdefault(encoded, []).append(name)

    for encoded, name in [
        (0, "positive-zero"), (0x80000000, "negative-zero"),
        (1, "minimum-subnormal"), (0x007fffff, "maximum-subnormal"),
        (0x80000001, "negative-minimum-subnormal"), (0x807fffff, "negative-maximum-subnormal"),
        (0x00800000, "minimum-normal"), (0x80800000, "negative-minimum-normal"),
        (0x7f7fffff, "maximum-finite"), (0xff7fffff, "negative-maximum-finite"),
        (0x7f800000, "positive-infinity"), (0xff800000, "negative-infinity"),
        (0x7fc00001, "quiet-nan"), (0x7f800001, "signaling-nan"),
        (0xffc12345, "negative-nan"),
    ]:
        put(encoded, name)
    # Exact integer and half-LSB centers, with both adjacent binary32 values.
    for integer in [-SCALE-2, -SCALE, -SCALE+1, -65537, -257, -4, -3, -2, -1,
                    0, 1, 2, 3, 4, 257, 65537, SCALE-2, SCALE-1, SCALE, SCALE+2]:
        for half in [F(0), F(1, 2)]:
            center = f32(F(integer, SCALE) + half / SCALE)
            for delta in [-1, 0, 1]:
                encoded = center + delta
                if 0 <= encoded <= 0xffffffff:
                    put(encoded, f"pcm-center-{integer}-plus-{half}-bit-neighbor-{delta}")
    # Power-of-two scaling, including the last finite scaled multiplication.
    for exponent in [-126, -100, -25, -24, -23, -22, -1, 0, 1, 10, 100, 104, 105, 106, 127]:
        center = f32(ieee.power_of_two(exponent))
        for sign in [0, 0x80000000]:
            for delta in [-1, 0, 1]:
                put((center + delta) | sign, f"power-{exponent}-sign-{sign != 0}-neighbor-{delta}")
    # Deterministic raw bit patterns include broad exponent/sign coverage.
    seed = 0x164acced
    for index in range(512):
        seed = (1664525 * seed + 1013904223) & 0xffffffff
        put(seed, f"seeded-bits-{index}")
    return [dict(input_f32_bits=f"{bits:08x}", labels=labels, **project(bits))
            for bits, labels in rows.items()]


def ordering_controls(rows):
    controls = []
    gains = [f32(F(1, 2)), f32(2), f32(F(3, 4)), 0x3f8ccccd]
    for row in rows:
        if not row["accepted"]:
            continue
        encoded = int(row["input_f32_bits"], 16)
        for gain in gains:
            try:
                multiplied = f32(value(encoded) * value(gain))
                before = project(multiplied)
                after = f32(value(int(row["output_f32_bits"], 16)) * value(gain))
            except AssertionError:
                continue
            if before["accepted"] and before["output_f32_bits"] != f"{after:08x}":
                controls.append(dict(input_f32_bits=f"{encoded:08x}", gain_f32_bits=f"{gain:08x}",
                                     gain_before_roundtrip_bits=before["output_f32_bits"],
                                     gain_after_roundtrip_bits=f"{after:08x}"))
    # Keep all exact differences; none are selected by observing candidate output.
    return controls


def main():
    # Hand-check half-LSB parity, clipping, negative zero and signed symmetry.
    for x, integer in [(F(1, 2), 0), (F(3, 2), 2), (F(5, 2), 2),
                       (-F(1, 2), 0), (-F(3, 2), -2), (-F(5, 2), -2)]:
        assert project(f32(x / SCALE))["signed_pcm24"] == integer
    assert project(0x80000000)["output_f32_bits"] == "00000000"
    assert project(f32(1))["signed_pcm24"] == SCALE - 1
    assert project(f32(-1))["signed_pcm24"] == -SCALE
    assert project(0x73ffffff)["accepted"]
    assert project(0x74000000)["reason"] == "scaled_float32_overflow"
    rows = inputs()
    orders = ordering_controls(rows)
    assert orders
    report = dict(
        schema_version=1,
        scope="Conditional PCM24 storage roundtrip analytical oracle; source accessor format selection remains a separate gate.",
        target_executions=0, candidate_calls_for_expected_values=0,
        generator=rec(Path(__file__)), helper=rec(HELPER),
        original_instruction_sources=[rec(ROOT / "research/evidence/cubase-static/cpr-audio-events-001/rate-converter/native-100326318.txt")],
        native_addresses={"scale":"100326528/100326568", "upper_clamp":"10032652c..530/100326570..574", "lower_clamp":"100326534/100326578..584", "ties_even":"100326588..5c4"},
        arithmetic="RN32(input * 2^23); signed24 saturation and nearest integer ties-even; exact binary32 integer/2^23. Integer zero returns positive zero.",
        policy="Reject nonfinite/subnormal inputs or overflow in the binary32 scaling operation before writes. These defensive exclusions are not assertions of native rejection.",
        pipeline_stage_conditions=[
            {"condition":"Input format is actually PCM24 and general converter performs rate stage before format conversion", "stages":["PCM24 decode to binary32", "selected stateful converter", "binary32 to signed24 round/clamp", "later actual format/channel/gain conversion"], "status":"Conditional original branch, not yet bound to this app's selected source accessor."},
            {"condition":"Actual converter input/output are Float32 and no intermediate PCM24 stage selected", "stages":["selected stateful converter", "later actual gain/layout stages"], "status":"Do not inject the PCM24 roundtrip merely because a source file was PCM24."},
        ],
        vectors=rows,
        ordering_discriminators=orders,
        ordering_limit="Both mathematical orderings are retained. These rows prove noncommutation; they do not independently select native gain placement for an unbound format pipeline.",
        totals=dict(vectors=len(rows), accepted=sum(r["accepted"] for r in rows), rejected=sum(not r["accepted"] for r in rows), gain_order_discriminators=len(orders)))
    destination = HERE / "accessor-pcm24-oracle-v2.json"
    with destination.open("x") as output:
        json.dump(report, output, indent=2); output.write("\n")
    print(json.dumps(dict(**report["totals"], output=rec(destination))))


if __name__ == "__main__":
    main()
