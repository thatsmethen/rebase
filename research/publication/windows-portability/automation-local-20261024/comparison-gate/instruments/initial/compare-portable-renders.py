#!/usr/bin/env python3
"""Compare the actual authored-example PCM hashes from four successful CI lanes."""
import argparse
import json
from pathlib import Path
import sys

from windows_automation_gate import require_automation_protocol

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
report = {"schema": "rebase.portable-render-comparison.v1", "status": "failed",
          "scope": "Cross-platform authored-example render only; no device playback or reference fidelity claim"}
try:
    paths = sorted(args.input.rglob("example-render.json"))
    records = [json.loads(path.read_text()) for path in paths]
    actual = [(row["platform"], row["configuration"]) for row in records]
    required = {(system, configuration) for system in ("Windows", "Darwin") for configuration in ("Debug", "Release")}
    if len(actual) != 4 or set(actual) != required:
        raise ValueError("Expected exactly Windows/macOS Debug and Release render records")
    if any(row.get("matches_predeclared_lock") is not True for row in records):
        raise ValueError("Every render must match the predeclared example lock")
    if any(row.get("regular_file") is not True or row.get("repeat_render_refused_without_modification") is not True
           for row in records):
        raise ValueError("Every render must verify regular-file publication and preservation on overwrite refusal")
    comparison_fields = ("frames", "channels", "sample_rate", "bits_per_sample", "pcm_sha256", "wav_sha256", "wav_bytes", "commit", "expected_render_lock_sha256")
    reference = records[0]
    for record in records[1:]:
        differing = [field for field in comparison_fields if record[field] != reference[field]]
        if differing:
            raise ValueError("Rendered output differs in: " + ", ".join(differing))
    report["matching_fields"] = {field: reference[field] for field in comparison_fields}
    report["lanes"] = [{key: row[key] for key in ("platform", "architecture", "configuration")} for row in records]
    app = Path(__file__).resolve().parent.parent
    example = json.loads((app / "Examples/Rebase Preview.rebaseproj/Project.json").read_text())
    lock = json.loads((app / "scripts/example-render-lock.json").read_text())
    automation = []
    for path, rendered in zip(paths, records):
        lane = json.loads((path.parent / "conformance.json").read_text())
        session = json.loads((path.parent / "session-protocol.json").read_text())
        if (lane.get("status") != "passed" or lane.get("commit") != rendered["commit"]
                or lane.get("platform") != rendered["platform"]
                or lane.get("configuration") != rendered["configuration"]
                or session.get("status") != "passed"):
            raise ValueError("Automation comparison needs a successful source-matched session for every lane")
        require_automation_protocol(session, example, lock)
        if lane.get("automation_control") != session["automation"]:
            raise ValueError("Automation conformance summary differs from its actual process receipt")
        automation.append(session["automation"])
    automation_fields = ("edited_wav_sha256", "edited_pcm_sha256", "restored_wav_sha256",
                         "restored_pcm_sha256", "original_track_id", "original_lane_id",
                         "original_point_count", "mutation_count", "invalid_requests_checked")
    if any(row[field] != automation[0][field] for row in automation[1:] for field in automation_fields):
        raise ValueError("Edited/restored automation output differs across platform or configuration")
    report["automation_matching_fields"] = {key: automation[0][key] for key in automation_fields}
    report["automation_scope"] = "Actual edited and restored authored-project WAV/PCM bytes; original locks remain unchanged. No device audio or reference equivalence claim."
    report["status"] = "passed"
except Exception as error:
    report["error"] = str(error)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
