#!/usr/bin/env python3
"""Read-only, bounded CPR structure probe. No Cubase execution or generic importer.

Only explicitly entered container/object paths are parsed: no regex resync, no
nearest-string attribution, no default tempo. Unknown bodies remain opaque.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


class ProbeError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes, start: int, end: int):
        self.data, self.pos, self.end = data, start, end

    def take(self, n: int) -> bytes:
        if n < 0 or n > self.end - self.pos:
            raise ProbeError(f"out of bounds at 0x{self.pos:x}, length {n}")
        result = self.data[self.pos:self.pos+n]
        self.pos += n
        return result

    def number(self, fmt: str):
        return struct.unpack(">" + fmt, self.take(struct.calcsize(">" + fmt)))[0]

    def string(self, *, terminated: bool = True) -> dict:
        offset = self.pos
        size = self.number("I")
        if size > 1_048_576:
            raise ProbeError(f"excessive string at 0x{offset:x}")
        raw = self.take(size)
        text_bytes = raw
        suffix = ""
        if terminated and raw:
            if raw.endswith(b"\0\xef\xbb\xbf"):
                text_bytes, suffix = raw[:-4], "nul_then_utf8_bom"
            elif raw.endswith(b"\0"):
                text_bytes, suffix = raw[:-1], "nul"
            else:
                raise ProbeError(f"unterminated string at 0x{offset:x}")
        if b"\0" in text_bytes:
            raise ProbeError(f"embedded NUL at 0x{offset:x}")
        return {"offset": offset, "byte_length": size,
                "text": text_bytes.decode("utf-8", errors="strict"), "suffix": suffix}


class Archive:
    def __init__(self, data: bytes, start: int, end: int):
        self.data, self.start, self.end = data, start, end
        self.classes: dict[int, dict] = {}
        self.objects: dict[int, dict] = {}

    def object(self, r: Reader) -> dict:
        start = r.pos
        declarations = []
        for _ in range(64):
            token_at = r.pos
            token = r.number("i")
            if token in (-1, -2):
                name = r.string()
                version = r.number("H")
                descriptor = {"offset": token_at, "relative_offset": token_at-self.start,
                              "class": name["text"], "version": version}
                self.classes[token_at-self.start] = descriptor
                declarations.append(descriptor)
                if token == -2:
                    continue
            elif token < 0:
                reference = token & 0x7fffffff
                if reference not in self.classes:
                    target = self.start + reference
                    if not self.start <= target < token_at:
                        raise ProbeError(f"unsupported non-backward class reference at 0x{token_at:x}")
                    # Native supports seeking to a missing class declaration.
                    # This probe permits only an explicit earlier -1 declaration.
                    lookup = Reader(self.data, target, self.end)
                    if lookup.number("i") != -1:
                        raise ProbeError(f"unsupported missing class reference at 0x{token_at:x}")
                    name = lookup.string()
                    version = lookup.number("H")
                    declared_size = lookup.number("I")
                    lookup.take(declared_size)
                    self.classes[reference] = {"offset": target, "relative_offset": reference,
                                               "class": name["text"], "version": version,
                                               "resolution": "explicit_backward_declaration_lookup"}
                descriptor = self.classes[reference]
            else:
                target = self.objects.get(token)
                return {"offset": start, "kind": "null" if token == 0 else "object_reference",
                        "relative_target": token, "target_known": token in self.objects,
                        "target_class": target["class"] if target else None,
                        "target_body_offset": target["body_offset"] if target else None,
                        "end": r.pos}
            size_at = r.pos
            size = r.number("I")
            body = r.pos
            r.take(size)
            obj = {"offset": start, "token_offset": token_at, "kind": "object",
                   "class": descriptor["class"], "version": descriptor["version"],
                   "class_declaration_offset": descriptor["offset"],
                   "class_resolution": descriptor.get("resolution", "previously_parsed_declaration"),
                   "declarations": declarations, "size_offset": size_at,
                   "body_offset": body, "body_bytes": size, "end": r.pos,
                   "body_sha256": hashlib.sha256(self.data[body:r.pos]).hexdigest()}
            # Native reader registers identity at the payload-length field,
            # not the first declaration token (32-bit archive mode).
            obj["relative_object_identity"] = size_at-self.start
            self.objects[size_at-self.start] = obj
            return obj
        raise ProbeError("excessive declaration chain")

    def body(self, obj: dict) -> Reader:
        return Reader(self.data, obj["body_offset"], obj["end"])


def attributes(r: Reader, depth: int = 0) -> list[dict]:
    if depth > 32:
        raise ProbeError("excessive attribute nesting")
    count = r.number("I")
    if count > 100_000:
        raise ProbeError("excessive attribute count")
    fields = []
    names = set()
    for _ in range(count):
        name = r.string()
        if name["text"] in names:
            raise ProbeError("duplicate attribute name")
        names.add(name["text"])
        type_at = r.pos
        code = r.number("H")
        value_at = r.pos
        if code == 1:
            value = r.number("q")
        elif code == 4:
            value = r.number("d")
            if not math.isfinite(value):
                raise ProbeError("nonfinite attribute")
        elif code == 8:
            value = r.string()
        elif code == 2:
            value = compound(r, depth+1)
        else:
            raise ProbeError(f"unsupported attribute type {code} at 0x{type_at:x}")
        fields.append({"name": name["text"], "offset": name["offset"],
                       "type_offset": type_at, "type_code": code,
                       "value_offset": value_at, "value": value, "end": r.pos})
    return fields


def compound(r: Reader, depth: int) -> dict:
    if depth > 32:
        raise ProbeError("excessive compound nesting")
    offset = r.pos
    code = r.number("H")
    if code == 20:
        name = r.string()
        identity_at = r.pos
        identity = r.number("Q")
        value = {"class": name["text"], "identity_offset": identity_at,
                 "opaque_identity": f"0x{identity:016x}", "attributes": attributes(r, depth)}
    elif code == 201:
        count = r.number("I")
        if count > 100_000:
            raise ProbeError("excessive compound array")
        value = {"items": [compound(r, depth+1) for _ in range(count)]}
    elif code == 6:
        value = {"attributes": attributes(r, depth)}
    else:
        raise ProbeError(f"unsupported compound subtype {code} at 0x{offset:x}")
    return {"offset": offset, "subtype": code, **value, "end": r.pos}


def metadata(archive: Archive, obj: dict) -> dict:
    if obj["class"] != "StMedia::PAttributes" or obj["version"] != 0:
        raise ProbeError("unsupported metadata root")
    r = archive.body(obj)
    fields = attributes(r)
    if r.pos != r.end:
        raise ProbeError("metadata root not exactly consumed")
    named = []
    if len(fields) != 1 or fields[0]["name"] != "PAttr" or fields[0]["type_code"] != 2 or fields[0]["value"]["subtype"] != 201:
        raise ProbeError("unsupported PAttr structure")
    seen = set()
    for item in fields[0]["value"]["items"]:
        if item.get("class") != "StMedia::PStringIDMediaAttribute":
            raise ProbeError("unsupported metadata attribute class")
        attr = {a["name"]: a for a in item["attributes"]}
        if not {"ID", "Type", "Flags"}.issubset(attr) or attr["ID"]["type_code"] != 8:
            raise ProbeError("invalid metadata attribute identity")
        name = attr["ID"]["value"]["text"]
        if name in seen:
            raise ProbeError("duplicate metadata identity")
        seen.add(name)
        type_code = attr["Type"]["value"]
        field = {1: "Long", 2: "Object", 4: "Float", 8: "String"}.get(type_code)
        if field not in attr or attr[field]["type_code"] != type_code:
            raise ProbeError("metadata type/value disagreement")
        named.append({"id": name, "id_offset": attr["ID"]["value_offset"],
                      "flags": attr["Flags"]["value"], "value": attr[field]})
    return {"attributes": fields, "named_values": named, "consumed_exactly": True,
            "semantic_limit": "Named metadata values only; not authoritative tempo, track, or DSP state."}


def track_list(archive: Archive, obj: dict, depth: int = 0) -> dict:
    if depth > 16 or obj["class"] not in ("MTrackList", "MListNode", "PAudioClip"):
        raise ProbeError("unsupported list class/depth")
    r = archive.body(obj)
    name = r.string()
    datum_at = r.pos
    datum_type = r.number("i")
    if datum_type in (0, 17):
        datum = {"objects": [archive.object(r), archive.object(r)]}
        for item in datum["objects"]:
            if item.get("class") == "MTempoTrackEvent":
                item["decoded"] = tempo_prefix(archive, item)
    elif datum_type in (1, 10):
        datum = {"scalar": r.number("d")}
    else:
        raise ProbeError(f"unsupported datum type {datum_type}")
    track_list_word = r.number("H") if obj["class"] == "MTrackList" else None
    count_at = r.pos
    count = r.number("I")
    if count > 100_000:
        raise ProbeError("excessive track count")
    children = []
    for _ in range(count):
        child = archive.object(r)
        if child.get("class") == "MTempoTrackEvent":
            child["decoded"] = tempo_prefix(archive, child)
        if child.get("kind") == "object" and child["class"] in (
                "MFolderTrack", "MDeviceTrackEvent", "MMidiTrackEvent", "MAudioTrackEvent",
                "MInstrumentTrackEvent", "MDrumTrackEvent", "MSamplerTrackEvent"):
            body = archive.body(child)
            child["event_prefix_hex"] = body.take(26).hex()
            node = archive.object(body)
            child["node"] = node
            if node.get("class") in ("MListNode", "MTrackList"):
                try:
                    node["decoded"] = track_list(archive, node, depth+1)
                except ProbeError as error:
                    node["decode_error"] = str(error)
            child["opaque_tail_offset"] = body.pos
        children.append(child)
        if child.get("class") == "MAudioEvent" and child["version"] == 6:
            body = archive.body(child)
            child["event_prefix"] = event_prefix(body)
            clip = archive.object(body)
            child["audio_clip"] = clip
            if clip.get("class") == "PAudioClip" and clip["version"] == 4:
                clip["decoded_node_prefix"] = track_list(archive, clip, depth+1)
                cr = archive.body(clip)
                cr.pos = clip["decoded_node_prefix"]["parsed_end"]
                path = archive.object(cr)
                clip["media_path_object"] = path
                if path.get("class") == "FNPath" and path["version"] == 0:
                    path["decoded"] = filename_path(archive, path)
                try:
                    clip["descriptor_suffix"] = media_descriptor_suffix(archive, cr)
                    cluster = archive.object(cr)
                    clip["audio_cluster"] = cluster
                    if cluster.get("class") == "AudioCluster" and cluster["version"] == 0:
                        cluster["decoded"] = audio_cluster(archive, cluster)
                except ProbeError as error:
                    clip["suffix_decode_error"] = str(error)
                clip["opaque_tail_offset"] = cr.pos
            child["opaque_tail_offset"] = body.pos
    return {"node_class": obj["class"], "name": name, "datum_offset": datum_at, "datum_type": datum_type,
            "datum": datum, "track_list_word": track_list_word,
            "count_offset": count_at, "count": count, "children": children,
            "parsed_end": r.pos, "opaque_tail_bytes": r.end-r.pos}


def tempo_prefix(archive: Archive, obj: dict) -> dict:
    if obj["version"] != 3:
        raise ProbeError("unsupported tempo version")
    r = archive.body(obj)
    count = r.number("i")
    if not 0 <= count <= 100_000:
        raise ProbeError("unsupported tempo count")
    records = []
    for _ in range(count):
        at = r.pos
        reciprocal, time_a, time_b, flag = r.number("f"), r.number("d"), r.number("d"), r.number("h")
        if not all(math.isfinite(v) for v in (reciprocal, time_a, time_b)) or reciprocal <= 0:
            raise ProbeError("unsupported nonfinite/nonpositive tempo record")
        bpm_f32 = struct.unpack(">f", struct.pack(">f", 60.0 / reciprocal))[0]
        records.append({"offset": at, "reciprocal_tempo_f32": reciprocal,
                        "native_getter_bpm_hundredths": int(bpm_f32 * 100 + 0.5),
                        "unbound_time_a_f64": time_a, "unbound_time_b_f64": time_b,
                        "unbound_flag_i16": flag})
    extra_at = r.pos
    extra = r.number("f")
    mode = r.number("H")
    return {"count": count, "record_stride": 22, "records": records,
            "fixed_bpm_offset": extra_at, "fixed_bpm_f32": extra, "fixed_enabled_u16": mode,
            "selected_mode": "fixed" if mode else "map",
            "opaque_attribute_tail_offset": r.pos,
            "limit": "Native reader/getters corroborate field widths, reciprocal BPM and fixed/map selection; timeline coordinate units and compatibility branches are not bound here."}


def event_prefix(r: Reader) -> dict:
    at = r.pos
    return {"offset": at, "unbound_word": r.number("H"),
            "unbound_f64_a": r.number("d"), "unbound_f64_b": r.number("d"),
            "unbound_f64_c": r.number("d"), "end": r.pos}


def filename_path(archive: Archive, obj: dict) -> dict:
    r = archive.body(obj)
    name = r.string()
    fourcc = r.take(4).hex()
    texts = [r.string(), r.string(), r.string()]
    discriminator_at = r.pos
    discriminator = r.take(6).hex()
    directory = r.string()
    if r.pos != r.end:
        raise ProbeError("FNPath observed layout did not consume exact body")
    return {"filename": name, "unbound_fourcc_hex": fourcc,
            "unbound_extension_description_strings": texts,
            "unbound_discriminator_offset": discriminator_at,
            "unbound_six_byte_prefix_hex": discriminator, "directory": directory,
            "consumed_exactly": True,
            "limit": "Observed typed string layout; native path construction and resolution semantics pending."}


def media_descriptor_suffix(archive: Archive, r: Reader) -> dict:
    # PMediaDescriptor reader0x1017aab94 establishes this ordering before
    # PAudioClip reads AudioCluster. Attribute tag meanings remain bounded.
    result = {"offset": r.pos, "identifier_string": r.string(), "unbound_i16": r.number("h"),
              "unbound_i32": r.number("i"), "unbound_f64": r.number("d")}
    count = r.number("I")
    if count > 100_000:
        raise ProbeError("excessive media attribute count")
    fields = []
    for _ in range(count):
        name = r.string()
        code = r.number("H")
        value_at = r.pos
        if code == 1: value = r.number("q")
        elif code == 4: value = r.number("d")
        elif code == 8: value = r.string()
        elif code in (0x12, 0x22, 0x92, 0xa2): value = archive.object(r)
        else: raise ProbeError(f"unsupported media attribute type0x{code:x}")
        fields.append({"name": name, "type_code": code, "value_offset": value_at, "value": value})
    return {**result, "attributes": fields, "end": r.pos,
            "limit": "Media attribute object values are bounded opaque records; ownership/processing semantics not inferred from tag flags."}


def audio_cluster(archive: Archive, obj: dict) -> dict:
    r = archive.body(obj)
    path = archive.object(r)
    vectors = []
    for _ in range(2):
        offset = r.pos
        word, count = r.number("H"), r.number("i")
        if not 0 <= count <= 100_000: raise ProbeError("excessive audio object vector")
        objects = []
        for _ in range(count):
            item = archive.object(r)
            if item.get("class") == "AudioFile" and item["version"] == 1:
                ar = archive.body(item)
                fields = {"offset": ar.pos, "media_frame_count_u64": ar.number("Q"),
                          "sample_size_i16": ar.number("h"), "frame_size_i16": ar.number("h"),
                          "audio_channels_i16": ar.number("h"), "sample_rate_f32": ar.number("f"),
                          "path": archive.object(ar)}
                if ar.pos < ar.end: fields["additional_path"] = archive.object(ar)
                if ar.pos != ar.end: raise ProbeError("AudioFile body not exactly consumed")
                fields["consumed_exactly"] = True
                item["decoded"] = fields
            objects.append(item)
        vectors.append({"offset": offset, "unbound_word": word, "count": count, "objects": objects})
    if r.pos != r.end: raise ProbeError("AudioCluster body not exactly consumed")
    return {"path": path, "vectors": vectors, "consumed_exactly": True,
            "limit": "Segment bodies remain opaque; metadata does not prove that referenced media exists or matches its declarations."}


def arrangement(archive: Archive, obj: dict) -> dict:
    if obj["class"] != "PArrangement" or obj["version"] != 4:
        raise ProbeError("unsupported arrangement root")
    r = archive.body(obj)
    root = archive.object(r)
    if root.get("class") != "MRoot" or root["version"] != 6:
        raise ProbeError("unsupported MRoot")
    rr = archive.body(root)
    root["event_prefix_hex"] = rr.take(26).hex()
    tracks = archive.object(rr)
    tracks["decoded"] = track_list(archive, tracks)
    root["track_list"] = tracks
    root["opaque_tail_offset"] = rr.pos
    return {"root": root, "opaque_tail_offset": r.pos}


def probe(path: Path) -> dict:
    before = path.stat()
    if not path.is_file() or before.st_size > 256*1024*1024:
        raise ProbeError("expected a regular CPR file at most 256 MiB")
    data = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ProbeError("source changed while reading")
    r = Reader(data, 0, len(data))
    if r.take(4) != b"RIFF" or r.number("I") != len(data)-12 or r.take(4) != b"NUND":
        raise ProbeError("unsupported CPR container")
    roots = []
    while r.pos < r.end:
        offset = r.pos
        if r.take(4) != b"ROOT":
            raise ProbeError("expected ROOT")
        size = r.number("I")
        rr = Reader(data, r.pos, r.pos+size)
        r.take(size)
        name, kind = rr.string(terminated=False), rr.string(terminated=False)
        if rr.pos != rr.end or r.take(4) != b"ARCH":
            raise ProbeError("invalid ROOT or missing ARCH")
        size = r.number("I")
        start = r.pos
        r.take(size)
        archive = Archive(data, start, r.pos)
        ar = Reader(data, start, r.pos)
        obj = archive.object(ar)
        if ar.pos != ar.end or obj.get("class") != kind["text"]:
            raise ProbeError("root object did not consume archive or class disagrees")
        record = {"offset": offset, "name": name["text"], "class": kind["text"],
                  "archive_start": start, "archive_bytes": size, "object": obj}
        try:
            if name["text"] == "Metadata": record["decoded"] = metadata(archive, obj)
            if name["text"] == "Arrangement1": record["decoded"] = arrangement(archive, obj)
        except ProbeError as error:
            record["decode_error"] = str(error)
        roots.append(record)
    return {"tool": "cpr_probe/0.2", "source": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "target_executed": False,
            "scope": "Bounded structural probe; unknown data and semantics remain opaque, not an importer.",
            "roots": roots}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="new JSON output file")
    args = parser.parse_args()
    try:
        result = probe(args.source)
        with args.out.open("x") as output:
            json.dump(result, output, indent=2, allow_nan=False)
            output.write("\n")
    except (OSError, ValueError, OverflowError, struct.error) as error:
        parser.exit(1, f"cpr_probe: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
