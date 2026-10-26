"""Validate the bounded native New/import journey without promoting UIA to hardware evidence."""
import hashlib
import math
import re
import uuid
import zlib
from pathlib import Path

from source_stream_gate import decode, digest, integer
from source_stream_window_gate import _png

CAPTURE = "native-audio-import-visual.png"
INPUT_EVIDENCE = "Actual WPF File menu/UIA controls with injected file paths and dirty-decision results; no physical dialogs"
CHECKS = tuple("documents-" + value for value in (
    "new-empty-scratch", "picker-cancel-preserves-state", "batch-import-selects-last-track",
    "real-waveforms", "batch-single-undo", "redo-restores-identities", "batch-failure-preserves-state",
    "dirty-new-cancel-preserves-state", "save-destination-cancel-preserves-state", "save-as-publishes-project",
    "saved-media-bytes-preserved", "clean-new-replaces-project", "reopen-preserves-project",
    "source-files-unchanged", "import-window-captured"))
COMMANDS = ("newProject", "importAudio", "saveAs", "undo", "redo", "open")
PHASES = ("new", "picker_cancelled", "imported", "undone", "redone", "batch_rejected",
          "dirty_new_cancelled", "save_destination_cancelled", "saved", "clean_new", "reopened")
SOURCE_LOCKS = (
    ("rhythm.wav", "1dca2a5d261b56bc30cf714ba4161f7a7f3f2014ec286d9b9f7519535ed10275"),
    ("pad.wav", "1b66fce5220aea385762380c55dcb54c017f029078c78fdabc227c66d638fc55"))
INVALID_BYTES = b"Authored invalid audio control"


def require(value, detail):
    if not value:
        raise ValueError("Documents window: " + detail)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value) is not None and uuid.UUID(value).int != 0


def counts(value, expected):
    require(isinstance(value, dict) and set(value) == set(COMMANDS) and
            all(integer(value[key], count, count) for key, count in zip(COMMANDS, expected)),
            "command order/counts differ")


def capture_image(capture, evidence, copied):
    require(isinstance(capture, dict) and capture.get("file") == CAPTURE and capture.get("frame_excluded") is True,
            "missing client-only import capture")
    require(integer(capture.get("waveform_count"), 2, 2) and number(capture.get("pixels_per_second"), 24, 24) and
            number(capture.get("horizontal_offset"), 0, 0) and number(capture.get("vertical_offset"), 0, 0),
            "waveforms or capture viewport differ")
    bounds = capture["bounds"]
    require(isinstance(bounds, dict), "missing measured client bounds")
    for dimension, suffix, minimum in (("width", "x", 1020), ("height", "y", 700)):
        require(number(bounds.get(dimension + "_dip"), minimum, 4096) and
                number(bounds.get("outer_" + dimension + "_dip"), bounds[dimension + "_dip"], 4096) and
                number(bounds.get("dpi_scale_" + suffix), .5, 4), "invalid client extent or DPI")
        pixels = math.ceil(bounds[dimension + "_dip"] * bounds["dpi_scale_" + suffix])
        require(integer(bounds.get("pixel_" + dimension), pixels, pixels) and pixels <= 4096,
                "pixel extent is not bound to client measurement")
    headers, clips = capture["headers"], capture["clips"]
    require(isinstance(headers, list) and isinstance(clips, list) and len(headers) == len(clips) == 2,
            "missing track/event geometry")
    for rows in (headers, clips):
        for row in rows:
            require(isinstance(row, dict) and all(number(row.get(key), -.5 if key in ("x", "y") else 1, 4096)
                    for key in ("x", "y", "width", "height")) and
                    row["x"] + row["width"] <= bounds["width_dip"] + .5 and
                    row["y"] + row["height"] <= bounds["height_dip"] + .5, "clipped track/event geometry")
        require(rows[1]["y"] >= rows[0]["y"] + rows[0]["height"] - .5,
                "track/event rows overlap or are reversed")
    for header, clip, media in zip(headers, clips, copied):
        require("clip_id" in header and header.get("track_id") == media["track_id"] and header.get("clip_id") is None and
                clip.get("track_id") == media["track_id"] and clip.get("clip_id") == media["clip_id"],
                "geometry identity differs from imported media")
        compact = abs(header["height"] - 44) <= .5
        require(compact or abs(header["height"] - 68) <= .5, "unrecognized track row density")
        inset = 3 if compact else 5
        require(abs(header["width"] - 198) <= .5 and abs(clip["width"] - 20 * 24) <= .5 and
                abs(clip["height"] - (header["height"] - 2 * inset)) <= .5 and
                abs(clip["y"] - header["y"] - inset) <= .5 and
                abs(clip["x"] - header["x"] - header["width"]) <= .5,
                "visible event does not match its zero-start,20-second interval")
    require(abs(headers[0]["x"] - headers[1]["x"]) <= .5 and abs(clips[0]["x"] - clips[1]["x"]) <= .5,
            "track/event columns are misaligned")
    # Reuse the full CRC, bounded decompression, row-filter and measured client
    # coverage parser. Visual acceptance still requires image review.
    image = _png(Path(evidence) / CAPTURE, capture["sha256"], bounds, capture.get("alpha_coverage"))
    image["file"] = CAPTURE
    return image


