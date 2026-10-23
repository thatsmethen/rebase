"""Independent forward-only CPR automatic-fade ownership probe; no target execution.

The generic envelope/count walker is reused from the earlier retained probe.
Unknown payloads are retained as objects, never treated as inaudible. This probe
establishes the normal-reader saved state, not arbitrary runtime callback state.
"""
from pathlib import Path
import hashlib
import json
import math
import struct
import sys

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
import cpr_probe as p


def require(value, message):
    if not value:
        raise p.ProbeError(message)


def resolve(a, obj):
    if obj["kind"] == "null":
        return None
    if obj["kind"] == "object_reference":
        require(obj["target_known"], "unresolved object identity")
        return a.objects[obj["relative_target"]]
    return obj


def object(a, r, cls, version, nullable=False):
    token = a.object(r)
    obj = resolve(a, token)
    if obj is None:
        require(nullable, f"null {cls}")
    else:
        require(obj["class"] == cls and obj["version"] == version,
                f"unverified {cls} class/version")
    return token, obj


def numeric(a, r):
    count_at = r.pos
    n = r.number("i")
    require(0 <= n <= 10000 and n <= (r.end-r.pos)//6, "invalid numeric attribute count")
    rows, keys = [], set()
    for _ in range(n):
        at, key, type_ = r.pos, r.number("I"), r.number("H")
        require(key not in keys, "duplicate numeric attribute key")
        keys.add(key)
        if type_ in (2, 0x12, 0x22, 0x92):
            value = a.object(r)
            resolve(a, value)
        elif type_ == 8:
            value, _ = object(a, r, "CmString", 0, nullable=True)
        elif type_ in (1, 0x801):
            value = r.number("q")
        else:
            raise p.ProbeError(f"unsupported numeric attribute type {type_:x}")
        rows.append(dict(offset=at, key=f"{key:08x}", type=type_, value=value))
    return dict(count_offset=count_at, count=n, fields=rows, end=r.pos)


def setting(a, r):
    token, obj = object(a, r, "MAutoFadeSetting", 0, nullable=True)
    if obj is None:
        return dict(token=token, setting=None)
    body = a.body(obj)
    flags_at, flags = body.pos, body.number("H")
    duration_at, duration_bits = body.pos, body.number("Q")
    require(math.isfinite(struct.unpack(">d", struct.pack(">Q", duration_bits))[0]),
            "nonfinite auto-fade duration")
    curves = []
    for _ in range(4):
        curve, _ = object(a, body, "MLinearInterpolator", 0, nullable=True)
        curves.append(curve)
    require(body.pos == body.end, "trailing auto-fade setting bytes")
    return dict(token=token, setting=dict(object=obj, flags_offset=flags_at,
        flags=flags, duration_offset=duration_at, duration_bits=f"{duration_bits:016x}",
        interpolators=curves, parsed_end=body.pos))


def no_hidden_errors(value):
    if isinstance(value, dict):
        require(not any("decode_error" in k for k in value), "unsupported counted hierarchy")
        for child in value.values():
            no_hidden_errors(child)
    elif isinstance(value, list):
        for child in value:
            no_hidden_errors(child)


def inspect(data):
    # Discover Arrangement1 from its actual RIFF/ROOT/ARCH envelopes.
    r = p.Reader(data, 0, len(data))
    require(r.take(4) == b"RIFF" and r.number("I") == len(data)-12
            and r.take(4) == b"NUND", "invalid CPR container")
    found = None
    while r.pos < r.end:
        require(r.take(4) == b"ROOT", "missing ROOT")
        size = r.number("I")
        header = p.Reader(data, r.pos, r.pos+size)
        r.take(size)
        name, cls = header.string(terminated=False)["text"], header.string(terminated=False)["text"]
        require(header.pos == header.end and r.take(4) == b"ARCH", "invalid ROOT extent")
        size = r.number("I")
        start = r.pos
        r.take(size)
        if name == "Arrangement1":
            require(found is None and cls == "PArrangement", "duplicate or wrong arrangement")
            found = (start, r.pos)
    require(found is not None, "missing arrangement")
    a = p.Archive(data, *found)
    ar = p.Reader(data, *found)
    arr = a.object(ar)
    require(ar.pos == ar.end, "unconsumed arrangement archive")
    parsed = p.arrangement(a, arr)
    no_hidden_errors(parsed)
    root = parsed["root"]
    # These versions come only from structurally entered object headers.
    for cls, version in (("MEvent", 1), ("MTrackEvent", 2)):
        versions = {d["version"] for d in a.classes.values() if d["class"] == cls}
        require(versions == {version}, f"unverified {cls} base version")
    tracks = [o for o in list(a.objects.values()) if o.get("class") == "MAudioTrackEvent"]
    rows = []
    for track in tracks:
        require(track["version"] == 1, "unverified audio track event version")
        body = a.body(track)
        body.pos = track["opaque_tail_offset"]
        attrs = numeric(a, body)
        resource_token, resource = object(a, body, "MAudioTrack", 0)
        word_at, word = body.pos, body.number("i")
        number_at, number_bits = body.pos, body.number("Q")
        automation_token, automation = object(a, body, "MAutomationNode", 1, nullable=True)
        local = setting(a, body)
        require(body.pos == body.end, "trailing audio track event bytes")
        rows.append(dict(track_identity=track["size_offset"], track_payload=track["body_offset"],
            attribute_tail=attrs, resource_token=resource_token, resource=resource,
            word_offset=word_at, word=word, number_offset=number_at, number_bits=f"{number_bits:016x}",
            automation_token=automation_token, automation=automation, local=local, parsed_end=body.pos))
    body = a.body(root)
    body.pos = root["opaque_tail_offset"]
    attrs = numeric(a, body)
    list_at, list_word, count = body.pos, body.number("H"), body.number("i")
    require(0 <= count <= 10000 and count <= (body.end-body.pos)//4, "invalid root auxiliary list")
    auxiliary = [a.object(body) for _ in range(count)]
    for obj in auxiliary:
        require(resolve(a, obj) is not None, "null root auxiliary object")
    roles = []
    for cls, version, nullable in (("FNPath", 0, False), ("PPool", 5, False),
        ("MMarkerTrackEvent", 0, True), ("MTempoTrackEvent", 3, False), ("MSignatureTrackEvent", 3, False)):
        token, obj = object(a, body, cls, version, nullable)
        roles.append(dict(role=cls, token=token, object=obj))
    project = setting(a, body)
    table_at, count = body.pos, body.number("h")
    require(0 <= count <= 10000 and count <= (body.end-body.pos)//6, "invalid root event table")
    entries, keys = [], set()
    for _ in range(count):
        at, key = body.pos, body.number("h")
        require(key not in keys, "duplicate root event table key")
        keys.add(key)
        token = a.object(body)
        obj = resolve(a, token)
        require(obj is not None, "null root event table object")
        entries.append(dict(offset=at, key=key, token=token))
    loudness, _ = object(a, body, "MLoudnessTrackEvent", 0, nullable=True)
    require(body.pos == body.end, "trailing root bytes")
    for track in rows:
        effective = track["local"]["setting"] or project["setting"]
        track["effective_origin"] = "track" if track["local"]["setting"] is not None else "project" if effective else "unresolved_default"
        track["effective_flags"] = effective["flags"] if effective else None
        track["zero_flag_bypass"] = effective is not None and effective["flags"] == 0
    return dict(source_sha256=hashlib.sha256(data).hexdigest(), source_bytes=len(data),
        archive_start=found[0], root_identity=root["size_offset"], root_payload=root["body_offset"],
        root_attribute_tail=attrs, root_auxiliary_list=dict(offset=list_at, word=list_word, count=len(auxiliary), objects=auxiliary),
        root_roles=roles, project=project, root_event_table=dict(offset=table_at, entries=entries),
        loudness=loudness, root_parsed_end=body.pos, tracks=rows,
        limits=["Fresh normal-reader saved state only; no proprietary code was executed.",
                "Unknown attribute, automation, resource, pool and interpolator bodies remain opaque.",
                "Zero flags skip automatic fades only; they do not authorize whole-project audio playback."])


def main():
    base = ROOT / "research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/Cubase 15.app/Contents/Project Templates/Cubase Pro"
    rows = []
    for name, sha in (("LoFi Hip Hop", "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495"),
                      ("Classic House", "28db9a9e6aca3357e0758c4b985c4bbdfb4e1d9268502d53238f0ceb2733e892")):
        data = (base / (name + ".cpr")).read_bytes()
        require(hashlib.sha256(data).hexdigest() == sha, "fixture source hash mismatch")
        result = inspect(data)
        result["fixture"] = name
        rows.append(result)
    with (HERE / "source-forward-probe.json").open("x") as output:
        json.dump(dict(target_executed=False, fixtures=rows), output, indent=2)
        output.write("\n")
    print(json.dumps([dict(fixture=r["fixture"], root_end=r["root_parsed_end"],
        project_flags=r["project"]["setting"]["flags"], tracks=[dict(identity=t["track_identity"],
        effective_origin=t["effective_origin"], flags=t["effective_flags"], end=t["parsed_end"]) for t in r["tracks"]]) for r in rows]))


if __name__ == "__main__":
    main()
