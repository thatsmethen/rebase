#!/usr/bin/env python3
"""Authored negative controls for the WPF receipt gate, not a WPF execution.

Three short real helper workers supply complete long-tail proofs. Window records
and PNG geometry are synthetic mutations; native Windows UI evidence must still
be collected independently. Private helper traffic stays under private/.
"""
import argparse
import copy
import importlib.util
import json
import shutil
import struct
import traceback
import uuid
import zlib
from pathlib import Path

from source_stream_gate import Reader, decode, raw_member
from source_stream_window_gate import (CAPTURE, CASES, CHECKS, CONTROLS, MODE, canonical,
                                       require_source_stream_window, sha)


def collect(helper, fixture_path, process_receipt, work):
    spec = importlib.util.spec_from_file_location("actual_stream_controls", Path(__file__).with_name("check-source-stream.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = decode(fixture_path.read_bytes())
    oracle = {row["case"]: row for row in process_receipt["scenarios"]}
    if sha(helper.read_bytes()) != process_receipt["helper_sha256"]:
        raise ValueError("The production helper differs from the actual worker receipt")
    client = module.base.Client(helper, work)
    seeds = {}
    worker = None
    try:
        for case in fixture["cases"]:
            name = case["name"]
            root = work / (name + ".rebaseproj")
            shutil.copytree(fixture_path.parent / case["root"], root)
            response = client.send("open", path=str(root), discardChanges=True)
            if response.get("ok") is not True:
                raise ValueError("The authored project did not open")
            expected = next(row for row in case["modes"] if row["mode"] == MODE)
            response = client.send("prepareSourceStream", clipID=case["anchorID"], mode=MODE,
                startSeconds=(expected["totalFrames"] - 1000) / expected["sampleRate"],
                path=str(work / (name + ".ticket.json")))
            if response.get("ok") is not True:
                raise ValueError("The real helper did not prepare the authored source")
            ticket = response["sourceStream"]
            worker = module.Worker(helper, work, name, ticket)

            class AdmissionTee:
                def __init__(self, source):
                    self.source, self.data, self.recording = source, bytearray(), True

                def read(self, count):
                    result = self.source.read(count)
                    if self.recording:
                        self.data.extend(result)
                        if len(self.data) > 8_388_624:
                            raise ValueError("Excessive admission bytes")
                    return result

            tee = AdmissionTee(worker.process.stdout)
            reader = worker.reader = Reader(tee, ticket)
            admission = reader.start()
            tee.recording = False
            raw = raw_member(bytes(tee.data[16:]), "proof")
            while reader.next() is not None:
                pass
            if worker.finish() != 0:
                raise ValueError("Real helper worker failed")
            worker = None
            normalized = copy.deepcopy(admission["proof"])
            normalized.pop("revision")
            expected_row = oracle["long-" + name + "-" + MODE + "-tail"]
            if sha(canonical(normalized)) != expected_row["normalized_proof_sha256"] or reader.hash.hexdigest() != expected_row["pcm_sha256"]:
                raise ValueError("Short real worker differs from the retained independent observation")
            seeds[name] = {"proof_json": raw.decode("utf-8"), "proof_sha256": sha(raw),
                           "pcm_sha256": reader.hash.hexdigest(), "frames": reader.emitted}
    finally:
        if worker is not None:
            worker.finish(kill=True)
        client.close()
    (work / "proof-seeds.json").write_bytes(canonical(seeds) + b"\n")
    return seeds


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def png(width=724, height=501, alpha=255, filtering=0, dpi=3779, trailing=b"", invalid_crc=False,
        short_pixels=False, extra_pixels=False, bad_filter=False):
    # Exercise every PNG predictor independently with authored opaque RGBA.
    rows, previous = [], bytes(width * 4)
    raw = bytes((28, 31, 35, alpha)) * width
    for _ in range(height):
        encoded = bytearray(len(raw))
        for i, value in enumerate(raw):
            left = raw[i - 4] if i >= 4 else 0
            up, diagonal = previous[i], previous[i - 4] if i >= 4 else 0
            if filtering == 0: predictor = 0
            elif filtering == 1: predictor = left
            elif filtering == 2: predictor = up
            elif filtering == 3: predictor = (left + up) // 2
            else:
                p = left + up - diagonal
                a, b, c = abs(p-left), abs(p-up), abs(p-diagonal)
                predictor = left if a <= b and a <= c else up if b <= c else diagonal
            encoded[i] = (value-predictor) & 255
        rows.append(bytes((5 if bad_filter else filtering,)) + encoded)
        previous = raw
    pixels = b"".join(rows)
    if short_pixels: pixels = pixels[:-1]
    if extra_pixels: pixels += b"\0"
    result = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
              chunk(b"pHYs", struct.pack(">IIB", dpi, dpi, 1)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
    if invalid_crc:
        result = result[:-1] + bytes((result[-1] ^ 1,))
    return result + trailing


def authored(fixture, fixture_sha, seeds):
    records = []
    for case in fixture["cases"]:
        proof = decode(seeds[case["name"]]["proof_json"].encode())
        revision = proof["revision"]
        state = sha(("synthetic-window-state-" + case["name"]).encode())
        total, rate = proof["totalFrames"], proof["sampleRate"]
        admissions = []
        for action in ("play", "seek", "resume"):
            value = copy.deepcopy(proof)
            value["startFrame"] = 0 if action == "play" else total - 1000
            value["frames"] = total - value["startFrame"]
            raw = canonical(value)
            admissions.append({"action": action, "generation": str(uuid.uuid4()), "revision": revision,
                "mode": MODE, "sample_rate": rate, "start_frame": value["startFrame"], "total_frames": total,
                "remaining_frames": value["frames"], "proof_json": raw.decode(), "proof_sha256": sha(raw),
                "source_sha256": value["sourceSHA256"], "project_manifest_sha256": value["projectManifestSHA256"],
                "current_project_sha256": value["currentProjectSHA256"], "report_sha256": value["importReportSHA256"],
                "contributors": [{"event_id": e["eventID"], "media_sha256": e["mediaSHA256"], "source_ordinal": e["sourceOrdinal"]}
                                 for e in value["sourceTrack"]["events"]],
                "fragment_event_ids": [e["eventID"] for e in value["sourceTrack"]["fragments"]],
                "worker_admission_valid": True, "endpoint_outcome": "unavailable", "native_started": False,
                "worker_joined": True, "state_sha256": state})
        records.append({"fixture": case["name"], "mode": MODE, "before_state_sha256": state, "after_state_sha256": state,
            "revision": revision, "availability": {"available": True, "live_available": True, "snapshot_export_available": False,
                "snapshot_export_reason": "Authored long duration exceeds bounded snapshot export", "sample_rate": rate,
                "total_frames": total, "play_enabled": True, "export_enabled": False},
            "admissions": admissions, "prepare_requests": 3, "snapshot_render_requests": 0, "inspection_requests": 1,
            "after_cancel": {"position_seconds": 0, "is_playing": False, "worker_joined": True, "inspection_revision": revision},
            "no_snapshot_render_request": True, "cancel_joined": True, "helper_responsive": True})
    controls = [{"name": "modes", "x": 18, "y": 18, "width": 244, "height": 395, "enabled": True},
                {"name": "position", "x": 300, "y": 350, "width": 105, "height": 26, "enabled": True},
                {"name": "seek", "x": 420, "y": 350, "width": 60, "height": 26, "enabled": True}]
    x = 18
    for name, width in (("refresh", 88), ("export", 90), ("play", 64), ("pause", 64), ("stop", 64), ("close", 70)):
        controls.append({"name": name, "x": x, "y": 440, "width": width, "height": 26, "enabled": name not in ("export", "pause")})
        x += width + 8
    return {"outcome": "passed", "checks": sorted(CHECKS), "source_stream_window": {"tested": True,
        "fixture_sha256": fixture_sha, "cases": records, "capture": {"file": CAPTURE, "sha256": "",
            "bounds": {"outer_width_dip": 740, "outer_height_dip": 540, "width_dip": 724, "height_dip": 501,
                       "dpi_scale_x": 1, "dpi_scale_y": 1, "pixel_width": 724, "pixel_height": 501},
            "controls": controls, "selected_mode": MODE, "details": "Authored geometry control; no native UI execution",
            "message": "", "frame_excluded": True}, "audio_device_playback_measured": False,
        "physical_input_tested": False, "native_frame_visual_tested": False,
        "input_evidence": "WPF UI Automation providers invoke production Play, source position/Seek, Stop and refresh actions; no physical input"}}


def set_path(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    private = output / "private"
    private.mkdir()
    evidence = private / "synthetic-pixels"
    evidence.mkdir()
    checks, real_workers = [], []
    result = {"schema": "rebase.source-stream-window-gate-controls.v1", "outcome": "failed",
        "evidence_class": "authored-gate-controls-with-real-helper-tail-proofs",
        "native_wpf_executed": False, "physical_input_tested": False, "audio_device_playback_measured": False,
        "reference_execution": False, "checks": checks, "real_workers": real_workers}
    stage = "input validation"
    status = 1
    log = (output / "controls.log").open("x", encoding="utf-8")
    try:
        fixture_bytes = args.fixture.read_bytes()
        fixture = decode(fixture_bytes)
        receipt_bytes = args.receipt.read_bytes()
        receipt = decode(receipt_bytes)
        result.update(fixture_sha256=sha(fixture_bytes), helper_sha256=sha(args.helper.read_bytes()),
                      process_receipt_sha256=sha(receipt_bytes), gate_sha256=sha(Path(__file__).with_name("source_stream_window_gate.py").read_bytes()),
                      instrument_sha256=sha(Path(__file__).read_bytes()))
        stage = "three actual bounded tail workers"
        seeds = collect(args.helper.resolve(), args.fixture.resolve(), receipt, private)
        for name in CASES:
            real_workers.append({"case": name, "mode": MODE, "frames": seeds[name]["frames"],
                "pcm_sha256": seeds[name]["pcm_sha256"], "proof_sha256": seeds[name]["proof_sha256"]})
        baseline = authored(fixture, sha(fixture_bytes), seeds)
        default_png = png()

        def run(label, mutation=None, accept=False, image=None, process_mutation=None):
            nonlocal stage
            stage = label
            sample, process = copy.deepcopy(baseline), copy.deepcopy(receipt)
            data = default_png if image is None else image
            (evidence / CAPTURE).write_bytes(data)
            sample["source_stream_window"]["capture"]["sha256"] = sha(data)
            if mutation: mutation(sample)
            if process_mutation: process_mutation(process)
            try:
                summary = require_source_stream_window(sample, evidence, fixture, process, sha(fixture_bytes))
            except ValueError:
                if accept: raise
            else:
                if not accept: raise AssertionError("Malformed evidence was accepted")
                if summary["admissions"] != 9 or summary["native_checks"] != 17:
                    raise AssertionError("Accepted summary is incomplete")
            checks.append(label)
            log.write("PASS " + label + "\n"); log.flush()

        run("authored unavailable endpoint receipt accepted", accept=True)
        def started(sample):
            for case in sample["source_stream_window"]["cases"]:
                for a in case["admissions"]:
                    a.update(endpoint_outcome="started", native_started=True, worker_joined=False)
        run("authored started endpoint receipt accepted without physical claim", started, accept=True)
        for filtering in range(1, 5):
            run("opaque PNG predictor " + str(filtering), accept=True, image=png(filtering=filtering))
        prefix = ("source_stream_window",)
        for label, path, value in (
            ("nonobject window", prefix, None),
            ("nonobject case", prefix + ("cases", 0), False),
            ("nonobject availability", prefix + ("cases", 0, "availability"), []),
            ("nonobject cancellation", prefix + ("cases", 0, "after_cancel"), True),
            ("nonobject admission", prefix + ("cases", 0, "admissions", 0), []),
            ("nonobject capture", prefix + ("capture",), False)):
            run(label, lambda s, p=path, v=value: set_path(s, p, v))
        fields = [(("outcome",), "failed"), (("checks",), sorted(CHECKS)[:-1]),
                  (("checks",), sorted(CHECKS) + [sorted(CHECKS)[0]]),
                  (prefix + ("tested",), False), (prefix + ("fixture_sha256",), "0"*64)]
        fields += [(prefix + (key,), True) for key in ("audio_device_playback_measured", "physical_input_tested", "native_frame_visual_tested")]
        fields += [(prefix + ("cases",), baseline["source_stream_window"]["cases"][:2])]
        cp = prefix + ("cases", 0)
        fields += [(cp + (key,), value) for key, value in (("mode", "sourceRate"), ("revision", True),
            ("after_state_sha256", "0"*64), ("prepare_requests", 2), ("snapshot_render_requests", 1),
            ("inspection_requests", 0), ("helper_responsive", False), ("cancel_joined", False))]
        fields += [(cp + ("availability", key), value) for key, value in (("live_available", False),
            ("available", False), ("snapshot_export_available", True), ("play_enabled", False), ("export_enabled", True),
            ("snapshot_export_reason", ""), ("sample_rate", True), ("total_frames", 32_000_000))]
        fields += [(cp + ("after_cancel", key), value) for key, value in (("position_seconds", 1),
            ("is_playing", True), ("worker_joined", False), ("inspection_revision", 99))]
        ap = cp + ("admissions", 0)
        fields += [(ap + (key,), value) for key, value in (("action", "resume"), ("generation", "bad"),
            ("revision", True), ("start_frame", 1), ("total_frames", 1), ("remaining_frames", 0),
            ("state_sha256", "0"*64), ("worker_admission_valid", False), ("endpoint_outcome", "failed"),
            ("native_started", True), ("worker_joined", False), ("proof_sha256", "0"*64),
            ("source_sha256", "0"*64), ("report_sha256", "0"*64), ("current_project_sha256", "0"*64),
            ("project_manifest_sha256", "0"*64), ("contributors", []), ("fragment_event_ids", []))]
        for index, (path, value) in enumerate(fields):
            run("malformed field %02d %s" % (index + 1, "/".join(map(str, path))), lambda s, p=path, v=value: set_path(s, p, v))
        run("generation reused across separate fixtures", lambda s: set_path(s, prefix + ("cases", 1, "admissions", 0, "generation"),
             s["source_stream_window"]["cases"][0]["admissions"][0]["generation"]))

        def proof_change(sample, mutate):
            admission = sample["source_stream_window"]["cases"][1]["admissions"][0]
            proof = decode(admission["proof_json"].encode())
            mutate(proof)
            raw = canonical(proof)
            admission.update(proof_json=raw.decode(), proof_sha256=sha(raw))
        for label, mutation in (
            ("covered contributor removed", lambda p: p["sourceTrack"]["events"].pop(0)),
            ("contributor priority changed", lambda p: p["sourceTrack"]["events"][0].update(priority=99)),
            ("track fragments removed", lambda p: p["sourceTrack"].update(fragments=[])),
            ("current project hash changed", lambda p: p.update(currentProjectSHA256="0"*64)),
            ("saved setup discarded", lambda p: p.pop("savedProjectAudioSetup", None)),
            ("extra proof member admitted", lambda p: p.update(unobserved=True)),
            ("snapshot hash fabricated", lambda p: p.update(wavSHA256="0"*64)),
            ("proof anchor changed", lambda p: p.update(eventID=str(uuid.uuid4()))),
            ("proof start changed", lambda p: p.update(startFrame=1))):
            run(label, lambda s, mutate=mutation: proof_change(s, mutate))
        def duplicate_proof(sample):
            admission = sample["source_stream_window"]["cases"][0]["admissions"][0]
            raw = '{"revision":0,' + admission["proof_json"][1:]
            admission.update(proof_json=raw, proof_sha256=sha(raw.encode()))
        run("duplicate raw proof member", duplicate_proof)
        run("failed independent worker receipt", process_mutation=lambda p: p.update(status="failed"))
        run("missing independent scenario", process_mutation=lambda p: p["scenarios"].pop())
        run("independent worker proof hash changed", process_mutation=lambda p: next(r for r in p["scenarios"] if
            r["case"] == "long-overlap-" + MODE + "-tail").update(normalized_proof_sha256="0"*64))
        cap = prefix + ("capture",)
        geometry = [(("file",), "../outside.png"), (("frame_excluded",), False), (("selected_mode",), "sourceRate"),
            (("bounds", "outer_width_dip"), 900), (("bounds", "width_dip"), float("nan")),
            (("bounds", "dpi_scale_x"), True), (("bounds", "pixel_height"), 500),
            (("controls", 0, "width"), 210), (("controls", 0, "height"), 200),
            (("controls", 1, "x"), -1), (("controls", 1, "enabled"), False),
            (("controls", 2, "x"), 300), (("controls", 3, "y"), 490),
            (("controls", 4, "enabled"), True), (("controls", 5, "enabled"), False),
            (("controls", 8, "name"), "stop")]
        for index, (path, value) in enumerate(geometry):
            run("malformed geometry %02d" % (index + 1), lambda s, p=cap+path, v=value: set_path(s, p, v))
        for label, options in (("transparent pixel coverage", {"alpha": 0}), ("bad PNG CRC", {"invalid_crc": True}),
            ("trailing PNG bytes", {"trailing": b"x"}), ("incorrect PNG DPI", {"dpi": 2000}),
            ("short decoded pixels", {"short_pixels": True}), ("excess decoded pixels", {"extra_pixels": True}),
            ("invalid row predictor", {"bad_filter": True})):
            run(label, image=png(**options))
        run("truncated PNG", image=default_png[:-10])
        run("unbound PNG hash", lambda s: set_path(s, cap+("sha256",), "0"*64))
        result["outcome"] = "passed"
        status = 0
    except BaseException:
        result["failed_stage"] = stage
        (private / "failure.log").write_text(traceback.format_exc())
        log.write("FAIL " + stage + "\n")
    finally:
        log.close()
        result["check_count"] = len(checks)
        result["controls_log_sha256"] = sha((output / "controls.log").read_bytes())
        (output / "observation.json").write_bytes(canonical(result) + b"\n")
    print(json.dumps({"outcome": result["outcome"], "checks": len(checks), "real_tail_workers": len(real_workers),
                      "native_wpf_executed": False}))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
