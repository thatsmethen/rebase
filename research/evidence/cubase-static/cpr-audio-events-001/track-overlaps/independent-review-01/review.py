"""Independent static and analytical review; executes no proprietary code.

Creates one new result exclusively. Existing research and application files are
read only. This is an authored value-model comparison, not machine emulation.
"""
from pathlib import Path
from fractions import Fraction
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import math
import random
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[4]
PIN = 'dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
TARGET = ROOT / 'research/targets/derived/Cubase15-arm64'
image = TARGET.read_bytes()
assert hashlib.sha256(image).hexdigest() == PIN
assert struct.unpack_from('<I', image)[0] == 0xfeedfacf
# Independently resolve file-backed Mach-O segments; do not use source_tools.
segments = []
offset = 32
for _ in range(struct.unpack_from('<I', image, 16)[0]):
    command, length = struct.unpack_from('<II', image, offset)
    assert length >= 8 and offset + length <= len(image)
    if command == 0x19:
        name, va, vs, fo, fs = struct.unpack_from('<16sQQQQ', image, offset + 8)
        segments.append((va, fo, fs))
    offset += length


def read(va, count):
    mappings = [(base, file, size) for base, file, size in segments
                if base <= va and va + count <= base + size]
    assert len(mappings) == 1
    base, file, size = mappings[0]
    return image[file + va - base:file + va - base + count]


def sha(path):
    b = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def envelope(path):
    raw = json.loads(path.read_text())
    assert not raw.get('isError')
    return raw.get('structuredContent') or json.loads(raw['content'][0]['text'])


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def bits(value):
    return struct.pack('>d', value).hex()


def encoded(rows):
    return [[r[0], r[1], r[2], bits(r[3]), bits(r[4])] for r in rows]


verification = json.loads((STUDY / 'verification.json').read_text())
assert verification['source_sha256'] == PIN and verification['target_executed'] is False
files = [sha(STUDY / n) for n in ['verification.json', 'normalizer_model.py', 'branch_controls.py', 'branch-controls.json', 'finding.json', 'write_finding.py', 'seal_study.py']]
finding = json.loads((STUDY / 'finding.json').read_text())
assert finding['finding_id'] == 'TRACK-OVERLAPS-001'
assert finding['source_sha256'] == PIN and finding['target_executed'] is False
assert finding['native_runtime_comparisons'] == 0
for label in ['verification', 'analytical_controls', 'analytical_model']:
    row = finding[label]
    assert sha(ROOT / row['path']) == row
for row in finding['prior_findings']:
    assert sha(ROOT / row['path']) == row
    files.append(row)
for claim in finding['claims']:
    for support in claim['support']:
        expected = next(r for r in verification['functions'] if r['entry'] == support['entry'])
        assert expected['directory'] == support['directory']
        assert expected['evidence_ids'] == support['evidence_ids']
readbacks = []
for item in verification['functions']:
    folder = ROOT / item['directory']
    entry = int(item['entry'], 16)
    native = folder / f'native-{entry:x}.txt'
    lines = re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$', native.read_text(), re.M)
    assert len(lines) == item['original_native_words']
    assert [int(a, 16) for a, _, _ in lines] == list(range(entry, entry + len(lines) * 4, 4))
    for a, word, _ in lines:
        assert read(int(a, 16), 4) == int(word, 16).to_bytes(4, 'little')
    function = envelope(folder / f'function-{entry:x}.json')
    byte_record = envelope(folder / f'bytes-{entry:x}.json')
    bundle = envelope(folder / f'bundle-{entry:x}.json')
    q = byte_record['raw_result']
    assert q['complete'] and q['returned_bytes'] == q['requested_bytes'] == len(lines) * 4
    assert bytes.fromhex(q['bytes_hex']) == read(entry, q['returned_bytes'])
    assert [function['evidence_id'], byte_record['evidence_id']] == item['evidence_ids']
    assert len(bundle['result']['records']) == 2
    for record in [function, byte_record]:
        assert any(record == row for row in bundle['result']['records'])
    assert all(int(line.split(':')[0], 16) in range(entry, entry + len(lines) * 4, 4)
               for line in function['raw_result']['value']['assembly'])
    for pin in item['files']:
        assert sha(ROOT / pin['path']) == pin
    files.extend(item['files'])
    readbacks.append(dict(entry=item['entry'], words=len(lines), bytes=len(lines)*4,
                          evidence_ids=item['evidence_ids']))
