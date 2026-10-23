#!/usr/bin/env python3
"""Independent, zero-tolerance oracle for the three pinned APP001 PCM16 assets.

Reads the saved project and source WAVs without importing application code.
Scope: 48 kHz stereo, centered/unmuted/non-solo tracks, gain, placement, and
source-frame-aligned trims. No resampling, pan law, effects, or format inference.
Exit 0 means exact sample/payload match, 1 mismatch, 2 rejected/invalid input.
"""
from __future__ import annotations

import argparse
from array import array
import datetime
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import platform
import struct
import sys
import uuid
import wave

from audio_probe import WaveError, read_wave


RATE = 48_000
MAX_FRAMES = RATE * 60
KNOWN_SOURCES = {
    "8fceb6cd8e474bc18d39f72dac2131737994c02fb4b3d8aa9b41ba4c5b578ad9": "Pulse",
    "785fbf196cac9cfac2bcfcf5b6c327425373db28584bd9e34c136c252eebd047": "Low Orbit",
    "9e8e234918695063082bd7ce5ec6e2d76decb89e8ee2164687a26826a3e413c1": "Glass Keys",
}
F32 = struct.Struct("<f")
SCOPE = "Self-authored APP001 application export only; no Cubase reference or whole-application equivalence claim."


class OutOfScope(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise OutOfScope(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def f32(value):
    return F32.unpack(F32.pack(value))[0]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def fields(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected.split()), f"Unsupported {label} fields")


def number(value, label, low, high):
    require(type(value) in (float, int) and math.isfinite(value) and low <= value <= high,
            f"{label} must be a finite number in [{low}, {high}]")
    return float(value)


def frame_position(seconds, label, exact=False):
    value = number(seconds, label, 0, 60) * RATE
    if exact:
        require(value.is_integer(), f"{label} must land exactly on a source frame; interpolation is outside scope")
    # All times are nonnegative; halfway cases round away from zero.
    return math.floor(value + 0.5)


def decode_source(path):
    raw = path.read_bytes()
    digest = sha(raw)
    require(digest in KNOWN_SOURCES, f"Not a pinned APP001 source: {path}")
    with wave.open(io.BytesIO(raw), "rb") as source:
        require((source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype())
                == (2, 2, RATE, "NONE"), "Only uncompressed 48 kHz stereo PCM16 sources are supported")
        frames = source.getnframes()
        require(frames == 12 * RATE, "Pinned APP001 source must contain exactly 12 seconds")
        pcm = source.readframes(frames)
        require(len(pcm) == frames * 4, "Source PCM16 payload is truncated")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples, {"path": str(path), "fixture": KNOWN_SOURCES[digest], "file_sha256": digest,
                     "pcm16_payload_sha256": sha(pcm), "frames": frames, "rate": RATE, "channels": 2}


def expected_mix(project_path):
    manifest = project_path / "Project.json" if project_path.is_dir() else project_path
    root = manifest.parent.resolve()
    raw = manifest.read_bytes()
    require(len(raw) <= 1024 * 1024, "Project manifest exceeds the 1 MiB oracle bound")
    project = json.loads(raw, object_pairs_hook=unique_object)
    fields(project, "id name sampleRate tempo tracks", "project")
    uuid.UUID(project["id"])
    require(isinstance(project["name"], str), "Project name must be text")
    require(number(project["sampleRate"], "sampleRate", RATE, RATE) == RATE, "48 kHz project required")
    number(project["tempo"], "tempo", 20, 400)
    require(isinstance(project["tracks"], list) and 1 <= len(project["tracks"]) <= 16, "Expected 1–16 tracks")
    tracks_seen, clips_seen, sources, prepared = set(), set(), {}, []
    total_frames = 0
    for track_index, track in enumerate(project["tracks"]):
        fields(track, "id name gainDB pan isMuted isSolo clips", "track")
        track_id = uuid.UUID(track["id"])
        require(track_id not in tracks_seen, "Duplicate track identifier")
        tracks_seen.add(track_id)
        require(isinstance(track["name"], str), "Track name must be text")
        require(track["isMuted"] is False and track["isSolo"] is False, "Mute/solo routing is outside this oracle's scope")
        require(number(track["pan"], "pan", 0, 0) == 0, "Only exact center pan is supported")
        gain = number(track["gainDB"], "gainDB", -96, 24)
        amplitude = math.pow(10.0, gain / 20.0)
        require(isinstance(track["clips"], list), "Track clips must be a list")
        for clip_index, clip in enumerate(track["clips"]):
            fields(clip, "id name mediaPath position sourceOffset duration", "clip")
            clip_id = uuid.UUID(clip["id"])
            require(clip_id not in clips_seen and len(clips_seen) < 64, "Duplicate clip identifier or more than 64 clips")
            clips_seen.add(clip_id)
            require(isinstance(clip["name"], str), "Clip name must be text")
            media = clip["mediaPath"]
            require(isinstance(media, str) and "\\" not in media and "\0" not in media, "Unsupported media path")
            parts = media.split("/")
            require(len(parts) >= 2 and parts[0] == "Media" and not any(p in ("", ".", "..") for p in parts), "Media must be a relative path inside Media/")
            candidate = root / PurePosixPath(media)
            require(candidate.resolve() == candidate and candidate.is_file(), "Symlinked or missing media is outside scope")
            if candidate not in sources:
                sources[candidate] = decode_source(candidate)
            samples, info = sources[candidate]
            start = frame_position(clip["position"], "position")
            offset = frame_position(clip["sourceOffset"], "sourceOffset", exact=True)
            frames = frame_position(clip["duration"], "duration")
            require(frames > 0 and offset + frames <= info["frames"], "Clip interval must be nonempty and inside its source")
            require(start + frames <= MAX_FRAMES, "Oracle timeline is bounded to 60 seconds")
            total_frames = max(total_frames, start + frames)
            prepared.append({"track_index": track_index, "clip_index": clip_index, "track_name": track["name"],
                             "clip_id": clip["id"], "source_path": str(candidate), "gain_db": gain,
                             "gain_binary64": amplitude.hex(), "start_frame": start,
                             "source_offset_frame": offset, "frames": frames,
                             "source_samples": samples, "amplitude": amplitude})
    require(total_frames > 0, "No nonempty clips to verify")
    require(sum(c["frames"] for c in prepared) <= RATE * 120, "Oracle prepared-source bound is 120 seconds")
    output = array("f", [0.0]) * (2 * total_frames)
    for clip in prepared:
        start, offset, count = clip["start_frame"], clip["source_offset_frame"], clip["frames"]
        source, amplitude = clip["source_samples"], clip["amplitude"]
        for sample in range(count * 2):
            gained = f32((source[offset * 2 + sample] / 32768.0) * amplitude)
            index = start * 2 + sample
            output[index] = f32(output[index] + gained)
    metadata = {"manifest_path": str(manifest.resolve()), "manifest_sha256": sha(raw),
                "name": project["name"], "sample_rate_hz": RATE, "channels": 2, "frames": total_frames,
                "sources": [v[1] for v in sources.values()],
                "ordered_clips": [{k: v for k, v in c.items() if k not in ("source_samples", "amplitude")} for c in prepared]}
    return output, metadata


def verify(project_path, export_path):
    expected, project = expected_mix(project_path)
    before = export_path.stat()
    actual = read_wave(export_path)
    after = export_path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), "Export changed while reading")
    require(actual.format_tag == 3 and actual.bits == 32 and actual.encoding == "ieee_float",
            "Only the application's plain IEEE float32 RIFF export is in scope")
    mismatches = []
    for field, want, got in (("sample_rate_hz", RATE, actual.rate), ("channels", 2, actual.channels),
                             ("frames", project["frames"], actual.frames)):
        if want != got:
            mismatches.append({"field": field, "expected": want, "actual": got})
    per_channel = []
    if not mismatches:
        for channel in range(2):
            different, zero_sign_differences, peak, squared, first, peak_frame = 0, 0, 0.0, 0.0, None, None
            for frame, got in enumerate(actual.samples[channel]):
                want = expected[frame * 2 + channel]
                delta = got - want
                if delta != 0:
                    different += 1
                    if first is None:
                        first = {"frame": frame, "seconds": frame / RATE, "expected": want, "actual": got, "residual": delta}
                    if abs(delta) > peak:
                        peak, peak_frame = abs(delta), frame
                    squared += delta * delta
                elif want == 0 and math.copysign(1, want) != math.copysign(1, got):
                    zero_sign_differences += 1
            per_channel.append({"channel_index": channel, "numeric_samples_different": different,
                                "zero_sign_bit_differences": zero_sign_differences,
                                "first_numeric_difference": first, "peak_absolute_residual": peak,
                                "peak_residual_frame": peak_frame, "rms_residual": math.sqrt(squared / actual.frames)})
    if sys.byteorder != "little":
        expected.byteswap()
    expected_hash = sha(expected.tobytes())
    exact_payload = expected_hash == actual.data_sha256
    exact_numeric = not mismatches and all(c["numeric_samples_different"] == 0 for c in per_channel)
    return {"status": "pass" if exact_payload and exact_numeric else "mismatch", "project": project,
            "export": actual.metadata(), "expected_interleaved_float32_payload_sha256": expected_hash,
            "structural_mismatches": mismatches, "per_channel": per_channel,
            "decoded_samples_equal": exact_numeric, "audio_payload_bytes_equal": exact_payload,
            "whole_file_equality_claimed": False,
            "policy": {"gain": "round_binary32((signed_PCM16 / 32768) * pow_binary64(10, gainDB / 20))",
                       "accumulation": "round_binary32(previous_sum + gained_sample), in saved project track order then clip order",
                       "placement_and_duration": "Nearest 48 kHz frame; nonnegative halfway values round away from zero",
                       "source_offset": "Must map exactly to an integer source frame",
                       "tolerance_peak": 0.0, "tolerance_rms": 0.0,
                       "transformations_to_export": [], "source_fixture_identity": "Pinned whole-file SHA256 whitelist"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path, help="Saved .rebaseproj directory or Project.json")
    parser.add_argument("--export", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New JSON evidence path; existing files are never replaced")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new evidence path")
    report = {"schema": "rebase.app001-export-oracle.v1", "scope": SCOPE,
              "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "oracle_sha256": sha(Path(__file__).read_bytes()),
              "wave_reader_sha256": sha(Path(__file__).with_name("audio_probe.py").read_bytes()),
              "python": platform.python_version(),
              "invocation": {"project": str(args.project.resolve()), "export": str(args.export.resolve())}}
    try:
        report.update(verify(args.project, args.export))
        code = 0 if report["status"] == "pass" else 1
    except (OutOfScope, WaveError, wave.Error, ValueError, TypeError, KeyError, OSError, OverflowError) as error:
        report.update(status="rejected", error=str(error), error_type=type(error).__name__)
        code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output.resolve()),
                      "decoded_samples_equal": report.get("decoded_samples_equal"),
                      "audio_payload_bytes_equal": report.get("audio_payload_bytes_equal"),
                      "error": report.get("error")}))
    return code


if __name__ == "__main__":
    sys.exit(main())
