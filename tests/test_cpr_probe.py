"""Synthetic framing controls plus explicit immutable shipped-template checks.

These tests validate a read-only probe, not CPR playback or Cubase conformance.
"""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cpr_probe", REPO / "scripts/cpr_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def u32(n): return struct.pack(">I", n)
def u16(n): return struct.pack(">H", n)
def text(s):
    b = s.encode() + b"\0"
    return u32(len(b)) + b


class CPRProbeTests(unittest.TestCase):
    def test_class_and_object_references_use_distinct_offsets(self):
        # Explicit Foo declaration starts0; its object identity is its size field.
        header = b"\xff" * 4 + text("Foo") + u16(3)
        identity = len(header)
        data = header + u32(2) + b"ab"
        data += u32(0x80000000) + u32(1) + b"c" + u32(identity)
        a = probe.Archive(data, 0, len(data)); r = probe.Reader(data, 0, len(data))
        first, second, reference = a.object(r), a.object(r), a.object(r)
        self.assertEqual(first["relative_object_identity"], identity)
        self.assertEqual(second["class"], "Foo")
        self.assertEqual(second["class_declaration_offset"], 0)
        self.assertTrue(reference["target_known"])
        self.assertEqual(reference["relative_target"], identity)
        self.assertEqual(r.pos, len(data))

    def test_missing_class_lookup_is_explicit_backward_only(self):
        header = b"\xff" * 4 + text("Hidden") + u16(1) + u32(0)
        data = header + u32(0x80000000) + u32(1) + b"x"
        a = probe.Archive(data, 0, len(data))
        obj = a.object(probe.Reader(data, len(header), len(data)))
        self.assertEqual(obj["class"], "Hidden")
        self.assertEqual(obj["class_resolution"], "explicit_backward_declaration_lookup")
        for bad in [u32(0x80000004) + u32(0), u32(0x80000000) + u32(0)]:
            with self.assertRaises(probe.ProbeError):
                probe.Archive(bad, 0, len(bad)).object(probe.Reader(bad, 0, len(bad)))

    def test_typed_attributes_are_counted_and_reject_unknown_types(self):
        data = u32(3) + text("Long") + u16(1) + struct.pack(">q", -3)
        data += text("Float") + u16(4) + struct.pack(">d", 126.5)
        data += text("String") + u16(8) + text("Named")
        r = probe.Reader(data, 0, len(data)); fields = probe.attributes(r)
        self.assertEqual([f["value"] for f in fields[:2]], [-3, 126.5])
        self.assertEqual(fields[2]["value"]["text"], "Named")
        self.assertEqual(r.pos, len(data))
        bad = u32(1) + text("unknown") + u16(99)
        with self.assertRaises(probe.ProbeError): probe.attributes(probe.Reader(bad, 0, len(bad)))
        with self.assertRaises(probe.ProbeError): probe.compound(probe.Reader(b"", 0, 0), 33)

    def test_container_does_not_resynchronize_or_accept_bad_lengths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "synthetic.cpr"
            for b in [b"RIFF" + u32(8) + b"NUND", b"RIFF" + u32(4) + b"NUNDjunk",
                      b"RIFF" + u32(8) + b"NUNDROOT" + u32(999)]:
                p.write_bytes(b)
                with self.assertRaises(probe.ProbeError): probe.probe(p)

    def test_tempo_records_use_22_bytes_and_full_u16_mode(self):
        # A byte-only mode read would mistake 0001 for false.
        body = u32(1) + struct.pack(">fddh", 0.5, 3.0, 2880.0, 0)
        body += struct.pack(">fH", 126.5, 1)
        a = probe.Archive(body, 0, len(body))
        result = probe.tempo_prefix(a, {"version": 3, "body_offset": 0, "end": len(body)})
        self.assertEqual(result["fixed_enabled_u16"], 1)
        self.assertEqual(result["selected_mode"], "fixed")
        self.assertEqual(result["fixed_bpm_f32"], 126.5)
        self.assertEqual(result["records"][0]["native_getter_bpm_hundredths"], 12000)
        self.assertEqual(result["opaque_attribute_tail_offset"], len(body))

    def test_signature_attributes_are_distinct_from_compact_prefix(self):
        # Entirely self-authored control: the compact prefix says4/4 while
        # the attribute-carried item says7/8. No target execution is involved.
        values = [("Flags", 1, 8), ("Start", 4, 6.25), ("Length", 4, 1.0),
                  ("Bar", 1, 3), ("Numerator", 1, 7), ("Denominator", 1, 8), ("Position", 1, 99)]
        def make(rows):
            fields = u32(len(rows)) + b"".join(text(n) + u16(t) + struct.pack(">q" if t == 1 else ">d", v) for n, t, v in rows)
            item = u16(20) + text("MTimeSignatureEvent") + struct.pack(">Q", 123) + fields
            container = u32(1) + text("SignatureEvent") + u16(2) + u16(201) + u32(1) + item
            obj = b"\xff" * 4 + text("FAttributes") + u16(0) + u32(len(container)) + container
            return u32(1) + struct.pack(">i6h", 0, 4, 4, 0, 0, 0, 8) + u32(1) + bytes.fromhex("736b6c43") + u16(2) + obj
        def decode(body):
            return probe.signature_track(probe.Archive(body, 0, len(body)),
                                         {"version": 3, "body_offset": 0, "end": len(body)})
        body = make(values)
        result = decode(body)
        self.assertEqual(result["compact_records"][0]["six_i16"][:2], [4, 4])
        fields = result["candidate_full_items"][0]["scalar_fields"]
        self.assertEqual((fields["Numerator"]["value"], fields["Denominator"]["value"]), (7, 8))
        self.assertEqual(fields["Position"]["value"], 99)
        self.assertTrue(result["consumed_exactly"])
        for bad in [body[:-1], body + b"x", make(values + [values[-1]]), make(values[:-1]),
                    make(values[:-1] + [("Position", 4, 99.0)])]:
            with self.assertRaises(probe.ProbeError): decode(bad)

    def test_signature_fixed_keys_and_flags_are_explicitly_bounded(self):
        prefix = u32(1) + struct.pack(">i6h", 0, 4, 4, 0, 0, 0, 8)
        scalar = bytes.fromhex("53636f4c") + u16(0x801) + struct.pack(">q", -7)
        body = prefix + u32(1) + scalar
        def decode(data):
            return probe.signature_track(probe.Archive(data, 0, len(data)),
                                         {"version": 3, "body_offset": 0, "end": len(data)})
        result = decode(body)
        self.assertEqual(result["attributes"][0]["value"], -7)
        self.assertEqual(result["candidate_full_items"], [])
        # No implicit full item synthesized when its container is absent.
        for bad in [prefix + u32(2) + scalar + scalar,
                    prefix + u32(1) + bytes.fromhex("53636f4c") + u16(0x101) + struct.pack(">q", 0),
                    u32(0x7fffffff) + prefix[4:]]:
            with self.assertRaises(probe.ProbeError): decode(bad)

    def test_shipped_metadata_track_names_and_audio_reference_paths(self):
        inventory = json.loads((REPO / "research/evidence/cubase-static/cpr-container-001/inventory.json").read_text())
        directory = REPO / inventory["source_directory"]
        if not directory.exists(): self.skipTest("Immutable proprietary fixtures not available")
        expected = {
            "Piano Page Layout.cpr": (["Input/Output", "Piano"], 134.0),
            "Stereo Mastering.cpr": (["Input/Output Channels", "Stereo Master", "Reference Track"], 120.0),
            "Classic House.cpr": (["Input/Output Channels", "Drums", "Bongos", "Riser", "Classic House Stabs", "Bass", "Vocal Chops"], 126.5),
        }
        for entry in inventory["records"]:
            result = probe.probe(directory / entry["name"])
            self.assertEqual(result["sha256"], entry["sha256"])
            roots = {r["name"]: r for r in result["roots"]}
            self.assertEqual(len(roots), 7)
            self.assertNotIn("decode_error", roots["Metadata"])
            self.assertNotIn("decode_error", roots["Arrangement1"])
            signatures = []
            def check(value):
                if isinstance(value, dict):
                    self.assertNotIn("decode_error", value)
                    if value.get("class") == "MSignatureTrackEvent" and "decoded" in value:
                        signatures.append(value["decoded"])
                    if "opaque_tail_bytes" in value and "datum" in value:
                        # PAudioClip has an explicitly preserved non-list suffix.
                        if value["node_class"] != "PAudioClip":
                            self.assertEqual(value["opaque_tail_bytes"], 0)
                    for v in value.values(): check(v)
                elif isinstance(value, list):
                    for v in value: check(v)
            check(roots["Arrangement1"])
            self.assertEqual(len(signatures), 1)
            signature = signatures[0]
            self.assertTrue(signature["consumed_exactly"])
            self.assertEqual(signature["compact_count"], 1)
            self.assertEqual(len(signature["candidate_full_items"]), 1)
            fields = signature["candidate_full_items"][0]["scalar_fields"]
            self.assertEqual({k: v["value"] for k, v in fields.items()},
                             {"Flags": 8, "Start": 0.0, "Length": 1.0, "Bar": 0,
                              "Numerator": 4, "Denominator": 4, "Position": 0})
            if entry["name"] in expected:
                names, tempo = expected[entry["name"]]
                node = roots["Arrangement1"]["decoded"]["root"]["track_list"]["decoded"]
                self.assertEqual([t["node"]["decoded"]["name"]["text"] for t in node["children"]], names)
                metadata = {v["id"]: v["value"]["value"] for v in roots["Metadata"]["decoded"]["named_values"]}
                self.assertEqual(metadata["MusicalTempo"], tempo)
                self.assertEqual(metadata["AudioSampleRate"], 44100.0)
                if entry["name"] == "Classic House.cpr":
                    audio = node["children"][2]["node"]["decoded"]["children"][0]
                    self.assertEqual(audio["offset"], 0x329a3)
                    path = audio["audio_clip"]["media_path_object"]["decoded"]
                    self.assertEqual(path["filename"]["text"], "Tech_House_Percussion_Loop_21_125bpm_BODTH.wav")
                    self.assertTrue(path["directory"]["text"].startswith("vstsound://A7F7DB52AF1D437F86C67714A904A9C9/"))
                    file = audio["audio_clip"]["audio_cluster"]["decoded"]["vectors"][0]["objects"][0]["decoded"]
                    self.assertEqual((file["media_frame_count_u64"], file["sample_size_i16"], file["frame_size_i16"], file["audio_channels_i16"], file["sample_rate_f32"]),
                                     (677376, 24, 6, 2, 44100.0))
                    self.assertTrue(file["path"]["target_known"])
                    self.assertEqual(file["path"]["target_class"], "FNPath")


if __name__ == "__main__": unittest.main()
