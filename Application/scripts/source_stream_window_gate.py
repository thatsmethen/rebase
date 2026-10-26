"""Strict boundary for native WPF source-stream observations.

This gate checks recorded actions, complete worker proofs, and client PNG bytes.
It does not turn a visual-tree render or an available endpoint into an audible
output, physical-input, desktop-frame, or reference-application observation.
"""
import copy
import hashlib
import json
import math
import struct
import uuid
import zlib
from pathlib import Path

from source_stream_gate import decode, digest, integer, require_receipt

MODE = "nativeTrackSavedProjectClock"
CASES = ("boundary", "overlap", "near-day")
CAPTURE = "native-source-stream-visual.png"
CONTROLS = ("modes", "position", "seek", "refresh", "export", "play", "pause", "stop", "close")
CHECKS = {"source-stream-" + case + "-" + suffix for case in CASES for suffix in
          ("availability", "play-admission", "seek-admission", "resume-admission", "cancel-and-helper-responsive")}
CHECKS |= {"source-stream-covered-contributor-retained", "source-stream-minimum-layout-captured"}


def require(value, message):
    if not value:
        raise ValueError("Source stream window: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    # Match the independent worker observer's semantic JSON normalization, not
    # Swift's raw proof encoding (which is separately bound by proofSHA256).
    def normalize(item):
        if isinstance(item, dict):
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, list):
            return [normalize(child) for child in item]
        if type(item) is float:
            require(math.isfinite(item), "nonfinite proof value")
            return int(item) if item.is_integer() else item
        return item
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _png(path, expected_hash, bounds, coverage):
    coverage_keys = {"root_background_alpha", "alpha_minimum", "alpha_254_pixels", "alpha_255_pixels",
                     "alpha_below_254_pixels", "total_pixels"}
    require(isinstance(coverage, dict) and set(coverage) == coverage_keys and
            all(integer(coverage[key], 0, 16_777_216) for key in coverage_keys) and
            coverage["root_background_alpha"] == 255, "missing or invalid measured client alpha coverage")
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 16_777_216,
            "missing, redirected, or excessive client PNG")
    data = path.read_bytes()
    require(digest(expected_hash) and sha(data) == expected_hash and data[:8] == b"\x89PNG\r\n\x1a\n",
            "client PNG identity differs")
    offset, chunks, compressed, physical, ended = 8, [], bytearray(), None, False
    width = height = 0
    idat_closed = False
    while offset < len(data):
        require(offset + 12 <= len(data), "truncated PNG chunk")
        length, kind = struct.unpack(">I4s", data[offset:offset + 8])
        require(length <= 16_777_216 and offset + 12 + length <= len(data), "invalid PNG chunk size")
        payload = data[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        require(zlib.crc32(kind + payload) & 0xffffffff == crc, "PNG CRC mismatch")
        if not chunks:
            require(kind == b"IHDR" and length == 13, "PNG missing initial IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            require(1 <= width <= 4096 and 1 <= height <= 4096 and
                    (depth, color, compression, filtering, interlace) == (8, 6, 0, 0, 0), "unexpected WPF PNG format")
        elif kind == b"IHDR":
            require(False, "repeated PNG header")
        if kind == b"IDAT":
            require(not idat_closed, "noncontiguous PNG pixel chunks")
            compressed.extend(payload)
        elif b"IDAT" in chunks:
            idat_closed = True
        if kind == b"pHYs":
            require(physical is None and length == 9, "duplicate or invalid PNG DPI")
            physical = struct.unpack(">IIB", payload)
        require(kind[0] & 32 or kind in (b"IHDR", b"IDAT", b"IEND"), "unknown critical PNG chunk")
        chunks.append(kind)
        offset += length + 12
        if kind == b"IEND":
            require(length == 0 and offset == len(data), "extra bytes after PNG end")
            ended = True
            break
    require(ended and compressed and physical is not None, "incomplete PNG pixel/DPI stream")
    require((width, height) == (bounds["pixel_width"], bounds["pixel_height"]), "PNG dimensions differ from measured bounds")
    require(physical[2] == 1 and all(abs(physical[i] - 96 * bounds[key] / .0254) <= 1 for i, key in
            enumerate(("dpi_scale_x", "dpi_scale_y"))), "PNG DPI differs from measured client scale")
    expected = (width * 4 + 1) * height
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(bytes(compressed), expected + 1)
    require(len(pixels) == expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
            "invalid or excessive PNG pixel stream")
    # Only alpha is needed for coverage. PNG predictors at byte offset 4k+3
    # depend on preceding alpha bytes, so this exactly decodes that channel.
    previous = bytearray(width)
    minimum, alpha254, alpha255, below254 = 255, 0, 0, 0
    for y in range(height):
        start = y * (width * 4 + 1)
        filtering = pixels[start]
        require(filtering in range(5), "invalid PNG row filter")
        current = bytearray(width)
        for x in range(width):
            left = current[x - 1] if x else 0
            up = previous[x]
            diagonal = previous[x - 1] if x else 0
            if filtering == 0: predictor = 0
            elif filtering == 1: predictor = left
            elif filtering == 2: predictor = up
            elif filtering == 3: predictor = (left + up) // 2
            else:
                p = left + up - diagonal
                a, b, c = abs(p - left), abs(p - up), abs(p - diagonal)
                predictor = left if a <= b and a <= c else up if b <= c else diagonal
            current[x] = (pixels[start + 1 + x * 4 + 3] + predictor) & 255
        minimum = min(minimum, min(current))
        alpha254 += current.count(254)
        alpha255 += current.count(255)
        below254 += sum(alpha < 254 for alpha in current)
        previous = current
    measured = {"root_background_alpha": 255, "alpha_minimum": minimum, "alpha_254_pixels": alpha254,
                "alpha_255_pixels": alpha255, "alpha_below_254_pixels": below254, "total_pixels": width * height}
    require(measured == coverage, "client PNG alpha histogram differs from measured capture")
    # Source-bound WPF captures have measured near-opaque254 as well as255.
    # Preserve that one-level raster tolerance; actual uncovered pixels fail.
    require(below254 == 0, "client PNG has pixels below the measured alpha254 coverage floor")
    return {"file": CAPTURE, "sha256": expected_hash, "width": width, "height": height,
            "alpha_coverage": measured, "crc_and_pixels_verified": True}


def _capture(capture, evidence):
    require(isinstance(capture, dict) and capture.get("file") == CAPTURE and
            capture.get("frame_excluded") is True and capture.get("selected_mode") == MODE,
            "missing complete-track client capture")
    require(all(isinstance(capture.get(key), str) and len(capture[key]) <= 65_536 for key in ("details", "message"))
            and capture["details"].strip(), "missing bounded source details")
    bounds = capture["bounds"]
    require(isinstance(bounds, dict) and all(number(bounds.get(key), 1, 4096) for key in
            ("outer_width_dip", "outer_height_dip", "width_dip", "height_dip")), "invalid client bounds")
    require(abs(bounds["outer_width_dip"] - 740) <= .5 and abs(bounds["outer_height_dip"] - 540) <= .5
            and 650 <= bounds["width_dip"] <= bounds["outer_width_dip"]
            and 400 <= bounds["height_dip"] <= bounds["outer_height_dip"], "capture is not the minimum dialog")
    for suffix in ("x", "y"):
        require(number(bounds.get("dpi_scale_" + suffix), .5, 4), "invalid client DPI")
    for dimension, suffix in (("width", "x"), ("height", "y")):
        require(integer(bounds.get("pixel_" + dimension), 1, 4096) and bounds["pixel_" + dimension] ==
                math.ceil(bounds[dimension + "_dip"] * bounds["dpi_scale_" + suffix]), "unbound pixel dimensions")
    controls = capture["controls"]
    require(isinstance(controls, list) and len(controls) == len(CONTROLS) and
            all(isinstance(item, dict) for item in controls), "missing client controls")
    indexed = {item.get("name"): item for item in controls}
    require(set(indexed) == set(CONTROLS), "duplicate or unknown client control")
    for name, item in indexed.items():
        require(all(number(item.get(key), -.5 if key in ("x", "y") else .01, 4096) for key in ("x", "y", "width", "height"))
                and item["x"] + item["width"] <= bounds["width_dip"] + .5
                and item["y"] + item["height"] <= bounds["height_dip"] + .5, "clipped client control: " + name)
        require(type(item.get("enabled")) is bool and (name == "pause" or item["enabled"] is (name != "export")),
                "wrong idle action availability: " + name)
        min_width = dict(modes=220, position=100, seek=60, refresh=88, export=90, play=64, pause=64, stop=64, close=70)[name]
        require(item["width"] >= min_width - .5 and item["height"] >= (250 if name == "modes" else 24) - .5,
                "unusable control extent: " + name)
    # These are siblings, so any positive overlap is clipping/occlusion, not a
    # legitimate control contained inside another measured control.
    for i, a in enumerate(controls):
        for b in controls[i + 1:]:
            require(min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]) <= .5 or
                    min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]) <= .5,
                    "overlapping client controls")
    return _png(Path(evidence) / CAPTURE, capture["sha256"], bounds, capture.get("alpha_coverage"))


