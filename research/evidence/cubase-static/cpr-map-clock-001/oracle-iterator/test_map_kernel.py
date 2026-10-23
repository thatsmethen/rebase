#!/usr/bin/env python3
"""Optimized self-authored C primitives versus frozen independent oracle.

The test-only wrappers expose internal math sites for instruction-level vectors
outside the public range. No target bytes are compiled or executed.
"""
from pathlib import Path
import ctypes as C
import hashlib
import json
import math
import platform
import re
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = ROOT / "Application/Sources/RebaseTimingDSP/native_tempo.c"
HEADER = SOURCE.parent / "include/native_tempo.h"
GOLD = HERE / "map-clock-goldens.json"
EXPECTED_GOLD = "98b3922f598f57e51e961252a61a6503c67cead5b8d17605024e2bedc202795c"
FIXED_GOLD = HERE.parents[1] / "cpr-audio-timing-001/reviewer-fixed-clock-vectors.json"
EXPECTED_FIXED_GOLD = "bc9d7eef520a3c82e1941ff3e37b48d07dc9dc09a21642db058062cc97221a02"
data = json.loads(GOLD.read_text())
assert hashlib.sha256(GOLD.read_bytes()).hexdigest() == EXPECTED_GOLD
fixed_data = json.loads(FIXED_GOLD.read_text())
assert hashlib.sha256(FIXED_GOLD.read_bytes()).hexdigest() == EXPECTED_FIXED_GOLD
prefix = SOURCE.read_bytes().split(b"\n/* New map contract only;")[0]
assert hashlib.sha256(prefix).hexdigest() == "00d86967975e90f88ade6d1f4223db6a7db5543729f8c39fbc9556a53967d3f3"
FLAGS = ["-fno-fast-math", "-ffp-contract=off", "-frounding-math"]
package = (ROOT / "Application/Package.swift").read_text()
assert '.target(name: "RebaseTimingDSP"' in package and all(flag in package for flag in FLAGS)


class Point(C.Structure):
    _fields_ = [("period_bits", C.c_uint32), ("seconds", C.c_double), ("ticks", C.c_double)]


def floating(bits):
    return struct.unpack(">d", int(bits, 16).to_bytes(8, "big"))[0]


def bits(x):
    return "0x" + struct.pack(">d", x).hex()


def points(rows):
    return (Point * len(rows))(*(Point(int(p["period_f32_bits"], 16), floating(p["seconds_f64_bits"]),
                                     floating(p["ticks_f64_bits"])) for p in rows))


def instruction_checks(assembly):
    """Check the emitted operation sites in the actual optimized public bodies."""
    bodies = {}
    current = None
    for line in assembly.splitlines():
        label = re.fullmatch(r"([0-9a-f]+) <([^>]+)>:", line)
        if label:
            current = label[2]
            bodies[current] = {"address": "0x" + label[1], "arithmetic": []}
        instruction = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\w+)\s*(.*)", line)
        if current and instruction and instruction[3] in {"fdiv", "fmul", "fadd", "fsub", "fmadd", "frintm"}:
            bodies[current]["arithmetic"].append({"address": "0x" + instruction[1],
                "word": instruction[2], "mnemonic": instruction[3], "operands": instruction[4]})
    expected = {
        "_rb_native_fixed_period": ["fdiv"],
        "_rb_native_fixed_seconds": ["fdiv", "fmul", "fdiv"],
        "_rb_native_fixed_ticks": ["fdiv", "fdiv", "fmul"],
        "_rb_native_map_validate": ["fsub", "fmul", "fdiv", "fadd"],
        "_rb_native_map_seconds": ["fsub", "fmul", "fdiv", "fadd"],
        # The zero path and positive path both appear in this linear inventory.
        "_rb_native_map_ticks": ["fdiv", "fmul", "fsub", "fdiv", "fmadd", "fmadd", "frintm", "fdiv"],
    }
    selected = {}
    for name, mnemonics in expected.items():
        body = bodies[name]
        actual = [row["mnemonic"] for row in body["arithmetic"]]
        assert actual == mnemonics, (name, actual, mnemonics)
        if name.startswith("_rb_native_fixed_"):
            assert body["arithmetic"][0]["operands"].startswith("s0,"), name
        selected[name] = body
    return selected


