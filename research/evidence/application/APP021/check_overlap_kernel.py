"""Compare an isolated authored C kernel to retained analytical controls.

This runs Rebase code only. The reference executable remains unexecuted.
"""
from pathlib import Path
from datetime import datetime, timezone
import ctypes
import hashlib
import json
import math
import random
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE / 'overlap-kernel-check'
STUDY = ROOT / 'research/evidence/cubase-static/cpr-audio-events-001/track-overlaps'
sys.path.insert(0, str(STUDY))
from normalizer_model import Range, normalize, values, EPSILON


def pin(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


OUT.mkdir()
sources = [ROOT / 'Application/Sources/RebaseTimingDSP/cpr_track_overlap.c',
           ROOT / 'Application/Sources/RebaseTimingDSP/include/cpr_track_overlap.h']
before = [pin(path) for path in sources]
for path in sources:
    shutil.copy2(path, OUT / path.name)
command = ['clang', '-std=c11', '-O2', '-ffp-contract=off', '-dynamiclib',
           str(OUT / 'cpr_track_overlap.c'), '-I', str(OUT), '-o', str(OUT / 'kernel.dylib')]
with (OUT / 'compile.log').open('x') as log:
    compiled = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
assert compiled.returncode == 0
library = ctypes.CDLL(str(OUT / 'kernel.dylib'))


class NativeRange(ctypes.Structure):
    _fields_ = [('sourceIndex', ctypes.c_int32), ('ordinal', ctypes.c_int32),
                ('priority', ctypes.c_int32), ('start', ctypes.c_double), ('end', ctypes.c_double)]


kernel = library.rb_cpr_track_overlap_normalize
kernel.argtypes = [ctypes.POINTER(NativeRange), ctypes.c_int32,
                  ctypes.POINTER(NativeRange), ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)]
kernel.restype = ctypes.c_int
bits = lambda value: struct.pack('>d', value).hex()


def encode(rows):
    return [[r[0], r[1], r[2], bits(r[3]), bits(r[4])] for r in rows]


def invoke(source):
    inputs = (NativeRange * len(source))(*[NativeRange(r.event, r.ordinal, r.priority, r.start, r.end) for r in source])
    output = (NativeRange * 8192)()
    count = ctypes.c_int32(-1)
    status = kernel(inputs, len(source), output, 8192, ctypes.byref(count))
    assert status == 0, status
    assert 0 <= count.value <= 8192
    return [(r.sourceIndex, r.ordinal, r.priority, r.start, r.end) for r in output[:count.value]]


stream = hashlib.sha256()
retained = json.loads((STUDY / 'branch-controls.json').read_text())
for case in retained['controls']:
    def decode(row):
        return (row['event'], row['ordinal'], row['priority'],
                struct.unpack('>d', bytes.fromhex(row['start_bits']))[0],
                struct.unpack('>d', bytes.fromhex(row['end_bits']))[0])
    source = [Range(*decode(row)) for row in case['input']]
    got = encode(invoke(source))
    expected = encode([decode(row) for row in case['output']])
    assert got == expected, case['label']
    stream.update(json.dumps([case['label'], got]).encode())

rng = random.Random(0xA0021)
thresholds = [math.nextafter(EPSILON, 0), EPSILON, math.nextafter(EPSILON, math.inf)]
priorities = [-(1 << 31), -4, -1, 0, 1, 5, (1 << 31) - 1]
for number in range(20_000):
    starts = sorted(rng.choice([0., 1., 2., 7.]) + rng.randrange(5) * rng.choice(thresholds)
                    for _ in range(rng.randrange(1, 25)))
    source = [Range(i, i, rng.choice(priorities), start,
                    start + rng.choice([EPSILON / 4, *thresholds, 1., 2., 8.]))
              for i, start in enumerate(starts)]
    got = encode(invoke(source))
    expected = encode(values(normalize(source)))
    assert got == expected, (number, source, got, expected)
    stream.update(json.dumps([encode(values(source)), got]).encode())

# Independent interval expectations at both resource extremes. These do not
# use the retained model's four-million-comparison cap.
n = 4096
quadratic = [Range(i, i, n-i, float(i), float(n+i)) for i in range(n)]
q = invoke(quadratic)
assert q == [(0, 0, n, 0., float(n))] + [(i, i, n-i, float(n+i-1), float(n+i)) for i in range(1, n)]
nested = [Range(i, i, 1, float(i), float(2*n-i)) for i in range(n)]
r = invoke(nested)
expected = [(i, i, 1, float(i), float(i+1)) for i in range(n-1)]
expected += [(n-1, n-1, 1, float(n-1), float(n+1))]
expected += [(i, i, 1, float(2*n-i-1), float(2*n-i)) for i in reversed(range(n-1))]
assert r == expected and len(r) == 8191

# Invalid input and insufficient output capacity must not partially publish.
negative = []
for label, source, capacity in [
    ('unsorted', [Range(0, 0, 1, 2., 4.), Range(1, 1, 1, 1., 3.)], 4),
    ('duplicate-ordinal', [Range(0, 0, 1, 0., 2.), Range(1, 0, 2, 1., 3.)], 4),
    ('nan', [Range(0, 0, 1, math.nan, 1.)], 4),
    ('short-output', [Range(0, 0, 1, 0., 8.), Range(1, 1, 2, 2., 4.)], 2),
]:
    inputs = (NativeRange * len(source))(*[NativeRange(r.event, r.ordinal, r.priority, r.start, r.end) for r in source])
    output = (NativeRange * 4)()
    ctypes.memset(output, 0xA5, ctypes.sizeof(output))
    original = bytes(output)
    count = ctypes.c_int32(731)
    status = kernel(inputs, len(source), output, capacity, ctypes.byref(count))
    assert status != 0 and count.value == 731 and bytes(output) == original, label
    negative.append(dict(label=label, status=status, output_unchanged=True))

after = [pin(path) for path in sources]
record = dict(status='passed', created_utc=datetime.now(timezone.utc).isoformat(),
    target_executed=False, native_runtime_comparisons=0,
    scope='Exact authored C-kernel output bits against retained analytical models and independently stated resource-bound intervals; not reference runtime behavior.',
    source_before=before, source_after=after, live_source_unchanged=before == after,
    compiled_sources=[pin(OUT / path.name) for path in sources], compile_command=command,
    compile_exit_code=compiled.returncode, compiled_library=pin(OUT / 'kernel.dylib'),
    inputs=[pin(STUDY / 'branch-controls.json'), pin(STUDY / 'normalizer_model.py'), pin(Path(__file__))],
    retained_cases=len(retained['controls']), clustered_epsilon_cases=20_000,
    output_stream_sha256=stream.hexdigest(), quadratic_4096_passed=True,
    nested_4096_fragments=8191, transactional_rejections=negative)
with (OUT / 'result.json').open('x') as output:
    json.dump(record, output, indent=2)
    output.write('\n')
print(json.dumps(dict(status=record['status'], retained=record['retained_cases'],
    clustered=record['clustered_epsilon_cases'], nested_fragments=8191,
    live_source_unchanged=before == after, record=pin(OUT / 'result.json'))))
