#!/usr/bin/env python3
"""Exercise all shared source modes in the actual JSONL helper.

Inputs are newly forward-authored controls, never reference playback. Raw process
traffic stays in a fresh private scratch folder; the report contains relative
coordinates and hashes only. Existing fixtures and earlier outcomes are retained.
"""
import argparse
import copy
import hashlib
import json
import math
import queue
import shutil
import struct
import subprocess
import tempfile
import threading
import traceback
from pathlib import Path


MODES = ("sourceRate", "nativeTimelineSourceRate", "nativeTimelineProjectClock",
         "nativeTimelineSavedProjectClock", "nativeTrackSavedProjectClock",
         "nativeMode0ProjectRate", "nativeMode1ProjectRate", "nativeMode2ProjectRate")
GATES = ("all_eight_modes", "read_only", "explicit_mode", "seek_fresh_cursor", "eof_revalidated",
         "complete_track_provenance", "covered_media_rejected", "stale_rejected", "invalid_rejected",
         "new_outputs_only", "source_unchanged")
MAX_REPLY = 16 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    """Normalize JSON numeric spelling only; retain every metadata field/value."""
    def normalize(item):
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("Non-finite metadata")
            return int(item) if item.is_integer() else item
        if isinstance(item, list):
            return [normalize(v) for v in item]
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()}
        return item
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def relative(root, name):
    path = Path(name)
    if path.is_absolute() or not path.parts or any(p in (".", "..") for p in path.parts):
        raise ValueError("Unsafe fixture path")
    candidate = root / path
    if candidate.resolve() != candidate.absolute() or any(p.is_symlink() for p in [candidate, *candidate.parents] if p != root.parent):
        raise ValueError("Redirected fixture path")
    return candidate


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Fixture contains a link")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return files


def events(project):
    return [event for track in project["tracks"] for event in track.get("unresolvedAudioEvents", [])]


def attachment(project, event):
    identity = event["files"][0]["object"]["identityOffset"]
    found = [a for a in project.get("cprMediaAttachments", [])
             if a["sourceFileIdentity"] == identity and a["sourceSHA256"] == event["sourceSHA256"]]
    if len(found) != 1:
        raise ValueError("Missing unique contributor media")
    return found[0]


def float_wave(data):
    if len(data) < 58 or data[:4] != b"RIFF" or data[8:12] != b"WAVE" or struct.unpack_from("<I", data, 4)[0] != len(data) - 8:
        raise ValueError("Invalid complete WAV")
    chunks, offset = {}, 12
    while offset + 8 <= len(data):
        tag, count = struct.unpack_from("<4sI", data, offset)
        offset += 8
        if tag in chunks or count > len(data) - offset:
            raise ValueError("Invalid WAV chunk")
        chunks[tag] = data[offset:offset + count]
        offset += count + count % 2
    if offset != len(data) or set(chunks) != {b"fmt ", b"fact", b"data"} or len(chunks[b"fmt "]) != 18:
        raise ValueError("Unexpected authored WAV format")
    fmt, channels, rate, byte_rate, align, bits, extension = struct.unpack("<HHIIHHH", chunks[b"fmt "])
    pcm = chunks[b"data"]
    if (fmt, channels, byte_rate, align, bits, extension) != (3, 2, rate * 8, 8, 32, 0) or len(pcm) % 8:
        raise ValueError("Invalid float stereo layout")
    count = len(pcm) // 8
    if chunks[b"fact"] != struct.pack("<I", count) or not all(math.isfinite(v[0]) for v in struct.iter_unpack("<f", pcm)):
        raise ValueError("Invalid finite PCM or fact count")
    return rate, count, pcm


