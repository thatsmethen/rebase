#!/usr/bin/env python3
"""Exercise the packaged JSONL helper interactively, before closing its input."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import queue
import struct
import subprocess
import tempfile
import threading


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
              "scope": "Interactive authored session process, musical ruler, source waveforms and optional source-event PCM; no GUI or audio device claim",
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
        with tempfile.TemporaryDirectory(prefix="rebase-protocol-check-") as work:
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
            if args.source_project is not None:
                source_journey(args, root, reopened["state"]["revision"], send, check, report)
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
