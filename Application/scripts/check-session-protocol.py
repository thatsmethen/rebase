#!/usr/bin/env python3
"""Exercise the packaged JSONL helper interactively, before closing its input."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import queue
import shutil
import struct
import subprocess
import tempfile
import threading
import uuid


def wav_chunks(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE" or struct.unpack_from("<I", data, 4)[0] + 8 != len(data):
        raise RuntimeError("Incomplete WAV envelope")
    chunks, offset = {}, 12
    while offset + 8 <= len(data):
        tag, length = struct.unpack_from("<4sI", data, offset)
        start = offset + 8
        if tag in chunks or start + length > len(data):
            raise RuntimeError("Invalid WAV chunk")
        chunks[tag] = data[start:start + length]
        offset = start + length + length % 2
    if offset != len(data) or b"data" not in chunks or b"fmt " not in chunks:
        raise RuntimeError("Incomplete WAV chunks")
    return chunks


def example_waveform_oracle(project_root, clip):
    """Direct signed-integer source oracle; independent of Swift's chunked reducer."""
    relative = Path(clip["mediaPath"])
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError("Unexpected example media path")
    data = (project_root / relative).read_bytes()
    chunks = wav_chunks(data)
    fmt = struct.unpack_from("<HHIIHH", chunks[b"fmt "])
    if fmt != (1, 2, 48000, 192000, 4, 16):
        raise RuntimeError("The authored waveform control requires its locked PCM16 source")
    pcm = chunks[b"data"]
    start = int(clip["sourceOffset"] * fmt[2])
    count = min(len(pcm) // fmt[4] - start, int(clip["duration"] * fmt[2]))
    if start < 0 or count <= 0 or len(pcm) % fmt[4]:
        raise RuntimeError("Invalid authored waveform control interval")
    bins = min(1600, count)
    peaks = []
    for index in range(bins):
        # Bin boundaries are derived directly, without the implementation's
        # frame-to-bin assignment or chunk traversal.
        first = start + (index * count + bins - 1) // bins
        last = start + ((index + 1) * count + bins - 1) // bins
        samples = struct.unpack("<" + str((last - first) * 2) + "h", pcm[first * 4:last * 4])
        peaks.append(max(abs(value) for value in samples) / 32768.0)
    return {"sampleRate": fmt[2], "sourceStartFrame": start, "sourceFrames": count,
            "mediaSHA256": hashlib.sha256(data).hexdigest(), "peaks": peaks}


def peak_words(values):
    if not isinstance(values, list) or not values or len(values) > 1600:
        raise RuntimeError("Invalid waveform peak count")
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in values):
        raise RuntimeError("Invalid waveform peak value")
    return struct.pack("<" + str(len(values)) + "f", *values)