for row in verification['dispatch']:
    assert int.from_bytes(read(int(row['table'], 16) + int(row['slot'], 16), 8), 'little') == int(row['target'], 16)
for row in verification['original_ranges']:
    r = row['source']
    raw = read(int(r['address'], 16), r['length'])
    assert raw == bytes.fromhex(r['bytes_hex']) and hashlib.sha256(raw).hexdigest() == r['sha256']
for folder in sorted(STUDY.glob('pass*')):
    if folder.is_dir():
        log = (folder / 'run.log').read_text().splitlines()
        assert log[-1] == 'CLOSED: isolated raw-slice MCP session'
        assert all(not json.loads(line)['isError'] for line in log[:-1])
        derivative = json.loads((folder / 'derivation.json').read_text())
        assert derivative['source_sha256'] == PIN
        for row in derivative['derivatives']:
            p = folder / row['raw_file']
            assert p.read_bytes() == read(int(row['entry'], 16), row['length'])
            assert sha(p)['sha256'] == row['raw_sha256']

model = load('normalizer_model', STUDY / 'normalizer_model.py')
control = load('review_existing_controls', STUDY / 'branch_controls.py')
epsilon = struct.unpack('>d', bytes.fromhex('3f1a36e2eb1c432d'))[0]
assert model.EPSILON == epsilon and bits(model.INITIAL_WATERMARK) == 'c14b774000000000'


@dataclass(eq=False)
class Node:
    event: int
    ordinal: int
    priority: int
    start: float
    end: float
    prev: object = None
    next: object = None


def independent_linked(source):
    """Separately authored linked value algorithm with rational-rounded distance.

    Different container representation and exact-rational subtraction verify
    numerical and successor handling; shared static inference is still a limit.
    """
    head = tail = None
    count = 0
    out = []
    watermark = -3600000.0

    def unlink(n):
        nonlocal head, tail
        if n.prev is None: head = n.next
        else: n.prev.next = n.next
        if n.next is None: tail = n.prev
        else: n.next.prev = n.prev
        n.prev = n.next = None

    def insert(n):
        nonlocal head, tail
        p = tail
        while p is not None and p.start > n.start:
            p = p.prev
        if p is None:
            n.next = head
            if head is None: tail = n
            else: head.prev = n
            head = n
        else:
            n.prev, n.next = p, p.next
            if p.next is None: tail = n
            else: p.next.prev = n
            p.next = n

    def far(a, b):
        difference = abs(Fraction.from_float(a) - Fraction.from_float(b))
        return float(difference) >= epsilon

    def publish(n):
        nonlocal watermark
        start = max(n.start, watermark)
        watermark = max(watermark, n.end)
        if n.end > start:
            out.append((n.event, n.ordinal, n.priority, start, n.end))

    # Do not sort source; initial append is separate from sorted reinsert.
    for r in source:
        n = Node(r.event, r.ordinal, r.priority, r.start, r.end, prev=tail)
        if tail is None: head = n
        else: tail.next = n
        tail = n
    while head is not None:
        current = head
        following = current.next
        unlink(current)
        while following is not None:
            count += 1
            if current.end < following.start or not far(current.end, following.start):
                publish(current)
                break
            if (current.priority, current.ordinal) > (following.priority, following.ordinal):
                successor = following.next
                unlink(following)
                if following.end >= current.end and far(following.end, current.end):
                    following.start = current.end
                    insert(following)
                following = successor
            else:
                if current.end >= following.end and far(current.end, following.end):
                    insert(Node(current.event, current.ordinal, current.priority, following.end, current.end))
                if current.start < following.start and far(current.start, following.start):
                    current.end = following.start
                    publish(current)
                break
        else:
            publish(current)
    return out, count


