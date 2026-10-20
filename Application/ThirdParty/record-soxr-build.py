#!/usr/bin/env python3
"""Record our public build environment; never identify it as the vendor build."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

third = Path(__file__).resolve().parent
build = Path(os.environ["BUILD_DIR"]).resolve()
def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
def record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}

lib = build / "install/lib/libsoxr.0.1.2.dylib"
source = []
for p in sorted((third / "soxr-0.1.3").rglob("*")):
    if p.is_symlink():
        source.append({"path": str(p.relative_to(third)), "symlink": os.readlink(p)})
    elif p.is_file():
        source.append({**record(p), "path": str(p.relative_to(third))})
result = {
    "scope": "Independent public-source candidate build; vendor build equivalence unknown",
    "commit": "945b592b70470e29f917f4de89b4281fbbd540c0",
    "source_version": "0.1.3", "upstream_dylib_abi_version": "0.1.2",
    "compiler": command("xcrun", "clang", "--version"),
    "sdk_path": command("xcrun", "--show-sdk-path"),
    "sdk_version": command("xcrun", "--show-sdk-version"),
    "cmake": command("cmake", "--version"),
    "architecture": "arm64", "minimum_macos": "14.0",
    "options": {"optimization": "-O3 -DNDEBUG", "fast_math": False,
        "fp_contract": "off", "CR32": True, "CR64": True, "SIMD": False,
        "VR32": False, "PFFFT": False, "AVFFT": False, "OpenMP": False,
        "high_precision_clock": True, "float_standard_precision_clock": False,
        "developer_trace": False, "LSR_bindings": False},
    "source": source, "library": record(lib),
    "compile_commands": record(build / "cmake/compile_commands.json"),
    "configured_header": record(build / "cmake/soxr-config.h"),
    "dependencies": command("otool", "-L", str(lib)),
    "load_commands": command("otool", "-l", str(lib)),
}
(build / "build-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"library": result["library"]}))