def automation_journey(args, work, state, send, check, report, lock):
    """Edit actual authored lanes through the production process, preserving locks.

    The complete expected document is compared after each accepted edit, so a
    targeted operation cannot silently change another lane, track or clip.
    Render hashes from new edits are observations, never replacements for the
    predeclared original example lock.
    """
    gates = ("existing_volume_projected", "edits_revision_bound", "stale_rejected",
             "invalid_rejected", "other_automation_preserved", "read_off_preserves_points",
             "read_off_uses_manual_gain", "pan_edit_read_roundtrip", "undo_restores_project",
             "undo_restores_locked_render", "redo_restores_edits", "save_reopen_preserves_edits",
             "source_unchanged")
    receipt = {"tested": False, **dict.fromkeys(gates, False),
               "evidence_class": "authored-shared-session-control", "playback_tested": False}
    report["automation"] = receipt
    original_files = {p.relative_to(args.example).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in args.example.rglob("*") if p.is_file()}
    original = copy.deepcopy(state["project"])
    current = state
    target_index = 1
    track = original["tracks"][target_index]
    track_id = track["id"]
    gain = next(lane for lane in track["automation"] if lane["parameter"] == "gainDB")
    source_track = json.loads((args.example / "Project.json").read_text(encoding="utf-8"))["tracks"][target_index]
    source_gain = next(lane for lane in source_track["automation"] if lane["parameter"] == "gainDB")
    original_points = [(0, -10, "linear"), (5, -7, "linear"), (10, -5, "linear"),
                       (17.5, -5, "linear"), (20, -12, "linear")]
    check(track["name"] == "Warm pad" and track_id == source_track["id"]
          and gain == source_gain and gain["isReadEnabled"] is True
          and [(p["time"], p["value"], p["interpolation"]) for p in gain["points"]] == original_points,
          "automation projection preserves all five authored volume points and their ordering")
    receipt.update(existing_volume_projected=True, original_point_count=5,
                   original_track_id=track_id, original_lane_id=gain["id"])
    projected = send("state")
    check(projected.get("ok") is True and projected["state"] == current,
          "reading the automation document projection preserves revision selection and history")
    snapshots = [copy.deepcopy(original)]

    def lane_in(project, parameter):
        return next((lane for lane in project["tracks"][target_index]["automation"]
                     if lane["parameter"] == parameter), None)

    def valid_uuid(value):
        try:
            return isinstance(value, str) and str(uuid.UUID(value)).lower() == value.lower()
        except (ValueError, AttributeError):
            return False

    def mutate(command, parameter, name, **values):
        nonlocal current
        before = current
        reply = send(command, before["revision"], trackID=track_id, parameter=parameter, **values)
        after = reply["state"]
        expected = copy.deepcopy(before["project"])
        lane = lane_in(expected, parameter)
        actual_lane = lane_in(after["project"], parameter)
        if lane is None:
            check(actual_lane is not None and valid_uuid(actual_lane.get("id"))
                  and actual_lane["id"] not in {item["id"] for item in track["automation"]},
                  name + " creates a distinct valid lane identity")
            lane = {"id": actual_lane["id"], "parameter": parameter, "isReadEnabled": True, "points": []}
            expected["tracks"][target_index]["automation"].append(lane)
        if command == "upsertAutomationPoint":
            point_id = values.get("pointID")
            if point_id is None:
                candidates = [p for p in actual_lane["points"] if p["time"] == values["time"]]
                check(len(candidates) == 1 and valid_uuid(candidates[0].get("id"))
                      and candidates[0]["id"] not in {p["id"] for p in lane["points"]},
                      name + " creates a distinct valid point identity")
                point_id = candidates[0]["id"]
            lane["points"] = [p for p in lane["points"] if p["id"] != point_id and p["time"] != values["time"]]
            lane["points"].append({"id": point_id, "time": values["time"], "value": values["value"],
                                   "interpolation": values.get("interpolation", "linear")})
            lane["points"].sort(key=lambda p: p["time"])
        elif command == "removeAutomationPoint":
            lane["points"] = [p for p in lane["points"] if p["id"] != values["pointID"]]
        elif command == "setAutomationRead":
            lane["isReadEnabled"] = values["enabled"]
        else:
            raise RuntimeError("Unknown automation control command")
        check(reply.get("ok") is True and after["revision"] == before["revision"] + 1
              and after["project"] == expected and after["selection"] == before["selection"]
              and after["dirty"] and after["canUndo"],
              name + " advances exactly one revision and preserves every unrelated document field")
        current = after
        snapshots.append(copy.deepcopy(expected))
        return lane

    # Create a pan lane first so every subsequent volume edit has another lane
    # on the same track whose exact identities, read state and values must survive.
    pan = mutate("upsertAutomationPoint", "pan", "pan point insertion", time=0, value=-0.25,
                 interpolation="step")
    pan_first = pan["points"][0]["id"]
    mutate("upsertAutomationPoint", "pan", "second pan point insertion", time=10, value=0.5)
    mutate("upsertAutomationPoint", "pan", "existing pan point edit", pointID=pan_first,
           time=0, value=-0.5, interpolation="linear")
    pan_before_read = copy.deepcopy(lane_in(current["project"], "pan"))
    mutate("setAutomationRead", "pan", "pan Read off", enabled=False)
    mutate("setAutomationRead", "pan", "pan Read on", enabled=True)
    check(lane_in(current["project"], "pan") == pan_before_read,
          "pan Read roundtrip preserves both authored edit points exactly")
    receipt["pan_edit_read_roundtrip"] = True

    old_revision = current["revision"]
    changed = gain["points"][1]
    mutate("upsertAutomationPoint", "gainDB", "existing volume point move and step edit",
           pointID=changed["id"], time=6, value=-9, interpolation="step")
    for command, fields in (("upsertAutomationPoint", {"time": 1, "value": -6}),
                            ("removeAutomationPoint", {"pointID": gain["points"][0]["id"]}),
                            ("setAutomationRead", {"enabled": False})):
        rejected = send(command, old_revision, trackID=track_id, parameter="gainDB", **fields)
        check(rejected.get("ok") is False and rejected.get("error", {}).get("code") == "staleRevision"
              and rejected["state"] == current, "stale " + command + " preserves document revision and history")
    receipt["stale_rejected"] = True

    missing_id = "00000000-0000-4000-8000-000000000001"
    invalid = [
        ("upsertAutomationPoint", {"time": -1, "value": -6}),
        ("upsertAutomationPoint", {"time": 86401, "value": -6}),
        ("upsertAutomationPoint", {"time": 1, "value": -97}),
        ("upsertAutomationPoint", {"time": 1, "value": 25}),
        ("upsertAutomationPoint", {"time": 1, "value": -6, "interpolation": "unsupported"}),
        ("upsertAutomationPoint", {"time": 1}),
        ("upsertAutomationPoint", {"value": -6}),
        ("upsertAutomationPoint", {"pointID": missing_id, "time": 1, "value": -6}),
        ("upsertAutomationPoint", {"parameter": "unsupported", "time": 1, "value": -6}),
        ("upsertAutomationPoint", {"parameter": None, "time": 1, "value": -6}),
        ("upsertAutomationPoint", {"parameter": "pan", "time": 1, "value": 1.01}),
        ("upsertAutomationPoint", {"parameter": "pan", "time": 1, "value": -1.01}),
        ("upsertAutomationPoint", {"trackID": missing_id, "time": 1, "value": -6}),
        ("removeAutomationPoint", {"pointID": missing_id}),
        ("setAutomationRead", {}),
    ]
    for index, (command, fields) in enumerate(invalid, 1):
        rejected = send(command, current["revision"], **{"trackID": track_id, "parameter": "gainDB", **fields})
        check(rejected.get("ok") is False and rejected["state"] == current,
              "invalid automation request " + str(index) + " is rejected without changing state or history")
    receipt["invalid_rejected"] = True
    same_point = next(p for p in lane_in(current["project"], "gainDB")["points"] if p["id"] == changed["id"])
    unchanged = send("upsertAutomationPoint", current["revision"], trackID=track_id, parameter="gainDB",
                     pointID=same_point["id"], time=same_point["time"], value=same_point["value"],
                     interpolation=same_point["interpolation"])
    check(unchanged.get("ok") is True and unchanged["state"] == current,
          "identical automation upsert does not create a revision or undo entry")
    mutate("upsertAutomationPoint", "gainDB", "new volume point insertion", time=7.5, value=-3)
    mutate("removeAutomationPoint", "gainDB", "volume point deletion", pointID=gain["points"][2]["id"])
    before_read = copy.deepcopy(lane_in(current["project"], "gainDB"))
    mutate("setAutomationRead", "gainDB", "volume Read off", enabled=False)
    check(lane_in(current["project"], "gainDB")["points"] == before_read["points"],
          "volume Read off preserves the complete edited curve")
    receipt["read_off_preserves_points"] = True
    repeated_read = send("setAutomationRead", current["revision"], trackID=track_id,
                         parameter="gainDB", enabled=False)
    check(repeated_read.get("ok") is True and repeated_read["state"] == current,
          "repeating automation Read state does not create a revision or undo entry")
    disabled_project = copy.deepcopy(current["project"])

    def render_checked(filename, label):
        output = work / filename
        reply = send("render", current["revision"], path=str(output))
        check(reply.get("ok") is True and reply["state"] == current and not output.is_symlink(), label)
        data = output.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        pcm_digest = hashlib.sha256(wav_chunks(data)[b"data"]).hexdigest()
        metadata = reply.get("render", {})
        check(metadata.get("revision") == current["revision"] and metadata.get("sha256") == digest
              and metadata.get("frames") == lock["frames"] and metadata.get("channels") == lock["channels"]
              and metadata.get("sampleRate") == lock["sample_rate"] and metadata.get("wavBytes") == len(data),
              label + " returns matching file and frame provenance")
        return data, digest, pcm_digest

    disabled_audio, _, _ = render_checked("automation-read-off.wav", "disabled volume automation renders read-only")
    mutate("setAutomationRead", "gainDB", "volume Read on", enabled=True)
    intended = copy.deepcopy(current["project"])
    edited_audio, edited_digest, edited_pcm = render_checked("automation-edited.wav", "edited automation renders read-only")
    check(edited_audio != disabled_audio and edited_digest != lock["wav_sha256"],
          "enabled edited automation changes the authored render and differs from its Read-off result")
    receipt.update(edits_revision_bound=True, other_automation_preserved=True)
    for expected in reversed(snapshots[:-1]):
        previous = current
        undone = send("undo", previous["revision"])
        check(undone.get("ok") is True and undone["state"]["revision"] == previous["revision"] + 1
              and undone["state"]["project"] == expected,
              "automation undo restores the exact preceding complete project at revision "
              + str(undone["state"]["revision"]))
        current = undone["state"]
    check(current["project"] == original and not current["dirty"] and not current["canUndo"],
          "all automation edits undo to the original clean project and empty undo history")
    receipt["undo_restores_project"] = True
    _, restored_digest, restored_pcm = render_checked("automation-restored.wav", "automation undo renders the original project")
    check(restored_digest == lock["wav_sha256"] and restored_pcm == lock["pcm_sha256"],
          "automation undo restores both predeclared example WAV and PCM hashes exactly")
    receipt["undo_restores_locked_render"] = True
    for expected in snapshots[1:]:
        previous = current
        redone = send("redo", previous["revision"])
        check(redone.get("ok") is True and redone["state"]["revision"] == previous["revision"] + 1
              and redone["state"]["project"] == expected,
              "automation redo restores the exact next complete project at revision "
              + str(redone["state"]["revision"]))
        current = redone["state"]
    check(current["project"] == intended and not current["canRedo"],
          "automation redo restores all intended volume and pan edits with stable identities")
    receipt["redo_restores_edits"] = True
    saved_path = work / "AutomationEdited.rebaseproj"
    saved = send("saveAs", current["revision"], path=str(saved_path))
    check(saved.get("ok") is True and saved["state"]["project"] == intended and not saved["state"]["dirty"],
          "automation edits save into a new project without changing their values or identities")
    reopened = send("open", saved["state"]["revision"], path=str(saved_path))
    check(reopened.get("ok") is True and reopened["state"]["project"] == intended
          and not reopened["state"]["dirty"] and not reopened["state"]["canUndo"],
          "saved automation lanes reopen exactly with clean document history")
    current = reopened["state"]
    reopened_audio, reopened_digest, reopened_pcm = render_checked("automation-reopened.wav", "reopened automation renders read-only")
    check(reopened_audio == edited_audio and reopened_digest == edited_digest and reopened_pcm == edited_pcm,
          "saved and reopened automation produces byte-identical edited audio")
    receipt["save_reopen_preserves_edits"] = True

    # Independent manual-fallback control: remove only the disabled gain lane
    # from a scratch derivative. The same pan lane and all other data remain.
    manual_root = work / "AutomationManualControl.rebaseproj"
    shutil.copytree(args.example, manual_root)
    manual_project = copy.deepcopy(disabled_project)
    manual_project["tracks"][target_index]["automation"] = [
        lane for lane in manual_project["tracks"][target_index]["automation"] if lane["parameter"] != "gainDB"]
    (manual_root / "Project.json").write_text(json.dumps(manual_project), encoding="utf-8")
    manual_opened = send("open", current["revision"], path=str(manual_root), asCopy=True)
    check(manual_opened.get("ok") is True and manual_opened["state"]["project"] == manual_project,
          "derived manual-gain control removes only the disabled gain lane")
    current = manual_opened["state"]
    manual_audio, _, _ = render_checked("automation-manual.wav", "manual-gain control renders read-only")
    check(manual_audio == disabled_audio,
          "Read-off volume automation uses exactly the same audio as manual gain without its lane")
    receipt["read_off_uses_manual_gain"] = True
    final_files = {p.relative_to(args.example).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in args.example.rglob("*") if p.is_file()}
    check(final_files == original_files, "automation controls preserve every bundled example file byte")
    receipt.update(tested=True, source_unchanged=True, mutation_count=len(snapshots)-1,
                   invalid_requests_checked=len(invalid), restored_wav_sha256=restored_digest,
                   restored_pcm_sha256=restored_pcm, edited_wav_sha256=edited_digest,
                   edited_pcm_sha256=edited_pcm)
    return current


