"""Bounded, independent RBAS v1 reader used by actual-worker conformance gates.

This reader consumes bytes incrementally and never buffers a whole timeline.
Malformed/truncated transport is an error, distinct from a verified terminal EOF.
"""
import hashlib
import json
import math
import struct
import uuid

MAX_METADATA = 8_388_608
MAX_CHUNK = 65_536
LOGICAL_DIGEST_DOMAIN = b"RBAS.logical-blocks.v1\0"
MODES = ("sourceRate", "nativeTimelineSourceRate", "nativeTimelineProjectClock",
         "nativeTimelineSavedProjectClock", "nativeTrackSavedProjectClock",
         "nativeMode0ProjectRate", "nativeMode1ProjectRate", "nativeMode2ProjectRate")


class StreamError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise StreamError(message)


def integer(value, low=0, high=(1 << 64) - 1):
    return type(value) is int and low <= value <= high


def digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON member")
        result[key] = value
    return result


def decode(data):
    try:
        value = json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(StreamError("Nonfinite JSON")))
    except (ValueError, UnicodeError) as error:
        raise StreamError("Invalid JSON metadata") from error
    require(isinstance(value, dict), "Metadata must be an object")
    return value


def raw_member(data, member):
    # Hash the bytes actually emitted for the proof; re-encoding JSON can change
    # valid floating point/exponent spelling across Swift, .NET and Python.
    text = data.decode("utf-8")
    decoder = json.JSONDecoder()
    offset = 0
    def white(index):
        while index < len(text) and text[index].isspace():
            index += 1
        return index
    offset = white(offset)
    require(text[offset] == "{", "Expected metadata object")
    offset += 1
    while True:
        offset = white(offset)
        if text[offset] == "}":
            break
        key, end = decoder.raw_decode(text, offset)
        offset = white(end)
        require(text[offset] == ":", "Invalid JSON member")
        start = white(offset + 1)
        _, end = decoder.raw_decode(text, start)
        if key == member:
            return text[start:end].encode("utf-8")
        offset = white(end)
        if text[offset] == "}":
            break
        require(text[offset] == ",", "Invalid JSON separator")
        offset += 1
    raise StreamError("Missing raw JSON member")


def read_exact(stream, count):
    result = bytearray()
    while len(result) < count:
        part = stream.read(count - len(result))
        require(bool(part), "Truncated stream")
        result.extend(part)
    return bytes(result)


def read_record(stream):
    header = read_exact(stream, 16)
    magic, version, kind, metadata_count, payload_count = struct.unpack("<4sHHII", header)
    require(magic == b"RBAS" and version == 1 and kind in (1, 2, 3, 4), "Unknown stream header")
    require(0 < metadata_count <= MAX_METADATA, "Metadata length outside bound")
    require(payload_count <= MAX_CHUNK * 8 and (kind == 2 or payload_count == 0), "Payload length outside bound")
    metadata_bytes = read_exact(stream, metadata_count)
    metadata = decode(metadata_bytes)
    payload = read_exact(stream, payload_count)
    return kind, metadata, metadata_bytes, payload


