#!/usr/bin/env python3
"""Bounded, resumable HTTP range acquisition with immutable source identity.

HTTPS is required except for loopback test servers. A strong ETag and expected
size must be supplied independently. The final SHA-256 is a custody fingerprint,
not a publisher-checksum comparison. No downloaded application is executed.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.parse


class RetryableTransferError(Exception):
    """No trusted response bytes arrived, but the pinned identity did not change."""


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def hash_region(path, start, length):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        handle.seek(start)
        while length:
            block = handle.read(min(length, 1024 * 1024))
            if not block:
                raise ValueError("local file ends before a recorded segment")
            digest.update(block)
            length -= len(block)
    return digest.hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def parse_headers(raw):
    status = None
    headers = {}
    for line in raw.decode("iso-8859-1").splitlines():
        if line.startswith("HTTP/"):
            status = int(line.split()[1])
            headers = {}
        elif ":" in line and status is not None:
            name, value = line.split(":", 1)
            name = name.strip().lower()
            if name in headers:
                raise ValueError(f"duplicate response header: {name}")
            headers[name] = value.strip()
    if status is None:
        raise ValueError("no HTTP response headers")
    return status, headers


def validate_identity(headers, source):
    if headers.get("etag") != source["etag"]:
        raise ValueError("response ETag differs from pinned object identity")
    if source["last_modified"] and headers.get("last-modified") != source["last_modified"]:
        raise ValueError("response Last-Modified differs from pinned object identity")
    if headers.get("content-encoding", "identity").lower() != "identity":
        raise ValueError("encoded response cannot be used as byte ranges")


def validate_range(raw, source, start, end):
    status, headers = parse_headers(raw)
    validate_identity(headers, source)
    if status != 206:
        raise ValueError(f"expected HTTP 206, received {status}")
    expected = f"bytes {start}-{end}/{source['size']}"
    if headers.get("content-range") != expected:
        raise ValueError(f"Content-Range mismatch; expected {expected}")
    if "content-length" in headers and int(headers["content-length"]) != end - start + 1:
        raise ValueError("Content-Length disagrees with requested range")
    return headers


def acquire(args):
    if not 1 <= args.workers <= 8 or not 1 <= args.max_seconds <= 900:
        raise ValueError("workers must be 1..8; max-seconds must be 1..900")
    if args.expected_size < 1 or args.chunk_bytes < 1 or args.request_seconds < 1:
        raise ValueError("sizes and request duration must be positive")
    parsed = urllib.parse.urlparse(args.url)
    local_test = parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if parsed.scheme != "https" and not local_test:
        raise ValueError("HTTPS required except for loopback instrument tests")
    if args.etag.startswith("W/"):
        raise ValueError("weak ETags cannot identify byte-range objects")
    etag = args.etag if args.etag.startswith('"') else f'"{args.etag}"'
    source = {"url": args.url, "size": args.expected_size,
              "etag": etag, "last_modified": args.last_modified}
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(str(output) + ".part")
    state_path = Path(str(output) + ".download.json")
    logs = Path(str(output) + ".acquisition")
    logs.mkdir(exist_ok=True)
    lock_handle = Path(str(output) + ".lock").open("a")
    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    if output.exists():
        raise ValueError("final output already exists; it will not be overwritten")
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    script_bytes = Path(__file__).read_bytes()
    (logs / (run_id + "-downloader.py")).write_bytes(script_bytes)
    start_clock = time.monotonic()
    deadline = start_clock + args.max_seconds
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state.get("source") != source:
            raise ValueError("saved source identity differs from requested source")
        position = 0
        for segment in state["segments"]:
            if segment["start"] != position or segment["end"] < position:
                raise ValueError("saved segment layout has a gap or overlap")
            size = segment["end"] - segment["start"] + 1
            if not 0 <= segment["received"] <= size:
                raise ValueError("saved segment length is invalid")
            if segment["received"]:
                observed = hash_region(partial, position, segment["received"])
                if observed != segment["sha256"]:
                    raise ValueError("local partial data no longer matches recorded SHA-256")
            position = segment["end"] + 1
        if position != source["size"]:
            raise ValueError("saved segments do not cover the pinned object")
        if partial.stat().st_size > source["size"]:
            raise ValueError("partial file exceeds pinned object size")
    else:
        segments = []
        prefix = partial.stat().st_size if partial.exists() else 0
        if prefix > source["size"]:
            raise ValueError("existing partial file exceeds pinned object size")
        if prefix:
            if not args.adopt_prefix_headers:
                raise ValueError("existing unjournaled prefix requires --adopt-prefix-headers")
            raw_headers = args.adopt_prefix_headers.read_bytes()
            status, headers = parse_headers(raw_headers)
            validate_identity(headers, source)
            if status != 200 or int(headers.get("content-length", -1)) != source["size"]:
                raise ValueError("prefix headers do not establish a full-object 200 response")
            (logs / "adopted-prefix.headers").write_bytes(raw_headers)
            segments.append({"start": 0, "end": prefix - 1, "received": prefix,
                             "sha256": hash_region(partial, 0, prefix),
                             "origin": "adopted sequential prefix; supplied HTTP headers"})
        for position in range(prefix, source["size"], args.chunk_bytes):
            segments.append({"start": position, "end": min(position + args.chunk_bytes, source["size"]) - 1,
                             "received": 0, "sha256": None, "origin": "validated range"})
        partial.touch(exist_ok=True)
        state = {"schema": "rebase.reference-acquisition.v1", "source": source,
                 "created_at": utc_now(), "segments": segments, "runs": []}
    state["runs"].append({"id": run_id, "started_at": utc_now(), "workers": args.workers,
                           "http_version": args.http_version, "max_seconds": args.max_seconds,
                           "downloader_sha256": hashlib.sha256(script_bytes).hexdigest()})
    state["status"] = "running"
    save_json(state_path, state)
    mutex = threading.Lock()
    stop = threading.Event()
    errors = []
    fd = os.open(partial, os.O_WRONLY)

    def total_received():
        return sum(segment["received"] for segment in state["segments"])

    def worker(index):
        segment = state["segments"][index]
        attempts_without_progress = 0
        request_number = 0
        while segment["received"] < segment["end"] - segment["start"] + 1:
            remaining_time = deadline - time.monotonic()
            if stop.is_set() or remaining_time <= 1:
                return
            request_number += 1
            beginning = segment["start"] + segment["received"]
            basename = f"{run_id}-{index:05d}-{request_number:04d}-{beginning}"
            headers_path = logs / (basename + ".headers")
            body_path = logs / (basename + ".body.part")
            seconds = min(args.request_seconds, remaining_time)
            command = ["curl", "--http1.1" if args.http_version == "1.1" else "--http2",
                       "--location", "--silent", "--show-error",
                       "--proto", "=http,https" if local_test else "=https",
                       "--proto-redir", "=http,https" if local_test else "=https",
                       "--connect-timeout", str(min(15, seconds)), "--max-time", str(seconds),
                       "--range", f"{beginning}-{segment['end']}", "--header", f"If-Match: {source['etag']}",
                       "--header", "Accept-Encoding: identity", "--dump-header", str(headers_path),
                       "--output", str(body_path), "--write-out",
                       '{"http_code":%{http_code},"size_download":%{size_download},"time_total":%{time_total},"speed_download":%{speed_download}}',
                       args.url]
            try:
                result = subprocess.run(command, capture_output=True, text=True,
                                        timeout=seconds + 1, check=False)
                record = {"returncode": result.returncode, "stderr": result.stderr, "curl": result.stdout,
                          "range_start": beginning, "range_end": segment["end"], "finished_at": utc_now()}
                save_json(logs / (basename + ".json"), record)
                raw_headers = headers_path.read_bytes()
                if not raw_headers.strip():
                    raise RetryableTransferError(f"no response headers; curl exit {result.returncode}")
                status, _ = parse_headers(raw_headers)
                if status in (408, 429, 500, 502, 503, 504):
                    raise RetryableTransferError(f"transient HTTP status {status}")
                validate_range(raw_headers, source, beginning, segment["end"])
                body = body_path.read_bytes()
                if len(body) > segment["end"] - beginning + 1:
                    raise ValueError("response body exceeds requested range")
                if not body:
                    raise RetryableTransferError("range request returned no bytes")
                # Partial responses from interrupted transfers can be retained only
                # after their identity/range headers pass, with the exact byte count.
                written = 0
                while written < len(body):
                    count = os.pwrite(fd, body[written:], beginning + written)
                    if count <= 0:
                        raise OSError("pwrite made no progress")
                    written += count
                os.fsync(fd)
                with mutex:
                    segment["received"] += len(body)
                    segment["sha256"] = hash_region(partial, segment["start"], segment["received"])
                    segment["last_response_headers"] = str(headers_path)
                    save_json(state_path, state)
                body_path.unlink()
                attempts_without_progress = 0
            except (OSError, ValueError, RetryableTransferError, subprocess.TimeoutExpired) as exc:
                attempts_without_progress += 1
                with mutex:
                    errors.append({"segment": index, "error": str(exc), "at": utc_now()})
                if isinstance(exc, ValueError):
                    stop.set()  # Identity/format failures must not be retried as trusted data.
                    return
                if attempts_without_progress >= 3:
                    stop.set()
                    return

    pending = [i for i, segment in enumerate(state["segments"])
               if segment["received"] < segment["end"] - segment["start"] + 1]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(worker, index) for index in pending]
            active = set(futures)
            while active:
                _, active = concurrent.futures.wait(active, timeout=min(20, max(0.1, deadline - time.monotonic())))
                if time.monotonic() >= deadline:
                    stop.set()
                with mutex:
                    print(json.dumps({"status": "progress", "received_bytes": total_received(),
                                      "expected_bytes": source["size"], "elapsed_seconds": round(time.monotonic() - start_clock, 2)}), flush=True)
                if stop.is_set():
                    for future in active:
                        future.cancel()
            for future in futures:
                if not future.cancelled():
                    future.result()
    finally:
        os.close(fd)
    completed = total_received() == source["size"]
    state["runs"][-1].update({"finished_at": utc_now(), "elapsed_seconds": round(time.monotonic() - start_clock, 3),
                              "errors": errors, "received_bytes": total_received()})
    if completed:
        if partial.stat().st_size != source["size"]:
            raise ValueError("complete segment coverage does not match final file size")
        digest = hash_region(partial, 0, source["size"])
        state["status"] = "complete"
        state["sha256"] = digest
        save_json(state_path, state)
        os.replace(partial, output)
        provenance = {"schema": state["schema"], "source": source, "acquired_at": utc_now(),
                      "path": str(output), "bytes": source["size"], "sha256": digest,
                      "checks": ["HTTP 206 Content-Range", "strong ETag with If-Match", "exact byte coverage", "exact final size"],
                      "checksum_scope": "Locally computed custody fingerprint; no publisher SHA-256 was supplied.",
                      "state_path": str(state_path), "headers_directory": str(logs)}
        save_json(Path(str(output) + ".provenance.json"), provenance)
        return {"status": "complete", "path": str(output), "sha256": digest, "bytes": source["size"]}, 0
    state["status"] = "error" if errors and stop.is_set() and time.monotonic() < deadline else "partial"
    save_json(state_path, state)
    return {"status": state["status"], "partial_path": str(partial), "state_path": str(state_path),
            "received_bytes": total_received(), "expected_bytes": source["size"], "errors": errors[-3:]}, 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-size", type=int, required=True)
    parser.add_argument("--etag", required=True)
    parser.add_argument("--last-modified")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--http-version", choices=("1.1", "2"), default="1.1")
    parser.add_argument("--chunk-bytes", type=int, default=4 * 1024 * 1024)
    parser.add_argument("--max-seconds", type=float, default=900)
    parser.add_argument("--request-seconds", type=float, default=90)
    parser.add_argument("--adopt-prefix-headers", type=Path)
    args = parser.parse_args()
    try:
        result, code = acquire(args)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        result, code = {"status": "error", "error": str(exc)}, 2
    print(json.dumps(result, sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