old_controls = json.loads((STUDY / 'branch-controls.json').read_text())
retained_control_count = 0
for row in old_controls['controls']:
    args = [model.Range(r['event'], r['ordinal'], r['priority'],
             struct.unpack('>d', bytes.fromhex(r['start_bits']))[0],
             struct.unpack('>d', bytes.fromhex(r['end_bits']))[0]) for r in row['input']]
    actual = model.values(model.normalize(args))
    separate, _ = independent_linked(args)
    expected = [[r['event'], r['ordinal'], r['priority'], r['start_bits'], r['end_bits']] for r in row['output']]
    assert encoded(actual) == encoded(separate) == expected
    retained_control_count += 1

# Multievent clustered endpoints exercise watermark and epsilon interactions
# absent from the producer's well-separated maximum-priority controls.
rng = random.Random(0xA0212026)
endpoints = sorted(set([0.0, math.nextafter(epsilon, 0), epsilon,
    math.nextafter(epsilon, math.inf), 2*epsilon, 3*epsilon, 0.5, 1.0,
    1+epsilon, math.nextafter(1+epsilon, 0), math.nextafter(1+epsilon, math.inf),
    2.0, 86400.0]))
priorities = [-2147483648, -100, -1, 0, 1, 2, 2147483647]
digest = hashlib.sha256()
for case in range(20000):
    count = rng.randrange(1, 25)
    starts = sorted(rng.randrange(0, len(endpoints)-1) for _ in range(count))
    ordinals = list(range(count))
    if case % 3 == 0: rng.shuffle(ordinals)
    args = [model.Range(i, ordinals[i], rng.choice(priorities), endpoints[a],
             endpoints[rng.randrange(a+1, len(endpoints))]) for i, a in enumerate(starts)]
    actual = model.values(model.normalize(args))
    separate, _ = independent_linked(args)
    assert encoded(actual) == encoded(separate), (case, args, actual, separate)
    assert all(x[4] <= y[3] for x, y in zip(actual, actual[1:]))
    assert all(r[3] >= args[r[0]].start and r[4] <= args[r[0]].end for r in actual)
    digest.update(json.dumps([encoded(model.values(args)), encoded(actual)], separators=(',',':')).encode())

# Independently repeat the mathematical producer controls without rewriting its
# original results. Reuse producer pair oracle as supplementary, not independent.
pair_count = 0
from itertools import combinations, product
pair_points = sorted(set([0., math.nextafter(epsilon,0.),epsilon,
    math.nextafter(epsilon, math.inf),2*epsilon,3*epsilon,1.,math.nextafter(1.,0.),
    math.nextafter(1.,math.inf),1.+epsilon,2.,86400.]))
windows = list(combinations(pair_points,2))
for (a,z),(b,y),ps in product(windows,windows,[(-2147483648,2147483647),(2,1),(1,1),(-1,0),(0,-1)]):
    if a > b: continue
    source = [model.Range(0,0,ps[0],a,z),model.Range(1,1,ps[1],b,y)]
    got = model.values(model.normalize(source))
    assert got == control.pair_oracle(*source)
    pair_count += 1
assert pair_count == old_controls['threshold_pair_cases'] == 12155

work_rows = []
for n in [16, 64, 128]:
    args = [model.Range(i,i,n-i,0.,float(i+1)) for i in range(n)]
    actual = model.values(model.normalize(args))
    separate, steps = independent_linked(args)
    assert actual == separate and steps == n*(n-1)//2 + n-2
    work_rows.append(dict(inputs=n, overlap_comparisons=steps, passed=True))

rate = 48000.0
period = 1.0/rate
event_start = .49/rate
fragment_start = 1.0 + .51/rate
context_offset = 0.0
snap = lambda x: int(x/period + (0.5 if x >= 0 else -0.5))
proper = snap(context_offset + (fragment_start-event_start))
incorrect = snap(context_offset) + snap(fragment_start) - snap(event_start)
assert proper == 48000 and incorrect == 48001

