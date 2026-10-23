#!/usr/bin/env python3
"""Independent envelope/reference/sample checks for symbolic parser controls.

This uses the pre-existing bounded cpr_probe reader, not the fixture writer.
It does not execute Cubase or validate opaque native ancillary object bodies.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("existing_cpr_probe", ROOT / "scripts/cpr_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def float_bits_from_signed24(n):
    if n == 0: return 0
    a = abs(n); top = a.bit_length()-1
    return (0x80000000 if n < 0 else 0) | ((top-23+127)<<23) | ((a<<(23-top))&0x7fffff)


def verify(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    rows = []
    for control in manifest["controls"]:
        path = folder / control["path"]; raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == control["sha256"]
        result = probe.probe(path)
        node = result["roots"][0]["decoded"]["root"]["track_list"]["decoded"]["children"][0]["node"]["decoded"]
        if control["name"] == "missing-counted-event":
            assert node["count"] == 1 and node["opaque_tail_bytes"] > 0
            rows.append(dict(name=control["name"], result="reduced count leaves unconsumed object bytes",
                             unconsumed=node["opaque_tail_bytes"]))
            continue
        assert node["opaque_tail_bytes"] == 0
        objects = control["structure"]["objects"]
        identities = {o["identity_offset"]:o for o in objects}
        assert len(identities) == len(objects)
        origin = control["structure"]["archive_origin"]
        for obj in objects:
            assert struct.unpack_from(">I",raw,obj["identity_offset"])[0] == obj["payload_bytes"]
            assert obj["payload_offset"] + obj["payload_bytes"] == obj["end"]
        for ref in control["structure"]["references"]:
            target = origin + struct.unpack_from(">I",raw,ref["offset"])[0]
            assert target == ref["target"] and target in identities and target < ref["offset"]
        events = [o for o in node["children"] if o.get("class") == "MAudioEvent"]
        assert len(events) == len(control["events"])
        assert len({o["relative_object_identity"] for o in events}) == len(events)
        actual = []
        for obj, expected in zip(events,control["events"]):
            prefix = obj["event_prefix"]
            assert prefix["unbound_word"] == 0
            assert prefix["unbound_f64_a"] == expected["ticks"]
            assert prefix["unbound_f64_b"] == expected["frames"]
            assert prefix["unbound_f64_c"] == expected["source_frame"]
            # Fixed120 BPM gives exactly .5 seconds/beat and480ticks/beat.
            assert expected["ticks"] / 960 * 44100 == expected["first_frame"]
            actual.append(dict(identity=obj["size_offset"], first=expected["first_frame"],
                end=expected["first_frame"]+expected["frames"], source=expected["source_frame"]))
        unknown = [o["class"] for o in node["children"] if o.get("class") != "MAudioEvent"]
        assert unknown == (["UnverifiedControlEvent"] if control["name"] == "unknown-child" else [])
        ordered = all(a["first"] < b["first"] for a,b in zip(actual,actual[1:]))
        disjoint = all(a["end"] <= b["first"] for a,b in zip(actual,actual[1:]))
        rows.append(dict(name=control["name"], count=node["count"], events=actual,
                         chronological=ordered, disjoint=disjoint, unknown_classes=unknown,
                         references_checked=len(control["structure"]["references"])))
    media = folder / manifest["media"]["path"]; raw = media.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["media"]["sha256"]
    assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE" and raw[36:40] == b"data"
    assert struct.unpack_from("<IHHIIHH",raw,16) == (16,1,2,44100,264600,6,24)
    assert struct.unpack_from("<I",raw,40)[0] == 1058400*6 == len(raw)-44
    extrema=[8388608,-8388609]
    for f in range(1058400):
        for c in range(2):
            at=44+f*6+c*3
            n=int.from_bytes(raw[at:at+3],"little",signed=True)
            expected=((f*(7919 if c==0 else 104729)+c*12345)%1048576)-524288
            assert n==expected
            bits=struct.unpack("<I",struct.pack("<f",n/8388608))[0]
            assert bits==float_bits_from_signed24(n)
            extrema=[min(extrema[0],n),max(extrema[1],n)]
    return dict(status="passed bounded symbolic-control verification", target_executed=False,
        classification="app-parser and independent sample-composition controls, not native-valid CPR",
        controls=rows, sample_values_checked=2116800, signed24_extrema=extrema,
        source_and_evidence=[pin(Path(__file__)),pin(ROOT/"scripts/cpr_probe.py"),pin(folder/"manifest.json")],
        limitations=["No current Swift importer or playback API was invoked by this verifier; parent integration tests must establish those results.",
                     "Minimal opaque ancillary bodies are not proved native-valid. Counted relationships and signal expectations do not establish Cubase execution or roundtrip compatibility."])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("folder",type=Path);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();result=verify(a.folder.resolve())
    with a.out.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print(json.dumps(pin(a.out.resolve())))


if __name__ == "__main__": main()