def _require(smoke, evidence, long_fixture, process_receipt, fixture_sha256):
    require(isinstance(smoke, dict) and smoke.get("outcome") == "passed", "native smoke did not pass")
    checks = smoke.get("checks")
    require(isinstance(checks, list) and all(isinstance(item, str) for item in checks) and len(checks) == len(set(checks))
            and {item for item in checks if item.startswith("source-stream-")} == CHECKS, "native action inventory differs")
    require(isinstance(long_fixture, dict) and long_fixture.get("schemaVersion") == 1 and
            long_fixture.get("evidenceClass") == "authored-synthetic-control", "unsupported long fixture")
    fixtures = long_fixture["cases"]
    require(isinstance(fixtures, list) and len(fixtures) == 3 and [row["name"] for row in fixtures] == list(CASES),
            "long fixture cases differ")
    short_path = Path(__file__).resolve().parents[1] / "Tests/Fixtures/SourceAuditionModes/expected.json"
    short_bytes = short_path.read_bytes()
    process = require_receipt(process_receipt, decode(short_bytes), long_fixture, sha(short_bytes), fixture_sha256)
    oracle = {row["case"]: row for row in process_receipt["scenarios"]}
    record = smoke.get("source_stream_window")
    require(isinstance(record, dict) and record.get("tested") is True and digest(fixture_sha256)
            and record.get("fixture_sha256") == fixture_sha256, "window fixture is unbound")
    require(all(record.get(key) is False for key in
            ("audio_device_playback_measured", "physical_input_tested", "native_frame_visual_tested")), "unsupported evidence claim")
    require(record.get("input_evidence") == "WPF UI Automation providers invoke production Play, source position/Seek, Stop and refresh actions; no physical input",
            "action evidence provenance differs")
    cases = record["cases"]
    require(isinstance(cases, list) and len(cases) == 3 and [row["fixture"] for row in cases] == list(CASES), "missing native cases")
    generations, endpoints = set(), {"unavailable": 0, "started": 0}
    for case, fixture in zip(cases, fixtures):
        expected = next(row for row in fixture["modes"] if row["mode"] == MODE)
        total, rate = expected["totalFrames"], expected["sampleRate"]
        revision = case["revision"]
        state = case["before_state_sha256"]
        require(integer(revision) and case["mode"] == MODE and digest(state) and case["after_state_sha256"] == state,
                "window changed its session")
        require(type(total) is int and total > 32_000_000 and total <= rate * 86400 and expected["tailFrames"] == 1000,
                "long control duration differs")
        availability = case["availability"]
        require(all(availability.get(key) is True for key in ("available", "live_available", "play_enabled")) and
                all(availability.get(key) is False for key in ("snapshot_export_available", "export_enabled")) and
                number(availability.get("sample_rate"), rate, rate) and integer(availability.get("total_frames"), total, total) and
                isinstance(availability.get("snapshot_export_reason"), str) and 0 < len(availability["snapshot_export_reason"].strip()) <= 4096,
                "long live/snapshot availability differs")
        require(all(integer(case.get(key), value, value) for key, value in
                (("prepare_requests", 3), ("snapshot_render_requests", 0), ("inspection_requests", 1))) and
                all(case.get(key) is True for key in ("no_snapshot_render_request", "cancel_joined", "helper_responsive")),
                "worker path or helper responsiveness not demonstrated")
        after = case["after_cancel"]
        require(number(after.get("position_seconds"), 0, 0) and after.get("is_playing") is False and
                after.get("worker_joined") is True and integer(after.get("inspection_revision"), revision, revision),
                "cancel did not preserve the live session")
        admissions = case["admissions"]
        require(isinstance(admissions, list) and len(admissions) == 3 and
                [item["action"] for item in admissions] == ["play", "seek", "resume"], "missing ordered live actions")
        for admission in admissions:
            generation = admission["generation"]
            require(isinstance(generation, str) and str(uuid.UUID(generation)).upper() == generation.upper() and
                    generation not in generations, "reused or invalid worker generation")
            generations.add(generation)
            start = 0 if admission["action"] == "play" else total - 1000
            require(admission.get("worker_admission_valid") is True and admission.get("state_sha256") == state and
                    admission.get("mode") == MODE and integer(admission.get("revision"), revision, revision) and
                    number(admission.get("sample_rate"), rate, rate) and integer(admission.get("start_frame"), start, start) and
                    integer(admission.get("total_frames"), total, total) and integer(admission.get("remaining_frames"), total-start, total-start),
                    "worker admission differs from live action")
            endpoint = admission["endpoint_outcome"]
            require(endpoint in endpoints and type(admission.get("worker_joined")) is bool and
                    admission.get("native_started") is (endpoint == "started") and
                    (endpoint != "unavailable" or admission["worker_joined"] is True), "unverified endpoint/worker ownership")
            endpoints[endpoint] += 1
            raw = admission["proof_json"]
            require(isinstance(raw, str) and 0 < len(raw) <= 8_388_608, "missing bounded complete proof")
            raw_bytes = raw.encode("utf-8")
            require(len(raw_bytes) <= 8_388_608 and digest(admission["proof_sha256"]) and sha(raw_bytes) == admission["proof_sha256"],
                    "raw complete proof hash differs")
            proof = decode(raw_bytes)
            require(proof.get("schema") == "rebase.source-stream-proof.v1" and proof.get("eventID") == fixture["anchorID"] and
                    proof.get("mode") == MODE and integer(proof.get("revision"), revision, revision) and
                    number(proof.get("sampleRate"), rate, rate) and integer(proof.get("totalFrames"), total, total) and
                    integer(proof.get("startFrame"), start, start) and integer(proof.get("frames"), total-start, total-start),
                    "complete proof interval or anchor differs")
            for field, source_field, expected_hash in (
                ("source_sha256", "sourceSHA256", fixture["sourceSHA256"]),
                ("report_sha256", "importReportSHA256", fixture["reportSHA256"]),
                ("project_manifest_sha256", "projectManifestSHA256", fixture["manifestSHA256"]),
                ("current_project_sha256", "currentProjectSHA256", proof.get("currentProjectSHA256"))):
                require(digest(expected_hash) and admission.get(field) == proof.get(source_field) == expected_hash,
                        "complete proof identity differs: " + field)
            track = proof["sourceTrack"]
            events, fragments = track["events"], track["fragments"]
            require(isinstance(events, list) and len(events) == len(fixture["events"]) and isinstance(fragments, list)
                    and 1 <= len(fragments) <= 16384, "incomplete track proof")
            projection = [{"event_id": e["eventID"], "media_sha256": e["mediaSHA256"], "source_ordinal": e["sourceOrdinal"]} for e in events]
            expected_events = [{"event_id": e["eventID"], "media_sha256": e["mediaSHA256"], "source_ordinal": e["ordinal"]} for e in fixture["events"]]
            require(projection == expected_events and admission["contributors"] == projection and
                    all(integer(e["sourceOrdinal"]) for e in events), "contributor projection differs")
            fragment_ids = [e["eventID"] for e in fragments]
            require(admission["fragment_event_ids"] == fragment_ids, "fragment projection differs")
            if case["fixture"] == "overlap":
                require(fixture["anchorID"] not in fragment_ids and fixture["anchorID"] in [e["eventID"] for e in events],
                        "covered contributor was discarded")
            # Bind all fields, including priorities, ranges, native/current
            # clocks and saved setup, to the separately drained worker proof.
            normalized = copy.deepcopy(proof)
            normalized.pop("revision")
            normalized["startFrame"], normalized["frames"] = total - 1000, 1000
            comparison = oracle["long-" + case["fixture"] + "-" + MODE + "-tail"]
            require(sha(canonical(normalized)) == comparison["normalized_proof_sha256"],
                    "complete proof differs from independent worker observation")
    image = _capture(record["capture"], evidence)
    return {"schema": "rebase.source-stream-window-summary.v1", "cases": len(cases), "admissions": len(generations),
            "native_checks": len(CHECKS), "fixture_sha256": fixture_sha256, "helper_sha256": process["helper_sha256"],
            "independent_worker_scenarios": process["scenarios"], "endpoint_outcomes": endpoints, "capture": image,
            "complete_proof_bound": True, "snapshot_render_requests": 0,
            "audio_device_playback_measured": False, "physical_input_tested": False,
            "native_frame_visual_tested": False, "visual_acceptance_claimed": False}


def require_source_stream_window(smoke, evidence, long_fixture, process_receipt, fixture_sha256):
    """Reject incomplete/malformed native evidence; return a path-free summary."""
    try:
        return _require(smoke, evidence, long_fixture, process_receipt, fixture_sha256)
    except (KeyError, TypeError, AttributeError, IndexError, StopIteration, UnicodeError,
            zlib.error, OSError, OverflowError, RecursionError) as error:
        raise ValueError("Source stream window: malformed or missing evidence") from error