def source_journey(args, work, revision, send, check, report):
    expected = json.loads(args.source_lock.read_text(encoding="utf-8"))
    source_original = {path.relative_to(args.source_project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in args.source_project.rglob("*") if path.is_file()}
    media_original = args.source_media.read_bytes()
    check(source_original.get("Project.json") == expected["manifestSHA256"]
          and hashlib.sha256(media_original).hexdigest() == expected["mediaSHA256"],
          "authored source manifest and selected media match predeclared hashes")
    opened = send("open", revision, path=str(args.source_project.resolve()), asCopy=True)
    check(opened.get("ok") is True and opened["state"]["needsSaveAs"] and not opened["state"]["dirty"],
          "authored source project opens as an isolated working copy")
    state = opened["state"]
    project = state["project"]
    events = [event for track in project["tracks"] for event in track.get("unresolvedAudioEvents", [])]
    check(len(events) == 1 and events[0]["id"] == expected["eventID"]
          and events[0]["sourceSHA256"] == expected["sourceSHA256"]
          and project["sampleRate"] == expected["projectSampleRate"]
          and not project.get("cprMediaAttachments", [])
          and all(not track["clips"] for track in project["tracks"]),
          "source fixture retains one unattached event and no ordinary clips")
    event_id = expected["eventID"]
    missing = work / "unattached-source.wav"
    rejected = send("renderSourceEvent", state["revision"], clipID=event_id, path=str(missing))
    check(rejected.get("ok") is False and rejected["state"] == state and not missing.exists(),
          "unattached source export fails without output or state changes")
    attached = send("attachSourceMedia", state["revision"], clipID=event_id, path=str(args.source_media.resolve()))
    attached_state = attached["state"]
    attached_project = attached_state["project"]
    attachments = attached_project.get("cprMediaAttachments", [])
    check(attached.get("ok") is True and attached_state["revision"] == state["revision"] + 1
          and attached_state["dirty"] and len(attachments) == 1
          and attachments[0]["mediaSHA256"] == expected["mediaSHA256"]
          and [event for track in attached_project["tracks"] for event in track.get("unresolvedAudioEvents", [])] == events
          and all(not track["clips"] for track in attached_project["tracks"]),
          "source attachment advances revision while preserving unresolved event semantics")
    stale = send("renderSourceEvent", state["revision"], clipID=event_id, path=str(missing))
    check(stale.get("ok") is False and stale["error"]["code"] == "staleRevision"
          and stale["state"] == attached_state and not missing.exists(),
          "stale source export is rejected without output")
    output = work / "source-event.wav"
    rendered = send("renderSourceEvent", attached_state["revision"], clipID=event_id, path=str(output))
    metadata = rendered.get("render", {})
    check(rendered.get("ok") is True and rendered["state"] == attached_state,
          "source export is read-only and returns a checked snapshot")
    data = output.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    check(not output.is_symlink() and metadata.get("kind") == "sourceEvent"
          and metadata.get("eventID") == event_id and metadata.get("revision") == attached_state["revision"]
          and metadata.get("sourceSHA256") == expected["sourceSHA256"]
          and metadata.get("mediaSHA256") == expected["mediaSHA256"]
          and metadata.get("sha256") == digest == expected["outputSHA256"]
          and metadata.get("wavBytes") == len(data) == expected["outputBytes"] and Path(metadata["path"]).samefile(output),
          "source output bytes and event provenance match predeclared locks")
    chunks = wav_chunks(data)
    fmt = struct.unpack_from("<HHIIHH", chunks[b"fmt "])
    pcm_digest = hashlib.sha256(chunks[b"data"]).hexdigest()
    rate, channels, frames = expected["sampleRate"], expected["channels"], expected["frames"]
    check(fmt == (3, channels, rate, rate * channels * 4, channels * 4, 32)
          and metadata.get("sampleRate") == rate and metadata.get("channels") == channels
          and metadata.get("frames") == frames and len(chunks[b"data"]) == frames * channels * 4
          and pcm_digest == expected["pcmSHA256"]
          and all(math.isfinite(sample[0]) for sample in struct.iter_unpack("<f", chunks[b"data"])),
          "source export uses exact locked Float32 PCM at the saved source rate")
    refused = send("renderSourceEvent", attached_state["revision"], clipID=event_id, path=str(output))
    check(refused.get("ok") is False and refused["state"] == attached_state and output.read_bytes() == data,
          "repeat source export preserves the existing WAV")
    whole = work / "unresolved-project.wav"
    rejected_project = send("render", attached_state["revision"], path=str(whole))
    check(rejected_project.get("ok") is False and rejected_project["error"]["code"] == "nativePlayback"
          and rejected_project["state"] == attached_state and not whole.exists(),
          "source attachment does not silently enable ordinary project rendering")
    undone = send("undo", attached_state["revision"])
    check(undone.get("ok") is True and undone["state"]["project"] == project and not undone["state"]["dirty"],
          "undo removes the source attachment without changing event semantics")
    undone_render = send("renderSourceEvent", undone["state"]["revision"], clipID=event_id, path=str(missing))
    check(undone_render.get("ok") is False and undone_render["state"] == undone["state"] and not missing.exists(),
          "source export remains unavailable after attachment undo")
    redone = send("redo", undone["state"]["revision"])
    check(redone.get("ok") is True and redone["state"]["project"] == attached_project,
          "redo restores the same checked source attachment")
    saved_path = work / "SavedSource.rebaseproj"
    saved = send("saveAs", redone["state"]["revision"], path=str(saved_path))
    check(saved.get("ok") is True and not saved["state"]["dirty"] and not saved["state"]["needsSaveAs"],
          "source working copy saves into a new project package")
    reopened = send("open", saved["state"]["revision"], path=str(saved_path))
    check(reopened.get("ok") is True and reopened["state"]["project"] == attached_project,
          "saved source package reopens with the same attachment and unresolved event")
    repeated = work / "reopened-source.wav"
    rerendered = send("renderSourceEvent", reopened["state"]["revision"], clipID=event_id, path=str(repeated))
    check(rerendered.get("ok") is True and repeated.read_bytes() == data,
          "reopened source package revalidates and renders identical bytes")
    final_source = {path.relative_to(args.source_project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in args.source_project.rglob("*") if path.is_file()}
    check(final_source == source_original and args.source_media.read_bytes() == media_original,
          "authored source fixture and selected PCM remain unchanged")
    report["source_journey_tested"] = True
    report["source"] = {"sourceSHA256": expected["sourceSHA256"], "mediaSHA256": expected["mediaSHA256"],
                        "outputSHA256": digest, "pcmSHA256": pcm_digest,
                        "frames": frames, "sampleRate": rate, "channels": channels,
                        "playback_tested": False}


def cpr_import_journey(args, work, send, check, report):
    """Exercise the actual helper with the already locked, authored archive.

    Inspection and historical-report retrieval must be separate from document
    mutation. The receipt deliberately contains no local paths or helper error
    messages, and each gate starts false so a partial run cannot look complete.
    """
    gates = ("review_read_only", "review_bounded", "cancellation_preserves_state",
             "superseded_review_rejected", "stale_revision_rejected", "changed_source_rejected",
             "explicit_partial_required", "dirty_replacement_guarded", "existing_destination_preserved",
             "import_published", "exact_source_and_report_preserved", "save_reopen_preserves_baseline",
             "historical_read_only", "tampered_report_rejected", "tampered_source_rejected")
    receipt = {"tested": False, **dict.fromkeys(gates, False)}
    report["cpr_import"] = receipt
    expected = json.loads(args.source_lock.read_text(encoding="utf-8"))
    fixture_cpr = args.source_project / "Compatibility" / "CPR" / "Original.cpr"
    fixture_report = args.source_project / "Compatibility" / "CPR" / "ImportReport.json"
    original = fixture_cpr.read_bytes()
    original_report = fixture_report.read_bytes()
    baseline_report = json.loads(original_report)
    baseline_project = baseline_report["recoveredProject"]
    source = work / "AuthoredSource.cpr"
    source.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()
    report_digest = hashlib.sha256(original_report).hexdigest()
    receipt.update(sourceSHA256=digest, reportSHA256=report_digest,
                   evidence_class="authored-synthetic-control", playback_tested=False)
    check(digest == expected["sourceSHA256"] and report_digest == expected["reportSHA256"]
          and baseline_report["sourceName"] == source.name and baseline_report["unsupported"],
          "CPR import controls use the locked authored source and historical report")
    current = send("state")["state"]

    def bounded_review(reply, state, historical=False):
        review = reply.get("cprReview", {})
        review_id = review.get("reviewID")
        valid_id = False
        if isinstance(review_id, str):
            try:
                valid_id = str(uuid.UUID(review_id)).lower() == review_id.lower()
            except ValueError:
                pass
        items = review.get("items")
        total, offset, next_offset = review.get("totalItems"), review.get("offset"), review.get("nextOffset")
        bounded = (isinstance(items, list) and len(items) <= 32
                   and set(review) <= {"reviewID", "sourceName", "sourceSHA256", "sourceByteCount",
                                       "interpretationProfile", "historical", "canImport", "recoveredTrackCount",
                                       "recoveredClipCount", "unresolvedEventCount", "totalItems", "offset",
                                       "nextOffset", "items"}
                   and type(total) is int and total > 0 and type(offset) is int and 0 <= offset < total
                   and all(isinstance(item, dict) and item.get("section") in
                           ("recovered", "tracks", "unresolved", "defaults", "metadata")
                           and isinstance(item.get("label"), str) and isinstance(item.get("detail"), str)
                           for item in items)
                   and len(json.dumps(review, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 131072
                   and offset + len(items) <= total
                   and ((next_offset is None and offset + len(items) == total)
                        or (type(next_offset) is int and next_offset == offset + len(items)
                            and offset < next_offset < total)))
        if not (reply.get("ok") is True and reply.get("state") == state and valid_id and bounded
                and review.get("sourceName") == source.name and review.get("sourceSHA256") == digest
                and review.get("sourceByteCount") == len(original)
                and review.get("interpretationProfile") == baseline_report["interpretationProfile"]
                and review.get("historical") is historical
                and review.get("canImport") is (not historical)
                and review.get("recoveredTrackCount") == len(baseline_project["tracks"])
                and review.get("recoveredClipCount") == sum(len(t["clips"]) for t in baseline_project["tracks"])
                and review.get("unresolvedEventCount") == sum(len(t.get("unresolvedAudioEvents", []))
                                                            for t in baseline_project["tracks"])):
            return None
        return review

    def inspect(state):
        reply = send("inspectCPR", state["revision"], path=str(source))
        review = bounded_review(reply, state)
        check(review is not None and review["offset"] == 0,
              "CPR inspection is bounded and preserves the complete active document state")
        return review

    review = inspect(current)
    receipt["review_read_only"] = True
    first_review = review
    all_items = list(review["items"])
    page_count = 1
    while review.get("nextOffset") is not None:
        if page_count > first_review["totalItems"]:
            raise RuntimeError("CPR review pagination did not terminate")
        reply = send("cprReviewPage", current["revision"], reviewID=first_review["reviewID"],
                     reviewOffset=review["nextOffset"])
        next_review = bounded_review(reply, current)
        check(next_review is not None and next_review["reviewID"] == first_review["reviewID"]
              and next_review["offset"] == review["nextOffset"]
              and next_review["totalItems"] == first_review["totalItems"],
              "CPR review pagination returns the same bounded read-only review")
        review = next_review
        all_items.extend(review["items"])
        page_count += 1
    repeated = send("cprReviewPage", current["revision"], reviewID=first_review["reviewID"], reviewOffset=0)
    check(repeated.get("ok") is True and repeated["state"] == current
          and repeated.get("cprReview") == first_review and len(all_items) == first_review["totalItems"]
          and {item["section"] for item in all_items} >= {"recovered", "tracks", "unresolved", "defaults"},
          "CPR review pages are stable complete and bounded without embedding the recovered project")
    last_offset = first_review["totalItems"] - 1
    tail = send("cprReviewPage", current["revision"], reviewID=first_review["reviewID"], reviewOffset=last_offset)
    tail_review = bounded_review(tail, current)
    check(tail_review is not None and tail_review["reviewID"] == first_review["reviewID"]
          and tail_review["offset"] == last_offset and tail_review["items"] == all_items[-1:]
          and tail_review.get("nextOffset") is None,
          "CPR review supports a bounded final-item page without repeating earlier rows")
    for invalid_offset in (-1, first_review["totalItems"] + 1):
        rejected = send("cprReviewPage", current["revision"], reviewID=first_review["reviewID"],
                        reviewOffset=invalid_offset)
        check(rejected.get("ok") is False and rejected["state"] == current,
              "invalid CPR review page offset is rejected without changing the active document")
    receipt.update(review_bounded=True, review_items_checked=len(all_items), review_pages_checked=page_count)
    cancelled = send("cancelCPRReview", current["revision"], reviewID=first_review["reviewID"])
    cancelled_destination = work / "CancelledImport.rebaseproj"
    after_cancel = send("importCPR", current["revision"], reviewID=first_review["reviewID"],
                        sourceSHA256=digest, path=str(cancelled_destination), allowPartial=True)
    cancelled_page = send("cprReviewPage", current["revision"], reviewID=first_review["reviewID"], reviewOffset=0)
    check(cancelled.get("ok") is True and cancelled["state"] == current
          and after_cancel.get("ok") is False and after_cancel["state"] == current
          and cancelled_page.get("ok") is False and cancelled_page["state"] == current
          and not cancelled_destination.exists(),
          "cancelling CPR review invalidates its token without publishing or changing the active document")
    receipt["cancellation_preserves_state"] = True
    old_review = inspect(current)
    review = inspect(current)
    superseded = send("importCPR", current["revision"], reviewID=old_review["reviewID"],
                      sourceSHA256=digest, path=str(cancelled_destination), allowPartial=True)
    check(review["reviewID"] != old_review["reviewID"] and superseded.get("ok") is False
          and superseded["state"] == current and not cancelled_destination.exists(),
          "a new CPR inspection invalidates the superseded review token")
    receipt["superseded_review_rejected"] = True
    stale = send("importCPR", current["revision"] - 1, reviewID=review["reviewID"],
                 sourceSHA256=digest, path=str(cancelled_destination), allowPartial=True)
    check(stale.get("ok") is False and stale["error"]["code"] == "staleRevision"
          and stale["state"] == current and not cancelled_destination.exists(),
          "stale CPR import revision is rejected without publishing or changing the active document")
    receipt["stale_revision_rejected"] = True
    changed = bytearray(original)
    changed[-1] ^= 1
    source.write_bytes(changed)
    rejected = send("importCPR", current["revision"], reviewID=review["reviewID"],
                    sourceSHA256=digest, path=str(cancelled_destination), allowPartial=True)
    check(rejected.get("ok") is False and rejected["state"] == current
          and not cancelled_destination.exists() and source.read_bytes() == changed,
          "source bytes changed after CPR review are rejected and left untouched")
    receipt["changed_source_rejected"] = True
    source.write_bytes(original)
    review = inspect(current)
    wrong_hash = send("importCPR", current["revision"], reviewID=review["reviewID"],
                      sourceSHA256="0" * 64, path=str(cancelled_destination), allowPartial=True)
    check(wrong_hash.get("ok") is False and wrong_hash["state"] == current and not cancelled_destination.exists(),
          "CPR import refuses a confirmation hash that does not identify its review")
    for consent in ({}, {"allowPartial": False}):
        review = inspect(current)
        refused = send("importCPR", current["revision"], reviewID=review["reviewID"],
                       sourceSHA256=digest, path=str(cancelled_destination), **consent)
        check(refused.get("ok") is False and refused["state"] == current and not cancelled_destination.exists(),
              "CPR import requires explicit acceptance of the partial recovery")
    receipt["explicit_partial_required"] = True

    # Check all three destination shapes. A failed request is allowed to consume
    # its review; each independent case therefore starts with a new inspection.
    for shape in ("file", "empty-directory", "populated-directory"):
        destination = work / ("Existing-" + shape + ".rebaseproj")
        if shape == "file":
            destination.write_bytes(b"existing destination is never replaced\n")
            before = destination.read_bytes()
        else:
            destination.mkdir()
            if shape == "populated-directory":
                (destination / "sentinel.txt").write_bytes(b"existing content is never replaced\n")
            before = {p.name: p.read_bytes() for p in destination.iterdir()}
        review = inspect(current)
        refused = send("importCPR", current["revision"], reviewID=review["reviewID"],
                       sourceSHA256=digest, path=str(destination), allowPartial=True)
        after = destination.read_bytes() if shape == "file" else {p.name: p.read_bytes() for p in destination.iterdir()}
        check(refused.get("ok") is False and refused["state"] == current and before == after,
              "CPR import preserves an existing " + shape + " destination")
    receipt["existing_destination_preserved"] = True

    track = current["project"]["tracks"][0]
    changed_gain = -7 if track["gainDB"] != -7 else -8
    edited = send("setGain", current["revision"], trackID=track["id"], value=changed_gain)
    check(edited.get("ok") is True and edited["state"]["dirty"],
          "CPR replacement control starts from an actual unsaved mixer edit")
    current = edited["state"]
    review = inspect(current)
    destination = work / "ImportedSource.rebaseproj"
    guarded = send("importCPR", current["revision"], reviewID=review["reviewID"],
                   sourceSHA256=digest, path=str(destination), allowPartial=True)
    check(guarded.get("ok") is False and guarded["error"]["code"] == "unsavedChanges"
          and guarded["state"] == current and not destination.exists(),
          "CPR import preserves unsaved edits unless discard is explicitly confirmed")
    cancelled_dirty = send("cancelCPRReview", current["revision"], reviewID=review["reviewID"])
    check(cancelled_dirty.get("ok") is True and cancelled_dirty["state"] == current and not destination.exists(),
          "cancelling CPR import review preserves the actual unsaved mixer edit")
    receipt["dirty_replacement_guarded"] = True
    review = inspect(current)
    imported = send("importCPR", current["revision"], reviewID=review["reviewID"],
                    sourceSHA256=digest, path=str(destination), allowPartial=True, discardChanges=True)
    check(imported.get("ok") is True and imported["state"]["revision"] == current["revision"] + 1
          and not imported["state"]["dirty"] and not imported["state"]["needsSaveAs"]
          and imported["state"]["project"] == baseline_project and destination.is_dir(),
          "confirmed CPR import publishes and activates the preserved recovered project")
    current = imported["state"]
    receipt["import_published"] = True
    preserved_source = destination / "Compatibility" / "CPR" / "Original.cpr"
    preserved_report = destination / "Compatibility" / "CPR" / "ImportReport.json"
    check(preserved_source.read_bytes() == original and preserved_report.read_bytes() == original_report
          and hashlib.sha256((destination / "Project.json").read_bytes()).hexdigest() == expected["manifestSHA256"]
          and not current["project"].get("cprMediaAttachments", [])
          and all(not t["clips"] for t in current["project"]["tracks"]),
          "CPR import preserves exact source report and manifest bytes without inferring playable clips")
    receipt["exact_source_and_report_preserved"] = True
    repeated_destination = work / "RepeatedImport.rebaseproj"
    repeated = send("importCPR", current["revision"], reviewID=review["reviewID"],
                    sourceSHA256=digest, path=str(repeated_destination), allowPartial=True)
    check(repeated.get("ok") is False and repeated["state"] == current and not repeated_destination.exists(),
          "successful CPR import consumes its confirmation token")

    historical = send("cprImportReport", current["revision"])
    history_review = bounded_review(historical, current, historical=True)
    check(history_review is not None and history_review["offset"] == 0,
          "historical CPR report is revalidated read-only and cannot offer import")
    history_page = send("cprReviewPage", current["revision"], reviewID=history_review["reviewID"], reviewOffset=0)
    rejected_history = send("importCPR", current["revision"], reviewID=history_review["reviewID"],
                            sourceSHA256=digest, path=str(repeated_destination), allowPartial=True)
    check(history_page.get("ok") is True and history_page["state"] == current
          and history_page.get("cprReview") == history_review and rejected_history.get("ok") is False
          and rejected_history["state"] == current and not repeated_destination.exists()
          and preserved_report.read_bytes() == original_report and preserved_source.read_bytes() == original,
          "historical CPR review pages cannot be used to publish another project")
    receipt["historical_read_only"] = True

    imported_track = current["project"]["tracks"][0]
    edited = send("setGain", current["revision"], trackID=imported_track["id"], value=-9)
    check(edited.get("ok") is True and edited["state"]["dirty"],
          "imported CPR project accepts an ordinary reversible mixer edit")
    edited_project = edited["state"]["project"]
    saved = send("save", edited["state"]["revision"])
    reopened = send("open", saved["state"]["revision"], path=str(destination))
    history_after_edit = send("cprImportReport", reopened["state"]["revision"])
    check(saved.get("ok") is True and not saved["state"]["dirty"]
          and reopened.get("ok") is True and reopened["state"]["project"] == edited_project
          and bounded_review(history_after_edit, reopened["state"], historical=True) is not None
          and preserved_report.read_bytes() == original_report and preserved_source.read_bytes() == original,
          "saving and reopening an edited CPR import preserves its original historical baseline")
    current = reopened["state"]
    receipt["save_reopen_preserves_baseline"] = True

    # Valid JSON with unchanged source identity must still be replay-checked.
    tampered = json.loads(original_report)
    tampered["recoveredFacts"][0] += " Authored tamper control."
    tampered_bytes = json.dumps(tampered, indent=2).encode("utf-8")
    preserved_report.write_bytes(tampered_bytes)
    cached_page = send("cprReviewPage", current["revision"],
                       reviewID=history_after_edit["cprReview"]["reviewID"], reviewOffset=0)
    rejected_report = send("cprImportReport", current["revision"])
    check(cached_page.get("ok") is False and cached_page["state"] == current
          and rejected_report.get("ok") is False and rejected_report["state"] == current
          and preserved_report.read_bytes() == tampered_bytes and preserved_source.read_bytes() == original,
          "historical CPR report rejects semantic tampering without repairing the stored evidence")
    receipt["tampered_report_rejected"] = True
    preserved_report.write_bytes(original_report)
    preserved_source.write_bytes(changed)
    rejected_source = send("cprImportReport", current["revision"])
    check(rejected_source.get("ok") is False and rejected_source["state"] == current
          and preserved_source.read_bytes() == changed and preserved_report.read_bytes() == original_report,
          "historical CPR report rejects altered preserved source bytes without repairing them")
    receipt["tampered_source_rejected"] = True
    preserved_source.write_bytes(original)
    restored = send("cprImportReport", current["revision"])
    check(bounded_review(restored, current, historical=True) is not None
          and source.read_bytes() == original and fixture_cpr.read_bytes() == original
          and fixture_report.read_bytes() == original_report,
          "CPR controls leave authored fixtures unchanged and restore only their temporary tamper controls")
    receipt["tested"] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-project", type=Path)
    parser.add_argument("--source-media", type=Path)
    parser.add_argument("--source-lock", type=Path)
    args = parser.parse_args()
    if any((args.source_project, args.source_media, args.source_lock)) and not all((args.source_project, args.source_media, args.source_lock)):
        parser.error("Source verification requires project, media and lock inputs together")
    lock = json.loads((Path(__file__).parent / "example-render-lock.json").read_text())
    report = {"schema": "rebase.session-protocol-check.v1", "status": "failed",
              "scope": "Interactive authored session process, automation editing, musical ruler, source waveforms, optional source-event PCM and reviewed CPR import; no GUI or audio device claim",
              "source_journey_tested": False, "checks": []}
    original = (args.example / "Project.json").read_bytes()
    process = subprocess.Popen([str(args.helper.resolve()), "--stdio"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    responses = queue.Queue(maxsize=2)

    def read_responses():
        try:
            while True:
                line = process.stdout.readline(16_777_217)
                responses.put(line)
                if not line or len(line) > 16_777_216:
                    return
        except Exception as error:
            responses.put(error)

    threading.Thread(target=read_responses, daemon=True).start()
    next_id = 0

    def send(command, revision=0, **values):
        nonlocal next_id
        report["last_command"] = command
        next_id += 1
        message = {"protocol": 1, "id": next_id, "command": command, "expectedRevision": revision, **values}
        process.stdin.write(json.dumps(message).encode("utf-8") + b"\n")
        process.stdin.flush()
        line = responses.get(timeout=120)
        if not isinstance(line, bytes) or not line or len(line) > 16_777_216 or not line.endswith(b"\n"):
            raise RuntimeError("Missing, failed or oversized session response")
        result = json.loads(line)
        if result.get("protocol") != 1 or result.get("id") != next_id:
            raise RuntimeError("Session response protocol or identifier mismatch")
        report["last_response_ok"] = result.get("ok")
        report["last_error_code"] = result.get("error", {}).get("code")
        return result

    def check(condition, name):
        if not condition:
            report["failed_check"] = name
            raise RuntimeError(name)
        report["checks"].append(name)

    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rebase-protocol-check-", dir=args.report.parent) as work:
            root = Path(work)
            opened = send("open", path=str(args.example.resolve()), asCopy=True)
            check(opened.get("ok") is True and opened["state"]["revision"] == 1 and opened["state"]["needsSaveAs"],
                  "example working copy opens before stdin EOF")
            project = opened["state"]["project"]
            check(len(project["tracks"]) == 4 and sum(len(t["clips"]) for t in project["tracks"]) == 11,
                  "example contains four tracks and eleven clips")
            ruler_reply = send("ruler", 1, value=100, duration=20)
            ruler = ruler_reply.get("ruler", {})
            check(ruler_reply.get("ok") is True and ruler_reply["state"] == opened["state"]
                  and ruler.get("revision") == 1 and ruler.get("duration") == 20
                  and ruler.get("pixelsPerSecond") == 100,
                  "musical ruler is read-only and returns the requested revision and extent")
            ticks = ruler.get("ticks", [])
            check(isinstance(ticks, list) and 13 <= len(ticks) <= 8192
                  and all(type(t.get("seconds")) in (int, float) and math.isfinite(t["seconds"])
                          and 0 <= t["seconds"] <= 20 and type(t.get("bar")) is bool
                          and isinstance(t.get("label"), str) for t in ticks)
                  and all(a["seconds"] < b["seconds"] for a, b in zip(ticks, ticks[1:])),
                  "musical ruler ticks are finite ordered and bounded by the requested extent")
            # Closed-form controls for the authored constant 96 BPM, 4/4 example:
            # one quarter is 60/96 = .625 seconds and one bar is 2.5 seconds.
            expected_first_beats = [(0, True, "1"), (0.625, False, "1"), (1.25, False, "1"),
                                    (1.875, False, "1"), (2.5, True, "2")]
            check([(t["seconds"], t["bar"], t["label"]) for t in ticks[:5]] == expected_first_beats,
                  "96 BPM quarter-note ruler positions and first bar transition match the independent example oracle")
            expected_bars = [(0, "1"), (2.5, "2"), (5, "3"), (7.5, "4")]
            check([(t["seconds"], t["label"]) for t in ticks if t["bar"]][:4] == expected_bars,
                  "4/4 bar boundaries are exactly 0, 2.5, 5 and 7.5 seconds")
            report["ruler"] = {"read_only": True, "stale_revision_rejected": False,
                               "pixels_per_second": 100, "duration": 20, "ticks_checked": len(ticks),
                               "first_bar_seconds": [item[0] for item in expected_bars],
                               "first_quarter_seconds": [item[0] for item in expected_first_beats],
                               "oracle": "Authored constant 96 BPM, 4/4: quarter = 5/8 seconds; bar = 5/2 seconds"}
            track = project["tracks"][0]
            waveforms = {}
            peak_digest = hashlib.sha256()
            for index, clip in enumerate(c for t in project["tracks"] for c in t["clips"]):
                oracle = example_waveform_oracle(args.example, clip)
                reply = send("waveform", 1, clipID=clip["id"])
                actual = reply.get("waveform", {})
                check(reply.get("ok") is True and reply["state"] == opened["state"]
                      and actual.get("revision") == 1 and actual.get("clipID") == clip["id"]
                      and all(actual.get(key) == oracle[key] for key in
                              ("sampleRate", "sourceStartFrame", "sourceFrames", "mediaSHA256"))
                      and peak_words(actual.get("peaks")) == peak_words(oracle["peaks"]),
                      "clip " + str(index + 1) + " waveform matches exact PCM16 source peaks without changing state")
                waveforms[clip["id"]] = actual
                peak_digest.update(peak_words(actual["peaks"]))
            report["waveform"] = {"clips_checked": len(waveforms),
                                  "peak_bins_checked": sum(len(item["peaks"]) for item in waveforms.values()),
                                  "float32_peak_words_sha256": peak_digest.hexdigest(),
                                  "oracle": "Independent signed PCM16 extrema over exact source intervals"}
            edited = send("setGain", 1, trackID=track["id"], value=-12)
            check(edited.get("ok") is True and edited["state"]["revision"] == 2 and edited["state"]["dirty"],
                  "shared mixer edit advances document revision")
            stale_ruler = send("ruler", 1, value=100, duration=20)
            check(stale_ruler.get("ok") is False and stale_ruler["error"]["code"] == "staleRevision"
                  and stale_ruler["state"] == edited["state"], "stale ruler request is rejected without changing state")
            report["ruler"]["stale_revision_rejected"] = True
            stale = send("toggleMute", 1, trackID=track["id"])
            check(stale.get("ok") is False and stale["error"]["code"] == "staleRevision"
                  and stale["state"]["revision"] == 2, "stale command leaves document unchanged")
            stale_waveform = send("waveform", 1, clipID=track["clips"][0]["id"])
            check(stale_waveform.get("ok") is False and stale_waveform["error"]["code"] == "staleRevision"
                  and stale_waveform["state"] == edited["state"], "stale waveform request is rejected without changing state")
            gained_waveform = send("waveform", 2, clipID=track["clips"][0]["id"])
            expected_waveform = {**waveforms[track["clips"][0]["id"]], "revision": 2}
            check(gained_waveform.get("ok") is True and gained_waveform["state"] == edited["state"]
                  and gained_waveform.get("waveform") == expected_waveform,
                  "mixer gain does not alter source waveform peaks")
            undone = send("undo", 2)
            check(undone.get("ok") is True and undone["state"]["project"] == project
                  and not undone["state"]["dirty"], "undo restores complete original project")
            wav = root / "example.wav"
            rendered = send("render", 3, path=str(wav))
            check(rendered.get("ok") is True, "session renders a snapshot")
            data = wav.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            metadata = rendered["render"]
            check(metadata["revision"] == 3 and metadata["frames"] == lock["frames"]
                  and metadata["channels"] == lock["channels"] and metadata["sampleRate"] == lock["sample_rate"]
                  and metadata["wavBytes"] == len(data) and Path(metadata["path"]).samefile(wav),
                  "snapshot metadata and native path match the rendered revision")
            check(not wav.is_symlink() and metadata["sha256"] == digest == lock["wav_sha256"],
                  "published regular WAV matches predeclared example bytes")
            check(data[:4] == b"RIFF" and data[8:12] == b"WAVE"
                  and struct.unpack_from("<I", data, 4)[0] + 8 == len(data), "snapshot has complete RIFF envelope")
            chunks, offset = {}, 12
            while offset + 8 <= len(data):
                tag, length = struct.unpack_from("<4sI", data, offset)
                start = offset + 8
                if tag in chunks or start + length > len(data):
                    raise RuntimeError("Invalid snapshot chunk")
                chunks[tag] = data[start:start + length]
                offset = start + length + length % 2
            check(offset == len(data) and b"data" in chunks and b"fmt " in chunks, "snapshot chunks are complete and unique")
            fmt = struct.unpack_from("<HHIIHH", chunks[b"fmt "])
            pcm = chunks[b"data"]
            pcm_digest = hashlib.sha256(pcm).hexdigest()
            check(fmt == (3, 2, 48000, 384000, 8, 32) and len(pcm) == lock["frames"] * 8
                  and pcm_digest == lock["pcm_sha256"], "Float32 stereo PCM matches predeclared sample hash")
            refused = send("render", 3, path=str(wav))
            check(refused.get("ok") is False and wav.read_bytes() == data, "existing WAV is preserved on repeat render")
            saved_path = root / "Saved.rebaseproj"
            saved = send("saveAs", 3, path=str(saved_path))
            check(saved.get("ok") is True and saved["state"]["revision"] == 4
                  and not saved["state"]["needsSaveAs"], "Save As publishes a new project package")
            reopened = send("open", 4, path=str(saved_path))
            check(reopened.get("ok") is True and reopened["state"]["project"] == project,
                  "saved project reopens with identical document semantics")
            check((args.example / "Project.json").read_bytes() == original, "bundled example manifest remains unchanged")
            automation_state = automation_journey(args, root, reopened["state"], send, check, report, lock)
            if args.source_project is not None:
                source_journey(args, root, automation_state["revision"], send, check, report)
                cpr_import_journey(args, root, send, check, report)
            process.stdin.close()
            check(process.wait(timeout=15) == 0, "EOF cleanly terminates session")
            report["wav_sha256"] = digest
            report["pcm_sha256"] = pcm_digest
            report["frames"] = metadata["frames"]
            report["status"] = "passed"
    except Exception as error:
        # Do not publish fixture paths or server-supplied data in this receipt.
        report["error_type"] = type(error).__name__
        report["failed_after_checks"] = len(report["checks"])
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=15)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
