"""Authored receipt/pixel mutation controls; does not execute or observe WPF."""
import argparse
import copy
import hashlib
import json
import struct
import uuid
import zlib
from pathlib import Path

from documents_window_gate import (CAPTURE, CHECKS, COMMANDS, INPUT_EVIDENCE, INVALID_BYTES,
                                   PHASES, SOURCE_LOCKS, require_documents_window)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def png(width=1024, height=704, alpha=255, dpi=3779, filter_byte=0, first_alpha=None):
    pixels = (bytes((filter_byte,)) + bytes((38, 42, 46, alpha)) * width) * height
    if first_alpha is not None:
        pixels = pixels[:4] + bytes((first_alpha,)) + pixels[5:]
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"pHYs", struct.pack(">IIB", dpi, dpi, 1)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def coverage(alpha=255, count=1024 * 704, first_alpha=None):
    counts = {alpha: count}
    if first_alpha is not None:
        counts[alpha] -= 1
        counts[first_alpha] = counts.get(first_alpha, 0) + 1
    return {"root_background_alpha": 255, "alpha_minimum": min(a for a, n in counts.items() if n),
            "alpha_254_pixels": counts.get(254, 0), "alpha_255_pixels": counts.get(255, 0),
            "alpha_below_254_pixels": sum(n for a, n in counts.items() if a < 254), "total_pixels": count}


def authored(example_bytes, helper_sha, image):
    # This is deliberately invented host state, UUIDs and opaque flat pixels.
    # Passing these proves validator consistency, never native UI execution.
    ids = [str(uuid.UUID(int=index + 1)) for index in range(5)]
    copied = [{"index": index, "media_path": "Media/Import-" + ids[4] + "/" + ids[index] + ".wav",
               "bytes": 3_840_044, "sha256": digest, "source_sha256": digest,
               "track_id": ids[index], "clip_id": ids[index + 2], "track_clip_count": 1,
               "position_seconds": 0, "duration_seconds": 20, "source_offset_seconds": 0}
              for index, (_, digest) in enumerate(SOURCE_LOCKS)]
    # Test oracle declares the expected journey independently of the gate's
    # internal table. Mutations below exercise each equality and type boundary.
    phases = []
    requests = dict.fromkeys(COMMANDS, 0)
    revisions = [30, 30, 31, 32, 33, 33, 33, 33, 34, 35, 36]
    actions = {0: "newProject", 2: "importAudio", 3: "undo", 4: "redo", 5: "importAudio", 8: "saveAs", 9: "newProject", 10: "open"}
    for index, phase in enumerate(PHASES):
        if index in actions: requests[actions[index]] += 1
        empty = index in (0, 1, 3, 9)
        selected = None if empty else copied[0 if index == 10 else 1]
        project_key = "new" if index in (0, 1, 3) else "another-new" if index == 9 else "imported"
        state_key = "new" if index in (0, 1) else "redone" if index in (4, 5, 6, 7) else phase
        phases.append({"phase": phase, "revision": revisions[index], "track_count": 0 if empty else 2,
            "dirty": index in (2, 4, 5, 6, 7), "needs_save_as": index not in (8, 10),
            "can_undo": index in (2, 4, 5, 6, 7, 8), "can_redo": index == 3,
            "state_sha256": sha(("authored-state-" + state_key).encode()),
            "project_sha256": sha(("authored-project-" + project_key).encode()),
            "track_id": selected["track_id"] if selected else None, "clip_id": selected["clip_id"] if selected else None,
            "position_seconds": 0, "requests": requests.copy()})
    headers, clips = [], []
    for index, media in enumerate(copied):
        headers.append({"x": 100, "y": 150 + index * 44, "width": 198, "height": 44,
                        "track_id": media["track_id"], "clip_id": None})
        clips.append({"x": 298, "y": 153 + index * 44, "width": 480, "height": 38,
                      "track_id": media["track_id"], "clip_id": media["clip_id"]})
    return {"outcome": "passed", "checks": ["unrelated-established-check", *CHECKS], "documents": {
        "tested": True, "helper_sha256": helper_sha, "example_manifest_sha256": sha(example_bytes),
        "invalid_input": {"bytes": len(INVALID_BYTES), "sha256": sha(INVALID_BYTES)},
        "inputs": [{"path": "Examples/Rebase Preview.rebaseproj/Media/" + name, "sha256": digest, "bytes": 3_840_044}
                   for name, digest in SOURCE_LOCKS], "copied_media": copied, "phases": phases, "requests": requests,
        "capture": {"file": CAPTURE, "sha256": sha(image), "bounds": {"outer_width_dip": 1040,
            "outer_height_dip": 743, "width_dip": 1024, "height_dip": 704, "dpi_scale_x": 1,
            "dpi_scale_y": 1, "pixel_width": 1024, "pixel_height": 704}, "headers": headers, "clips": clips,
            "waveform_count": 2, "pixels_per_second": 24, "horizontal_offset": 0, "vertical_offset": 0,
            "frame_excluded": True, "alpha_coverage": coverage()}, "physical_input_tested": False, "native_file_pickers_tested": False,
        "playback_tested": False, "input_evidence": INPUT_EVIDENCE}}


