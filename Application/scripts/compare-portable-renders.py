#!/usr/bin/env python3
"""Compare the actual authored-example PCM hashes from four successful CI lanes."""
import argparse
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
report = {"schema": "rebase.portable-render-comparison.v1", "status": "failed",
          "scope": "Cross-platform authored-example render only; no device playback or reference fidelity claim"}
try:
    records = [json.loads(path.read_text()) for path in sorted(args.input.rglob("example-render.json"))]
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
    report["status"] = "passed"
    report["matching_fields"] = {field: reference[field] for field in comparison_fields}
    report["lanes"] = [{key: row[key] for key in ("platform", "architecture", "configuration")} for row in records]
except Exception as error:
    report["error"] = str(error)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
