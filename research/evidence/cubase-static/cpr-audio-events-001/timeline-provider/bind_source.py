"""Bind original-image tables and selected instruction spans without execution."""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s

cells = []
for table, slots in [
    (0x1047AC688, {0: 0x101D42E70, 0x660: 0x101D3E5A0}),
    (0x1047AD130, {0x18: 0x101D3E5A8, 0x20: 0x101D404F8,
                   0x28: 0x101D3E6F8}),
    (0x10444AA98, {0x118: 0x1001F9090, 0x1B0: 0x1001F96F8}),
    (0x10444ACC0, {0: 0x1001FD4F4, 0x18: 0x1001F9854,
                   0x20: 0x1001F96E8}),
    (0x104436BE0, {0xD0: 0x101A17CCC, 0xD8: 0x101A17CD4,
                   0xE0: 0x101A17CDC, 0xE8: 0x101A17CE4,
                   0xF0: 0x101A17CEC, 0xF8: 0x101A17D08,
                   0x100: 0x101A17D14, 0x108: 0x101A17D1C}),
]:
    for slot, expected in slots.items():
        region = s.region(table + slot, 8)
        actual = int.from_bytes(bytes.fromhex(region["bytes_hex"]), "little")
        assert actual == expected, (hex(table), hex(slot), hex(actual))
        region.update(table=hex(table), slot=hex(slot), target=hex(actual))
        cells.append(region)

spans = []
for label, start, end in [
    ("Concrete channel primary and secondary vptr assignments",
     0x101D3B958, 0x101D3BA14),
    ("Channel IID acceptance and adjusted interface result",
     0x101D42E84, 0x101D42ED8),
    ("MAudioTrack QI and selector interface installation",
     0x1001F90A8, 0x1001F9104),
    ("Provider setters", 0x101D3E5A0, 0x101D3E5B0),
    ("MAudioTrack rebuild then range invalidation",
     0x1001F9618, 0x1001F9678),
    ("Concrete segment start getter", 0x101A17CD4, 0x101A17CDC),
    ("Concrete segment end getter", 0x101A17D08, 0x101A17D14),
    ("Concrete segment offset getter", 0x101A17D1C, 0x101A17D24),
    ("Builder rate provider or explicit44100 fallback",
     0x10171C5A0, 0x10171C5C4),
    ("Builder constructs type10 sample datum",
     0x10020F320, 0x10020F338),
    ("Type10 datum reciprocal", 0x101C2267C, 0x101C2268C),
    ("Context event start and optional transform",
     0x1016E300C, 0x1016E30E4),
    ("Offset conversion: negate, delta conversion, negate",
     0x1016E3794, 0x1016E37D8),
    ("Finite event interval intersection and retained context",
     0x10020E474, 0x10020E550),
    ("Singleton range publication preserves positive interval",
     0x10020EA38, 0x10020EA84),
]:
    region = s.region(start, end - start)
    region["label"] = label
    spans.append(region)

jump = s.region(0x103ADA008, 18)
selector = bytes.fromhex(jump["bytes_hex"])[10]
assert 0x101C22600 + selector * 4 == 0x101C2267C
jump.update(type10_index=10, type10_target="0x101c2267c")

prior_paths = [
    "timeline-playback/finding.json",
    "timeline-playback/linkage.json",
    "event-rendering/finalization-finding.json",
    "event-rendering/processed-event-vtables.json",
    "event-rendering/pass1/function-10020f2e8.json",
    "event-rendering/pass1/native-10020f2e8.txt",
    "event-rendering/pass3/native-101a17ccc.txt",
    "event-rendering/pass3/native-101a17cec.txt",
    "event-rendering/pass3/native-101a17d14.txt",
    "event-rendering/pass4/native-1002115a0.txt",
    "event-rendering/pass7/native-1001f91a0.txt",
    "live-binding/finding.json",
    "live-binding/pass18/native-101d3b918.txt",
    "live-binding/pass21/native-101d3eb24.txt",
    "timebase/finding.json",
    "timebase/pass3/native-1016e2640.txt",
    "timebase/pass6/native-1016e4d98.txt",
]
prior = []
for relative in prior_paths:
    path = HERE.parent / relative
    raw = path.read_bytes()
    prior.append(dict(path=str(path.relative_to(ROOT)), bytes=len(raw),
                      sha256=hashlib.sha256(raw).hexdigest()))

output = dict(source_sha256=s.PIN, dispatch_cells=cells, instruction_spans=spans,
              type10_jump_table=jump, immutable_prior_evidence=prior,
              target_execution=False,
              limits=["Original-image static bindings, not a live hosted object.",
                      "The setter stores a pointer; it performs no retain/release itself.",
                      "Concrete receiver bindings are conditional on the captured classes.",
                      "Builder rate is a provider result or44100 fallback, not inferred "
                      "from an arbitrary AudioFile rate."])
(HERE / "original-bindings.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps(dict(dispatch_cells=len(cells), instruction_spans=len(spans),
                      prior_records=len(prior))))
