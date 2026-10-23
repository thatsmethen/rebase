#!/usr/bin/env python3
"""Check our optimized C kernel against the independent analytical oracle.

No Cubase code is loaded or executed. The temporary dylib is built from this
repository's self-authored kernel and removed after the comparison.
"""
import ctypes
import hashlib
import json
import pathlib
import platform
import struct
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
SOURCE = ROOT / "Application/Sources/RebaseTimingDSP/native_tempo.c"
HEADER = SOURCE.parent / "include/native_tempo.h"
VECTORS = ROOT / "research/evidence/cubase-static/cpr-audio-timing-001/reviewer-fixed-clock-vectors.json"
OUTPUT = pathlib.Path(__file__).with_name("native-clock-optimized-comparison.json")
DISASSEMBLY = pathlib.Path(__file__).with_name("native-clock-optimized-disassembly.txt")
PIN = "bc9d7eef520a3c82e1941ff3e37b48d07dc9dc09a21642db058062cc97221a02"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert digest(VECTORS) == PIN, "Independent analytical oracle changed"
    vectors = json.loads(VECTORS.read_bytes())["vectors"]
    compiler = subprocess.check_output(["xcrun", "--find", "clang"], text=True).strip()
    compiler_version = subprocess.check_output([compiler, "--version"], text=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="rebase-native-clock-") as temporary:
        library = pathlib.Path(temporary) / "native-clock.dylib"
        arguments = ["xcrun", "clang", "-std=c11", "-O3", "-dynamiclib", "-fno-fast-math",
                     "-ffp-contract=off", "-frounding-math", "-I", str(HEADER.parent),
                     str(SOURCE), "-o", str(library)]
        subprocess.run(arguments, check=True, capture_output=True, text=True)
        disassembly = subprocess.check_output(["xcrun", "otool", "-tvV", str(library)], text=True)
        DISASSEMBLY.write_text(disassembly)
        module = ctypes.CDLL(str(library))
        for vector in vectors:
            function = (module.rb_native_fixed_seconds if vector["direction"] == "ticks_to_seconds"
                        else module.rb_native_fixed_ticks)
            function.argtypes = [ctypes.c_uint32, ctypes.c_double, ctypes.POINTER(ctypes.c_double)]
            function.restype = ctypes.c_int
            bpm = int(vector["bpm_f32_bits"], 16)
            value = struct.unpack(">d", int(vector["input_f64_bits"], 16).to_bytes(8, "big"))[0]
            output = ctypes.c_double()
            status = function(bpm, value, ctypes.byref(output))
            bits = int.from_bytes(struct.pack(">d", output.value), "big")
            expected = int(vector["result_f64_bits"], 16)
            results.append({"direction": vector["direction"], "bpm_bits": vector["bpm_f32_bits"],
                            "input_bits": vector["input_f64_bits"], "expected_bits": f"0x{expected:016x}",
                            "actual_bits": f"0x{bits:016x}", "status": status,
                            "exact": status == 0 and bits == expected})
        library_hash = digest(library)
    report = {"scope": "Self-authored optimized kernel versus independently derived rational IEEE oracle; no target execution or target FP mode observation",
              "source_sha256": digest(SOURCE), "header_sha256": digest(HEADER),
              "oracle_sha256": PIN, "script_sha256": digest(pathlib.Path(__file__)),
              "compiler_version": compiler_version, "platform": platform.platform(),
              "arguments": arguments, "temporary_library_sha256": library_hash,
              "disassembly_sha256": digest(DISASSEMBLY),
              "temporary_library_retained": False, "vector_count": len(results),
              "exact_count": sum(item["exact"] for item in results), "results": results}
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    assert len(results) == 36 and all(item["exact"] for item in results), "Kernel mismatch"
    print(f"{len(results)} optimized vectors exact; {OUTPUT}")


if __name__ == "__main__":
    main()
