#!/usr/bin/env python3
"""Exercise the packaged JSONL helper interactively, before closing its input."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import struct
import subprocess
import tempfile
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((Path(__file__).parent / "example-render-lock.json").read_text())
    report = {"schema": "rebase.session-protocol-check.v1", "status": "failed",
              "scope": "Interactive authored session process and example PCM; no GUI or audio device claim", "checks": []}
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
            track = project["tracks"][0]
            edited = send("setGain", 1, trackID=track["id"], value=-12)
            check(edited.get("ok") is True and edited["state"]["revision"] == 2 and edited["state"]["dirty"],
                  "shared mixer edit advances document revision")
            stale = send("toggleMute", 1, trackID=track["id"])
            check(stale.get("ok") is False and stale["error"]["code"] == "staleRevision"
                  and stale["state"]["revision"] == 2, "stale command leaves document unchanged")
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
