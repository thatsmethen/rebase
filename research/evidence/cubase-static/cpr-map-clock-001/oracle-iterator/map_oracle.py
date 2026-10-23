#!/usr/bin/env python3
"""Analytical IEEE map-clock oracle. No target or candidate code is executed.

The exact rational is rounded after each native f32/f64 instruction. FMA has
one rounding, unlike multiply followed by add. Signed zero is retained where
the native operation sequence determines it. No host float computes results.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
MASK = 1 << 63


def pow2(n):
    return F(1 << n) if n >= 0 else F(1, 1 << -n)


def nearest_integer(x):
    q, r = divmod(x.numerator, x.denominator)
    return q + (2 * r > x.denominator or (2 * r == x.denominator and q & 1))


def encode(x, p=53, eb=11, zero_sign=0):
    """IEEE nearest/ties-even encoding, exact rational input."""
    x = F(x)
    sign = int(x < 0) if x else zero_sign
    x = abs(x)
    if not x:
        return sign << (p + eb - 1)
    bias = (1 << (eb - 1)) - 1
    exponent = x.numerator.bit_length() - x.denominator.bit_length()
    if x < pow2(exponent):
        exponent -= 1
    emin = 1 - bias
    m = nearest_integer(x / pow2(max(exponent, emin) - (p - 1)))
    if m == 1 << p:
        exponent += 1
        m >>= 1
    if exponent > bias:
        raise OverflowError("finite oracle domain exceeded")
    if exponent < emin and m < 1 << (p - 1):
        exp, fraction = 0, m
    else:
        exp, fraction = max(exponent, emin) + bias, m - (1 << (p - 1))
    return (sign << (eb + p - 1)) | (exp << (p - 1)) | fraction


def decode(bits, p=53, eb=11):
    assert 0 <= bits < 1 << (p + eb)
    fraction = bits & ((1 << (p - 1)) - 1)
    exponent = (bits >> (p - 1)) & ((1 << eb) - 1)
    if exponent == (1 << eb) - 1:
        raise ValueError("NaN/infinity is outside the oracle domain")
    sign = -1 if bits >> (p + eb - 1) else 1
    bias = (1 << (eb - 1)) - 1
    return sign * ((F((1 << (p - 1)) + fraction) * pow2(exponent - bias - (p - 1)))
                   if exponent else F(fraction) * pow2(1 - bias - (p - 1)))


def op(a, b, operation):
    x, y = decode(a), decode(b)
    if operation == "add":
        exact, zero_sign = x + y, int(bool(a & b & MASK))
    elif operation == "sub":
        return op(a, b ^ MASK, "add")
    elif operation == "mul":
        exact, zero_sign = x * y, int(bool((a ^ b) & MASK))
    elif operation == "div":
        if not y:
            raise ZeroDivisionError()
        exact, zero_sign = x / y, int(bool((a ^ b) & MASK))
    else:
        raise ValueError(operation)
    # An exact cancellation of nonzero numbers produces +0 in nearest mode.
    if operation == "add" and (x or y):
        zero_sign = 0
    return encode(exact, zero_sign=zero_sign)


def fma(a, b, c):
    x, y, z = decode(a), decode(b), decode(c)
    exact = x * y + z
    zero_sign = int(not x * y and not z and bool((a ^ b) & MASK) and bool(c & MASK))
    return encode(exact, zero_sign=zero_sign)


C480, C1000, CHALF = encode(480), encode(1000), encode(F(1, 2))


def quantize(raw, split=False):
    shifted = op(op(raw, C1000, "mul"), CHALF, "add") if split else fma(raw, C1000, CHALF)
    value = decode(shifted)
    floor_bits = encode(value.numerator // value.denominator)
    return op(floor_bits, C1000, "div"), shifted, floor_bits


def point(period, seconds=F(0), ticks=F(0)):
    return {"period_f32_bits": period, "seconds_f64_bits": encode(seconds), "ticks_f64_bits": encode(ticks), "kind": 0}


def inverse_index(points, query):
    """Literal bounded count2 generic search, filter=null, fresh index=0.

    Follows 1016c1424 with d0=invalid, e8=current, d8=next,
    e0=previous, f8=first,100=last. Return value of moves is old item;
    caller subsequently uses next() then current() for current/next segment.
    """
    index, trace = 0, []
    count = len(points)
    assert count in (1, 2)
    if count == 1:
        return 0, ["1016c3f94: index=count-1=0"]
    def current():
        return decode(points[index]["ticks_f64_bits"])
    x = decode(query)
    if current() == x:
        return index, ["1016c148c: current.Start==query; return"]
    if current() > x:
        trace.append("1016c14d8: current.Start>query; backward branch")
        while 0 <= index < count and current() > x:
            index -= 1
            trace.append("1016c1510: previous returns old item, decrements index")
        if not 0 <= index < count:
            index = 0
            trace.append("1016c153c..1554: first resets index0")
        return index, trace
    trace.append("1016c14d8: current.Start<=query; forward branch")
    while 0 <= index < count:
        if current() == x:
            trace.append("1016c1578: current.Start==query; return current index")
            return index, trace
        if current() > x:
            index -= 1
            trace.append("1016c15f8: previous tail decrements index; return")
            return index, trace
        index += 1
        trace.append("1016c15b0: next returns old item, increments index")
    index = count - 1
    trace.append("1016c15dc..15f4: last resets index=count-1")
    return index, trace


def clock(points, input_bits, direction):
    assert len(points) in (1, 2)
    assert all(p["kind"] == 0 for p in points)
    x = decode(input_bits)
    if x < 0:
        raise ValueError("negative coordinates excluded")
    if direction == "seconds_to_ticks":
        index = 0 if len(points) == 1 or x <= decode(points[1]["seconds_f64_bits"]) else 1
        trace = ["10173b064: count1=index0; count2 seconds<=last.A=index0, otherwise1"]
    else:
        index, trace = inverse_index(points, input_bits)
    p = points[index]
    period = encode(decode(p["period_f32_bits"], 24, 8))
    stages = {"promoted_period": period}
    if direction == "seconds_to_ticks":
        if x == 0:
            # With valid first tempo item: nonpositive branch10173af2c..af58.
            quotient = op(input_bits, encode(decode(points[0]["period_f32_bits"], 24, 8)), "div")
            result = op(quotient, C480, "mul")
            stages.update(zero_quotient=quotient, result=result)
            trace = ["10173add8..af58: zero branch; first tempo period; no quantization"]
        else:
            delta = op(input_bits, p["seconds_f64_bits"], "sub")
            quotient = op(delta, period, "div")
            raw = fma(quotient, C480, p["ticks_f64_bits"])
            result, shifted, floored = quantize(raw)
            split_raw = op(op(quotient, C480, "mul"), p["ticks_f64_bits"], "add")
            split_quantizer, _, _ = quantize(raw, split=True)
            stages.update(delta=delta, quotient=quotient, raw_tick=raw, quantizer_fma=shifted,
                          quantizer_floor=floored, result=result, split_raw_tick=split_raw,
                          split_raw_result=quantize(split_raw)[0], split_quantizer_result=split_quantizer)
    elif direction == "ticks_to_seconds":
        delta = op(input_bits, p["ticks_f64_bits"], "sub")
        product = op(delta, period, "mul")
        scaled = op(product, C480, "div")
        result = op(p["seconds_f64_bits"], scaled, "add")
        reordered = op(p["seconds_f64_bits"], op(op(delta, C480, "div"), period, "mul"), "add")
        stages.update(delta=delta, product=product, scaled=scaled, result=result, reordered_result=reordered)
    else:
        raise ValueError(direction)
    return {"direction": direction, "input_f64_bits": hx(input_bits), "selected_index": index,
            "trace": trace, "stages_f64_bits": {k: hx(v) for k, v in stages.items()}, "result_f64_bits": hx(result)}


def hx(x):
    return f"0x{x:016x}"


def map_json(points):
    return [{k: (f"0x{v:08x}" if k == "period_f32_bits" else hx(v)) if k.endswith("bits") else v
             for k, v in p.items()} for p in points]


def self_check():
    assert encode(F(1)) == 0x3ff0000000000000
    assert encode(F(1) + pow2(-53)) == encode(1)  # ties to even lower
    assert encode(F(1) + 3 * pow2(-53)) == encode(1) + 2  # ties to even upper
    assert encode(pow2(-1074)) == 1 and encode(pow2(-1075)) == 0
    assert op(MASK, C480, "mul") == MASK
    assert op(MASK, 0, "add") == 0
    assert fma(encode(F(1)+pow2(-52)), encode(F(1)-pow2(-52)), encode(-1)) == encode(-pow2(-104))
    assert op(op(encode(F(1)+pow2(-52)), encode(F(1)-pow2(-52)), "mul"), encode(-1), "add") == 0
    assert quantize(encode(F(1, 2)))[0] == encode(F(1, 2))


def main():
    self_check()
    maps = {
        "piano-origin": [point(0x3ee540f5)],
        "piano-period-next": [point(0x3ee540f6)],
        "half-origin": [point(0x3f000000)],
        "lofi-two-jump": [point(0x3f400000), point(0x3f000000, F(600), F(384000))],
        "stereo-two-jump": [point(0x3f000000), point(0x3f000000, F(600), F(576000))],
        # Arithmetic-only state, not a valid imported fixture: discriminates knot sides.
        "synthetic-unequal-anchor": [point(0x3ee540f5), point(0x3f400001, F(600), F(643201))],
    }
    vectors = []
    for name, points in maps.items():
        for direction in ("seconds_to_ticks", "ticks_to_seconds"):
            center = encode(600) if direction == "seconds_to_ticks" else points[-1]["ticks_f64_bits"]
            values = [0, MASK, encode(1), encode(F(1, 44100)), encode(F(14880))]
            if center:
                values += [center - 1, center, center + 1]
            if len(points) == 1:
                # Inputs which land near the map quantizer's first half quantum.
                half_input = encode(F(1, 2000) * decode(points[0]["period_f32_bits"], 24, 8) / 480)
                values += [half_input - 1, half_input, half_input + 1]
            for bits in dict.fromkeys(values):
                v = clock(points, bits, direction); v["map"] = name; vectors.append(v)
    # Internal quantizer half-way cases independently distinguish fused vs split.
    quantizer_vectors = []
    for n in [0, 1, 2, 17, 999, 1000, 1000001, (1 << 32) + 1, (1 << 40) + 3,
              (1 << 52) + 3]:
        at = encode(F(2 * n + 1, 2000))
        for raw in [at - 1, at, at + 1]:
            result, shifted, floor_bits = quantize(raw)
            split, _, _ = quantize(raw, True)
            quantizer_vectors.append({"raw_tick_f64_bits": hx(raw), "fma_bits": hx(shifted),
                                      "floor_bits": hx(floor_bits), "result_bits": hx(result),
                                      "split_multiply_add_result_bits": hx(split),
                                      "within_existing_app_tick_bound": decode(raw) <= 480_000_000_000})
    # Find bounded deterministic arithmetic cases exposing the first FMA too.
    discriminators = []
    for anchor in [F(643201), F(100000000001), F(400000000003)]:
        points = [point(0x3ee540f5), point(0x3f400001, F(600), anchor)]
        for i in range(1, 2000):
            bits = encode(F(600) + F(i, 997))
            v = clock(points, bits, "seconds_to_ticks")
            s = v["stages_f64_bits"]
            if s["raw_tick"] != s["split_raw_tick"]:
                discriminators.append({"points": map_json(points), **v,
                                       "final_result_also_differs": s["result"] != s["split_raw_result"]})
            if sum(row["final_result_also_differs"] for row in discriminators) >= 4:
                break
        if sum(row["final_result_also_differs"] for row in discriminators) >= 4:
            break
    # Keep a small independently reproducible subset rather than a large search inventory.
    raw_only = [v for v in discriminators if not v["final_result_also_differs"]][:3]
    discriminators = raw_only + [v for v in discriminators if v["final_result_also_differs"]][:4]
    assert any(v["result_bits"] != v["split_multiply_add_result_bits"] for v in quantizer_vectors)
    assert discriminators
    # Internal selector controls: fresh unfiltered iterator, before/at/after tick knot.
    selection = []
    points = maps["lofi-two-jump"]
    for bits in [0, encode(384000) - 1, encode(384000), encode(384000) + 1]:
        idx, trace = inverse_index(points, bits)
        assert idx == (0 if decode(bits) < 384000 else 1)
        selection.append({"input_tick_bits": hx(bits), "selected_index": idx,
                          "caller_next_returns": idx, "caller_current_after_next": idx + 1 if idx == 0 else None,
                          "native_path": trace})
    result = {
        "scope": "Independent exact-rational analytical outputs; no target runtime or candidate execution",
        "model": "Every operation nearest/ties-even IEEE; explicit fused operations; integer rational floor; serialized f32 periods promoted exactly",
        "preconditions": "1/2 selected kind0 records, unchanged serialized anchors; finite inputs, nonnegative coordinates, fresh filter-null iterator. Lifecycle/cache/list ownership is separately pending. Synthetic unequal anchors are arithmetic controls, not approved imports.",
        "zero": "+0/-0 forward uses first-period division and multiply, no quantizer. Inverse follows nonnegative jump path; origin +A addition yields +0 for either signed input zero.",
        "quantizer_discriminator_scope": "The internal quantizer split/FMA discriminator occurs above the existing app tick bound. It validates the instruction-level oracle, not permission to expand the application domain. Half-step and neighbor vectors within the bound are retained without claiming they distinguish fused/split evaluation.",
        "first_fma_discriminator_scope": "The first-FMA controls retain raw-tick differences even when the subsequent quantizer erases that difference. Each row states whether its final result also differs; no stronger end-to-end discrimination is implied.",
        "maps": {name: map_json(points) for name, points in maps.items()},
        "vectors": vectors, "quantizer_vectors": quantizer_vectors,
        "first_fma_discriminators": discriminators, "inverse_selector_traces": selection,
        "counts": {"map_vectors": len(vectors), "quantizer_vectors": len(quantizer_vectors),
                   "quantizer_split_discriminators": sum(v["result_bits"] != v["split_multiply_add_result_bits"] for v in quantizer_vectors),
                   "first_fma_discriminators": len(discriminators),
                   "first_fma_final_discriminators": sum(v["final_result_also_differs"] for v in discriminators)},
        "source_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (HERE / "map-clock-goldens.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
