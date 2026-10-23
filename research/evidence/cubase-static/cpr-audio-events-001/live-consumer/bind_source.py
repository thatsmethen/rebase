"""Pin concrete dispatch, imported zeroing and scalar instruction authority."""
from pathlib import Path
import hashlib, json, struct, sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as source

cells = []
for table, slots in [
    (0x104467eb0, {0xf8: 0x1003841a0, 0x138: 0x1003838c0,
                   0x140: 0x10038509c, 0x150: 0x1003838b0,
                   0x158: 0x100383890, 0x190: 0x100383688,
                   0x1e8: 0x100384ac4, 0x1f0: 0x100384638,
                   0x1f8: 0x100384a04}),
    (0x104468148, {0x18: 0x100384ce4}),
    (0x104468198, {0: 0x1003849e8, 8: 0x100384a64}),
]:
    for slot, expected in slots.items():
        row = source.region(table + slot, 8)
        target = int.from_bytes(bytes.fromhex(row["bytes_hex"]), "little")
        assert target == expected
        row.update(table=hex(table), slot=hex(slot), target=hex(target))
        cells.append(row)

literals = []
for address, expected in [
    (0x103937358, b"N9Steinberg20VSTAudioStreamPlayerE"),
    (0x103937338, b"N9Steinberg17AudioStreamPlayerE"),
    (0x1038e0ed7, b"VstOpTrack"),
]:
    row = source.region(address, len(expected) + 1)
    assert bytes.fromhex(row["bytes_hex"]) == expected + b"\0"
    row["literal"] = expected.decode()
    literals.append(row)
for table, typeinfo, name in [
    (0x104467eb0, 0x1044681f0, 0x103937358),
    (0x104467be8, 0x1044681a8, 0x103937338),
]:
    assert int.from_bytes(bytes.fromhex(source.region(table - 8, 8)["bytes_hex"]), "little") == typeinfo
    assert int.from_bytes(bytes.fromhex(source.region(typeinfo + 8, 8)["bytes_hex"]), "little") == name
    for address, size in [(table - 16, 16), (typeinfo, 24)]:
        row = source.region(address, size)
        row["name"] = "Original RTTI linkage"
        cells.append(row)
capacity = source.region(0x103937330, 8)
assert bytes.fromhex(capacity["bytes_hex"]) == struct.pack("<II", 32768, 0)

spans = []
for label, start, end in [
    ("Concrete factory and three vptr assignments", 0x1003838f0, 0x10038395c),
    ("Successful-open ring allocation and callback registration", 0x1003841a0, 0x100384624),
    ("Active producer half-capacity threshold and guards", 0x100384b24, 0x100384bb0),
    ("Stereo interleaved write, wrap and submitted counter", 0x100384c28, 0x100384c90),
    ("Consumer difference, stopped branch and availability", 0x100384650, 0x1003846f8),
    ("Consumer normal stereo per-channel copy", 0x1003847b0, 0x100384850),
    ("Consumer drain stereo per-channel copy", 0x100384850, 0x1003848c8),
    ("Consumer timeline counter and return", 0x1003849bc, 0x1003849e8),
    ("Callback receiver adjustment", 0x1003849e8, 0x100384a04),
    ("Writer receiver adjustment", 0x100384ce4, 0x100384cec),
    ("VstOpTrack callback registration", 0x101df4ea4, 0x101df4f50),
]:
    row = source.region(start, end - start)
    row["name"] = label
    spans.append(row)

data = source.data
sections, pos = [], 32
for _ in range(struct.unpack_from("<I", data, 16)[0]):
    command, size = struct.unpack_from("<II", data, pos)
    if command == 0x19:
        for index in range(struct.unpack_from("<I", data, pos + 64)[0]):
            at = pos + 72 + index * 80
            address, length, offset = struct.unpack_from("<QQI", data, at + 32)
            flags, reserved1, reserved2 = struct.unpack_from("<III", data, at + 64)
            sections.append((address, length, offset, flags, reserved1, reserved2))
    elif command == 2:
        symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", data, pos + 8)
    elif command == 0xb:
        indirectoff, indirectcount = struct.unpack_from("<II", data, pos + 56)
    pos += size
stub = 0x103881008
section, = [entry for entry in sections if entry[0] <= stub < entry[0] + entry[1]
            and entry[3] & 255 == 8]
index = section[4] + (stub - section[0]) // section[5]
assert index < indirectcount
symbol = struct.unpack_from("<I", data, indirectoff + index * 4)[0]
assert symbol < nsyms
strx = struct.unpack_from("<I", data, symoff + symbol * 16)[0]
name = data[stroff + strx:data.index(0, stroff + strx, stroff + strsize)].decode()
assert name == "_bzero"
imported = source.region(stub, section[5])
imported.update(symbol=name, symbol_index=symbol, indirect_index=index)

# Earlier exploratory table files remain unchanged; recheck their exact source bytes.
checked = []
for filename in ["player-tables.json", "player-callback-cells.json",
                 "selected_accessor-vtable.json", "selected-secondary-vtable.json"]:
    original = json.loads((HERE / filename).read_text())
    entries = original if isinstance(original, list) else [original]
    for row in entries:
        actual = source.region(int(row["address"], 16), row["length"])
        assert all(row[key] == actual[key] for key in
                   ["address", "file_offset", "length", "bytes_hex", "sha256"])
    checked.append(dict(path=filename, entries=len(entries),
                        sha256=hashlib.sha256((HERE / filename).read_bytes()).hexdigest()))

report = dict(source_sha256=source.PIN, dispatch_cells=cells, literals=literals,
              capacity=capacity, instruction_spans=spans, imported_zeroing=imported,
              exploratory_byte_checks=checked, target_execution=False,
              scope="Original-image byte and indirect-symbol bindings. No target or dependency execution.")
(HERE / "original-bindings.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(dict(cells=len(cells), literals=len(literals), spans=len(spans),
                      import_symbol=name)))
