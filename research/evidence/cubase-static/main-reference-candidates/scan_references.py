"""Read-only bounded address-materialization candidates, not semantic analysis."""
from bisect import bisect_right
from hashlib import sha256
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "research/targets/derived/Cubase15-arm64"
before = SOURCE.stat()
data = SOURCE.read_bytes()
assert struct.unpack_from("<I", data)[0] == 0xfeedfacf
segments, sections, starts = [], [], []
position = 32
for _ in range(struct.unpack_from("<I", data, 16)[0]):
    command, size = struct.unpack_from("<II", data, position)
    if command == 0x19:
        v = struct.unpack_from("<II16sQQQQIIII", data, position)
        segments.append(dict(name=v[2].rstrip(b"\0").decode(), address=v[3],
                             vm_size=v[4], offset=v[5], file_size=v[6]))
        for n in range(v[-2]):
            s = struct.unpack_from("<16s16sQQIIIIIIII", data, position + 72 + 80*n)
            sections.append(dict(name=s[0].rstrip(b"\0").decode(),
                                 segment=s[1].rstrip(b"\0").decode(),
                                 address=s[2], size=s[3], offset=s[4]))
    if command == 0x26:
        _, _, fs_offset, fs_size = struct.unpack_from("<IIII", data, position)
    position += size
text = next(s for s in segments if s["name"] == "__TEXT")
code = next(s for s in sections if s["name"] == "__text")
address, delta, shift = text["address"], 0, 0
for b in data[fs_offset:fs_offset+fs_size]:
    delta |= (b & 127) << shift
    if b & 128:
        shift += 7
    else:
        if delta == 0:
            break
        address += delta
        starts.append(address)
        delta, shift = 0, 0

def map_offset(offset):
    matches = [s for s in segments if s["offset"] <= offset < s["offset"]+s["file_size"]]
    assert len(matches) == 1
    s = matches[0]
    return s["address"] + offset - s["offset"]

def enclosing(address):
    i = bisect_right(starts, address) - 1
    return dict(start=hex(starts[i]), next_start=hex(starts[i+1]) if i+1 < len(starts) else None,
                note="LC_FUNCTION_STARTS predecessor; not proof of exact function end")

targets = []
for line in (ROOT / "research/evidence/cubase-static/main-string-candidates.txt").read_text().splitlines()[1:]:
    offset, label = line.split(" ", 1)
    offset = int(offset, 16)
    assert data[offset:offset+len(label)+1] == label.encode()+b"\0"
    pointers, at = [], 0
    pattern = struct.pack("<Q", map_offset(offset))
    while (at := data.find(pattern, at)) != -1:
        if at % 8 == 0:
            pointers.append(dict(file_offset=hex(at), address=hex(map_offset(at))))
        at += 1
    targets.append(dict(label=label, file_offset=hex(offset), address=hex(map_offset(offset)),
                        raw_aligned_pointer_occurrences=pointers))

target_by_address = {int(t["address"], 16): t["label"] for t in targets}
pages = {a & ~4095 for a in target_by_address}
hits = []
for relative, (word,) in enumerate(struct.iter_unpack("<I", data[code["offset"]:code["offset"]+code["size"]])):
    pc = code["address"] + relative * 4
    if word & 0x9f000000 not in (0x10000000, 0x90000000):
        continue
    immediate = ((word >> 5 & 0x7ffff) << 2) | (word >> 29 & 3)
    if immediate & (1 << 20):
        immediate -= 1 << 21
    if word & 0x9f000000 == 0x10000000:
        if pc + immediate in target_by_address:
            hits.append(dict(kind="ADR", at=hex(pc), target=hex(pc+immediate),
                             label=target_by_address[pc+immediate], function=enclosing(pc)))
        continue
    page = (pc & ~4095) + (immediate << 12)
    if page not in pages:
        continue
    register = word & 31
    for distance in range(1, 13):
        offset = code["offset"] + relative * 4 + 4 * distance
        if offset + 4 > code["offset"]+code["size"]:
            break
        add = struct.unpack_from("<I", data, offset)[0]
        if add & 0xff800000 != 0x91000000 or add >> 5 & 31 != register:
            continue
        value = page + ((add >> 10 & 4095) << (12 if add & (1 << 22) else 0))
        if value not in target_by_address:
            continue
        hits.append(dict(kind="ADRP_ADD_candidate", at=hex(pc), add_at=hex(pc+distance*4),
                         target=hex(value), label=target_by_address[value], adrp_register=register,
                         result_register=add & 31, intervening_instructions=distance-1,
                         status="Adjacent pair" if distance == 1 else "Requires clobber/control-flow validation",
                         function=enclosing(pc)))
after = SOURCE.stat()
assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) == (
    before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
result = dict(scope="Static address-materialization candidates; names establish no signal behavior",
              source=str(SOURCE), source_sha256=sha256(data).hexdigest(), source_bytes=len(data),
              scan="All aligned __text words; ADR or ADRP followed within12 instructions by matching ADD immediate. Intervening writes/branches not modeled; validate retained candidates in disassembly.",
              segments=segments, sections=sections, function_starts=dict(offset=fs_offset, bytes=fs_size,
              sha256=sha256(data[fs_offset:fs_offset+fs_size]).hexdigest(), count=len(starts)), targets=targets, hits=hits)
(OUT / "raw-reference-candidates.json").write_text(json.dumps(result, indent=2)+"\n")
print(json.dumps(dict(hits=hits, targets=targets), indent=2))
