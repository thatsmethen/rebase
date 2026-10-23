#!/usr/bin/env python3
"""Check authored overlap graph structure with the existing bounded CPR probe.

Writer-independent parsing is not independent reviewer authorship, native
serialization validity, or reference execution. No application code is run.
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
spec = importlib.util.spec_from_file_location("bounded_cpr_probe", ROOT/"scripts/cpr_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def record(path):
    raw = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def verify(folder):
    manifest = json.loads((folder/"manifest.json").read_text())
    assert manifest["target_executed"] is False and manifest["native_validity_established"] is False
    assert manifest["vendor_bytes_copied"] == 0
    checks = []
    for control in manifest["controls"]:
        path = folder/control["path"]; raw = path.read_bytes()
        assert len(raw) == control["bytes"] and hashlib.sha256(raw).hexdigest() == control["sha256"]
        result = probe.probe(path)
        node = result["roots"][0]["decoded"]["root"]["track_list"]["decoded"]["children"][0]["node"]["decoded"]
        assert node["opaque_tail_bytes"] == 0 and node["count"] == len(control["events"])
        observed = []
        file_identities = []
        objects = control["structure"]["objects"]
        identities = {x["identity_offset"] for x in objects}
        assert len(identities) == len(objects)
        origin = control["structure"]["archive_origin"]
        for obj in objects:
            assert struct.unpack_from(">I",raw,obj["identity_offset"])[0] == obj["payload_bytes"]
            assert obj["payload_offset"]+obj["payload_bytes"] == obj["end"]
        for ref in control["structure"]["references"]:
            target = origin+struct.unpack_from(">I",raw,ref["offset"])[0]
            assert target == ref["target"] and target in identities and target < ref["offset"]
        for ordinal, (obj, expected) in enumerate(zip(node["children"], control["events"])):
            assert obj["class"] == "MAudioEvent"
            prefix = obj["event_prefix"]
            assert prefix["unbound_word"] == 0
            assert [prefix["unbound_f64_"+x] for x in "abc"] == [expected[k] for k in ["ticks","frames","source_frame"]]
            clip = obj["audio_clip"]
            priority = struct.unpack_from(">i", raw, clip["end"]+4)[0]
            assert priority == expected["priority"]
            assert clip["media_path_object"]["decoded"]["filename"]["text"] == f"Overlap Signal {ordinal}.wav"
            file = next(x for x in objects if x["label"] == f"file{ordinal}")
            file_identities.append(file["identity_offset"])
            observed.append(dict(ordinal=ordinal,event_identity=obj["size_offset"],priority=priority,
                ticks=expected["ticks"],frames=expected["frames"],source_frame=expected["source_frame"]))
        assert len(set(file_identities)) == len(file_identities)
        assert struct.unpack_from(">f",raw,control["saved_rate_offset"])[0] == control["saved_rate"]
        checks.append(dict(name=control["name"],events=observed,distinct_source_files=len(file_identities),
            saved_rate=control["saved_rate"],references_checked=len(control["structure"]["references"])))
    values = 0
    for media in manifest["media"]:
        raw = (folder/media["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == media["sha256"] and len(raw) == media["bytes"]
        assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE" and raw[36:40] == b"data"
        assert struct.unpack_from("<IHHIIHH",raw,16) == (16,1,2,44100,264600,6,24)
        assert struct.unpack_from("<I",raw,40)[0] == manifest["media_frames"]*6 == len(raw)-44
        for frame in range(manifest["media_frames"]):
            for channel in range(2):
                at = 44+6*frame+3*channel
                actual = int.from_bytes(raw[at:at+3],"little",signed=True)
                expected = (frame*(7919 if channel == 0 else 104729)
                            +channel*12345+media["index"]*131071)%1048576-524288
                assert actual == expected
                values += 1
    return dict(status="passed bounded structural and integer PCM checks",target_executed=False,
        native_validity_established=False,application_executed=False,controls=checks,
        sample_values_checked=values,source_and_evidence=[record(Path(__file__)),record(ROOT/"scripts/cpr_probe.py"),
            record(folder/"manifest.json")],limitations=[
            "The existing probe checks envelope/reference/prefix structure; ancillary native object bodies remain unproved.",
            "The generator and this check share reviewer authorship. Parser implementation and integer sample recomputation are separate; independent reviewer acceptance is still required.",
            "Native overlap semantics and Swift sample composition require their separate static review and integration tests."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path); parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args(); result = verify(args.folder.resolve())
    with args.out.open("x") as f: json.dump(result,f,indent=2); f.write("\n")
    print(json.dumps(record(args.out.resolve())))
