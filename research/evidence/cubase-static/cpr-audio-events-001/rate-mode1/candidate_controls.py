"""Run reconstruction-only safety/count controls; never load the native target.

The independent sample/coefficient oracle is a separate APP013 study. These
controls do not claim native runtime comparisons.
"""
from pathlib import Path
import ctypes as C
import hashlib
import json
import math
import struct
import subprocess

H = Path(__file__).resolve().parent
R = H.parents[4]
LIB = H / "controls/libmode1-candidate.dylib"
SRC = R / "Application/Sources/RebaseTimingDSP/native_rate_mode1.c"
HDR = R / "Application/Sources/RebaseTimingDSP/include/native_rate_mode1.h"
command = ["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
           "-fno-fast-math", "-ffp-contract=off", "-dynamiclib",
           "-I", str(HDR.parent), str(SRC), "-o", str(LIB)]
subprocess.run(command, check=True)
d = C.CDLL(str(LIB))
P = C.c_void_p
Z = C.c_size_t
U = C.c_uint32
F = C.c_float
D = C.c_double


class Snapshot(C.Structure):
    _fields_ = [("ratio", D), ("step", D), ("phase", D),
                ("input", C.c_uint64), ("generated", C.c_uint64),
                ("returned", C.c_uint64), ("channels", U),
                ("capacity", U), ("fresh", U), ("finished", U)]


for name, args in {
    "create": [D, D, U, C.POINTER(P)],
    "snapshot": [P, C.POINTER(Snapshot)], "reset": [P],
    "count": [P, Z, U, C.POINTER(Z)],
    "count_blocks": [P, Z, Z, C.POINTER(Z)],
    "process": [P, C.POINTER(F), Z, C.POINTER(F), Z, U, C.POINTER(Z)],
    "copy_table": [P, U, Z, Z, C.POINTER(D)],
    "copy_storage": [P, U, Z, Z, C.POINTER(D)],
}.items():
    f = getattr(d, "rb_native_mode1_" + name)
    f.argtypes = args
    f.restype = C.c_int
d.rb_native_mode1_destroy.argtypes = [P]
d.rb_native_mode1_destroy.restype = None


def call(name, *args):
    return getattr(d, "rb_native_mode1_" + name)(*args)


def create(rin=48000, rout=44100, channels=2):
    p = P()
    assert call("create", rin, rout, channels, C.byref(p)) == 0
    return p


def snapshot(p):
    s = Snapshot()
    assert call("snapshot", p, C.byref(s)) == 0
    return s


def state_hash(p):
    s = snapshot(p)
    h = hashlib.sha256(bytes(s))
    for c in range(s.channels):
        buffer = (D * (s.capacity + 129))()
        assert call("copy_storage", p, c, 0, len(buffer), buffer) == 0
        h.update(bytes(buffer))
    return h.hexdigest()


def process(p, n, final, value=0.125):
    s = snapshot(p)
    count = Z(999)
    assert call("count", p, n, final, C.byref(count)) == 0
    src = (F * (n * s.channels))(*([value] * (n * s.channels))) if n else None
    dst = (F * (count.value * s.channels + 4))()
    for i in range(len(dst)):
        dst[i] = 17
    out = Z(777)
    assert call("process", p, src, n, dst, count.value, final, C.byref(out)) == 0
    assert out.value == count.value
    assert all(dst[i] == 17 for i in range(count.value * s.channels, len(dst)))
    return out.value, hashlib.sha256(bytes(dst)[:-16]).hexdigest()


rows = []
for rin, rout in [(44100, 48000), (48000, 32000), (48000, 48000),
                  (8000, 192000), (192000, 8000)]:
    for channels in (1, 2):
        for chunks in ([0], [1], [1, 127], [63, 65], [64, 64],
                       [8192, 1], [0, 128], [128, 0]):
            p = create(rin, rout, channels)
            total = 0
            digests = []
            for i, n in enumerate(chunks):
                count, digest = process(p, n, int(i == len(chunks) - 1))
                total += count
                digests.append(digest)
            s = snapshot(p)
            assert s.input == sum(chunks) and s.returned == total and s.finished == 1
            assert call("count", p, 1, 0, C.byref(Z())) == 4
            rows.append({"rates": [rin, rout], "channels": channels,
                         "chunks": chunks, "returned": total,
                         "native_generated": s.generated, "output_hashes": digests})
            d.rb_native_mode1_destroy(p)

aggregate = []
for rate in (8000, 32000, 44100, 48000, 192000):
    for n in (0, 1, 63, 64, 65, 8193, 16385):
        p = create(44100, rate, 2)
        expected = Z()
        before = state_hash(p)
        assert call("count_blocks", p, n, 8192, C.byref(expected)) == 0
        assert state_hash(p) == before
        remaining = n
        actual = 0
        while True:
            take = min(remaining, 8192)
            actual += process(p, take, int(take == remaining))[0]
            remaining -= take
            if not remaining:
                break
        assert actual == expected.value
        aggregate.append({"source": 44100, "output": rate, "frames": n, "count": actual})
        d.rb_native_mode1_destroy(p)

rejections = []
p = create(48000, 48000, 1)
for name, n, final, value, capacity, expected_error in [
    ("nonfinite", 128, 0, math.inf, 1024, 3),
    ("subnormal", 128, 0, 2 ** -149, 1024, 3),
    ("output_capacity", 128, 0, 0.125, 0, 2),
    ("block_limit", 1000001, 0, 0.125, 0, 1),
]:
    before = state_hash(p)
    src = (F * min(n, 128))(*([value] * min(n, 128)))
    dst = (F * 1024)(*([17] * 1024))
    count = Z(999)
    assert call("process", p, src, n, dst, capacity, final, C.byref(count)) == expected_error
    assert count.value == 999 and all(x == 17 for x in dst) and state_hash(p) == before
    rejections.append(name)
before = state_hash(p)
alias = (F * 1024)(*([0.125] * 1024))
assert call("process", p, alias, 128, alias, 1024, 0, C.byref(Z(999))) == 1
assert state_hash(p) == before
rejections.append("input_output_alias")
process(p, 128, 0)
before = state_hash(p)
sentinel = Z(999)
assert call("count", p, 65536, 1, C.byref(sentinel)) == 6
assert sentinel.value == 999 and state_hash(p) == before
rejections.append("native_terminal_allocation_overrun")
# The native resize branch is supported, including its history reset.
count, _ = process(p, 65537, 1)
assert snapshot(p).capacity == 65537 + 1024
assert call("reset", p) == 0
assert snapshot(p).fresh == 1 and snapshot(p).capacity == 66561
d.rb_native_mode1_destroy(p)

for rin, rout, channels in [(7999, 48000, 2), (48000, 192001, 2),
                            (48000.5, 48000, 2), (48000, 48000, 0),
                            (math.nan, 48000, 2)]:
    p = P(123)
    assert call("create", rin, rout, channels, C.byref(p)) == 1 and p.value == 123
    rejections.append("invalid_create")

def pin(path):
    return {"path": str(path.relative_to(R)), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

report = {"scope": "Candidate-only safety/count consistency; not an independent sample oracle.",
          "target_execution": False, "compile": command, "passed": True,
          "source": [pin(SRC), pin(HDR)], "stream_controls": rows,
          "aggregate_controls": aggregate, "rejections": rejections}
(H / "controls/candidate-controls.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"passed": True, "streams": len(rows), "aggregate": len(aggregate),
                  "rejections": len(rejections)}))