results, fixed_results, negative_count = [], [], 0
with tempfile.TemporaryDirectory(prefix="rebase-map-kernel-") as temporary:
    tmp = Path(temporary)
    harness = tmp / "harness.c"
    # The actual application translation unit is included unchanged. Test-only
    # exports do not exist in the app; they cannot bypass public validation there.
    harness.write_text('#include ' + json.dumps(str(SOURCE)) + '\n' +
        'double test_raw(double q,double a) { return map_raw_tick(q,a); }\n' +
        'double test_quantize(double r) { return map_quantize(r); }\n' +
        'int test_getround(void) { return fegetround(); }\n' +
        'int test_upward(void) { return fesetround(FE_UPWARD); }\n' +
        'int test_restore(int r) { return fesetround(r); }\n')
    library = tmp / "map-kernel.dylib"
    arguments = ["xcrun", "clang", "-std=c11", "-O3", "-dynamiclib", *FLAGS,
                 "-Wall", "-Wextra", "-Werror", "-I", str(HEADER.parent), str(harness), "-o", str(library)]
    subprocess.run(arguments, check=True, capture_output=True, text=True)
    assembly = subprocess.run(["xcrun", "llvm-objdump", "-d", str(library)], check=True, capture_output=True, text=True).stdout
    (HERE / "optimized-map-kernel-disassembly.txt").write_text(assembly)
    emitted = instruction_checks(assembly)
    lib = C.CDLL(str(library))
    for name in ["rb_native_map_seconds", "rb_native_map_ticks"]:
        fn = getattr(lib, name)
        fn.argtypes = [C.POINTER(Point), C.c_uint32, C.c_double, C.POINTER(C.c_double)]
        fn.restype = C.c_int
    lib.rb_native_map_validate.argtypes = [C.POINTER(Point), C.c_uint32]
    lib.rb_native_map_validate.restype = C.c_int
    lib.test_raw.argtypes = [C.c_double, C.c_double]; lib.test_raw.restype = C.c_double
    lib.test_quantize.argtypes = [C.c_double]; lib.test_quantize.restype = C.c_double
    assert lib.test_getround() == 0

    for name in ["rb_native_fixed_seconds", "rb_native_fixed_ticks"]:
        getattr(lib, name).argtypes = [C.c_uint32, C.c_double, C.POINTER(C.c_double)]
        getattr(lib, name).restype = C.c_int
    lib.rb_native_fixed_period.argtypes = [C.c_uint32, C.POINTER(C.c_uint32)]
    lib.rb_native_fixed_period.restype = C.c_int
    for vector in fixed_data["vectors"]:
        bpm = int(vector["bpm_f32_bits"], 16)
        period = C.c_uint32()
        assert lib.rb_native_fixed_period(bpm, C.byref(period)) == 0
        assert period.value == int(vector["period_f32_bits"], 16)
        output = C.c_double(12345.0)
        fn = lib.rb_native_fixed_ticks if vector["direction"] == "seconds_to_ticks" else lib.rb_native_fixed_seconds
        assert fn(bpm, floating(vector["input_f64_bits"]), C.byref(output)) == 0
        assert bits(output.value) == vector["result_f64_bits"]
        fixed_results.append({"direction": vector["direction"], "bpm": vector["bpm_f32_bits"],
            "input": vector["input_f64_bits"], "actual": bits(output.value)})

    def run(rows, vector):
        pts = points(rows)
        fn = lib.rb_native_map_ticks if vector["direction"] == "seconds_to_ticks" else lib.rb_native_map_seconds
        output = C.c_double(12345.0)
        status = fn(pts, len(rows), floating(vector["input_f64_bits"]), C.byref(output))
        assert status == 0 and bits(output.value) == vector["result_f64_bits"], (vector, status, bits(output.value))
        return {"direction": vector["direction"], "input": vector["input_f64_bits"],
                "expected": vector["result_f64_bits"], "actual": bits(output.value), "status": status}

    for vector in data["vectors"]:
        results.append({"map": vector["map"], **run(data["maps"][vector["map"]], vector)})
    for vector in data["first_fma_discriminators"]:
        run(vector["points"], vector)
        stages = vector["stages_f64_bits"]
        actual = lib.test_raw(floating(stages["quotient"]), floating(vector["points"][vector["selected_index"]]["ticks_f64_bits"]))
        assert bits(actual) == stages["raw_tick"]
    for vector in data["quantizer_vectors"]:
        assert bits(lib.test_quantize(floating(vector["raw_tick_f64_bits"]))) == vector["result_bits"]

    good = (Point * 2)(Point(0x3f400000, 0, 0), Point(0x3f000000, 600, 384000))
    assert lib.rb_native_map_validate(good, 2) == 0
    assert lib.rb_native_map_validate(good, 1) == 0
    # Canonicality is a distinct promotion check: no tolerated or rewritten A.
    for changed_a in [math.nextafter(600, -math.inf), math.nextafter(600, math.inf), 601]:
        noncanonical = (Point * 2)(good[0], Point(0x3f000000, changed_a, 384000))
        assert lib.rb_native_map_validate(noncanonical, 2) == 1
        negative_count += 1
    assert lib.rb_native_map_validate(points(data["maps"]["synthetic-unequal-anchor"]), 2) == 1
    negative_count += 1

    def rejected(pts, count, value=1.0):
        global negative_count
        for fn in [lib.rb_native_map_seconds, lib.rb_native_map_ticks]:
            output = C.c_double(-12345.25)
            assert fn(pts, count, value, C.byref(output)) != 0
            assert bits(output.value) == bits(-12345.25)
            negative_count += 1

    for count in [0, 3, 0xffffffff]:
        rejected(good, count)
        assert lib.rb_native_map_validate(good, count) == 1
    rejected(None, 1)
    for period in [0, 0x80000000, 1, 0x7fc00000, 0x7f800000, 0xbf000000]:
        rejected((Point * 1)(Point(period, 0, 0)), 1)
    for a, b in [(-0.0, 0), (0, -0.0), (1, 0), (0, 1), (math.nan, 0), (0, math.inf)]:
        rejected((Point * 1)(Point(0x3f000000, a, b)), 1)
    for a, b in [(0, 384000), (600, 0), (math.inf, 384000), (600, math.nan),
                 (3000000001, 384000), (600, 480000000001), (math.ulp(0.0), 1)]:
        rejected((Point * 2)(good[0], Point(0x3f000000, a, b)), 2)
    for value in [math.nan, math.inf, -1, math.ulp(0.0), 480000000001.0]:
        rejected(good, 2, value)
    output = C.c_double(-12345.25)
    assert lib.rb_native_map_ticks(good, 2, 3000000001, C.byref(output)) != 0
    assert output.value == -12345.25
    for fn in [lib.rb_native_map_seconds, lib.rb_native_map_ticks]:
        assert fn(good, 2, 1, None) == 1
        negative_count += 1
    # Finite normal inputs may still generate unrepresentable intermediates.
    for fn, period, value in [(lib.rb_native_map_seconds, 0x00800000, 2.2250738585072014e-308),
                              (lib.rb_native_map_ticks, 0x00800000, 1.0),
                              (lib.rb_native_map_seconds, 0x7f7fffff, 3000000000.0),
                              (lib.rb_native_map_ticks, 0x7f7fffff, 2.2250738585072014e-308)]:
        output = C.c_double(-12345.25)
        assert fn((Point * 1)(Point(period, 0, 0)), 1, value, C.byref(output)) != 0
        assert output.value == -12345.25
        negative_count += 1
    rounding = lib.test_getround()
    try:
        assert lib.test_upward() == 0
        assert lib.rb_native_map_validate(good, 2) == 2
        for fn in [lib.rb_native_map_seconds, lib.rb_native_map_ticks]:
            output = C.c_double(-12345.25)
            assert fn(good, 2, 1, C.byref(output)) == 2 and output.value == -12345.25
            negative_count += 1
    finally:
        assert lib.test_restore(rounding) == 0
    record = {
        "scope": "Self-authored optimized C map primitives versus independent rational native-instruction oracle; no target execution",
        "passed": True, "map_vectors": len(results), "raw_fma_vectors": len(data["first_fma_discriminators"]),
        "quantizer_vectors": len(data["quantizer_vectors"]), "rejection_checks": negative_count,
        "fixed_regression_vectors": len(fixed_results), "fixed_oracle_sha256": EXPECTED_FIXED_GOLD,
        "instruction_checks": emitted, "instruction_checks_passed": True,
        "compiler": subprocess.run(["xcrun", "clang", "--version"], check=True, capture_output=True, text=True).stdout.strip(),
        "arguments": arguments, "platform": platform.platform(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "header_sha256": hashlib.sha256(HEADER.read_bytes()).hexdigest(),
        "unchanged_fixed_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
        "oracle_sha256": EXPECTED_GOLD, "test_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "optimized_disassembly_sha256": hashlib.sha256(assembly.encode()).hexdigest(),
        "temporary_library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "temporary_library_retained": False, "results": results, "fixed_results": fixed_results,
        "limits": "Public primitives preserve detached anchors; importer must additionally call canonical validator and prove provenance/lifecycle. Test-only private math wrappers include out-of-public-domain quantizer controls and are absent from the app."
    }
(HERE / "optimized-map-kernel-comparison.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({k: record[k] for k in ["passed", "map_vectors", "raw_fma_vectors", "quantizer_vectors", "rejection_checks", "fixed_regression_vectors", "instruction_checks_passed"]}))
