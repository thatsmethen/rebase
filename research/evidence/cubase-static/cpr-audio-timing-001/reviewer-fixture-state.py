#!/usr/bin/env python3
"""Bounded template tempo tails/variation observations, no native execution."""
from pathlib import Path
import hashlib
import importlib.util
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location("probe", ROOT/"scripts/cpr_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def objects(x):
    if isinstance(x, dict):
        if x.get("kind") == "object":
            yield x
        for v in x.values():
            yield from objects(v)
    elif isinstance(x, list):
        for v in x:
            yield from objects(v)


def fixed_attrs(a, r):
    at = r.pos
    n = r.number("I")
    assert n <= 10000
    rows, seen = [], set()
    for _ in range(n):
        start = r.pos
        key, code = r.number("I"), r.number("H")
        assert key not in seen
        seen.add(key)
        if code in (1, 0x801):
            value = r.number("q")
        elif code in (2, 0x22):
            value = a.object(r)
            if value.get("class") == "MTrackVariationCollection":
                value["reviewer_decoded"] = variation(a, value)
        else:
            raise ValueError((hex(start), hex(key), hex(code)))
        rows.append({"offset":start,"key":f"0x{key:08x}","type":f"0x{code:x}",
                     "value":value,"end":r.pos})
    return {"offset":at,"count":n,"fields":rows,"end":r.pos}


def variation(a, obj):
    assert obj["version"] == 0
    r = a.body(obj)
    index_at = r.pos
    index, flags, n = r.number("i"), r.number("H"), r.number("i")
    assert 0 <= n <= 10000
    rows = []
    for _ in range(n):
        child = a.object(r)
        assert child.get("class") == "MTrackVariation" and child["version"] == 0
        v = a.body(child)
        name = v.string()
        alternate = a.object(v)
        integer_at, integer = v.pos, v.number("i")
        assert v.pos == v.end
        child["reviewer_decoded"] = {"name":name,"alternate_MDataNode":alternate,
                                     "trailing_i32_offset":integer_at,"trailing_i32":integer,
                                     "consumed_exactly":True}
        rows.append(child)
    assert r.pos == r.end
    return {"index_offset":index_at,"serialized_i32":index,"native_index_if_10_is_minus1":-1 if index==10 else index,
            "flags_u16":flags,"object_count":n,"objects":rows,"consumed_exactly":True,
            "body_hex":a.data[obj['body_offset']:obj['end']].hex(),
            "limit":"Count and nullness are structural; inertness/effective selection requires native post-read analysis."}


def main():
    rows = []
    for p in sorted((HERE.parent/"cpr-signature-001/fixtures").glob("*-signature-v01.json")):
        j = json.loads(p.read_text())
        data = (ROOT/j["source"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == j["sha256"]
        arr = next(r for r in j["roots"] if r["name"] == "Arrangement1")
        a = probe.Archive(data,arr["archive_start"],arr["archive_start"]+arr["archive_bytes"])
        obs = list(objects(arr))
        # Register only structurally retained declarations/objects, no string scan.
        for o in obs:
            for d in o.get("declarations",[]):
                a.classes[d["relative_offset"]] = d
            a.objects[o["relative_object_identity"]] = o
        tempos, signatures = [], []
        for o in obs:
            if o["class"] == "MTempoTrackEvent":
                prefix = o["decoded"]
                r = probe.Reader(data,prefix["opaque_attribute_tail_offset"],o["end"])
                track = fixed_attrs(a,r)
                items = [fixed_attrs(a,r) for _ in range(prefix["count"])]
                assert r.pos == r.end
                tempos.append({"object":{k:o[k] for k in ['body_offset','body_bytes','body_sha256','version']},
                               "prefix":prefix,"track_attributes":track,"item_attributes":items,
                               "consumed_exactly":True})
            if o["class"] == "MSignatureTrackEvent":
                for field in o["decoded"]["attributes"]:
                    if field["key_u32_be"] == 0x69435654:
                        obj = dict(field["value"])
                        obj["reviewer_decoded"] = variation(a,obj)
                        signatures.append(obj)
        rows.append({"source":j["source"],"source_sha256":j["sha256"],
                     "fixture_path":str(p.relative_to(ROOT)),"fixture_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                     "tempo_objects":tempos,"signature_variations":signatures})
    out = {"scope":"Exact structural template observations correlated with native collection/item reader widths; no target execution",
           "native_reader_addresses":{"collection":"0x1030f2cdc","object_vector":"0x1030f91c4","variation":"0x1017a4250"},
           "native_reader_status":"Communicated by independent native agent; lifecycle effect is separately reviewed, not inferred from null alone",
           "probe_sha256":hashlib.sha256((ROOT/'scripts/cpr_probe.py').read_bytes()).hexdigest(),"fixtures":rows}
    (HERE/"reviewer-template-state.json").write_text(json.dumps(out,indent=2)+"\n")
    for row in rows:
        t = row["tempo_objects"][0]
        var = next(f['value']['reviewer_decoded'] for f in t['track_attributes']['fields'] if f['key']=='0x69435654')
        print(Path(row['source']).stem,t['prefix']['selected_mode'],t['prefix']['count'],
              'tempo_variations',var['serialized_i32'],var['flags_u16'],var['object_count'],
              [c['reviewer_decoded']['alternate_MDataNode']['kind'] for c in var['objects']])


if __name__ == '__main__':
    main()
