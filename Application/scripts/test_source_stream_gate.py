"""Negative transport controls independent of the Swift worker implementation."""
import copy
import hashlib
import io
import json
import struct
import unittest
from pathlib import Path
from source_stream_gate import Reader, StreamError, MAX_METADATA, MAX_CHUNK, LOGICAL_DIGEST_DOMAIN, require_long_proof


def encode(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def frame(kind, metadata, payload=b""):
    raw = encode(metadata) if isinstance(metadata, dict) else metadata
    return struct.pack("<4sHHII", b"RBAS", 1, kind, len(raw), len(payload)) + raw + payload


class SourceStreamGateTests(unittest.TestCase):
    def setUp(self):
        self.pcm = struct.pack("<ffff", 0.25, -0.5, -0.0, 0.125)
        proof = dict(schema="rebase.source-stream-proof.v1", revision=2,
            eventID="00000000-0000-0000-0000-000000000001", mode="nativeTimelineSourceRate", sampleRate=48000,
            startFrame=32_000_001, totalFrames=32_000_003, frames=2, channels=2)
        self.admit = {**{k: v for k, v in proof.items() if k != "schema"},
            "schema": "rebase.source-stream-admission.v1", "proof": proof,
            "generation": "00000000-0000-0000-0000-000000000002", "maximumChunkFrames": MAX_CHUNK,
            "proofSHA256": hashlib.sha256(encode(proof)).hexdigest()}
        self.expected = copy.deepcopy(self.admit)
        self.block = dict(generation=self.admit["generation"], sequence=0, absoluteFrame=32_000_001,
            frames=2, logicalBlock=0, logicalOffset=0, logicalFrames=2, sha256=hashlib.sha256(self.pcm).hexdigest())
        self.end = dict(generation=self.admit["generation"], nextSequence=1, nextAbsoluteFrame=32_000_003,
            frames=2, pcmSHA256=hashlib.sha256(self.pcm).hexdigest(), peakLogicalFrames=2,
            peakPayloadFrames=2, emittedLogicalBlocks=1)

    def run_stream(self, wire):
        reader = Reader(io.BytesIO(wire), self.expected)
        reader.start()
        blocks = []
        while (block := reader.next()) is not None:
            blocks.append(block)
        return reader, b"".join(blocks)

    def wire(self):
        return frame(1, self.admit) + frame(2, self.block, self.pcm) + frame(3, self.end)

    def test_valid_long_interval_and_signed_zero(self):
        reader, pcm = self.run_stream(self.wire())
        self.assertEqual(pcm, self.pcm)
        self.assertEqual(reader.emitted, 2)
        self.assertEqual(reader.peak_payload_bytes, 16)

    def test_transport_splits_preserve_one_logical_block(self):
        left = {**self.block, "frames": 1, "sha256": hashlib.sha256(self.pcm[:8]).hexdigest()}
        right = {**left, "sequence": 1, "absoluteFrame": 32_000_002, "logicalOffset": 1,
                 "sha256": hashlib.sha256(self.pcm[8:]).hexdigest()}
        wire = frame(1, self.admit) + frame(2, left, self.pcm[:8]) + frame(2, right, self.pcm[8:]) + frame(3, {**self.end, "nextSequence": 2, "peakPayloadFrames": 1})
        split, pcm = self.run_stream(wire)
        self.assertEqual(pcm, self.pcm)
        self.assertEqual(split.logical_hash.hexdigest(), self.run_stream(self.wire())[0].logical_hash.hexdigest())

    def test_logical_digest_has_stable_little_endian_encoding(self):
        reader, _ = self.run_stream(self.wire())
        self.assertEqual(reader.logical_hash.hexdigest(), hashlib.sha256(b"RBAS.logical-blocks.v1\0\x02\0\0\0\0\0\0\0").hexdigest())
        self.assertEqual((reader.logical_block, reader.observed_peak_logical_frames), (1, 2))

    def test_same_pcm_count_and_maximum_do_not_hide_reordered_blocks(self):
        def observe(lengths):
            total = sum(lengths)
            admit = copy.deepcopy(self.admit)
            for item in (admit, admit["proof"]):
                item.update(startFrame=0, totalFrames=total, frames=total)
            admit["proofSHA256"] = hashlib.sha256(encode(admit["proof"])).hexdigest()
            wire = frame(1, admit); position = 0
            for index, length in enumerate(lengths):
                payload = bytes(length * 8)
                wire += frame(2, {**self.block, "sequence": index, "absoluteFrame": position,
                    "frames": length, "logicalBlock": index, "logicalFrames": length,
                    "sha256": hashlib.sha256(payload).hexdigest()}, payload)
                position += length
            wire += frame(3, {**self.end, "nextSequence": len(lengths), "nextAbsoluteFrame": total, "frames": total,
                "pcmSHA256": hashlib.sha256(bytes(total * 8)).hexdigest(), "peakLogicalFrames": max(lengths),
                "peakPayloadFrames": max(lengths), "emittedLogicalBlocks": len(lengths)})
            self.expected = admit
            return self.run_stream(wire)[0]
        left, right = observe([2, 1, 2]), observe([1, 2, 2])
        self.assertEqual(left.hash.hexdigest(), right.hash.hexdigest())
        self.assertEqual((left.logical_block, left.observed_peak_logical_frames), (right.logical_block, right.observed_peak_logical_frames))
        self.assertNotEqual(left.logical_hash.hexdigest(), right.logical_hash.hexdigest())

    def test_producer_diagnostics_must_match_observed_headers(self):
        for key in ("peakLogicalFrames", "peakPayloadFrames", "emittedLogicalBlocks"):
            for value in (0, self.end[key] + 1, True, None):
                with self.subTest(key=key, value=value), self.assertRaises(StreamError):
                    self.run_stream(frame(1, self.admit) + frame(2, self.block, self.pcm) + frame(3, {**self.end, key: value}))

    def test_all_truncation_boundaries_refused(self):
        wire = self.wire()
        for offset in range(len(wire)):
            with self.subTest(offset=offset), self.assertRaises(StreamError):
                self.run_stream(wire[:offset])

    def test_metadata_substitution_refused(self):
        cases = [("generation", "00000000-0000-0000-0000-000000000003"), ("sequence", 1), ("sequence", False),
            ("absoluteFrame", 32_000_000), ("frames", 0), ("frames", 3), ("frames", True),
            ("logicalBlock", 1), ("logicalBlock", False), ("logicalOffset", 1), ("logicalFrames", 1),
            ("logicalFrames", 16_000_001), ("sha256", "0" * 64)]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(StreamError):
                self.run_stream(frame(1, self.admit) + frame(2, {**self.block, key: value}, self.pcm) + frame(3, self.end))

    def test_admission_or_proof_substitution_refused(self):
        for key, value in (("revision", 3), ("generation", "foreign"), ("mode", "unknown"), ("sampleRate", 0),
                           ("startFrame", 1), ("frames", 1), ("proofSHA256", "0" * 64), ("maximumChunkFrames", MAX_CHUNK + 1)):
            with self.subTest(key=key), self.assertRaises(StreamError):
                self.run_stream(frame(1, {**self.admit, key: value}))
        for key, value in (("eventID", "foreign"), ("wavSHA256", "0" * 64), ("frames", 1)):
            changed = copy.deepcopy(self.admit)
            changed["proof"][key] = value
            changed["proofSHA256"] = hashlib.sha256(encode(changed["proof"])).hexdigest()
            self.expected["proofSHA256"] = changed["proofSHA256"]
            with self.subTest(proof_key=key), self.assertRaises(StreamError):
                self.run_stream(frame(1, changed))

    def test_terminal_corruption_and_failure_refused(self):
        for key, value in (("generation", "foreign"), ("nextSequence", 0), ("nextSequence", True),
                           ("nextAbsoluteFrame", 1), ("frames", 1), ("pcmSHA256", "0" * 64)):
            with self.subTest(key=key), self.assertRaises(StreamError):
                self.run_stream(frame(1, self.admit) + frame(2, self.block, self.pcm) + frame(3, {**self.end, key: value}))
        for extra in (b"x", frame(3, self.end)):
            with self.assertRaises(StreamError):
                self.run_stream(self.wire() + extra)
        for last in (frame(1, self.admit), frame(3, self.end), frame(4, {"generation": self.admit["generation"], "code": "failed"})):
            with self.assertRaises(StreamError):
                self.run_stream(frame(1, self.admit) + last)

    def test_nonfinite_payload_and_changed_bytes_refused(self):
        for payload in (self.pcm[:-1] + b"\x00", struct.pack("<ffff", float("nan"), 0, 0, 0), struct.pack("<ffff", float("inf"), 0, 0, 0)):
            block = {**self.block, "sha256": hashlib.sha256(payload).hexdigest()}
            with self.assertRaises(StreamError):
                self.run_stream(frame(1, self.admit) + frame(2, block, payload) + frame(3, self.end))

    def test_duplicate_invalid_json_and_header_bounds_refused_before_payload(self):
        for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'\xff', b'[]'):
            with self.assertRaises(StreamError):
                self.run_stream(frame(1, raw))
        for magic, version, kind, meta, payload in ((b"NOPE", 1, 1, 1, 0), (b"RBAS", 2, 1, 1, 0),
            (b"RBAS", 1, 0, 1, 0), (b"RBAS", 1, 1, MAX_METADATA + 1, 0),
            (b"RBAS", 1, 1, 1, 1), (b"RBAS", 1, 2, 1, MAX_CHUNK * 8 + 1)):
            with self.assertRaises(StreamError):
                self.run_stream(struct.pack("<4sHHII", magic, version, kind, meta, payload))

    def test_zero_output_eof_has_proof(self):
        for item in (self.admit, self.admit["proof"]):
            item["startFrame"] = item["totalFrames"]
            item["frames"] = 0
        self.admit["proofSHA256"] = hashlib.sha256(encode(self.admit["proof"])).hexdigest()
        self.expected = copy.deepcopy(self.admit)
        terminal = {**self.end, "nextSequence": 0, "frames": 0, "pcmSHA256": hashlib.sha256(b"").hexdigest(),
                    "peakLogicalFrames": 0, "peakPayloadFrames": 0, "emittedLogicalBlocks": 0}
        reader, pcm = self.run_stream(frame(1, self.admit) + frame(3, terminal))
        self.assertEqual(pcm, b"")
        self.assertEqual(reader.logical_hash.hexdigest(), hashlib.sha256(LOGICAL_DIGEST_DOMAIN).hexdigest())


