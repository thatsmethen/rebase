#!/usr/bin/env python3
"""Read-only APP004 persisted-package checks; Python standard library only.

Snapshot the nine APP003 historical files before GUI work:
  python3 .../verify-gui-packages.py snapshot --out .../historical-before.json
Verify a new package using a retained independent cpr_probe/0.3 JSON:
  python3 .../verify-gui-packages.py verify --package NAME.rebaseproj \
    --fixture PROBE.json --historical-before .../historical-before.json \
    --out CHECK.json [--allow-project-name-change]
Check only historical preservation after GUI work:
  python3 .../verify-gui-packages.py history --before BEFORE.json --out AFTER.json

This does not execute either application, replay the native reader, or assert
GUI actions, reference runtime equivalence or full CPR recovery. It cross-checks
persisted output against independently retained fixture offsets and raw bytes.
All outputs are exclusive-create; no package/source files are written.
"""
from pathlib import Path
import argparse
import copy
import datetime
import hashlib
import json
import math
import struct
import sys

ROOT = Path(__file__).resolve().parents[4]
HISTORICAL_ROOT = ROOT / "research/evidence/application/APP003"
PACKAGE_NAMES = ("Classic House Recovery.rebaseproj", "Stereo Mastering Recovery.rebaseproj",
                 "Stereo Mastering Copy.rebaseproj")
PACKAGE_FILES = ("Project.json", "Compatibility/CPR/ImportReport.json", "Compatibility/CPR/Original.cpr")
CONTRACT = "cubase-15.0.30.287-arm64-fixed-v1"
PROFILE = "cpr-static-subset-v2"


class VerificationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def path_at_root(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def read(path, pins=None, limit=268_435_456):
    path = path_at_root(path)
    require(path.absolute() == path.resolve(), f"Redirected path: {path}")
    before = path.stat()
    require(path.is_file() and before.st_size <= limit, f"Not a bounded regular file: {path}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    require(identity(before) == identity(after) and len(data) == before.st_size,
            f"File changed during read: {path}")
    if pins is not None:
        pins.append({"path": str(path), "bytes": len(data), "sha256": sha(data)})
    return data


def strict_json(data):
    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject(value):
        raise VerificationError(f"Nonfinite JSON literal: {value}")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def number(data, fmt, offset):
    require(type(offset) is int and 0 <= offset <= len(data) - struct.calcsize(fmt),
            f"Numeric extent outside source: {offset}")
    return struct.unpack_from(fmt, data, offset)[0]


def history_snapshot():
    expected = {str(HISTORICAL_ROOT / name / relative)
                for name in PACKAGE_NAMES for relative in PACKAGE_FILES}
    actual = set()
    for name in PACKAGE_NAMES:
        package = HISTORICAL_ROOT / name
        require(package.is_dir() and package.resolve() == package, f"Historical package missing/redirected: {package}")
        for path in package.rglob("*"):
            require(not path.is_symlink(), f"Historical package symlink: {path}")
            if path.is_file():
                actual.add(str(path))
    require(actual == expected, f"Historical package file inventory differs: {sorted(actual ^ expected)}")
    pins = []
    for path in sorted(expected):
        read(path, pins)
    return {"scope": "Exact byte hashes of all nine retained files in three APP003 packages; no source reinterpretation.",
            "file_count": len(pins), "files": pins}


def compare_history(before_path, pins):
    before = strict_json(read(before_path, pins))
    require(before.get("id") == "APP004-HISTORICAL-PACKAGE-SNAPSHOT" and before.get("status") == "passed",
            "Expected a successful before-snapshot from this verifier.")
    after = history_snapshot()
    require(before["historical_packages"]["files"] == after["files"], "APP003 historical package bytes changed.")
    return {**after, "unchanged_from_before": True, "before_snapshot": str(path_at_root(before_path))}


def object_map(fixture, source):
    objects = {}
    for value in walk(fixture):
        if value.get("kind") != "object":
            continue
        identity, start, size = value["size_offset"], value["body_offset"], value["body_bytes"]
        require(start == identity + 4 and number(source, ">I", identity) == size,
                "Fixture object identity/length framing mismatch.")
        require(0 <= start <= start + size <= len(source), "Fixture object exceeds source bounds.")
        require(sha(source[start:start + size]) == value["body_sha256"], "Fixture object payload hash mismatch.")
        if identity in objects:
            require(objects[identity] == value, "Fixture contains inconsistent object identity.")
        objects[identity] = value
    return objects


def signature_values(source, fixture_objects):
    candidates = [o for o in fixture_objects.values() if o.get("class") == "MSignatureTrackEvent" and "decoded" in o]
    require(len(candidates) == 1, "Verifier supports one independently decoded signature object.")
    obj = candidates[0]
    decoded = obj["decoded"]
    require(obj["version"] == 3 and decoded["consumed_exactly"], "Unsupported signature fixture framing.")
    require(decoded["compact_count"] == number(source, ">I", decoded["count_offset"]) == 1,
            "Expected exactly one compact signature.")
    compact = decoded["compact_records"]
    require(len(compact) == 1, "Unexpected compact record list.")
    at = compact[0]["offset"]
    record = struct.unpack_from(">i6h", source, at)
    require(list(record) == [compact[0]["position_i32"], *compact[0]["six_i16"]],
            "Compact fixture values disagree with source bytes.")
    require(record[0] == 0 and record[3:] == (0, 0, 0, 8), "Unsupported compact origin/extras.")
    items = decoded["candidate_full_items"]
    require(len(items) == 1, "Expected one typed signature item.")
    fields = items[0]["scalar_fields"]
    values = {}
    for name, field in fields.items():
        start, type_at, value_at = field["offset"], field["type_offset"], field["value_offset"]
        name_size = number(source, ">I", start)
        require(source[start + 4:start + 4 + name_size] == name.encode("ascii") + b"\0"
                and type_at == start + 4 + name_size and value_at == type_at + 2,
                f"Named scalar framing differs: {name}")
        code = number(source, ">H", type_at)
        require(code == field["type_code"] and code in (1, 4), f"Unsupported scalar type: {name}")
        value = number(source, ">q" if code == 1 else ">d", value_at)
        require(value == field["value"] and field["end"] == value_at + 8, f"Named scalar bytes differ: {name}")
        values[name] = value
    require(fields["Bar"]["type_code"] == fields["Numerator"]["type_code"] == fields["Denominator"]["type_code"] == 1,
            "Origin signature requires exact integer types.")
    require(values["Bar"] == 0 and values["Flags"] == 8 and values["Start"] == 0 and values["Length"] == 1,
            "Unsupported typed signature origin/flags.")
    meter = (values["Numerator"], values["Denominator"])
    require(meter == record[1:3] and 1 <= meter[0] <= 64 and meter[1] in (1, 2, 4, 8, 16),
            "Compact/typed meter disagreement or unsupported meter.")
    return obj, meter, values


def verify_package(args, pins):
    package = path_at_root(args.package)
    fixture = strict_json(read(args.fixture, pins))
    require(fixture.get("target_executed") is False and fixture.get("tool") == "cpr_probe/0.3",
            "Expected retained independent cpr_probe/0.3 evidence.")
    source = read(fixture["source"], pins)
    require(sha(source) == fixture["sha256"] and len(source) == fixture["bytes"], "Fixture source pin mismatch.")
    original = read(package / PACKAGE_FILES[2], pins)
    require(original == source, "Preserved CPR is not byte-identical to the pinned fixture source.")
    report_bytes = read(package / PACKAGE_FILES[1], pins, limit=8_388_608)
    report = strict_json(report_bytes)
    project = strict_json(read(package / PACKAGE_FILES[0], pins, limit=8_388_608))
    require(report["schemaVersion"] == 2 and report["interpretationProfile"] == PROFILE,
            "New package does not declare the expected schema/profile.")
    require(report["sourceSHA256"] == sha(source) and report["sourceByteCount"] == len(source),
            "Report source hash/length mismatch.")
    require(report["sourceName"] == Path(fixture["source"]).name, "Report source name mismatch.")
    baseline = report["recoveredProject"]
    require(isinstance(baseline, dict), "Report contains no recovered project.")
    differences = sorted(k for k in project.keys() | baseline.keys() if project.get(k) != baseline.get(k))
    expected_project = copy.deepcopy(baseline)
    if args.project_clock == "converted":
        require(expected_project["tempoMap"].get("nativeClock") is not None,
                "Conversion verification requires a native clock in the historical import baseline.")
        del expected_project["tempoMap"]["nativeClock"]
    if args.allow_project_name_change:
        expected_project["name"] = project["name"]
    require(project == expected_project,
            f"Saved project differs from baseline outside the explicit name/clock conversion allowance: {differences}")
    copy_check = None
    if args.copied_from:
        prior = path_at_root(args.copied_from)
        require(read(prior / PACKAGE_FILES[2], pins) == original, "Copy changed preserved CPR bytes.")
        require(read(prior / PACKAGE_FILES[1], pins, limit=8_388_608) == report_bytes, "Copy changed historical import report bytes.")
        copy_check = {"source_package": str(prior), "original_and_report_byte_identical": True}
    objects = object_map(fixture, source)
    report_objects = {}
    for obj in report["nativeObjects"]:
        identity, start, size = obj["identityOffset"], obj["payloadOffset"], obj["payloadByteCount"]
        require(identity not in report_objects, "Duplicate native object identity in report.")
        require(start == identity + 4 and number(source, ">I", identity) == size
                and 0 <= start <= start + size <= len(source), "Reported object extent mismatch.")
        require(sha(source[start:start + size]) == obj["payloadSHA256"], "Reported object payload hash mismatch.")
        if identity in objects:
            for a, b in (("className", "class"), ("version", "version"), ("declarationOffset", "class_declaration_offset"),
                         ("objectOffset", "offset"), ("payloadOffset", "body_offset"), ("payloadByteCount", "body_bytes")):
                require(obj[a] == objects[identity][b], f"Reported versus fixture object field mismatch: {a}")
        report_objects[identity] = obj
    clocks = [report.get("nativeClock"), baseline["tempoMap"].get("nativeClock"), project["tempoMap"].get("nativeClock")]
    require(clocks[0] == clocks[1], "Report and recovered baseline native clock descriptors differ.")
    require(clocks[2] == (None if args.project_clock == "converted" else clocks[0]),
            "Saved project clock differs from the explicitly requested recovered/converted state.")
    tempos = [o for o in objects.values() if o.get("class") == "MTempoTrackEvent" and "decoded" in o]
    require(len(tempos) == 1 and tempos[0]["version"] == 3, "Expected one independently decoded v3 tempo object.")
    tempo = tempos[0]
    count = number(source, ">I", tempo["body_offset"])
    require(0 < count <= 10_000, "Invalid tempo record count.")
    fixed_at = tempo["body_offset"] + 4 + count * 22
    require(fixed_at + 6 <= tempo["end"] and fixed_at == tempo["decoded"]["fixed_bpm_offset"], "Fixed-tempo field extent mismatch.")
    bits = number(source, ">I", fixed_at)
    bpm = number(source, ">f", fixed_at)
    mode = number(source, ">H", fixed_at + 4)
    require(mode == tempo["decoded"]["fixed_enabled_u16"] and bpm == tempo["decoded"]["fixed_bpm_f32"], "Tempo fixture scalar mismatch.")
    clock = clocks[0]
    if mode:
        require(math.isfinite(bpm) and 20 <= bpm <= 400 and isinstance(clock, dict), "Fixed source has no supported native clock.")
        expected = {"contract": CONTRACT, "fixedBPMBits": bits, "sourceSHA256": sha(source),
                    "sourceObjectOffset": tempo["size_offset"], "interpretationProfile": PROFILE}
        require(clock == expected, "Native clock descriptor does not match original Float32 bits/object identity.")
        require(tempo["size_offset"] in report_objects, "Native clock object absent from report.")
    else:
        require(clock is None, "Map-mode source incorrectly acquired a fixed native clock.")
    events = project["tempoMap"]["events"]
    require(len(events) == 1 and events[0]["beat"] == 0 and events[0]["curve"] == "jump"
            and events[0]["bpm"] == project["tempo"] == (bpm if mode else 120), "Project scalar tempo mismatch.")
    signature, meter, fields = signature_values(source, objects)
    require(signature["size_offset"] in report_objects, "Recovered signature object absent from report.")
    signature_events = project["signatureMap"]["events"]
    require(len(signature_events) == 1 and signature_events[0]["beat"] == 0
            and (signature_events[0]["numerator"], signature_events[0]["denominator"]) == meter,
            "Saved meter does not match the consistent source origin signature.")
    require(any(f"Recovered consistent origin signature {meter[0]}/{meter[1]}" in fact for fact in report["recoveredFacts"]),
            "Report lacks the bounded recovered-meter fact.")
    return {
        "source_preservation": {"byte_identical": True, "source_sha256": sha(source), "source_bytes": len(source)},
        "report_and_project": {"schema_version": 2, "interpretation_profile": PROFILE,
                               "baseline_differences": differences, "expected_project_clock_state": args.project_clock,
                               "copy_preservation": copy_check, "native_object_payload_hashes_checked": len(report_objects)},
        "native_clock": {"mode_u16": mode, "descriptor": clock, "source_object_identity_offset": tempo["size_offset"],
                         "saved_project_descriptor": clocks[2],
                         "fixed_bpm_bits_u32": bits, "fixed_bpm_field_offset": fixed_at, "source_fixed_bpm": bpm,
                         "scope": "Source field bits, descriptor and persisted-project consistency; arithmetic and native runtime are not executed."},
        "signature": {"numerator": meter[0], "denominator": meter[1], "beat": 0,
                      "source_object_identity_offset": signature["size_offset"], "typed_bar": fields["Bar"],
                      "typed_position": fields.get("Position"), "compact_and_typed_agree": True,
                      "scope": "Pinned independent structural fixture plus reread compact and typed scalar bytes. No independent replay of host compatibility or variation lifecycle."}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--out", required=True, type=Path)
    history = commands.add_parser("history")
    history.add_argument("--before", required=True, type=Path)
    history.add_argument("--out", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--package", required=True, type=Path)
    verify.add_argument("--fixture", required=True, type=Path)
    verify.add_argument("--historical-before", required=True, type=Path)
    verify.add_argument("--allow-project-name-change", action="store_true")
    verify.add_argument("--project-clock", choices=("recovered", "converted"), default="recovered")
    verify.add_argument("--copied-from", type=Path)
    verify.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = path_at_root(args.out)
    require(not output.exists(), "Refusing to overwrite an existing evidence output.")
    require(not any(part.endswith(".rebaseproj") for part in output.parts), "Evidence output must be outside project packages.")
    result = {"id": "APP004-HISTORICAL-PACKAGE-SNAPSHOT" if args.command == "snapshot" else "APP004-INDEPENDENT-PERSISTED-PACKAGE-CHECK",
              "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "command": args.command, "verifier_sha256": sha(Path(__file__).read_bytes()), "input_pins": [],
              "limits": ["Read-only persisted-file verification; GUI action provenance is separately owned.",
                         "No target execution, application execution, native runtime comparison, or full project fidelity claim.",
                         "A historical hash match proves preservation, not compatibility replay or correctness of its earlier interpretation."]}
    try:
        if args.command == "snapshot":
            result["historical_packages"] = history_snapshot()
        elif args.command == "history":
            result["historical_packages"] = compare_history(args.before, result["input_pins"])
        else:
            result["package_checks"] = verify_package(args, result["input_pins"])
            result["historical_packages"] = compare_history(args.historical_before, result["input_pins"])
        result["status"] = "passed"
    except (VerificationError, OSError, ValueError, KeyError, TypeError, struct.error) as error:
        result["status"] = "failed"
        result["error"] = str(error)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(result["status"], output, sha(output.read_bytes()))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
