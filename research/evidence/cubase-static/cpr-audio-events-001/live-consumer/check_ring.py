"""Independent FIFO/word oracle for a candidate value operation, not target execution."""
from pathlib import Path
import ctypes as c
import hashlib
import json
import random
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = ROOT / "Application/Sources/RebaseTimingDSP/cpr_live_stereo_ring.c"
HEADER = SOURCE.parent / "include/cpr_live_stereo_ring.h"
LIB = HERE / "candidate-ring.dylib"
COMMAND = ["clang", "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror",
           "-fno-fast-math", "-ffp-contract=off", "-frounding-math",
           "-dynamiclib", "-I", str(HEADER.parent), str(SOURCE), "-o", str(LIB)]
subprocess.run(COMMAND, check=True)
lib = c.CDLL(str(LIB))
fp = c.POINTER(c.c_float)

class State(c.Structure):
    _fields_ = [("left", fp), ("right", fp), ("w", c.c_int32), ("r", c.c_int32),
                ("submitted", c.c_int64), ("timeline", c.c_int64)]

class Result(c.Structure):
    _fields_ = [("copied", c.c_int32), ("silent", c.c_int32), ("timeline", c.c_int64)]

lib.rb_cpr_live_ring_init.argtypes = [c.POINTER(State), fp, fp]
lib.rb_cpr_live_ring_write.argtypes = [c.POINTER(State), fp, c.c_int32]
lib.rb_cpr_live_ring_consume.argtypes = [c.POINTER(State), fp, fp, c.c_int64,
                                       c.c_int64, c.c_uint8, c.c_uint8, c.POINTER(Result)]

left = (c.c_uint32 * 32768)()
right = (c.c_uint32 * 32768)()
state = State()
assert lib.rb_cpr_live_ring_init(c.byref(state), c.cast(left, fp), c.cast(right, fp)) == 0
rng = random.Random(0x100384638)
queue = []
submitted = consumed = timeline = 0
counts = {k: 0 for k in ["write", "would_block", "normal", "hold", "drain", "stop", "zero"]}
rows = []
digest = hashlib.sha256()
patterns = [0, 0x80000000, 0x3f800000, 0xbf800000, 0x00000001, 0x7f7fffff,
            0x7fc12345, 0xff800000]  # Pure stereo word copies do no FP arithmetic.
for iteration in range(1200):
    if iteration % 3 != 2:
        count = [16386, 16385, 1][iteration] if iteration < 3 else rng.choice(
            [0, 1, 2, 8191, 8192, 16384, 16385, 16386, rng.randrange(1, 4000)])
        words = [patterns[(submitted * 2 + i) % len(patterns)] ^
                 (rng.randrange(0, 2048) if i % 8 > 3 else 0)
                 for i in range(2 * count)]
        array = (c.c_uint32 * len(words))(*words)
        # Independent per-frame free-space predicate, rather than the
        # candidate's algebraically collapsed whole-request inequality.
        free = 32768 - len(queue)
        accepted = True
        for _ in range(count):
            if free < 16384:
                accepted = False
                break
            free -= 1
        before = bytes(state), bytes(left), bytes(right)
        status = lib.rb_cpr_live_ring_write(c.byref(state), c.cast(array, fp), count)
        assert status == (0 if accepted else 4), (iteration, count, len(queue), status)
        if accepted:
            queue.extend(zip(words[::2], words[1::2]))
            submitted += count
            counts["write"] += 1
        else:
            assert before == (bytes(state), bytes(left), bytes(right))
            counts["would_block"] += 1
        rows.append([iteration, "write", count, status, len(queue)])
    else:
        count = rng.choice([0, 1, 17, 8192, 32768, rng.randrange(1, 5000)])
        stopped, drain = (int(rng.randrange(8) == 0), int(rng.randrange(3) == 0))
        before_available = len(queue)
        if stopped:
            expected = [(0, 0)] * count
            taken = 0
            timeline += count
            counts["stop"] += 1
        elif len(queue) >= count:
            expected, queue = queue[:count], queue[count:]
            taken = count
            timeline += count
            counts["normal"] += 1
        elif drain:
            taken = len(queue)
            expected, queue = queue + [(0, 0)] * (count - taken), []
            timeline += count
            counts["drain"] += 1
        else:
            taken = 0
            expected = [(0, 0)] * count
            counts["hold"] += 1
        consumed += taken
        if count == 0:
            counts["zero"] += 1
        l = (c.c_uint32 * count)(*([0xaaaaaaaa] * count))
        r = (c.c_uint32 * count)(*([0xbbbbbbbb] * count))
        result = Result(-9, -9, -9)
        start = rng.choice([-100000, 0, 900000000])
        status = lib.rb_cpr_live_ring_consume(c.byref(state), c.cast(l, fp), c.cast(r, fp),
                                            start, start + count, stopped, drain, c.byref(result))
        assert status == 0
        assert list(zip(l, r)) == expected, (iteration, count, stopped, drain)
        assert (result.copied, result.silent, result.timeline) == (taken, count-taken, timeline)
        digest.update(bytes(l)); digest.update(bytes(r))
        rows.append([iteration, "consume", count, stopped, drain, before_available, taken, timeline])
    assert (state.w, state.r, state.submitted, state.timeline) == (
        submitted % 32768, consumed % 32768, submitted, timeline)
    assert (state.w - state.r) % 32768 == len(queue)
assert submitted > 32768 * 10 and consumed > 32768 * 10
assert all(counts[k] > 0 for k in counts)
report = {
    "status": "passed",
    "scope": "Optimized authored C against independent raw-word FIFO oracle; no target code or hardware",
    "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    "header_sha256": hashlib.sha256(HEADER.read_bytes()).hexdigest(),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "compiler": subprocess.check_output(["clang", "--version"], text=True).splitlines()[0],
    "command": COMMAND, "operation_count": len(rows), "branch_counts": counts,
    "submitted_frames": submitted, "consumed_frames": consumed, "timeline_frames": timeline,
    "all_output_words_sha256": digest.hexdigest(),
    "operations_sha256": hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest(),
    "target_execution_count": 0,
}
(HERE / "candidate-ring-check.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
