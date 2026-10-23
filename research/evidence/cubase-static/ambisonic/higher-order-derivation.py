"""Decode retained static evidence; no target execution or candidate expansion."""
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
THIN = HERE / "vstambiconverter.arm64.macho"
ORIGINAL = ROOT / "research/targets/downloads/partial-components-01/components/Cubase 15.app/Contents/VST3/vstambiconverter.vst3/Contents/MacOS/vstambiconverter"
EXPECTED_THIN = "e8341c6b31ac6b65cf7e8c18bdfbaa18ac24b20160b4287dc385b202eb29b883"
EXPECTED_ORIGINAL = "e803dd1390ee7989306b15c0fccca52e5d3097ae7a489dc6834f82b50ba485c5"
SLICE_OFFSET = 2162688

def digest(value):
    return sha256(value).hexdigest()

thin_before, original_before = THIN.stat(), ORIGINAL.stat()
thin, original = THIN.read_bytes(), ORIGINAL.read_bytes()
assert digest(thin) == EXPECTED_THIN and digest(original) == EXPECTED_ORIGINAL
assert original[SLICE_OFFSET:SLICE_OFFSET+len(thin)] == thin
evidence = json.loads((HERE / "conversion-constant-tables.json").read_text())["structuredContent"]
read = evidence["normalized_result"]
raw = bytes.fromhex(read["bytes_hex"])
assert read["complete"] and read["returned_bytes"] == read["requested_bytes"] == len(raw) == 388
base = int(read["address"], 16)
# __TEXT address/file mapping was independently checked and retained previously.
old = json.loads((HERE / "first-order-byte-ranges.json").read_text())
text = next(s for s in old["segments"] if s["name"] == "__TEXT")
assert text["vmaddr"] == text["fileoff"] == 0
assert base + len(raw) <= text["filesize"]
assert raw == thin[base:base+len(raw)]
assert digest(raw) == "c49accecf95f469477a7f57bcc31e6e35ff5d51ee1ff63479b9268bb5a3fc874"

tables = {}
provenance = []
for name, offset, fmt in [("map_A", 0, "16I"), ("map_B", 64, "16I"),
                          ("gain_A", 132, "16d"), ("gain_B", 260, "16d")]:
    length = struct.calcsize("<" + fmt)
    blob = raw[offset:offset+length]
    values = list(struct.unpack("<" + fmt, blob))
    tables[name] = values
    row = dict(name=name, address=hex(base+offset), thin_file_offset=base+offset,
               original_file_offset=SLICE_OFFSET+base+offset, length=length,
               bytes_hex=blob.hex(), sha256=digest(blob), values=values)
    if name.startswith("gain"):
        row["binary64_bits"] = [f"0x{x:016x}" for x in struct.unpack("<16Q", blob)]
        row["binary32_nearest_even_bits"] = [
            f"0x{struct.unpack('<I', struct.pack('<f', x))[0]:08x}" for x in values]
        row["binary32_nearest_even_values"] = [struct.unpack("<f", struct.pack("<f", x))[0]
                                               for x in values]
        row["narrowing_caution"] = "Reference nearest-even conversion; actual target FP control state is unobserved."
    provenance.append(row)

contracts = []
for count in (9, 16):
    for direction in ("A", "B"):
        scatter = tables["map_"+direction][:count]
        assert sorted(scatter) == list(range(count))
        gather = [scatter.index(j) for j in range(count)]
        gains = next(r for r in provenance if r["name"] == "gain_"+direction)
        equations = [dict(destination=j, source=gather[j], gain_index=j,
                          gain_binary64_bits=gains["binary64_bits"][j],
                          gain_binary32_nearest_even_bits=gains["binary32_nearest_even_bits"][j])
                     for j in range(count)]
        contracts.append(dict(channel_count=count, direction=direction,
                              normalized_parameter_condition="0 <= p < 0.5" if direction == "A" else "0.5 <= p <= 1",
                              source_to_destination=scatter, destination_to_source=gather,
                              destination_gain_binary64=gains["values"][:count],
                              destination_gain_binary64_bits=gains["binary64_bits"][:count],
                              destination_gain_binary32_nearest_even=gains["binary32_nearest_even_values"][:count],
                              destination_gain_binary32_nearest_even_bits=gains["binary32_nearest_even_bits"][:count],
                              per_destination_equations=equations))

composition = []
for count in (9, 16):
    for first, second in (("A", "B"), ("B", "A")):
        first_map, second_map = tables["map_"+first], tables["map_"+second]
        first_gain, second_gain = tables["gain_"+first], tables["gain_"+second]
        rows = []
        for source in range(count):
            middle = first_map[source]
            destination = second_map[middle]
            assert destination == source
            product = Fraction.from_float(first_gain[middle]) * Fraction.from_float(second_gain[destination])
            rows.append(dict(source=source, intermediate_destination=middle, final_destination=destination,
                             first_gain_index=middle, second_gain_index=destination,
                             exact_stored_coefficient_product=f"{product.numerator}/{product.denominator}",
                             product_decimal_for_display=float(product)))
        composition.append(dict(channel_count=count, order=first+"_then_"+second, rows=rows))

def unchanged(before, after):
    return (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)

assert unchanged(thin_before, THIN.stat()) and unchanged(original_before, ORIGINAL.stat())
(HERE / "higher-order-byte-provenance.json").write_text(json.dumps(dict(
    scope="Source bytes and static table decoding only; no target runtime validation",
    original_path=str(ORIGINAL), original_sha256=EXPECTED_ORIGINAL,
    thin_path=str(THIN), thin_sha256=EXPECTED_THIN,
    slice_offset=SLICE_OFFSET, slice_length=len(thin), source_slice_identical=True,
    retained_table_evidence_file="conversion-constant-tables.json", evidence_id=evidence["evidence_id"],
    read_address=hex(base), read_bytes=len(raw), read_sha256=digest(raw), read_matches_source=True,
    unused_padding=dict(address=hex(base+128), bytes_hex=raw[128:132].hex()),
    tables=provenance), indent=2)+"\n")
(HERE / "higher-order-table-contract.json").write_text(json.dumps(dict(
    scope="Static-derived channel operators; no target sample comparison",
    operation="For each destination j and frame n: y[j][n] = multiply_in_sample_precision(x[inverse(map)[j]][n], convert_stored_binary64_gain_to_sample_precision(gain[j])). Copy precedes destination-indexed gain.",
    float32_rounding_caution="Stored gains are binary64; FCVT S,D precedes vDSP_vsmul. Listed binary32 bits assume nearest-even rounding and are not evidence of the target FPCR setting.",
    contracts=contracts, coefficient_only_compositions=composition,
    composition_caution="Exact rational products assume direct buffer-index chaining, with no host channel reordering or other intermediate transform, and omit sample rounding and runtime behavior. Inverse permutation alone does not establish inverse operators. Gains belong to destination indices. These records are a disconfirmation check, not measured round-trip output."), indent=2)+"\n")
print("Decoded 4 tables and 4 channel/direction contracts; source bytes verified.")