class Reader:
    def __init__(self, stream, expected):
        self.stream = stream
        self.expected = expected
        self.admission = None
        self.next_sequence = 0
        self.absolute = 0
        self.emitted = 0
        self.logical_block = 0
        self.logical_offset = 0
        self.logical_frames = None
        self.hash = hashlib.sha256()
        # Completed logical lengths, encoded as UInt64 little endian in order.
        # Transport fragments do not enter this digest, so chunk-size changes
        # cannot hide or invent a shared output-stage block boundary.
        self.logical_hash = hashlib.sha256(LOGICAL_DIGEST_DOMAIN)
        self.observed_peak_logical_frames = 0
        self.terminal = None
        self.peak_payload_bytes = 0
        self.peak_metadata_bytes = 0

    def start(self):
        require(self.admission is None, "Repeated admission")
        kind, record, raw, payload = read_record(self.stream)
        require(kind == 1 and not payload, "Worker did not admit its source")
        require(record.get("schema") == "rebase.source-stream-admission.v1", "Unknown admission schema")
        try:
            uuid.UUID(record.get("generation", ""))
        except (ValueError, TypeError, AttributeError) as error:
            raise StreamError("Invalid generation") from error
        for key in ("generation", "revision", "eventID", "mode", "sampleRate", "startFrame", "totalFrames", "frames", "proofSHA256"):
            require(record.get(key) == self.expected.get(key), "Admission changed " + key)
        rate = record.get("sampleRate")
        require(type(rate) in (int, float) and math.isfinite(rate) and 8000 <= rate <= 192000 and rate == int(rate), "Invalid source rate")
        require(record.get("mode") in MODES and record.get("channels") == 2, "Invalid source format")
        require(integer(record.get("revision")), "Invalid revision")
        total, start, remaining = (record.get(key) for key in ("totalFrames", "startFrame", "frames"))
        require(integer(total, 1, int(rate) * 86400) and integer(start, 0, total) and integer(remaining, 0, total)
                and start + remaining == total, "Invalid admitted interval")
        require(integer(record.get("maximumChunkFrames"), 1, MAX_CHUNK), "Invalid transport bound")
        proof = record.get("proof")
        require(isinstance(proof, dict) and proof.get("schema") == "rebase.source-stream-proof.v1", "Missing preparation proof")
        require(digest(record.get("proofSHA256")) and hashlib.sha256(raw_member(raw, "proof")).hexdigest() == record["proofSHA256"], "Proof digest mismatch")
        for key in ("revision", "eventID", "mode", "sampleRate", "startFrame", "totalFrames", "frames", "channels"):
            require(proof.get(key) == record[key], "Proof changed " + key)
        require(not any(key in proof for key in ("wavSHA256", "wavBytes", "wavFileName", "maximumFrames")), "Stream proof fabricated snapshot receipt")
        self.admission = record
        self.absolute = start
        self.peak_metadata_bytes = len(raw)
        return record

    def next(self):
        require(self.admission is not None and self.terminal is None, "Invalid reader phase")
        kind, record, raw, payload = read_record(self.stream)
        self.peak_metadata_bytes = max(self.peak_metadata_bytes, len(raw))
        require(record.get("generation") == self.admission["generation"], "Foreign stream generation")
        if kind == 4:
            raise StreamError("Worker reported source production failure")
        if kind == 3:
            require(all(integer(record.get(key)) for key in ("nextSequence", "nextAbsoluteFrame", "frames"))
                    and record.get("nextSequence") == self.next_sequence and record.get("nextAbsoluteFrame") == self.absolute
                    and record.get("frames") == self.emitted == self.admission["frames"]
                    and self.absolute == self.admission["totalFrames"] and self.logical_offset == 0,
                    "Premature or inconsistent stream EOF")
            require(record.get("pcmSHA256") == self.hash.hexdigest(), "Terminal PCM digest mismatch")
            for key, observed in (("peakLogicalFrames", self.observed_peak_logical_frames),
                                  ("peakPayloadFrames", self.peak_payload_bytes // 8),
                                  ("emittedLogicalBlocks", self.logical_block)):
                require(integer(record.get(key)) and record[key] == observed,
                        "Producer diagnostic differs from observed " + key)
            require(self.stream.read(1) == b"", "Extra bytes after terminal EOF")
            self.terminal = record
            return None
        require(kind == 2, "Repeated admission or invalid record")
        frames = record.get("frames")
        require(integer(record.get("sequence")) and integer(record.get("absoluteFrame"))
                and record.get("sequence") == self.next_sequence and record.get("absoluteFrame") == self.absolute,
                "Discontinuous PCM sequence or position")
        require(integer(frames, 1, self.admission["maximumChunkFrames"]) and len(payload) == frames * 8,
                "Invalid PCM extent")
        require(frames <= self.admission["totalFrames"] - self.absolute, "PCM exceeds admitted interval")
        logical_frames = record.get("logicalFrames")
        require(integer(record.get("logicalBlock")) and integer(record.get("logicalOffset"))
                and record.get("logicalBlock") == self.logical_block and record.get("logicalOffset") == self.logical_offset
                and integer(logical_frames, 1, 16_000_000) and self.logical_offset + frames <= logical_frames,
                "Changed logical block partition")
        if self.logical_frames is not None:
            require(logical_frames == self.logical_frames, "Logical block length changed")
        self.logical_frames = logical_frames
        require(record.get("sha256") == hashlib.sha256(payload).hexdigest(), "PCM digest mismatch")
        require(all(math.isfinite(sample[0]) for sample in struct.iter_unpack("<f", payload)), "Nonfinite PCM")
        self.hash.update(payload)
        self.emitted += frames
        self.absolute += frames
        self.next_sequence += 1
        self.logical_offset += frames
        if self.logical_offset == logical_frames:
            self.logical_hash.update(struct.pack("<Q", logical_frames))
            self.observed_peak_logical_frames = max(self.observed_peak_logical_frames, logical_frames)
            self.logical_block += 1
            self.logical_offset = 0
            self.logical_frames = None
        self.peak_payload_bytes = max(self.peak_payload_bytes, len(payload))
        return payload


GATES = ("snapshot_equivalence", "complete_proof", "fresh_generations", "partition_invariance", "long_tail",
         "long_complete", "zero_eof", "read_only", "covered_tamper", "ticket_tamper", "source_revalidation",
         "worker_cancel", "bounded_transport", "locked_inputs_unchanged")

SUCCESS_FIELDS = {"schema", "status", "evidence_class", "helper_sha256", "fixture_manifest_sha256",
    "long_fixture_manifest_sha256", "checks", "gates", "scenarios", "playback_tested", "reference_execution", "scope"}


def require_long_proof(proof, case, project, report, revision, mode, current_project_sha256):
    """Bind long-stream provenance to frozen authored inputs, not another worker.

    This checks complete identities and ordered fixture fragment membership. It
    does not recreate the native floating-point segment projection algorithm.
    Exact source PCM/counts are checked separately against the locked tail.
    """
    expected = next((item for item in case["modes"] if item["mode"] == mode), None)
    require(expected is not None and mode in MODES[1:5], "Unknown long fixture mode")
    controls = {item["eventID"]: item for item in case["events"]}
    tracks = [track for track in project["tracks"]
              if any(event["id"] == case["anchorID"] for event in track.get("unresolvedAudioEvents", []))]
    require(len(tracks) == 1 and len(controls) == len(case["events"]), "Ambiguous long fixture membership")
    current_track = tracks[0]
    events = {event["id"]: event for event in current_track["unresolvedAudioEvents"]}
    require(set(events) == set(controls), "Long fixture project membership changed")
    anchor = controls[case["anchorID"]]
    role = {MODES[1]: "source-clock-unconverted", MODES[2]: "current-project-clock-unconverted",
            MODES[3]: "saved-project-clock-unconverted", MODES[4]: "saved-project-clock-unconverted"}[mode]
    require(proof.get("schema") == "rebase.source-stream-proof.v1"
            and proof.get("revision") == revision and proof.get("eventID") == case["anchorID"]
            and proof.get("mode") == mode and proof.get("clockRole") == role and proof.get("channels") == 2
            and proof.get("sourceSHA256") == case["sourceSHA256"]
            and proof.get("mediaSHA256") == anchor["mediaSHA256"]
            and proof.get("projectManifestSHA256") == case["manifestSHA256"]
            and proof.get("importReportSHA256") == case["reportSHA256"]
            and current_project_sha256 == case["manifestSHA256"]
            and digest(current_project_sha256) and proof.get("currentProjectSHA256") == current_project_sha256
            and proof.get("sampleRate") == expected["sampleRate"] and proof.get("totalFrames") == expected["totalFrames"]
            and proof.get("sourceSampleRate") == anchor["rate"] and proof.get("projectSampleRate") == case["projectRate"]
            and proof.get("currentNativeClock") == project["tempoMap"].get("nativeClock")
            and proof.get("preservedNativeClock") == report.get("nativeClock"), "Long proof identity or clock changed")
    if mode in MODES[3:5]:
        require(proof.get("savedProjectAudioSetup") == report.get("audioSetup")
                and isinstance(proof.get("savedProjectAudioSetup"), dict), "Long proof lost complete saved setup")
    else:
        require("savedProjectAudioSetup" not in proof, "Long proof invented a saved-rate context")
    contracts = {MODES[1]: "cpr-15.0.30.287-direct-source-segment-v1",
                 MODES[2]: "cpr-15.0.30.287-direct-project-clock-segment-v1",
                 MODES[3]: "cpr-15.0.30.287-direct-saved-project-clock-segment-v1",
                 MODES[4]: "cpr-15.0.30.287-direct-saved-project-clock-segment-v1"}
    def valid_range(value):
        return (isinstance(value, dict) and value.get("contract") == contracts[mode]
                and all(type(value.get(key)) in (int, float) and math.isfinite(value[key])
                        and 0 <= value[key] <= 86400 for key in ("position", "duration", "offset"))
                and value["duration"] > 0)
    if mode != MODES[4]:
        require(proof.get("sourceKind") == "event" and "sourceTrack" not in proof
                and proof.get("name") == events[case["anchorID"]]["name"]
                and valid_range(proof.get("timelineRange")), "Long event proof changed scope or range")
        return
    track = proof.get("sourceTrack")
    require(isinstance(track, dict) and proof.get("sourceKind") == "track" and valid_range(proof.get("timelineRange")),
            "Long track proof changed scope")
    retained = [item for item in report["recoveredTracks"] if item.get("importedTrackID") == current_track["id"]]
    require(len(retained) == 1, "Long track has no unique report identity")
    native = [item for item in report["nativeObjects"] if item.get("objectOffset") == retained[0]["sourceOffset"]
              and item.get("className") == retained[0]["nativeClassName"]]
    require(len(native) == 1 and track.get("trackIdentity") == native[0]["identityOffset"]
            and proof.get("name") == retained[0]["name"]
            and track.get("contract") == "cpr-15.0.30.287-priority-track-fresh-root-mode0-v1"
            and type(track.get("freshRootMode")) is int and track["freshRootMode"] == 0
            and type(track.get("snappedEmptyFragmentCount")) is int and track["snappedEmptyFragmentCount"] == 0,
            "Long track reconstruction context changed")
    contributors = track.get("events")
    require(isinstance(contributors, list) and len(contributors) == len(controls)
            and [item.get("eventID") for item in contributors] == [item["eventID"] for item in case["events"]],
            "Long track omitted or reordered a counted contributor")
    for item in contributors:
        control = controls[item["eventID"]]
        require(item.get("eventIdentity") == events[item["eventID"]]["event"]["identityOffset"]
                and item.get("sourceOrdinal") == control["ordinal"] and item.get("priority") == control["priority"]
                and item.get("sourceSampleRate") == control["rate"] and item.get("mediaSHA256") == control["mediaSHA256"]
                and all(type(item.get(k)) in (int, float) and math.isfinite(item[k]) and 0 <= item[k] <= 86400
                        for k in ("canonicalStart", "canonicalEnd"))
                and item["canonicalStart"] < item["canonicalEnd"] and valid_range(item.get("range")),
                "Long track contributor identity, media or original range changed")
    require(proof["timelineRange"] == next(item["range"] for item in contributors if item["eventID"] == case["anchorID"]),
            "Long track lost the selected anchor's original range")
    fragments = track.get("fragments")
    # The forward-authored overlap fixture has later equal-priority winner 1,
    # stronger middle winner 2, then winner 1 again; contributor 0 stays covered.
    ordinals = [1, 2, 1] if case["name"] == "overlap" else [0]
    by_ordinal = {item["ordinal"]: item for item in case["events"]}
    require(isinstance(fragments, list) and len(fragments) == len(ordinals), "Long track fragment set changed")
    previous = -1.0
    for item, ordinal in zip(fragments, ordinals):
        control = by_ordinal[ordinal]
        require(item.get("eventID") == control["eventID"] and item.get("sourceOrdinal") == ordinal
                and item.get("eventIdentity") == events[control["eventID"]]["event"]["identityOffset"]
                and valid_range(item.get("range")) and item["range"]["position"] > previous,
                "Long track fragment membership, order or range changed")
        previous = item["range"]["position"]


def require_receipt(receipt, short_fixture, long_fixture, short_digest, long_digest, helper_digest=None, snapshot_receipt=None):
    require(isinstance(receipt, dict) and set(receipt) == SUCCESS_FIELDS, "Unexpected successful stream receipt field")
    require(receipt.get("schema") == "rebase.source-stream-control.v1" and receipt.get("status") == "passed"
            and receipt.get("evidence_class") == "authored-shared-worker-control"
            and receipt.get("playback_tested") is False and receipt.get("reference_execution") is False,
            "Incomplete or misclassified worker receipt")
    require(receipt.get("fixture_manifest_sha256") == short_digest and digest(short_digest)
            and receipt.get("long_fixture_manifest_sha256") == long_digest and digest(long_digest)
            and digest(receipt.get("helper_sha256"))
            and (helper_digest is None or receipt["helper_sha256"] == helper_digest), "Unbound worker input identity")
    require(isinstance(receipt.get("gates"), dict) and set(receipt["gates"]) == set(GATES)
            and all(value is True for value in receipt["gates"].values()), "Missing source-stream gates")
    checks = receipt.get("checks")
    require(isinstance(checks, list) and len(checks) >= 500 and len(checks) == len(set(checks))
            and all(isinstance(item, str) and item for item in checks), "Incomplete source-stream check inventory")
    expected = {}
    for case in short_fixture["cases"]:
        modes = MODES if case["name"] == "single" else MODES[1:5]
        for mode in modes:
            for seek in ("full", "odd", "eof", "rewind", "partition"):
                expected[case["name"] + "-" + mode + "-" + seek] = (mode, None, seek)
    for case in long_fixture["cases"]:
        for mode in case["modes"]:
            for seek in ("tail", "eof"):
                expected["long-" + case["name"] + "-" + mode["mode"] + "-" + seek] = (mode["mode"], mode, seek)
            if case["name"] == "boundary" and mode["mode"] == "nativeTimelineSavedProjectClock":
                expected["long-boundary-" + mode["mode"] + "-full"] = (mode["mode"], mode, "full")
    scenarios = receipt.get("scenarios")
    require(isinstance(scenarios, list) and len(scenarios) == len(expected) == 85
            and all(isinstance(row, dict) for row in scenarios), "Incomplete worker scenario set")
    seen = set()
    by_label = {}
    allowed_fields = {"case", "mode", "sample_rate", "start_frame", "total_frames", "frames", "pcm_sha256", "proof_sha256",
        "normalized_proof_sha256", "transport_chunk_bound", "records", "peak_payload_bytes", "peak_metadata_bytes",
        "producer_peak_logical_frames", "producer_peak_payload_frames", "producer_logical_blocks",
        "observed_logical_blocks", "observed_peak_logical_frames", "logical_blocks_sha256"}
    for row in scenarios:
        require(set(row) == allowed_fields, "Unexpected source-stream receipt field")
        label = row.get("case")
        require(label in expected and label not in seen, "Repeated or unexpected worker scenario")
        seen.add(label)
        by_label[label] = row
        mode, long_mode, seek = expected[label]
        require(row.get("mode") == mode, "Worker scenario changed mode")
        rate, total, start, frames = (row.get(key) for key in ("sample_rate", "total_frames", "start_frame", "frames"))
        require(type(rate) in (float, int) and math.isfinite(rate) and 8000 <= rate <= 192000 and rate == int(rate)
                and integer(total, 1, int(rate) * 86400) and integer(start, 0, total) and integer(frames, 0, total)
                and start + frames == total, "Invalid scenario extent")
        require(all(digest(row.get(key)) for key in ("pcm_sha256", "proof_sha256", "normalized_proof_sha256", "logical_blocks_sha256")),
                "Missing stream content identity")
        bound = row.get("transport_chunk_bound")
        require(bound == (257 if seek in ("partition", "tail") else MAX_CHUNK)
                and integer(row.get("records"), 0, frames)
                and integer(row.get("peak_payload_bytes"), 0, bound * 8)
                and integer(row.get("peak_metadata_bytes"), 1, MAX_METADATA)
                and integer(row.get("producer_peak_payload_frames"), 0, bound)
                and integer(row.get("producer_peak_logical_frames"), 0, 16_000_000)
                and integer(row.get("producer_logical_blocks"), 0, frames)
                and integer(row.get("observed_logical_blocks"), 0, frames)
                and integer(row.get("observed_peak_logical_frames"), 0, 16_000_000)
                and row["observed_logical_blocks"] == row["producer_logical_blocks"]
                and row["observed_peak_logical_frames"] == row["producer_peak_logical_frames"], "Invalid bounded producer counters")
        if seek == "eof":
            require(frames == row["records"] == row["producer_peak_payload_frames"] == row["producer_peak_logical_frames"]
                    == row["producer_logical_blocks"] == row["peak_payload_bytes"] == 0
                    and row["pcm_sha256"] == hashlib.sha256(b"").hexdigest()
                    and row["logical_blocks_sha256"] == hashlib.sha256(LOGICAL_DIGEST_DOMAIN).hexdigest(), "Unverified empty EOF")
        else:
            require(frames > 0 and row["records"] > 0 and row["producer_logical_blocks"] > 0
                    and 0 < row["peak_payload_bytes"] == row["producer_peak_payload_frames"] * 8,
                    "Missing emitted PCM counters")
        if long_mode:
            require(total == long_mode["totalFrames"] > 32_000_000 and rate == long_mode["sampleRate"]
                    and row["producer_peak_logical_frames"] <= 4096, "Long control lost its independent duration bound")
            if seek == "tail":
                require(frames == long_mode["tailFrames"] and row["pcm_sha256"] == long_mode["tailPCMSHA256"],
                        "Long tail differs from frozen shared-cursor control")
            if seek == "full":
                require(start == 0 and frames == total, "Long full drain omitted frames")
    for case in short_fixture["cases"]:
        for mode in (MODES if case["name"] == "single" else MODES[1:5]):
            prefix = case["name"] + "-" + mode + "-"
            full = by_label[prefix + "full"]
            expected_rate = (case["events"][0]["rate"] if mode in MODES[:2] else case["savedRate"]
                             if mode in MODES[3:5] else case["projectRate"])
            require(full["sample_rate"] == expected_rate and full["start_frame"] == 0,
                    "Source scenario changed its declared clock")
            for seek in ("rewind", "partition"):
                require(all(by_label[prefix + seek][key] == full[key] for key in
                    ("frames", "start_frame", "total_frames", "sample_rate", "pcm_sha256", "normalized_proof_sha256",
                     "logical_blocks_sha256", "observed_logical_blocks", "observed_peak_logical_frames")),
                    "Rewind or transport partition changed samples or complete proof")
            odd = by_label[prefix + "odd"]
            require(odd["start_frame"] == 1 and odd["total_frames"] == full["total_frames"]
                    and odd["sample_rate"] == expected_rate, "Odd seek changed its interval or clock")
    if snapshot_receipt is not None:
        require(snapshot_receipt.get("status") == "passed" and snapshot_receipt.get("helper_sha256") == receipt["helper_sha256"],
                "Snapshot oracle belongs to a different helper or failed")
        snapshot_rows = snapshot_receipt.get("scenarios", [])
        require(len(snapshot_rows) == 48, "Missing snapshot oracle scenarios")
        for snapshot in snapshot_rows:
            row = by_label.get(snapshot["case"] + "-" + snapshot["mode"] + "-" + snapshot["seek"])
            require(row is not None and all(row[key] == snapshot[key] for key in
                ("frames", "start_frame", "total_frames", "sample_rate", "pcm_sha256")),
                "Stream output differs from separate locked snapshot oracle receipt")
    return {"schema": "rebase.source-stream-summary.v1", "scenarios": len(scenarios), "checks": len(checks),
            "fixture_manifest_sha256": short_digest, "long_fixture_manifest_sha256": long_digest,
            "helper_sha256": receipt["helper_sha256"], "playback_tested": False, "reference_execution": False}