def _validate(smoke, evidence, example_manifest_bytes, expected_helper_sha256):
    require(isinstance(smoke, dict) and smoke.get("outcome") == "passed", "native journey did not pass")
    checks = smoke["checks"]
    require(isinstance(checks, list) and all(isinstance(value, str) for value in checks) and
            len(checks) == len(set(checks)) and tuple(value for value in checks if value.startswith("documents-")) == CHECKS,
            "missing, duplicated, or reordered document actions")
    require(isinstance(example_manifest_bytes, bytes) and 0 < len(example_manifest_bytes) <= 65_536,
            "invalid source-bound example manifest")
    example = decode(example_manifest_bytes)
    require(isinstance(example, dict) and example.get("schema") == "rebase.example.v1" and
            example.get("project") == "Rebase Preview.rebaseproj" and
            all(integer(example.get(key), value, value) for key, value in
                (("sample_rate", 48000), ("channels", 2), ("sample_width_bits", 16), ("duration_seconds", 20))),
            "example format differs from the authored input")
    files = example["files"]
    require(isinstance(files, list) and all(isinstance(item, dict) and isinstance(item.get("path"), str) for item in files) and
            len({item["path"] for item in files}) == len(files), "ambiguous example inventory")
    indexed = {item["path"]: item for item in files}
    record = smoke["documents"]
    require(isinstance(record, dict) and record.get("tested") is True and digest(expected_helper_sha256) and
            record.get("helper_sha256") == expected_helper_sha256 and
            record.get("example_manifest_sha256") == sha(example_manifest_bytes), "unbound helper or example identity")
    require(record.get("input_evidence") == INPUT_EVIDENCE and all(record.get(key) is False for key in
            ("physical_input_tested", "native_file_pickers_tested", "playback_tested")), "unsupported evidence claim")
    invalid = record["invalid_input"]
    require(isinstance(invalid, dict) and integer(invalid.get("bytes"), len(INVALID_BYTES), len(INVALID_BYTES)) and
            invalid.get("sha256") == sha(INVALID_BYTES), "invalid-batch source is unbound")
    inputs, copied = record["inputs"], record["copied_media"]
    require(isinstance(inputs, list) and isinstance(copied, list) and len(inputs) == len(copied) == 2,
            "incomplete source/copied media inventory")
    batches = set()
    for index, ((filename, expected), source, media) in enumerate(zip(SOURCE_LOCKS, inputs, copied)):
        lock = indexed["Media/" + filename]
        require(lock.get("sha256") == expected and integer(lock.get("bytes"), 3_840_044, 3_840_044), "example lock differs")
        require(isinstance(source, dict) and source.get("path") == "Examples/Rebase Preview.rebaseproj/Media/" + filename and
                source.get("sha256") == expected and integer(source.get("bytes"), 3_840_044, 3_840_044), "selected input differs")
        require(isinstance(media, dict) and integer(media.get("index"), index, index) and
                media.get("sha256") == expected and media.get("source_sha256") == expected and
                integer(media.get("bytes"), 3_840_044, 3_840_044) and integer(media.get("track_clip_count"), 1, 1),
                "saved media bytes or track shape differ")
        require(identifier(media.get("track_id")) and identifier(media.get("clip_id")), "invalid imported identities")
        path = media["media_path"]
        require(isinstance(path, str) and len(path) <= 160, "invalid media path")
        parts = path.split("/")
        require(len(parts) == 3 and parts[0] == "Media" and parts[1].startswith("Import-") and
                identifier(parts[1][7:]) and parts[2].endswith(".wav") and identifier(parts[2][:-4]),
                "media is not an exclusive ordinary import asset")
        batches.add(parts[1])
        require(number(media.get("position_seconds"), 0, 0) and number(media.get("duration_seconds"), 20, 20) and
                number(media.get("source_offset_seconds"), 0, 0), "imported source interval differs")
    require(len(batches) == 1 and all(len({row[key].lower() for row in copied}) == 2 for key in
            ("track_id", "clip_id", "media_path")), "duplicate media identity or split batch publication")
    phases = record["phases"]
    require(isinstance(phases, list) and len(phases) == len(PHASES) and
            all(isinstance(row, dict) for row in phases) and tuple(row.get("phase") for row in phases) == PHASES,
            "document phase order differs")
    base = phases[0]["revision"]
    require(integer(base, 1, (1 << 64) - 7), "invalid initial revision")
    # revision delta, tracks, dirty, needsSaveAs, undo, redo, cumulative requests
    expected_phases = (
        (0, 0, False, True, False, False, (1, 0, 0, 0, 0, 0)),
        (0, 0, False, True, False, False, (1, 0, 0, 0, 0, 0)),
        (1, 2, True, True, True, False, (1, 1, 0, 0, 0, 0)),
        (2, 0, False, True, False, True, (1, 1, 0, 1, 0, 0)),
        (3, 2, True, True, True, False, (1, 1, 0, 1, 1, 0)),
        (3, 2, True, True, True, False, (1, 2, 0, 1, 1, 0)),
        (3, 2, True, True, True, False, (1, 2, 0, 1, 1, 0)),
        (3, 2, True, True, True, False, (1, 2, 0, 1, 1, 0)),
        (4, 2, False, False, True, False, (1, 2, 1, 1, 1, 0)),
        (5, 0, False, True, False, False, (2, 2, 1, 1, 1, 0)),
        (6, 2, False, False, False, False, (2, 2, 1, 1, 1, 1)))
    for phase, (delta, tracks, dirty, save_as, undo, redo, requests) in zip(phases, expected_phases):
        require(integer(phase.get("revision"), base + delta, base + delta) and integer(phase.get("track_count"), tracks, tracks) and
                phase.get("dirty") is dirty and phase.get("needs_save_as") is save_as and
                phase.get("can_undo") is undo and phase.get("can_redo") is redo and
                number(phase.get("position_seconds"), 0, 0), "phase state or revision differs: " + phase["phase"])
        require(digest(phase.get("state_sha256")) and digest(phase.get("project_sha256")), "missing phase identities")
        counts(phase.get("requests"), requests)
        selected = None if tracks == 0 else copied[0 if phase["phase"] == "reopened" else 1]
        require("track_id" in phase and "clip_id" in phase and
                phase.get("track_id") == (selected["track_id"] if selected else None) and
                phase.get("clip_id") == (selected["clip_id"] if selected else None), "selected event differs")
    for indices, key in (((0, 1), "state_sha256"), ((4, 5, 6, 7), "state_sha256"),
                         ((0, 1, 3), "project_sha256"), ((2, 4, 5, 6, 7, 8, 10), "project_sha256")):
        require(len({phases[index][key] for index in indices}) == 1, "cancellation,undo or reopen identity differs")
    require(len({phases[index]["state_sha256"] for index in (0, 2, 3, 4, 8, 9, 10)}) == 7 and
            len({phases[index]["project_sha256"] for index in (0, 2, 9)}) == 3, "distinct document transitions reused identity")
    counts(record.get("requests"), expected_phases[-1][-1])
    image = capture_image(record["capture"], evidence, copied)
    return {"schema": "rebase.documents-window-summary.v1", "native_checks": len(CHECKS), "phases": len(PHASES),
            "helper_sha256": expected_helper_sha256, "example_manifest_sha256": sha(example_manifest_bytes),
            "source_sha256": [value for _, value in SOURCE_LOCKS], "copied_media_bound": True,
            "single_batch_history_bound": True, "requests": record["requests"], "capture": image,
            "physical_input_tested": False, "native_file_pickers_tested": False, "playback_tested": False,
            "visual_acceptance_claimed": False}


def require_documents_window(smoke, evidence, example_manifest_bytes, expected_helper_sha256):
    """Return a path-free summary; raise ValueError for malformed or incomplete evidence."""
    try:
        return _validate(smoke, evidence, example_manifest_bytes, expected_helper_sha256)
    except (KeyError, TypeError, AttributeError, IndexError, UnicodeError, OSError, zlib.error,
            OverflowError, RecursionError) as error:
        raise ValueError("Documents window: malformed or missing evidence") from error
