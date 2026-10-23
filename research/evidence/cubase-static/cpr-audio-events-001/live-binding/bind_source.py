"""Recheck concrete original-image dispatch, constants and imported operations."""
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
    (0x1047e7db8, {0x40: 0x101f17150, 0x80: 0x101f2bf2c,
                   0x138: 0x101f17eb8}),
    (0x1047e7fb0, {0: 0x101f2cc1c, 0x20: 0x101f2cc94,
                   0x28: 0x101f2ccb8, 0x38: 0x101f2cd44,
                   0x40: 0x101f2cd68, 0x48: 0x101f2cd84}),
    (0x1047e80c8, {0x48: 0x101f2d0dc}),
    (0x104e201e0, {0x78: 0x102fc7528, 0x80: 0x102fc7544,
                   0x98: 0x102fc7564}),
    (0x1047d9968, {0x78: 0x102fc7528, 0x98: 0x102fc7564}),
    (0x1046b32e0, {0: 0x1019807c8, 8: 0x10198085c}),
    (0x1047ac688, {0x608: 0x101d41b8c}),
    (0x1047ad0e0, {0: 0x101d40088}),
    (0x1047ad100, {8: 0x101d3f7d8}),
]:
    for slot, expected in slots.items():
        r = s.region(table + slot, 8)
        actual = int.from_bytes(bytes.fromhex(r["bytes_hex"]), "little")
        assert actual == expected, (hex(table), hex(slot), hex(actual))
        r.update(table=hex(table), slot=hex(slot), target=hex(actual))
        cells.append(r)

identities = []
for table, typeinfo, name, text in [
    (0x1047e7db8, 0x1047e7f88, 0x103b01170,
     "N9Steinberg11AudioEngine10VstOpTrackE"),
    (0x1047ac688, 0x1047ad1c8, 0x103ae5bb9,
     "N9Steinberg15VSTAudioChannelE"),
    (0x1046b2f50, 0x1046b3300, 0x103aa38f8,
     "N9Steinberg12AudioProcess8Audition12StreamPlayerE"),
]:
    assert bytes.fromhex(s.region(table - 8, 8)["bytes_hex"]) == struct.pack("<Q", typeinfo)
    assert bytes.fromhex(s.region(typeinfo + 8, 8)["bytes_hex"]) == struct.pack("<Q", name)
    r = s.region(name, len(text) + 1)
    assert bytes.fromhex(r["bytes_hex"]) == text.encode() + b"\0"
    r.update(table=hex(table), typeinfo=hex(typeinfo), literal=text)
    identities.append(r)

spans = []
for label, start, end in [
    ("VstOpTrack vptr/callback/provider initialization", 0x101f2bbcc, 0x101f2bc34),
    ("Callback admission and window arithmetic", 0x101f2c478, 0x101f2c528),
    ("Sentinel and channel loops", 0x101f2c528, 0x101f2c628),
    ("Transport prefix decision and zeroing", 0x101f2c628, 0x101f2c6dc),
    ("Signed offset setter", 0x101f17ed8, 0x101f17f00),
    ("Engine rate and reciprocal setter", 0x102fc756c, 0x102fc758c),
    ("Audition player callback registration", 0x101980550, 0x10198066c),
    ("Ordinary channel initialized callback and fill-provider vptrs", 0x101d3b9e0, 0x101d3b9f0),
    ("Ordinary channel embedded timeline buffer initialization", 0x101d3ba40, 0x101d3ba7c),
    ("Ordinary channel final fill-provider assignment", 0x101d3bcf8, 0x101d3bd04),
    ("Timeline buffer fill dispatch", 0x101d0ce48, 0x101d0ce74),
    ("Observed event source and gained accessor", 0x101d3ef58, 0x101d3f0c4),
    ("Observed event gain/seek/read call sequence", 0x101d3f260, 0x101d3f2d4),
]:
    r = s.region(start, end - start)
    r["label"] = label
    spans.append(r)

rate = s.region(0x103ade670, 16)
rate["values"] = struct.unpack("<2d", bytes.fromhex(rate["bytes_hex"]))
assert rate["values"] == (44100.0, 1.0 / 44100.0)

data, sections, pos = s.data, [], 32
for _ in range(struct.unpack_from("<I", data, 16)[0]):
    cmd, length = struct.unpack_from("<II", data, pos)
    if cmd == 0x19:
        for i in range(struct.unpack_from("<I", data, pos + 64)[0]):
            at = pos + 72 + 80 * i
            address, size, offset = struct.unpack_from("<QQI", data, at + 32)
            flags, reserved1, reserved2 = struct.unpack_from("<III", data, at + 64)
            sections.append((address, size, offset, flags, reserved1, reserved2))
    elif cmd == 2:
        symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", data, pos + 8)
    elif cmd == 0xb:
        indirectoff, indirectcount = struct.unpack_from("<II", data, pos + 56)
    pos += length
imports = []
for stub, expected in [(0x103881008, "_bzero"), (0x103881560, "_memcpy")]:
    sec, = [r for r in sections if r[0] <= stub < r[0] + r[1] and r[3] & 255 == 8]
    idx = sec[4] + (stub - sec[0]) // sec[5]
    assert idx < indirectcount
    symbol = struct.unpack_from("<I", data, indirectoff + idx * 4)[0]
    assert symbol < nsyms
    strx = struct.unpack_from("<I", data, symoff + symbol * 16)[0]
    name = data[stroff + strx:data.index(0, stroff + strx, stroff + strsize)].decode()
    assert name == expected
    r = s.region(stub, sec[5])
    r.update(symbol=name, indirect_index=idx, symbol_index=symbol)
    imports.append(r)

prior = []
for path in [
    "renderer-selection/finding.json",
    "renderer-selection/pass6/native-10197fef4.txt",
    "renderer-selection/pass6/function-10197fef4.json",
    "live-consumer/finding.json",
    "live-consumer/original-bindings.json",
    "rate-selection/finding.json",
]:
    p = HERE.parent / path
    prior.append(dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size,
                      sha256=hashlib.sha256(p.read_bytes()).hexdigest()))

out = dict(source_sha256=s.PIN, dispatch_cells=cells, identities=identities,
           instruction_spans=spans, engine_initial_rate=rate, imports=imports,
           prior_immutable_evidence=prior, target_execution=False,
           limits=["Static bindings, not observed host instance/configuration.",
                   "Ordinary timeline consumer retained as next-work evidence; "
                   "provider+0x1610 and precise event-coordinate contract remain unclosed."])
(HERE / "original-bindings.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(dict(dispatch_cells=len(cells), identities=len(identities),
                      spans=len(spans), imports=len(imports))))
