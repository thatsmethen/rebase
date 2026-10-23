#!/usr/bin/env python3
"""Compare the actual authored-example PCM hashes from four successful CI lanes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from windows_automation_gate import require_automation_protocol


def read_object(path, schema):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property")
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError("Non-finite JSON number")

    try:
        result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys,
                            parse_constant=reject_constant)
    except (OSError, ValueError) as error:
        raise ValueError("Missing or malformed receipt: " + path.name) from error
    if not isinstance(result, dict) or result.get("schema") != schema:
        raise ValueError("Unsupported receipt schema: " + path.name)
    return result


def positive_integer(value):
    return type(value) is int and value > 0


def digest(value, length=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value) is not None


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
report = {"schema": "rebase.portable-render-comparison.v1", "status": "failed",
          "scope": "Cross-platform authored-example render only; no device playback or reference fidelity claim"}
try:
    app = Path(__file__).resolve().parent.parent
    lock_path = app / "scripts/example-render-lock.json"
    lock = read_object(lock_path, "rebase.example-render-lock.v1")
    lock_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    example = json.loads((app / "Examples/Rebase Preview.rebaseproj/Project.json").read_text(encoding="utf-8"))
    expected_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=app,
                                             text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
    if not digest(expected_commit, 40):
        raise ValueError("The comparison checkout has no supported source commit identity")
    architectures = {"Windows": "AMD64", "Darwin": "arm64"}
    integer_fields = ("frames", "channels", "sample_rate", "bits_per_sample", "wav_bytes")
    locked_fields = ("frames", "channels", "sample_rate", "bits_per_sample", "pcm_sha256", "wav_sha256")
    paths = sorted(args.input.rglob("example-render.json"))
    records = [read_object(path, "rebase.portable-render.v1") for path in paths]
    for row in records:
        if (row.get("platform") not in architectures
                or row.get("architecture") != architectures[row["platform"]]
                or row.get("configuration") not in ("Debug", "Release")):
            raise ValueError("Render record has an unsupported platform, architecture or configuration")
        if not digest(row.get("commit"), 40) or row["commit"] != expected_commit:
            raise ValueError("Render source identity differs from the comparison checkout")
        if any(not positive_integer(row.get(field)) for field in integer_fields):
            raise ValueError("Render dimensions must be positive integers")
        if any(not digest(row.get(field)) for field in ("pcm_sha256", "wav_sha256", "expected_render_lock_sha256")):
            raise ValueError("Render or lock identity is missing or malformed")
        if (row["expected_render_lock_sha256"] != lock_digest
                or any(row.get(field) != lock[field] for field in locked_fields)):
            raise ValueError("Render fields differ from the actual predeclared example lock")
        # The encoded file must at least contain the declared PCM and a RIFF
        # envelope. Exact audio bytes remain bound by the unchanged WAV hash.
        if row["bits_per_sample"] % 8 or row["wav_bytes"] <= row["frames"] * row["channels"] * (row["bits_per_sample"] // 8) + 12:
            raise ValueError("Rendered WAV size cannot contain its declared PCM")
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
    automation = []
    for path, rendered in zip(paths, records):
        lane = read_object(path.parent / "conformance.json", "rebase.portable-ci.v1")
        session = read_object(path.parent / "session-protocol.json", "rebase.session-protocol-check.v1")
        if (lane.get("status") != "passed" or lane.get("commit") != rendered["commit"]
                or lane.get("platform") != rendered["platform"]
                or lane.get("architecture") != rendered["architecture"]
                or lane.get("configuration") != rendered["configuration"]
                or session.get("status") != "passed"):
            raise ValueError("Automation comparison needs a successful source-matched session for every lane")
        checks = session.get("checks")
        if (not isinstance(checks, list) or not checks
                or any(not isinstance(check, str) or not check for check in checks)):
            raise ValueError("Session receipt has no complete nonempty check inventory")
        if (not positive_integer(session.get("frames")) or session["frames"] != rendered["frames"]
                or session.get("wav_sha256") != rendered["wav_sha256"]
                or session.get("pcm_sha256") != rendered["pcm_sha256"]):
            raise ValueError("Session original render differs from its lane's locked render")
        require_automation_protocol(session, example, lock)
        require_automation_protocol({"automation": lane.get("automation_control")}, example, lock)
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
