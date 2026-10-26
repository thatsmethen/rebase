#!/usr/bin/env python3
"""Exercise the packaged source worker against snapshot and long-tail controls.

Only forward-authored inputs are executed. Private tickets, paths and stderr stay
in fresh scratch; published results contain hashes/counts/relative case labels.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import tempfile
import threading
import traceback
from pathlib import Path
from source_stream_gate import Reader, StreamError, read_record, require_long_proof

spec = importlib.util.spec_from_file_location("audition_controls", Path(__file__).with_name("check-cpr-audition-modes.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
MODES = base.MODES
GATES = ("snapshot_equivalence", "complete_proof", "fresh_generations", "partition_invariance", "long_tail",
         "long_complete", "zero_eof", "read_only", "covered_tamper", "ticket_tamper", "source_revalidation",
         "worker_cancel", "bounded_transport", "locked_inputs_unchanged")


class Worker:
    def __init__(self, helper, work, label, ticket, chunk=None, seconds=90):
        self.stderr = (work / (label + "-worker-stderr.log")).open("xb")
        self.process = subprocess.Popen([str(helper), "--source-stream"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.stderr, bufsize=0)
        self.timed_out = False
        def expire():
            self.timed_out = True
            self.process.kill()
        self.timer = threading.Timer(seconds, expire)
        self.timer.daemon = True
        self.timer.start()
        self.startup = {"schema": "rebase.source-stream-start.v1", **{k: ticket[k] for k in
            ("ticketPath", "ticketSHA256", "capability", "generation")}}
        if chunk is not None:
            self.startup["maximumChunkFrames"] = chunk
        self.process.stdin.write(base.canonical(self.startup) + b"\n")
        self.process.stdin.flush()
        self.reader = Reader(self.process.stdout, ticket)

    def finish(self, kill=False):
        try:
            if kill and self.process.poll() is None:
                self.process.kill()
            status = self.process.wait(timeout=10)
        finally:
            self.timer.cancel()
            self.process.stdin.close()
            self.process.stdout.close()
            self.stderr.close()
        if self.timed_out:
            raise TimeoutError("Source worker exceeded bounded observation time")
        return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--long-fixtures", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or not args.report.parent.is_dir():
        raise SystemExit("Choose a new report in an existing directory")
    helper = args.helper.resolve()
    fixtures, long_fixtures = args.fixtures.resolve(), args.long_fixtures.resolve()
    work = Path(tempfile.mkdtemp(prefix="source-stream-", dir=args.report.parent)).resolve()
    report = {"schema": "rebase.source-stream-control.v1", "status": "failed",
        "evidence_class": "authored-shared-worker-control", "helper_sha256": base.sha(helper.read_bytes()),
        "fixture_manifest_sha256": base.sha((fixtures / "expected.json").read_bytes()),
        "long_fixture_manifest_sha256": base.sha((long_fixtures / "expected.json").read_bytes()),
        "checks": [], "gates": dict.fromkeys(GATES, False), "scenarios": [],
        "playback_tested": False, "reference_execution": False}
    client, worker = None, None
    current_check = "fixture admission"
    generations = set()
    serial = 0
    long_context = None
    def check(value, message):
        nonlocal current_check
        current_check = message
        if not value:
            raise AssertionError(message)
        report["checks"].append(message)
    def prepare(case, mode, label, seconds=0, rewind=False):
        nonlocal serial
        serial += 1
        path = work / (str(serial) + "-" + label + ".ticket.json")
        stable = copy.deepcopy(client.state)
        result = client.send("prepareSourceStream", clipID=case["anchorID"], mode=mode,
                             path=str(path), startSeconds=seconds, rewindAtEnd=rewind)
        check(result.get("ok") is True and client.state == stable, label + " read-only ticket")
        ticket = result.get("sourceStream", {})
        check(ticket.get("ticketPath") == str(path) and path.is_file() and not path.is_symlink()
              and ticket.get("ticketSHA256") == base.sha(path.read_bytes()), label + " exact ticket identity")
        check(ticket.get("generation") not in generations and ticket.get("generation")
              and ticket.get("revision") == stable["revision"] and ticket.get("eventID") == case["anchorID"]
              and ticket.get("mode") == mode, label + " fresh bound generation")
        generations.add(ticket["generation"])
        return ticket
    def consume(ticket, label, chunk=None, collect=True, seconds=90):
        nonlocal worker
        worker = Worker(helper, work, label, ticket, chunk, seconds)
        admission = worker.reader.start()
        if long_context is not None:
            case, project, frozen_report = long_context
            require_long_proof(admission["proof"], case, project, frozen_report, ticket["revision"], ticket["mode"],
                               case["manifestSHA256"])
            check(True, label + " complete provenance bound to frozen long fixture")
        pcm = bytearray() if collect else None
        tail = bytearray()
        while (block := worker.reader.next()) is not None:
            if pcm is not None:
                # Every collection case is a tiny source or explicitly sought
                # suffix; the complete long stream only retains its last1000.
                check_length = len(pcm) + len(block)
                if check_length > 2 * 1024 * 1024:
                    raise StreamError("Control tried to accumulate a long timeline")
                pcm.extend(block)
            tail.extend(block)
            if len(tail) > 8000:
                del tail[:-8000]
        reader = worker.reader
        check(worker.finish() == 0, label + " explicit EOF and clean worker exit")
        worker = None
        check(reader.peak_payload_bytes <= admission["maximumChunkFrames"] * 8
              and reader.peak_metadata_bytes <= 8_388_608, label + " bounded observed wire buffers")
        terminal = reader.terminal
        check(terminal.get("peakPayloadFrames", 65_537) <= admission["maximumChunkFrames"]
              and terminal.get("peakLogicalFrames", 16_000_001) <= 16_000_000,
              label + " producer output buffer counters within shared bounds")
        summary = {"case": label, "mode": admission["mode"], "sample_rate": admission["sampleRate"],
            "start_frame": admission["startFrame"], "total_frames": admission["totalFrames"], "frames": reader.emitted,
            "pcm_sha256": reader.hash.hexdigest(), "proof_sha256": admission["proofSHA256"],
            "normalized_proof_sha256": base.sha(base.canonical({k: v for k, v in admission["proof"].items() if k != "revision"})),
            "transport_chunk_bound": admission["maximumChunkFrames"], "records": reader.next_sequence,
            "peak_payload_bytes": reader.peak_payload_bytes, "peak_metadata_bytes": reader.peak_metadata_bytes,
            "producer_peak_logical_frames": terminal["peakLogicalFrames"],
            "producer_peak_payload_frames": terminal["peakPayloadFrames"],
            "producer_logical_blocks": terminal.get("emittedLogicalBlocks"),
            "observed_logical_blocks": reader.logical_block,
            "observed_peak_logical_frames": reader.observed_peak_logical_frames,
            "logical_blocks_sha256": reader.logical_hash.hexdigest()}
        report["scenarios"].append(summary)
        return admission, bytes(pcm) if pcm is not None else None, bytes(tail), summary
    def refused_worker(ticket, label):
        nonlocal worker
        worker = Worker(helper, work, label, ticket)
        try:
            kind, metadata, _, payload = read_record(worker.process.stdout)
            check(kind == 4 and not payload and isinstance(metadata.get("code"), str)
                  and isinstance(metadata.get("message"), str), label + " explicit admission failure")
            check(worker.process.stdout.read(1) == b"", label + " no admitted PCM")
            check(worker.finish() != 0, label + " failed worker exit")
            worker = None
        except BaseException:
            if worker:
                worker.finish(kill=True); worker = None
            raise
    try:
        initial = base.inventory(fixtures), base.inventory(long_fixtures)
        expected = json.loads((fixtures / "expected.json").read_bytes())
        expected_long = json.loads((long_fixtures / "expected.json").read_bytes())
        check(expected["evidenceClass"] == expected_long["evidenceClass"] == "authored-synthetic-control",
              "both fixture suites declare authored provenance")
        client = base.Client(helper, work)
        roots = {}
        for case in [*expected["cases"], *expected_long["cases"]]:
            suite = fixtures if case in expected["cases"] else long_fixtures
            key = ("short-" if suite == fixtures else "long-") + case["name"]
            source = base.relative(suite, case["root"])
            for relative, digest_key in (("Project.json", "manifestSHA256"), ("Compatibility/CPR/Original.cpr", "sourceSHA256"),
                                         ("Compatibility/CPR/ImportReport.json", "reportSHA256")):
                check(base.sha((source / relative).read_bytes()) == case[digest_key], key + " " + digest_key + " lock")
            project = json.loads((source / "Project.json").read_bytes())
            retained = base.events(project)
            check([event["id"] for event in retained] == [event["eventID"] for event in case["events"]],
                  key + " complete frozen contributor membership")
            for event, control in zip(retained, case["events"]):
                attachment = base.attachment(project, event)
                check(attachment["mediaSHA256"] == control["mediaSHA256"]
                      and base.sha(base.relative(source, attachment["mediaPath"]).read_bytes()) == control["mediaSHA256"],
                      key + " media lock " + str(control["ordinal"]))
            destination = work / (key + ".rebaseproj")
            shutil.copytree(source, destination)
            roots[key] = (source, destination)
        for case in expected["cases"]:
            root = roots["short-" + case["name"]][1]
            check(client.send("open", path=str(root), discardChanges=True).get("ok") is True, case["name"] + " open")
            client.send("selectClip", clipID=case["anchorID"])
            track_id = next(t["id"] for t in client.state["project"]["tracks"] if any(e["id"] == case["anchorID"] for e in t.get("unresolvedAudioEvents", [])))
            check(client.send("setGain", trackID=track_id, value=-6).get("ok") is True, case["name"] + " dirty gain")
            client.send("setPan", trackID=track_id, value=0.25)
            check(client.send("undo").get("ok") is True and client.state["dirty"] and client.state["canRedo"], case["name"] + " undo redo custody")
            modes = MODES if case["name"] == "single" else MODES[1:5]
            for mode in modes:
                full_ticket = None
                full_pcm = None
                for seek in ("full", "odd", "eof", "rewind"):
                    label = case["name"] + "-" + mode + "-" + seek
                    seconds = 0 if seek == "full" else 1 / full_ticket["sampleRate"] if seek == "odd" else 1e100 if seek == "eof" else (full_ticket["totalFrames"] - 0.25) / full_ticket["sampleRate"]
                    rewind = seek == "rewind"
                    ticket = prepare(case, mode, label, seconds, rewind)
                    admission, pcm, _, summary = consume(ticket, label)
                    output = work / (label + ".wav")
                    stable = copy.deepcopy(client.state)
                    rendered = client.send("renderSourceEvent", clipID=case["anchorID"], mode=mode, path=str(output), startSeconds=seconds, rewindAtEnd=rewind)
                    check(rendered.get("ok") is True and client.state == stable, label + " snapshot oracle read-only")
                    wave_rate, wave_frames, wave_pcm = base.float_wave(output.read_bytes())
                    snapshot_proof = json.loads(output.with_name(output.name + ".source-audition.json").read_bytes())
                    omit = {"schema", "wavFileName", "wavBytes", "wavSHA256", "maximumFrames"}
                    normalized_snapshot = {k: v for k, v in snapshot_proof.items() if k not in omit}
                    normalized_stream = {k: v for k, v in admission["proof"].items() if k != "schema"}
                    check(base.canonical(normalized_snapshot) == base.canonical(normalized_stream), label + " complete snapshot proof equivalence")
                    check(pcm == wave_pcm and wave_rate == admission["sampleRate"] and wave_frames == admission["frames"], label + " exact snapshot PCM equivalence")
                    if seek == "full":
                        full_ticket, full_pcm = ticket, pcm
                    if seek == "eof":
                        check(pcm == b"" and summary["records"] == 0, label + " verified zero-output EOF")
                partition = prepare(case, mode, case["name"] + "-" + mode + "-partition")
                _, split_pcm, _, _ = consume(partition, case["name"] + "-" + mode + "-partition", chunk=257)
                check(split_pcm == full_pcm, case["name"] + " " + mode + " odd transport partition invariant")
            # A separate worker must revalidate everything after ticket issuance.
            # Mutations occur only in disposable fixture copies and are restored.
            proof_ticket = prepare(case, modes[-1], case["name"] + "-ticket-corrupt")
            ticket_path = Path(proof_ticket["ticketPath"])
            ticket_bytes = ticket_path.read_bytes()
            ticket_path.write_bytes(ticket_bytes + b" ")
            refused_worker(proof_ticket, case["name"] + "-ticket-corrupt")
            ticket_path.write_bytes(ticket_bytes)
            for suffix, relative in (("source", "Compatibility/CPR/Original.cpr"), ("report", "Compatibility/CPR/ImportReport.json"), ("manifest", "Project.json")):
                ticket = prepare(case, modes[-1], case["name"] + "-changed-" + suffix)
                target = root / relative
                original = target.read_bytes()
                changed = bytearray(original); changed[-1] ^= 1
                target.write_bytes(changed)
                try:
                    refused_worker(ticket, case["name"] + "-changed-" + suffix)
                finally:
                    target.write_bytes(original)
            if case["name"] == "overlap":
                ticket = prepare(case, "nativeTrackSavedProjectClock", "covered-media-eof", 1e100)
                event = next(e for e in base.events(client.state["project"]) if e["id"] == case["anchorID"])
                target = base.relative(root, base.attachment(client.state["project"], event)["mediaPath"])
                original = target.read_bytes(); changed = bytearray(original); changed[-1] ^= 1
                target.write_bytes(changed)
                try:
                    refused_worker(ticket, "covered-media-eof")
                finally:
                    target.write_bytes(original)
            check(client.send("redo").get("ok") is True, case["name"] + " redo retained after worker activity")
        for case in expected_long["cases"]:
            root = roots["long-" + case["name"]][1]
            check(client.send("open", path=str(root), discardChanges=True).get("ok") is True, case["name"] + " long open")
            # ProjectStore encodes these unchanged authored projects with the
            # same pretty/sorted writer that produced the frozen manifest.
            # currentProjectSHA256 covers those bytes, not compact Python JSON.
            check(client.state["project"] == json.loads((root / "Project.json").read_bytes()),
                  case["name"] + " current project equals unchanged locked manifest")
            long_context = (case, copy.deepcopy(client.state["project"]),
                            json.loads((root / "Compatibility/CPR/ImportReport.json").read_bytes()))
            inspection_state = copy.deepcopy(client.state)
            inspection = client.send("inspectSourceEvent", clipID=case["anchorID"])
            check(inspection.get("ok") is True and client.state == inspection_state,
                  case["name"] + " long inspection read-only")
            availability = {row["mode"]: row for row in inspection.get("sourceInspection", {}).get("modes", [])}
            for mode in case["modes"]:
                label = "long-" + case["name"] + "-" + mode["mode"]
                total, rate = mode["totalFrames"], mode["sampleRate"]
                check(availability.get(mode["mode"], {}).get("available") is True
                      and availability[mode["mode"]].get("liveAvailable") is True
                      and availability[mode["mode"]].get("snapshotExportAvailable") is False,
                      label + " live preparation and snapshot limits separated")
                ticket = prepare(case, mode["mode"], label + "-tail", (total - mode["tailFrames"]) / rate)
                _, pcm, _, summary = consume(ticket, label + "-tail", chunk=257)
                check(summary["total_frames"] == total > 32_000_000 and summary["frames"] == mode["tailFrames"]
                      and base.sha(pcm) == mode["tailPCMSHA256"], label + " bounded exact long tail")
                eof = prepare(case, mode["mode"], label + "-eof", 1e100)
                consume(eof, label + "-eof")
                if case["name"] == "boundary" and mode["mode"] == "nativeTimelineSavedProjectClock":
                    expected_hash = hashlib.sha256()
                    zero_bytes = (total - mode["tailFrames"]) * 8
                    zeros = bytes(65_536)
                    while zero_bytes:
                        count = min(zero_bytes, len(zeros)); expected_hash.update(zeros[:count]); zero_bytes -= count
                    expected_hash.update(pcm)
                    ticket = prepare(case, mode["mode"], label + "-full")
                    _, _, tail, full = consume(ticket, label + "-full", collect=False, seconds=600)
                    check(full["frames"] == total and full["pcm_sha256"] == expected_hash.hexdigest()
                          and base.sha(tail) == mode["tailPCMSHA256"] and full["producer_peak_logical_frames"] <= 4096,
                          "complete >32M-frame timeline drained with bounded output buffers and independent silence/tail digest")
            # Cancel while a near-day producer can be blocked by a full stdout
            # pipe; then prove the editing session is still responsive.
            mode = case["modes"][-1]["mode"]
            ticket = prepare(case, mode, "cancel-" + case["name"])
            worker = Worker(helper, work, "cancel-" + case["name"], ticket)
            worker.reader.start()
            check(worker.reader.next() is not None, case["name"] + " worker started before cancellation")
            check(worker.finish(kill=True) != 0, case["name"] + " disposable worker cancellation joined")
            worker = None
            check(client.send("inspectSourceEvent", clipID=case["anchorID"]).get("ok") is True,
                  case["name"] + " editing helper survives cancelled producer")
        for key, (source, destination) in roots.items():
            check(base.inventory(source) == base.inventory(destination), key + " all project bytes unchanged")
        check(initial == (base.inventory(fixtures), base.inventory(long_fixtures)), "all original locked inputs unchanged")
        client.close(); client = None
        report["status"] = "passed"
        report["gates"] = dict.fromkeys(GATES, True)
        report["scope"] = "Actual separate helper workers over authored inputs. Complete shared proof and PCM compared with snapshot renderer; long provenance independently bound to fixture identities and long output drained incrementally. Ordered logical-block digest uses RBAS.logical-blocks.v1 NUL followed by completed UInt64 little-endian lengths; producer EOF counters equal observed headers. Buffer counts are not whole-process memory profiling or physical device playback. No proprietary execution."
    except BaseException as error:
        report["failed_check"] = current_check
        report["error_class"] = type(error).__name__
        (work / "failure-private.log").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        if worker:
            try:
                worker.finish(kill=True)
            except BaseException:
                pass
        if client:
            try:
                client.close()
            except BaseException:
                pass
        with args.report.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False); handle.write("\n")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "scenarios": len(report["scenarios"]),
                      "failed_check": report.get("failed_check")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
