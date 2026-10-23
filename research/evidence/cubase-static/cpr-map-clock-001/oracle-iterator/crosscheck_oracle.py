#!/usr/bin/env python3
"""Independent host-IEEE sanity check of rational goldens, not target execution."""
from pathlib import Path
import ctypes
import hashlib
import json
import math
import platform
import struct

HERE = Path(__file__).resolve().parent
golden = HERE / "map-clock-goldens.json"
data = json.loads(golden.read_text())
lib = ctypes.CDLL(None)
lib.fegetround.restype = ctypes.c_int
assert lib.fegetround() == 0, "requires host FE_TONEAREST"
lib.fma.argtypes = [ctypes.c_double] * 3
lib.fma.restype = ctypes.c_double


def floating(bits, fmt="d"):
    return struct.unpack(">" + fmt, int(bits, 16).to_bytes(8 if fmt == "d" else 4, "big"))[0]


def bits(value):
    return "0x" + struct.pack(">d", value).hex()


def run(points, vector):
    x = floating(vector["input_f64_bits"])
    if vector["direction"] == "seconds_to_ticks":
        index = 0 if len(points) == 1 or x <= floating(points[1]["seconds_f64_bits"]) else 1
    else:
        index = 0 if len(points) == 1 or x < floating(points[1]["ticks_f64_bits"]) else 1
    assert index == vector["selected_index"]
    p = points[index]
    period = floating(p["period_f32_bits"], "f")
    a, b = floating(p["seconds_f64_bits"]), floating(p["ticks_f64_bits"])
    if vector["direction"] == "seconds_to_ticks":
        if x == 0:
            result = (x / floating(points[0]["period_f32_bits"], "f")) * 480.0
        else:
            quotient = (x - a) / period
            raw = lib.fma(quotient, 480.0, b)
            shifted = lib.fma(raw, 1000.0, 0.5)
            result = float(math.floor(shifted)) / 1000.0
            expected = vector["stages_f64_bits"]
            assert bits(raw) == expected["raw_tick"]
            assert bits(shifted) == expected["quantizer_fma"]
    else:
        product = (x - b) * period
        result = a + product / 480.0
    assert bits(result) == vector["result_f64_bits"], (vector, bits(result))


for v in data["vectors"]:
    run(data["maps"][v["map"]], v)
for v in data["first_fma_discriminators"]:
    run(v["points"], v)
for v in data["quantizer_vectors"]:
    raw = floating(v["raw_tick_f64_bits"])
    shifted = lib.fma(raw, 1000.0, 0.5)
    assert bits(shifted) == v["fma_bits"]
    assert bits(float(math.floor(shifted)) / 1000.0) == v["result_bits"]
    assert bits(float(math.floor(raw * 1000.0 + 0.5)) / 1000.0) == v["split_multiply_add_result_bits"]
record = {
    "scope": "Host scalar IEEE/libSystem fma sanity check against independent Fraction oracle; no Cubase code executed",
    "platform": platform.platform(), "rounding": "FE_TONEAREST", "passed": True,
    "map_vectors": len(data["vectors"]), "raw_fma_vectors": len(data["first_fma_discriminators"]),
    "quantizer_vectors": len(data["quantizer_vectors"]),
    "goldens_sha256": hashlib.sha256(golden.read_bytes()).hexdigest(),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "limitation": "Does not validate lifecycle, target FPCR, map ownership, target output or an application implementation. Oracle outputs were derived with Fraction, not host arithmetic."
}
(HERE / "oracle-crosscheck.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record))