def set_path(value, path, replacement):
    for key in path[:-1]: value = value[key]
    value[path[-1]] = replacement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    evidence = output / "authored-pixels"; evidence.mkdir()
    example_path = Path(__file__).resolve().parents[1] / "Examples/example.json"
    example = example_path.read_bytes()
    helper = sha(b"Authored helper identity, no helper execution")
    image = png(); baseline = authored(example, helper, image)
    checks = []
    result = {"schema": "rebase.documents-window-gate-controls.v1", "outcome": "failed",
              "evidence_class": "authored-receipt-and-pixel-mutation-controls", "native_wpf_executed": False,
              "helper_executed": False, "physical_input_tested": False, "playback_tested": False,
              "example_manifest_sha256": sha(example), "gate_sha256": sha(Path(__file__).with_name("documents_window_gate.py").read_bytes()),
              "instrument_sha256": sha(Path(__file__).read_bytes()), "checks": checks}
    def run(label, mutation=None, accept=False, pixels=None, manifest=None, helper_override=None, absent=False):
        sample = copy.deepcopy(baseline); data = image if pixels is None else pixels
        path = evidence / CAPTURE
        if absent:
            if path.exists(): path.unlink()
        else: path.write_bytes(data)
        sample["documents"]["capture"]["sha256"] = sha(data)
        if mutation: mutation(sample)
        try:
            summary = require_documents_window(sample, evidence, example if manifest is None else manifest,
                                               helper if helper_override is None else helper_override)
            accepted = True
        except ValueError:
            accepted = False; summary = None
        checks.append({"name": label, "expected": "accepted" if accept else "rejected",
                       "observed": "accepted" if accepted else "rejected", "passed": accepted == accept})
        if accepted != accept: raise AssertionError(label + " produced an unexpected gate result")
        return summary
    try:
        result["baseline_summary"] = run("complete-authored-control", accept=True)
        for label, path, value in (
            ("failed-smoke", ["outcome"], "failed"), ("no-record", ["documents"], None),
            ("boolean-test-counter", ["documents", "phases", 0, "revision"], True),
            ("wrong-helper", ["documents", "helper_sha256"], "0" * 64),
            ("wrong-example", ["documents", "example_manifest_sha256"], "0" * 64),
            ("unperformed", ["documents", "tested"], False),
            ("physical-claim", ["documents", "physical_input_tested"], True),
            ("dialog-claim", ["documents", "native_file_pickers_tested"], True),
            ("playback-claim", ["documents", "playback_tested"], True),
            ("input-provenance", ["documents", "input_evidence"], "physical click"),
            ("invalid-control-hash", ["documents", "invalid_input", "sha256"], "f" * 64),
            ("invalid-control-size", ["documents", "invalid_input", "bytes"], 0),
            ("source-hash", ["documents", "inputs", 0, "sha256"], "0" * 64),
            ("source-path", ["documents", "inputs", 0, "path"], "../rhythm.wav"),
            ("source-size", ["documents", "inputs", 1, "bytes"], 3840043),
            ("saved-hash", ["documents", "copied_media", 0, "sha256"], "0" * 64),
            ("saved-source-hash", ["documents", "copied_media", 1, "source_sha256"], "0" * 64),
            ("saved-bool-size", ["documents", "copied_media", 1, "bytes"], True),
            ("saved-index", ["documents", "copied_media", 1, "index"], 0),
            ("saved-traversal", ["documents", "copied_media", 1, "media_path"], "Media/../outside.wav"),
            ("two-clips-per-track", ["documents", "copied_media", 0, "track_clip_count"], 2),
            ("wrong-insertion", ["documents", "copied_media", 0, "position_seconds"], 1),
            ("short-duration", ["documents", "copied_media", 1, "duration_seconds"], 19),
            ("trimmed-source", ["documents", "copied_media", 1, "source_offset_seconds"], .5),
            ("invalid-uuid", ["documents", "copied_media", 1, "track_id"], "not-a-uuid"),
            ("bad-state-hash", ["documents", "phases", 0, "state_sha256"], ""),
            ("extra-import-revision", ["documents", "phases", 2, "revision"], 32),
            ("missing-dirty", ["documents", "phases", 2, "dirty"], False),
            ("missing-save-as", ["documents", "phases", 2, "needs_save_as"], False),
            ("partial-undo", ["documents", "phases", 3, "track_count"], 1),
            ("more-than-one-undo", ["documents", "phases", 3, "can_undo"], True),
            ("redo-lost-identity", ["documents", "phases", 4, "project_sha256"], "a" * 64),
            ("failed-batch-mutates", ["documents", "phases", 5, "state_sha256"], "a" * 64),
            ("dirty-cancel-mutates", ["documents", "phases", 6, "state_sha256"], "a" * 64),
            ("save-cancel-dispatches", ["documents", "phases", 7, "requests", "saveAs"], 1),
            ("save-remains-dirty", ["documents", "phases", 8, "dirty"], True),
            ("clean-new-history", ["documents", "phases", 9, "can_redo"], True),
            ("reopen-lost-project", ["documents", "phases", 10, "project_sha256"], "a" * 64),
            ("reopen-history-leak", ["documents", "phases", 10, "can_undo"], True),
            ("incorrect-selection", ["documents", "phases", 2, "clip_id"], None),
            ("picker-cancel-dispatches", ["documents", "phases", 1, "requests", "importAudio"], 1),
            ("total-request-count", ["documents", "requests", "newProject"], 3),
            ("missing-waveforms", ["documents", "capture", "waveform_count"], 0),
            ("capture-unsafe-path", ["documents", "capture", "file"], "../capture.png"),
            ("capture-unbound-hash", ["documents", "capture", "sha256"], "0" * 64),
            ("frame-not-excluded", ["documents", "capture", "frame_excluded"], False),
            ("zoom-mismatch", ["documents", "capture", "pixels_per_second"], 32),
            ("scrolled-viewport", ["documents", "capture", "horizontal_offset"], 50),
            ("bool-pixels", ["documents", "capture", "bounds", "pixel_width"], True),
            ("DPI-mismatch", ["documents", "capture", "bounds", "dpi_scale_x"], 1.5),
            ("nonfinite-geometry", ["documents", "capture", "clips", 0, "x"], float("nan")),
            ("clipped-event", ["documents", "capture", "clips", 0, "x"], 900),
            ("short-event-geometry", ["documents", "capture", "clips", 0, "width"], 479),
            ("overlapping-rows", ["documents", "capture", "clips", 1, "y"], 153),
            ("unbound-geometry-id", ["documents", "capture", "clips", 0, "clip_id"], None)):
            run(label, lambda value, p=path, v=value: set_path(value, p, v))
        run("missing-label", lambda value: value["checks"].pop())
        run("duplicate-label", lambda value: value["checks"].append(CHECKS[0]))
        run("reordered-labels", lambda value: value["checks"].reverse())
        run("missing-phase", lambda value: value["documents"]["phases"].pop())
        run("omitted-empty-selection", lambda value: value["documents"]["phases"][0].pop("clip_id"))
        run("omitted-header-selection", lambda value: value["documents"]["capture"]["headers"][0].pop("clip_id"))
        run("reordered-phases", lambda value: value["documents"]["phases"].reverse())
        run("duplicate-media-id", lambda value: value["documents"]["copied_media"][1].update(track_id=value["documents"]["copied_media"][0]["track_id"]))
        run("split-batch", lambda value: value["documents"]["copied_media"][1].update(media_path="Media/Import-" + str(uuid.UUID(int=9)) + "/" + str(uuid.UUID(int=10)) + ".wav"))
        run("unexpected-command", lambda value: value["documents"]["requests"].update(render=1))
        run("missing-client-image", absent=True)
        run("wrong-pixel-extent", pixels=png(width=1023))
        run("uncovered-alpha", lambda value: value["documents"]["capture"].update(alpha_coverage=coverage(253)), pixels=png(alpha=253))
        run("transparent-pixel", lambda value: value["documents"]["capture"].update(alpha_coverage=coverage(first_alpha=0)), pixels=png(first_alpha=0))
        run("measured-alpha254", lambda value: value["documents"]["capture"].update(alpha_coverage=coverage(254)), accept=True, pixels=png(alpha=254))
        run("measured-alpha254-and255", lambda value: value["documents"]["capture"].update(alpha_coverage=coverage(first_alpha=254)), accept=True, pixels=png(first_alpha=254))
        run("missing-alpha-coverage", lambda value: value["documents"]["capture"].pop("alpha_coverage"))
        run("null-alpha-coverage", lambda value: value["documents"]["capture"].update(alpha_coverage=None))
        for label, key, replacement in (("nonopaque-root", "root_background_alpha", 254),
                ("boolean-alpha-count", "alpha_254_pixels", False), ("negative-alpha-count", "alpha_254_pixels", -1),
                ("wrong-alpha254-count", "alpha_254_pixels", 1), ("wrong-alpha255-count", "alpha_255_pixels", 720895),
                ("wrong-alpha-total", "total_pixels", 720895), ("wrong-alpha-minimum", "alpha_minimum", 254),
                ("false-alpha-hole", "alpha_below_254_pixels", 1)):
            run(label, lambda value, k=key, v=replacement: value["documents"]["capture"]["alpha_coverage"].update({k: v}))
        run("extra-alpha-field", lambda value: value["documents"]["capture"]["alpha_coverage"].update(unmeasured=True))
        run("bad-pixel-filter", pixels=png(filter_byte=5))
        run("wrong-PNG-DPI", pixels=png(dpi=4000))
        run("truncated-image", pixels=image[:-1])
        run("trailing-image-data", pixels=image + b"extra")
        run("image-CRC-mismatch", pixels=image[:-1] + bytes((image[-1] ^ 1,)))
        run("invalid-example-JSON", manifest=b'{"schema":"bad"}')
        run("duplicate-example-JSON", manifest=b'{"schema":1,"schema":2}')
        run("invalid-expected-helper", helper_override="bad")
        expanded = lambda value: [row.update(y=150 + index * 68, height=68) for index, row in enumerate(value["documents"]["capture"]["headers"])] + [row.update(y=155 + index * 68, height=58) for index, row in enumerate(value["documents"]["capture"]["clips"])]
        run("valid-normal-density", expanded, accept=True)
        result["outcome"] = "passed"
    finally:
        # Restore the explicit authored baseline PNG; no malformed test pixel is
        # left under a filename that could be mistaken for the accepted control.
        (evidence / CAPTURE).write_bytes(image)
        (output / "authored-baseline.json").write_text(json.dumps(baseline, indent=2) + "\n")
        result["control_count"] = len(checks)
        log = "\n".join(row["name"] + ": " + row["observed"] for row in checks) + "\n"
        # Explicit bytes keep the log and its receipt identical on Windows,
        # where text-mode writing would translate LF into CRLF.
        log_path = output / "controls.log"
        log_path.write_bytes(log.encode("utf-8"))
        result["controls_log_sha256"] = sha(log_path.read_bytes())
        (output / "observation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"outcome": result["outcome"], "control_count": len(checks), "native_wpf_executed": False}))


if __name__ == "__main__":
    main()