class Client:
    def __init__(self, helper, work):
        self.stderr = (work / "helper-stderr.log").open("xb")
        self.traffic = (work / "helper-jsonl.log").open("xb")
        self.process = subprocess.Popen([str(helper), "--stdio"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.stderr)
        self.messages = queue.Queue()
        self.id = 0
        self.state = None
        def read():
            try:
                while True:
                    line = self.process.stdout.readline(MAX_REPLY + 2)
                    if not line:
                        self.messages.put(None)
                        return
                    self.messages.put(line)
            except BaseException as error:
                self.messages.put(error)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, command, expected=None, allow_unbound_failure=False, **fields):
        self.id += 1
        request = {"protocol": 1, "id": self.id, "command": command,
                   "expectedRevision": expected if expected is not None else (self.state or {}).get("revision", 0), **fields}
        line = canonical(request) + b"\n"
        self.traffic.write(b">" + line); self.traffic.flush()
        self.process.stdin.write(line); self.process.stdin.flush()
        reply = self.messages.get(timeout=60)
        if not isinstance(reply, bytes) or len(reply) > MAX_REPLY or not reply.endswith(b"\n"):
            raise RuntimeError("Missing or excessive helper response")
        self.traffic.write(b"<" + reply); self.traffic.flush()
        value = json.loads(reply)
        bound = value.get("id") == self.id or (allow_unbound_failure and value.get("id") is None and value.get("ok") is False)
        if value.get("protocol") != 1 or not bound or not isinstance(value.get("state"), dict):
            raise RuntimeError("Unbound helper response")
        self.state = value["state"]
        return value

    def close(self):
        try:
            self.process.stdin.close()
            status = self.process.wait(timeout=10)
        except BaseException:
            self.process.kill(); self.process.wait(timeout=10)
            raise
        finally:
            self.stderr.close(); self.traffic.close()
        if status != 0:
            raise RuntimeError("Helper did not exit successfully")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or not args.report.parent.is_dir():
        raise SystemExit("Choose a new report in an existing directory")
    helper, fixtures = args.helper.resolve(), args.fixtures.resolve()
    work = Path(tempfile.mkdtemp(prefix="cpr-modes-", dir=args.report.parent)).resolve()
    report = {"schema": "rebase.cpr-audition-modes-control.v1", "status": "failed",
              "evidence_class": "authored-shared-session-control", "helper_sha256": sha(helper.read_bytes()),
              "fixture_manifest_sha256": sha((fixtures / "expected.json").read_bytes()),
              "checks": [], "gates": dict.fromkeys(GATES, False), "scenarios": [],
              "playback_tested": False, "reference_execution": False}
    current_check = "initial fixture admission"
    client = None
    def check(condition, name):
        nonlocal current_check
        current_check = name
        if not condition:
            raise AssertionError(name)
        report["checks"].append(name)
    try:
        expected = json.loads((fixtures / "expected.json").read_bytes())
        check(expected["schemaVersion"] == 1 and expected["evidenceClass"] == "authored-synthetic-control"
              and [c["name"] for c in expected["cases"]] == ["single", "overlap"], "authored fixture declaration")
        initial_files = inventory(fixtures)
        fixture_cases = {}
        for case in expected["cases"]:
            source = relative(fixtures, case["root"])
            project = json.loads((source / "Project.json").read_bytes())
            check(sha((source / "Project.json").read_bytes()) == case["manifestSHA256"]
                  and sha((source / "Compatibility/CPR/Original.cpr").read_bytes()) == case["sourceSHA256"]
                  and sha((source / "Compatibility/CPR/ImportReport.json").read_bytes()) == case["reportSHA256"],
                  case["name"] + " exact source report and project locks")
            retained = events(project)
            check([e["id"] for e in retained] == [e["eventID"] for e in case["events"]]
                  and case["anchorID"] == retained[0]["id"], case["name"] + " complete retained identities")
            for event, control in zip(retained, case["events"]):
                media = attachment(project, event)
                check(media["mediaSHA256"] == control["mediaSHA256"]
                      and sha(relative(source, media["mediaPath"]).read_bytes()) == control["mediaSHA256"],
                      case["name"] + " contributor " + str(control["ordinal"]) + " media lock")
            destination = work / (case["name"] + ".rebaseproj")
            shutil.copytree(source, destination)
            fixture_cases[case["name"]] = (case, destination, project)
        client = Client(helper, work)
        report["inspection"] = []
        for case_name in ("single", "overlap"):
            case, root, original_project = fixture_cases[case_name]
            reply = client.send("open", path=str(root), discardChanges=True)
            check(reply.get("ok") is True, case_name + " open actual helper project")
            client.send("selectClip", clipID=case["anchorID"])
            track_id = next(t["id"] for t in original_project["tracks"] if any(e["id"] == case["anchorID"] for e in t.get("unresolvedAudioEvents", [])))
            check(client.send("setGain", trackID=track_id, value=-6).get("ok") is True, case_name + " dirty gain edit")
            check(client.send("setPan", trackID=track_id, value=0.25).get("ok") is True, case_name + " create redo history")
            check(client.send("undo").get("ok") is True, case_name + " retain dirty state and redo")
            stable = copy.deepcopy(client.state)
            check(stable["dirty"] is True and stable["canUndo"] is True and stable["canRedo"] is True
                  and stable["selection"]["clipID"] == case["anchorID"], case_name + " meaningful read-only precondition")
            inspected = client.send("inspectSourceEvent", clipID=case["anchorID"])
            inspection = inspected.get("sourceInspection", {})
            check(inspected.get("ok") is True and client.state == stable and inspection.get("revision") == stable["revision"]
                  and inspection.get("eventID") == case["anchorID"] and inspection.get("sourceSHA256") == case["sourceSHA256"]
                  and inspection.get("availabilityScope") == "preparation-only" and inspection.get("maximumFrames") == 32_000_000
                  and [r.get("mode") for r in inspection.get("modes", [])] == list(MODES), case_name + " all mode availability bound to unchanged state")
            availability = {r["mode"]: r for r in inspection["modes"]}
            selected_modes = MODES if case_name == "single" else MODES[1:5]
            check(all(availability[m].get("available") is True for m in selected_modes)
                  and all(availability[m].get("available") is False
                          and isinstance(availability[m].get("reason"), str) and availability[m]["reason"]
                          for m in MODES if m not in selected_modes), case_name + " admitted modes prepared")
            report["inspection"].append({"case": case_name, "modes": [{k: v for k, v in r.items() if k != "reason"} for r in inspection["modes"]]})
            current_events = {e["id"]: e for e in events(stable["project"])}
            expected_events = {e["eventID"]: e for e in case["events"]}
            baseline_pcm = {}
            def render(mode, seek, seconds=0, rewind=False, omit_mode=False):
                output = work / (case_name + "-" + mode + "-" + seek + ".wav")
                fields = {"clipID": case["anchorID"], "path": str(output), "startSeconds": seconds, "rewindAtEnd": rewind}
                if not omit_mode:
                    fields["mode"] = mode
                response = client.send("renderSourceEvent", **fields)
                receipt = response.get("render", {})
                check(response.get("ok") is True and client.state == stable, case_name + " " + mode + " " + seek + " leaves full session unchanged")
                manifest_path = output.with_name(output.name + ".source-audition.json")
                check(receipt.get("path") == str(output) and receipt.get("manifestPath") == str(manifest_path)
                      and output.is_file() and not output.is_symlink() and manifest_path.is_file() and not manifest_path.is_symlink(),
                      case_name + " " + mode + " " + seek + " exact new output paths")
                wave, proof_bytes = output.read_bytes(), manifest_path.read_bytes()
                check(len(proof_bytes) <= 8_388_608 and receipt.get("manifestBytes") == len(proof_bytes)
                      and receipt.get("manifestSHA256") == sha(proof_bytes) and receipt.get("wavBytes") == len(wave)
                      and receipt.get("sha256") == sha(wave), case_name + " " + mode + " " + seek + " complete output hash binding")
                proof = json.loads(proof_bytes)
                rate, frames, pcm = float_wave(wave)
                expected_rate = case["events"][0]["rate"] if mode in MODES[:2] else case["savedRate"] if mode in MODES[3:5] else case["projectRate"]
                clock_role = ("source-rate" if mode == MODES[0] else "source-clock-unconverted" if mode == MODES[1]
                              else "current-project-clock-unconverted" if mode == MODES[2]
                              else "saved-project-clock-unconverted" if mode in MODES[3:5]
                              else "current-project-rate-converted")
                check(proof.get("schema") == "rebase.source-audition-manifest.v1"
                      and receipt.get("kind") == "sourceEvent" and proof.get("wavFileName") == output.name
                      and proof.get("wavSHA256") == sha(wave) and proof.get("wavBytes") == len(wave)
                      and all(proof.get(k) == receipt.get(k) for k in ("mode", "revision", "eventID", "sourceSHA256", "mediaSHA256", "sampleRate", "frames", "startFrame", "totalFrames"))
                      and proof.get("mode") == mode and proof.get("eventID") == case["anchorID"]
                      and proof.get("sourceSHA256") == case["sourceSHA256"]
                      and proof.get("mediaSHA256") == case["events"][0]["mediaSHA256"]
                      and proof.get("projectManifestSHA256") == case["manifestSHA256"]
                      and proof.get("importReportSHA256") == case["reportSHA256"]
                      and proof.get("sampleRate") == rate == expected_rate and proof.get("frames") == frames
                      and proof.get("startFrame") + frames == proof.get("totalFrames")
                      and proof.get("totalFrames") == availability[mode]["frames"]
                      and proof.get("maximumFrames") == 32_000_000 and proof.get("channels") == 2
                      and receipt.get("channels") == 2 and proof.get("clockRole") == clock_role
                      and proof.get("timelineRange") == availability[mode].get("timelineRange")
                      and proof.get("projectSampleRate") == case["projectRate"]
                      and isinstance(proof.get("currentProjectSHA256"), str) and len(proof["currentProjectSHA256"]) == 64
                      and all(c in "0123456789abcdef" for c in proof["currentProjectSHA256"]),
                      case_name + " " + mode + " " + seek + " complete manifest semantics")
                frozen_report = json.loads((root / "Compatibility/CPR/ImportReport.json").read_bytes())
                check(proof.get("currentNativeClock") == stable["project"]["tempoMap"].get("nativeClock")
                      and proof.get("preservedNativeClock") == frozen_report.get("nativeClock"),
                      case_name + " " + mode + " " + seek + " original and active clocks preserved")
                if mode in MODES[3:5]:
                    setup = proof.get("savedProjectAudioSetup", {})
                    check(setup.get("sourceSHA256") == case["sourceSHA256"]
                          and setup.get("baseRateBits") == struct.unpack("<I", struct.pack("<f", case["savedRate"]))[0]
                          and setup.get("factorBits") == 0x3ff0000000000000
                          and setup.get("setup", {}).get("className") == "PArrangeSetup", case_name + " " + mode + " " + seek + " saved setup raw proof")
                if mode == "nativeTrackSavedProjectClock":
                    track = proof.get("sourceTrack", {})
                    contributors, fragments = track.get("events", []), track.get("fragments", [])
                    check(proof.get("sourceKind") == "track" and track.get("freshRootMode") == 0
                          and len(contributors) == len(case["events"])
                          and {e["eventID"] for e in contributors} == set(expected_events), case_name + " " + seek + " complete original contributor set")
                    for contributor in contributors:
                        control = expected_events[contributor["eventID"]]
                        check(contributor.get("eventIdentity") == current_events[contributor["eventID"]]["event"]["identityOffset"]
                              and contributor.get("sourceOrdinal") == control["ordinal"] and contributor.get("priority") == control["priority"]
                              and contributor.get("sourceSampleRate") == control["rate"] and contributor.get("mediaSHA256") == control["mediaSHA256"],
                              case_name + " " + seek + " contributor " + str(control["ordinal"]) + " identity priority and media")
                    check(bool(fragments) and all(f["eventID"] in expected_events
                          and f["sourceOrdinal"] == expected_events[f["eventID"]]["ordinal"]
                          and f["eventIdentity"] == current_events[f["eventID"]]["event"]["identityOffset"]
                          and all(type(f["range"][k]) in (float, int) and math.isfinite(f["range"][k]) for k in ("position", "duration", "offset"))
                          and f["range"]["duration"] > 0 for f in fragments), case_name + " " + seek + " full fragment identities and finite ranges")
                    if case_name == "overlap":
                        check(case["anchorID"] not in {f["eventID"] for f in fragments}
                              and len(fragments) == 3 and len({f["eventID"] for f in fragments}) == 2,
                              "overlap " + seek + " covered anchor retained and winner tail restored")
                else:
                    check(proof.get("sourceKind") == "event" and "sourceTrack" not in proof,
                          case_name + " " + mode + " " + seek + " event scope explicit")
                if seek == "full":
                    check(proof["startFrame"] == 0 and frames > 0, case_name + " " + mode + " full span")
                    baseline_pcm[mode] = pcm
                elif seek == "odd":
                    check(proof["startFrame"] == 1 and pcm == baseline_pcm[mode][8:], case_name + " " + mode + " admitted odd suffix exact")
                elif seek == "eof":
                    check(frames == 0 and len(wave) == 58 and proof["startFrame"] == proof["totalFrames"], case_name + " " + mode + " exact EOF with provenance")
                elif seek == "rewind":
                    check(proof["startFrame"] == 0 and pcm == baseline_pcm[mode], case_name + " " + mode + " rounded EOF rewinds")
                normalized = {k: v for k, v in proof.items() if k not in ("wavFileName", "revision")}
                report["scenarios"].append({"case": case_name, "mode": mode, "seek": seek,
                    "source_sha256": proof["sourceSHA256"], "media_sha256": proof["mediaSHA256"],
                    "sample_rate": rate, "frames": frames, "start_frame": proof["startFrame"], "total_frames": proof["totalFrames"],
                    "wav_sha256": sha(wave), "pcm_sha256": sha(pcm), "normalized_manifest_sha256": sha(canonical(normalized))})
                return proof
            for mode in selected_modes:
                full = render(mode, "full", omit_mode=mode == "sourceRate")
                render(mode, "odd", seconds=1 / full["sampleRate"])
                render(mode, "eof", seconds=1e100)
                render(mode, "rewind", seconds=(full["totalFrames"] - 0.25) / full["sampleRate"], rewind=True)
            for command in ("inspectSourceEvent", "renderSourceEvent"):
                refused = client.send(command, expected=stable["revision"] - 1,
                                      clipID=case["anchorID"], path=str(work / (case_name + "-stale.wav")))
                check(refused.get("ok") is False and refused.get("error", {}).get("code") == "staleRevision"
                      and client.state == stable, case_name + " " + command + " stale refusal")
            invalid_output = work / (case_name + "-invalid.wav")
            for index, invalid in enumerate(({"mode": "unknown"}, {"mode": ""}, {"startSeconds": -1}, {"rewindAtEnd": "yes"})):
                refused = client.send("renderSourceEvent", allow_unbound_failure="rewindAtEnd" in invalid,
                                      clipID=case["anchorID"], path=str(invalid_output), **invalid)
                check(refused.get("ok") is False and client.state == stable and not invalid_output.exists()
                      and not invalid_output.with_name(invalid_output.name + ".source-audition.json").exists(),
                      case_name + " invalid source request " + str(index))
            sentinel = b"other-writer-control"
            existing = work / (case_name + "-exists.wav")
            existing.write_bytes(sentinel)
            refused = client.send("renderSourceEvent", clipID=case["anchorID"], mode=selected_modes[0], path=str(existing))
            check(refused.get("ok") is False and client.state == stable and existing.read_bytes() == sentinel,
                  case_name + " existing WAV preserved")
            existing_sidecar_wave = work / (case_name + "-sidecar-exists.wav")
            existing_sidecar = existing_sidecar_wave.with_name(existing_sidecar_wave.name + ".source-audition.json")
            existing_sidecar.write_bytes(sentinel)
            refused = client.send("renderSourceEvent", clipID=case["anchorID"], mode=selected_modes[0], path=str(existing_sidecar_wave))
            check(refused.get("ok") is False and client.state == stable and existing_sidecar.read_bytes() == sentinel
                  and not existing_sidecar_wave.exists(), case_name + " existing sidecar preserved")
            if case_name == "overlap":
                covered = current_events[case["anchorID"]]
                media = relative(root, attachment(stable["project"], covered)["mediaPath"])
                original = media.read_bytes(); changed = bytearray(original); changed[-1] ^= 1; media.write_bytes(changed)
                refused_output = work / "covered-tamper-eof.wav"
                refused = client.send("renderSourceEvent", clipID=case["anchorID"], mode="nativeTrackSavedProjectClock",
                                      path=str(refused_output), startSeconds=1e100)
                check(refused.get("ok") is False and client.state == stable and not refused_output.exists()
                      and not refused_output.with_name(refused_output.name + ".source-audition.json").exists(),
                      "fully covered media tamper rejected even at EOF")
                media.write_bytes(original)
            check(client.send("redo").get("ok") is True
                  and next(t for t in client.state["project"]["tracks"] if t["id"] == track_id)["pan"] == 0.25,
                  case_name + " preserved redo remains functional")
            check(inventory(root) == inventory(relative(fixtures, case["root"])), case_name + " source package bytes unchanged")
        check(inventory(fixtures) == initial_files, "all locked fixture inputs unchanged")
        client.close(); client = None
        report["gates"] = dict.fromkeys(GATES, True)
        report["status"] = "passed"
        report["scope"] = "Actual helper execution over forward-authored controls. Normalized proof excludes only revision and WAV filename; all remaining clock/source/contributor metadata is compared. Odd-suffix equality uses admitted normal samples; conditional callback sentinel parity is covered separately by shared unit controls. No device or proprietary reference execution."
    except BaseException as error:
        report["failed_check"] = current_check
        report["error_class"] = type(error).__name__
        (work / "failure-private.log").write_text(traceback.format_exc(), encoding="utf-8")
        if client is not None:
            try:
                client.close()
            except BaseException:
                pass
    finally:
        with args.report.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False); handle.write("\n")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
                      "scenarios": len(report["scenarios"]), "failed_check": report.get("failed_check")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
