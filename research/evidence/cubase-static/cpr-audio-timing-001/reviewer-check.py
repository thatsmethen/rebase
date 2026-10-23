#!/usr/bin/env python3
"""Independent immutable-source checks and rational IEEE-754 clock oracle.

No target code is run. The oracle models round-to-nearest/ties-to-even normal
finite arithmetic; it does not establish the target process FPCR environment.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import re
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "research/targets/derived/Cubase15-arm64"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def round_int(x):
    q, r = divmod(x.numerator, x.denominator)
    return q + (2*r > x.denominator or (2*r == x.denominator and q & 1))


def pow2(n):
    return F(2**n) if n >= 0 else F(1, 2**-n)


def encode(x, p, eb):
    """Round an exact rational to IEEE bits, with no floating calculations."""
    sign = int(x < 0)
    x = abs(x)
    if not x:
        return 0
    bias = (1 << (eb-1))-1
    e = x.numerator.bit_length()-x.denominator.bit_length()
    if x < pow2(e):
        e -= 1
    emin = 1-bias
    step = max(e, emin)-(p-1)
    m = round_int(x / pow2(step))
    if m == (1 << p):
        e += 1
        m >>= 1
    if e > bias:
        raise OverflowError("oracle finite domain exceeded")
    if e < emin and m < 1 << (p-1):
        exponent, fraction = 0, m
    else:
        exponent, fraction = max(e, emin)+bias, m-(1 << (p-1))
    return (sign << (eb+p-1)) | (exponent << (p-1)) | fraction


def decode(bits, p, eb):
    sign = -1 if bits >> (p+eb-1) else 1
    fraction = bits & ((1 << (p-1))-1)
    exponent = (bits >> (p-1)) & ((1 << eb)-1)
    assert exponent != (1 << eb)-1
    bias = (1 << (eb-1))-1
    if exponent:
        return sign * F((1 << (p-1))+fraction) * pow2(exponent-bias-(p-1))
    return sign * F(fraction) * pow2(1-bias-(p-1))


def r64(x):
    return decode(encode(x, 53, 11), 53, 11)


def vector(bpm_bits, input_bits, direction):
    bpm = decode(bpm_bits, 24, 8)
    x = decode(input_bits, 53, 11)
    period_bits = encode(F(60)/bpm, 24, 8)
    period = decode(period_bits, 24, 8)
    if direction == "ticks_to_seconds":
        intermediate = r64(period*x)
        output = r64(intermediate/480)
        reordered = r64(period*r64(x/480))
        ideal = r64(r64(F(60)*x)/r64(bpm*480))
    else:
        intermediate = r64(x/period)
        output = r64(intermediate*480)
        reordered = r64(r64(x*480)/period)
        ideal = r64(r64(x*bpm)*8)
    return {"direction": direction, "bpm_f32_bits": f"0x{bpm_bits:08x}",
            "bpm_decimal": str(float(bpm)), "input_f64_bits": f"0x{input_bits:016x}",
            "input_decimal": str(float(x)), "period_f32_bits": f"0x{period_bits:08x}",
            "period_f64_bits": f"0x{encode(period,53,11):016x}",
            "intermediate_f64_bits": f"0x{encode(intermediate,53,11):016x}",
            "result_f64_bits": f"0x{encode(output,53,11):016x}",
            "result_decimal": str(float(output)),
            "reordered_result_f64_bits": f"0x{encode(reordered,53,11):016x}",
            "ideal_bpm_formula_f64_bits": f"0x{encode(ideal,53,11):016x}"}


def main():
    data = SOURCE.read_bytes()
    assert sha(data) == "dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb"
    magic, cpu, subtype, ftype, ncmds, cmdsize, flags, reserved = struct.unpack_from("<8I", data)
    assert magic == 0xfeedfacf and cpu == 0x100000c
    pos, segments, fs = 32, [], None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, pos)
        if cmd == 0x19:
            name, va, vs, off, length = struct.unpack_from("<16sQQQQ", data, pos+8)
            segments.append((name.rstrip(b"\0").decode(), va, vs, off, length))
        if cmd == 0x26:
            fs = struct.unpack_from("<II", data, pos+8)
        pos += size
    assert pos == 32+cmdsize and fs
    def offset(va):
        for _, start, _, off, length in segments:
            if start <= va < start+length:
                return off+va-start
        raise ValueError(hex(va))
    fdata = data[fs[0]:sum(fs)]
    starts, acc, value, shift = [], 0x100000000, 0, 0
    for byte in fdata:
        value |= (byte & 127) << shift
        if byte & 128:
            shift += 7
        else:
            if not value:
                break
            acc += value
            starts.append(acc)
            value, shift = 0, 0
    records, hashes = [], {}
    manifests = sorted(HERE.glob("derivation*.json"))
    for manifest in manifests:
        hashes[manifest.name] = sha(manifest.read_bytes())
        for rec in json.loads(manifest.read_text())["derivatives"]:
            entry = int(rec["entry"], 16)
            end = int(rec["next_declared_function_start"], 16)
            idx = starts.index(entry)
            assert starts[idx+1] == end
            raw = (HERE/rec["raw_file"]).read_bytes()
            assert raw == data[offset(entry):offset(entry)+end-entry]
            assert sha(raw) == rec["raw_sha256"]
            npath = HERE/rec["original_native_disassembly"]
            native = re.findall(r"^([0-9a-f]+):\s+([0-9a-f]{8})\s", npath.read_text(), re.M)
            for a, word in native:
                assert struct.unpack_from("<I", data, offset(int(a,16)))[0] == int(word,16)
            assert len(native)*4 == len(raw)
            bp, fp = HERE/f"bytes-{entry:x}.json", HERE/f"function-{entry:x}.json"
            readback = json.loads(bp.read_text())["structuredContent"]["normalized_result"]
            assert readback["complete"] and bytes.fromhex(readback["bytes_hex"]) == raw
            dossier = json.loads(fp.read_text())["structuredContent"]["normalized_result"]
            native_addresses = {int(a,16) for a,_ in native}
            addresses = [int(line.split(":")[0],16) for line in dossier["assembly"]]
            assert all(a in native_addresses for a in addresses)
            records.append({"entry":rec["entry"],"bytes":len(raw),"sha256":sha(raw),
                            "native_words":len(native),"rea_addresses":len(addresses)})
            for p in [HERE/rec["raw_file"],npath,bp,fp]:
                hashes[p.name] = sha(p.read_bytes())
    vp = HERE/"tempo-interface-vtables.json"
    vslots = []
    for cls in json.loads(vp.read_text())["classes"]:
        for table in cls["tables"]:
            va = int(table["vtable"],16)
            # The retained table is prefixed by Itanium offset-to-top and RTTI.
            assert struct.unpack_from("<q",data,offset(va-16))[0] == table["offset_to_top"]
            for slot in table["slots"]:
                at = va+int(slot["slot"],16)
                assert struct.unpack_from("<Q",data,offset(at))[0] == int(slot["address"],16)
                vslots.append({"at":hex(at),"target":slot["address"]})
    hashes[vp.name] = sha(vp.read_bytes())
    extra_native = []
    for relative in ["cpr-objects-001/native/pass2/native-10173bdac.txt",
                     "cpr-objects-001/native/pass3/native-101c23184.txt",
                     "cpr-signature-001/pass4/native-101701cf4.txt"]:
        p = HERE.parent/relative
        rows = re.findall(r"^([0-9a-f]+):\s+([0-9a-f]{8})\s",p.read_text(),re.M)
        for address, word in rows:
            assert struct.unpack_from('<I',data,offset(int(address,16)))[0] == int(word,16)
        extra_native.append({"path":str(p.relative_to(ROOT)),"sha256":sha(p.read_bytes()),"native_words":len(rows)})
    for name in ['tempo-item-vtable.json','tempo-iterator-vtable.json','native-linkage.json']:
        p = HERE/name
        j = json.loads(p.read_text())
        if name == 'native-linkage.json':
            for span in j['spans']:
                at = offset(int(span['address'],16))
                assert data[at:at+span['length']] == bytes.fromhex(span['bytes_hex'])
        else:
            for slot in j['slots']:
                at = int(j['vtable'],16)+int(slot['slot'],16)
                target = slot.get('target',slot['address'])
                assert struct.unpack_from('<Q',data,offset(at))[0] == int(target,16)
        hashes[name] = sha(p.read_bytes())
    out = {"scope":"Independent raw-source and retained-evidence integrity, not runtime validation",
           "source_sha256":sha(data),"parsed_segments":segments,"function_starts_sha256":sha(fdata),
           "functions":records,"function_count":len(records),"bytes_checked":sum(r['bytes'] for r in records),
           "native_words_checked":sum(r['native_words'] for r in records),
           "rea_addresses_checked":sum(r['rea_addresses'] for r in records),
           "vtable_slots_checked":vslots,"additional_native_linkage":extra_native,"input_sha256":hashes}
    (HERE/"reviewer-source-checks.json").write_text(json.dumps(out,indent=2)+"\n")
    vectors = []
    for bpm in [F(65),F(70),F(92),F(253,2),F(120)]:
        bb = encode(bpm,24,8)
        for direction, inputs in [("ticks_to_seconds",[F(1),F(14880),F(123456789,1000)]),
                                  ("seconds_to_ticks",[F(1),F(1,44100),F(600)])]:
            vectors.extend(vector(bb,encode(x,53,11),direction) for x in inputs)
    # Adjacent inputs and a non-decimal f32 BPM discriminate operation order.
    vectors.extend(vector(0x42fd0001,bits,d) for d in ["ticks_to_seconds","seconds_to_ticks"]
                   for bits in [0x3ff0000000000001,0x407e000000000001,0x40f23456789abcde])
    assert any(v["result_f64_bits"] != v["reordered_result_f64_bits"] for v in vectors)
    (HERE/"reviewer-fixed-clock-vectors.json").write_text(json.dumps({
        "scope":"Analytical golden vectors from native instruction contract; no target runtime output",
        "rounding":"Exact Fraction arithmetic; each f32/f64 operation rounds nearest, ties to even",
        "preconditions":"Positive finite BPM and inputs, normal finite intermediates; FPCR not observed",
        "ticks_to_seconds":"p=round32(60/BPM); round64(round64(double(p)*ticks)/480)",
        "seconds_to_ticks":"p=round32(60/BPM); round64(round64(seconds/double(p))*480)",
        "integer_bits_encoding":"Hex numerical bit pattern; no byte-endian ambiguity",
        "vectors":vectors},indent=2)+"\n")
    print(json.dumps({"functions":len(records),"native_words":out["native_words_checked"],
                      "vectors":len(vectors),"reordering_discriminators":sum(v['result_f64_bits']!=v['reordered_result_f64_bits'] for v in vectors)}))


if __name__ == "__main__":
    main()