result = dict(
    schema_version=1,
    review_id='TRACK-OVERLAPS-INDEPENDENT-01',
    status='passed-with-explicit-bounds',
    source_sha256=PIN,
    source_bytes=len(image),
    target_executed=False,
    native_runtime_comparisons=0,
    owned_changes='Only this new independent-review-01 directory; existing evidence and application read only.',
    custody=dict(functions=len(readbacks),original_words=sum(r['words'] for r in readbacks),
        original_bytes=sum(r['bytes'] for r in readbacks),dispatch_slots=len(verification['dispatch']),
        focused_original_ranges=len(verification['original_ranges']),closed_raw_sessions=2,
        readbacks=readbacks),
    analytical_checks=dict(retained_cases=retained_control_count,repeated_pair_cases=pair_count,
        independent_linked_multievent_epsilon_cases=20000,linked_case_stream_sha256=digest.hexdigest(),
        quadratic_work_controls=work_rows,
        projection_counterexample=dict(rate=rate,event_start_bits=bits(event_start),
          fragment_start_bits=bits(fragment_start),context_offset_bits=bits(context_offset),
          correct_offset_frame=proper,incorrect_reused_rounded_offset_frame=incorrect)),
    semantic_findings=[
      dict(id='OVERLAP-REVIEW-1', addresses=['0x10020e884','0x10020e91c','0x10020e940','0x10020e954','0x10020e984'],
        conclusion='For finite values, overlap competition starts iff current.end >= next.start and abs(RN64(current.end-next.start)) >= binary64 bits3f1a36e2eb1c432d. Priority is signedInt32; larger wins. Equal priority compares signedInt32 original collector ordinal; greater-or-equal following ordinal takes following-wins. Unique bounded admitted ordinals make this later-original-order wins.'),
      dict(id='OVERLAP-REVIEW-2', addresses=['0x10020e988','0x10020e9b4','0x10020e9c8','0x10020ea1c','0x10020ea84','0x10020eab8','0x10020eb3c'],
        conclusion='Current wins: save next successor before unlink, remove following, retain tail at current.end only if following.end-current.end meets epsilon, reinsert after equal starts, then continue with the SAVED successor. Following wins: optionally clone current tail starting at following.end, preserve original identity/context/ordinal, publish current prefix only if start is strictly earlier and prefix difference meets epsilon. Native list callbacks/lifetimes are outside this value algorithm.'),
      dict(id='OVERLAP-REVIEW-3', addresses=['0x10020e8a8','0x10020ea38','0x10020eae8','0x10020eb58'],
        conclusion='All publications clamp start upward to the prior-end watermark, update watermark=max(prior,end), then keep only positive end-start. A subepsilon overlap bypasses priority, so earlier publication retains its overlap and following is later clamped. Do not replace the algorithm with a generic priority envelope at epsilon boundaries; positive subepsilon singleton ranges can survive.'),
      dict(id='OVERLAP-REVIEW-4', addresses=['0x10021372c','0x100213754','0x1007ddd78','0x10020f440','0x10020f480','0x10020f4a4','0x10020f4a8','0x10020f630','0x1002104fc'],
        conclusion='Clone copies ordinal/event/context and current range endpoints. Each normalized fragment is builder-projected from ORIGINAL event start and ORIGINAL context offset: RN64(contextOffset+RN64(fragmentStart-originalStart)). Start/end/offset are independently snapped, stored coordinates roundtrip, concrete getterEnd is recomputed, then native-reader quantization occurs. Snapped end<=start means omit that fragment; never trim an already-rounded whole-event segment.'),
      dict(id='OVERLAP-REVIEW-5', addresses=['0x1000ee2f0','0x10221d068','0x1000ea130','0x10020e940','0x10020e984','0x100210590','0x1002105b4'],
        conclusion='All saved Int32 priority values are admissible to the reviewed complete plain-track context. Serialization writes four bytes to MAudioEvent+80 with no range clamp; the bound virtual getter returns them; comparisons are signed. The already-reviewed fresh/default filter and collector do not depend on priority. On the no-neighbor/no-fade/zero-auto-fade builder path, normalized range/event/context and event gain are used and no event priority field is forwarded to PAudioSegment. This supports a track-specific priority override while retaining conservative single-event API guards; it is not a global claim that priority has no other consumers.'),
    ],
    integration_contract=[
      'Retain exact complete membership and original source/media identities; every counted event must pass the same direct-track, fresh-root-mode0, saved-clock, no-lanes, no-fades, immutable-attributes and supported-media predicates. Fully occluded contributors remain in membership and media checks.',
      'Permit all saved Int32 priorities only within the complete-track normalizer context; do not change saved priority or enable unsupported single-event/export paths incidentally.',
      'Require finite nonnegative positive canonical ranges in original chronological source order. Do not sort input. Generate unique original admitted ordinals before normalization and preserve them across all splits. Counted index matches admitted order only because every child passes unchanged.',
      'Use binary64 epsilon bits3f1a36e2eb1c432d and separate subtraction/absolute-value comparisons; equality enters threshold branches. Preserve publication watermark and saved-successor/reinsertion behavior.',
      'Keep immutable original eventStart/eventEnd/contextOffset with each fragment. Reproject through builder and then reader, preserving empty-fragment disposition and all source-capacity/rate checks. Do not substitute raw media rate for saved builder/reader rate.',
      'Verify all source/media before installing playback. Fragments of one event may share immutable decoded media but identity, gain, original ordinal and independently projected offset stay attached.',
      'Add exact PCM selection and offset tests for crossing, nested, equal-start/range, signed minimum/maximum, older split tails, epsilon neighbors, snapped-empty fragments, boundary seeks, complete occlusion and missing/changed occluded media.',
      'Expose and test input/fragment/work/sample limits as reconstruction bounds. The existing4000000-comparison guard is not a native bound and does not admit every4096-input pattern. Fail atomically rather than publishing a partial track on exhaustion.',
    ],
    blockers=[],
    qualifications=[
      'This review admits static reconstruction of the stated value path, not hosted application equivalence or target runtime behavior. Original target/proprietary components remained unexecuted.',
      'Native priority getters are called repeatedly; the reconstruction assumes immutable restored MAudioEvent state. Host callback mutation, recursive container contributors, alternate filters/root modes, lanes, fades, mixing and object lifetime/allocation failure are outside this contract.',
      'Independent linked implementation changes representation and distance arithmetic but is still derived from the same manually interpreted native algorithm; it is not an independent target oracle.',
      'Source corpus contains retained raw analysis intervals with omitted imports/globals; original-image readbacks validate words and dispatch bindings, not blanket control-flow completeness.',
      'No application integration or app tests were performed by this review. Existing application files were inspected only; final integrated source needs its own checks.',
      'Quadratic work pattern proved and checked through128inputs: same start, increasing ends, descending priorities gives n(n-1)/2+n-2 comparisons. At4096 this formula implies8390654, exceeding existing model guard; full-size case was not executed.',
    ],
    reviewed_input_files=files,
    final_finding_review=dict(finding=sha(STUDY/'finding.json'),passed=True,
      claim_ids=[c['id'] for c in finding['claims']],
      notes=['All four claims match the reviewed finite plain-track path; claim1 headline is read with claim3 epsilon qualification.',
        'The explicit four-million-comparison qualification correctly narrows the4096-input statement.',
        'Builder-snapped-empty omission and fully occluded contributor accounting are accurately stated.']),
    reviewer_script=sha(Path(__file__)),
)
with (HERE/'review.json').open('x') as f:
    json.dump(result,f,indent=2)
    f.write('\n')
print(json.dumps(dict(status=result['status'],functions=len(readbacks),retained_cases=retained_control_count,
    repeated_pair_cases=pair_count,independent_clustered_cases=20000,result=sha(HERE/'review.json'))))