class LongProofGateTests(unittest.TestCase):
    """Authored metadata mutations; no worker or native projection is run."""
    def setUp(self):
        root = Path(__file__).resolve().parent.parent / "Tests/Fixtures/SourceStreamTimelines"
        self.case = next(case for case in json.loads((root / "expected.json").read_bytes())["cases"] if case["name"] == "overlap")
        package = root / self.case["root"]
        self.project = json.loads((package / "Project.json").read_bytes())
        self.report = json.loads((package / "Compatibility/CPR/ImportReport.json").read_bytes())
        self.project_sha = self.case["manifestSHA256"]
        mode = next(item for item in self.case["modes"] if item["mode"] == "nativeTrackSavedProjectClock")
        track = self.project["tracks"][0]
        events = {item["id"]: item for item in track["unresolvedAudioEvents"]}
        control = self.case["events"][0]
        recovered = self.report["recoveredTracks"][0]
        native = next(item for item in self.report["nativeObjects"] if item["objectOffset"] == recovered["sourceOffset"])
        def extent(position):
            return dict(contract="cpr-15.0.30.287-direct-saved-project-clock-segment-v1", position=position, duration=0.001, offset=0.001)
        contributors = [dict(eventID=item["eventID"], eventIdentity=events[item["eventID"]]["event"]["identityOffset"],
            sourceOrdinal=item["ordinal"], priority=item["priority"], sourceSampleRate=item["rate"], mediaSHA256=item["mediaSHA256"],
            canonicalStart=1000, canonicalEnd=1001, range=extent(1000)) for item in self.case["events"]]
        fragments = [dict(eventID=self.case["events"][ordinal]["eventID"], sourceOrdinal=ordinal,
            eventIdentity=events[self.case["events"][ordinal]["eventID"]]["event"]["identityOffset"], range=extent(1000 + index * 0.002))
            for index, ordinal in enumerate((1, 2, 1))]
        self.proof = dict(schema="rebase.source-stream-proof.v1", revision=3, eventID=self.case["anchorID"],
            mode=mode["mode"], clockRole="saved-project-clock-unconverted", channels=2, sourceSHA256=self.case["sourceSHA256"],
            mediaSHA256=control["mediaSHA256"], projectManifestSHA256=self.case["manifestSHA256"],
            importReportSHA256=self.case["reportSHA256"], currentProjectSHA256=self.project_sha,
            sampleRate=mode["sampleRate"], totalFrames=mode["totalFrames"], sourceSampleRate=control["rate"],
            projectSampleRate=self.case["projectRate"], currentNativeClock=self.project["tempoMap"]["nativeClock"],
            preservedNativeClock=self.report["nativeClock"], savedProjectAudioSetup=self.report["audioSetup"],
            sourceKind="track", name=recovered["name"], timelineRange=extent(1000), sourceTrack=dict(trackIdentity=native["identityOffset"],
                contract="cpr-15.0.30.287-priority-track-fresh-root-mode0-v1", freshRootMode=0,
                snappedEmptyFragmentCount=0, events=contributors, fragments=fragments))

    def validate(self):
        require_long_proof(self.proof, self.case, self.project, self.report, 3, "nativeTrackSavedProjectClock", self.project_sha)

    def test_authored_long_proof_is_accepted(self): self.validate()

    def test_source_report_and_project_identity_changes_are_rejected(self):
        for key in ("sourceSHA256", "mediaSHA256", "projectManifestSHA256", "importReportSHA256", "currentProjectSHA256"):
            old = self.proof[key]; self.proof[key] = "0" * 64
            with self.subTest(key=key), self.assertRaises(StreamError): self.validate()
            self.proof[key] = old

    def test_clock_and_complete_setup_changes_are_rejected(self):
        for key in ("currentNativeClock", "preservedNativeClock", "savedProjectAudioSetup"):
            old = self.proof[key]; self.proof[key] = {**old, "extra": "changed"}
            with self.subTest(key=key), self.assertRaises(StreamError): self.validate()
            self.proof[key] = old

    def test_covered_contributor_omission_is_rejected(self):
        self.proof["sourceTrack"]["events"].pop(0)
        with self.assertRaises(StreamError): self.validate()

    def test_contributor_media_substitution_is_rejected(self):
        self.proof["sourceTrack"]["events"][0]["mediaSHA256"] = "0" * 64
        with self.assertRaises(StreamError): self.validate()

    def test_duplicate_contributor_is_rejected(self):
        self.proof["sourceTrack"]["events"][0] = self.proof["sourceTrack"]["events"][1]
        with self.assertRaises(StreamError): self.validate()

    def test_missing_restored_tail_fragment_is_rejected(self):
        self.proof["sourceTrack"]["fragments"].pop()
        with self.assertRaises(StreamError): self.validate()

    def test_covered_anchor_fragment_is_rejected(self):
        self.proof["sourceTrack"]["fragments"][0]["eventID"] = self.case["anchorID"]
        with self.assertRaises(StreamError): self.validate()

    def test_fragment_order_and_identity_change_are_rejected(self):
        self.proof["sourceTrack"]["fragments"].reverse()
        with self.assertRaises(StreamError): self.validate()

    def test_nonfinite_fragment_is_rejected(self):
        self.proof["sourceTrack"]["fragments"][1]["range"]["position"] = float("inf")
        with self.assertRaises(StreamError): self.validate()

    def test_track_anchor_range_mismatch_is_rejected(self):
        self.proof["timelineRange"]["position"] += 1
        with self.assertRaises(StreamError): self.validate()


if __name__ == "__main__":
    unittest.main()
