#!/usr/bin/env python3
"""Deterministic WAV stimuli and absolute-position comparisons; stdlib only.

This is a short-capture research instrument, not an application equivalence test.
Samples are decoded to full-scale-normalized doubles. No alignment, gain fitting,
resampling, channel permutation, cropping, or silence removal is performed.
"""

from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import sys


SCHEMA = "rebase.audio-probe.v1"
RATE = 48_000
PCM24_SCALE = 1 << 23
GENERATION_SCOPE = "Synthetic instrument evidence only; no Cubase equivalence conclusion."
COMPARISON_SCOPE = (
    "Numerical sample-comparison evidence only; no input provenance, protocol "
    "conformance or Cubase equivalence conclusion is inferred."
)
# Fixed integer tables avoid platform-dependent sine/libm generation differences.
SINE48 = (
    0, 4277, 8481, 12540, 16384, 19948, 23170, 25997, 28378, 30274, 31651,
    32488, 32767, 32488, 31651, 30274, 28378, 25997, 23170, 19948, 16384,
    12540, 8481, 4277, 0, -4277, -8481, -12540, -16384, -19948, -23170,
    -25997, -28378, -30274, -31651, -32488, -32767, -32488, -31651,
    -30274, -28378, -25997, -23170, -19948, -16384, -12540, -8481, -4277,
)
SINE32 = (
    0, 6393, 12540, 18205, 23170, 27245, 30274, 32138, 32767, 32138,
    30274, 27245, 23170, 18205, 12540, 6393, 0, -6393, -12540, -18205,
    -23170, -27245, -30274, -32138, -32767, -32138, -30274, -27245,
    -23170, -18205, -12540, -6393,
)


class WaveError(ValueError):
    """An unsupported or malformed input cannot produce a passing comparison."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def riff_chunk(name: bytes, payload: bytes) -> bytes:
    return name + struct.pack("<I", len(payload)) + payload + b"\0" * (len(payload) % 2)


@dataclass
class Wave:
    path: str
    file_sha256: str
    data_sha256: str
    format_tag: int
    encoding: str
    bits: int
    rate: int
    channel_mask: int | None
    samples: list[array]
    chunks: list[dict]

    @property
    def channels(self) -> int:
        return len(self.samples)

    @property
    def frames(self) -> int:
        return len(self.samples[0])

    def metadata(self) -> dict:
        return {
            "path": self.path,
            "file_sha256": self.file_sha256,
            "data_sha256": self.data_sha256,
            "format_tag": self.format_tag,
            "encoding": self.encoding,
            "bits_per_sample": self.bits,
            "sample_rate_hz": self.rate,
            "channels": self.channels,
            "channel_mask": self.channel_mask,
            "frames": self.frames,
            "duration_seconds": self.frames / self.rate,
            "chunks": self.chunks,
        }


def read_wave(path: Path | str) -> Wave:
    """Read RIFF WAVE PCM16/24/32 or float32/64, including full-width extensible.

    RF64, RIFX, compressed formats, reduced valid-bit widths, duplicate audio/fmt
    chunks and inconsistent sizes are rejected. Ancillary chunks are retained in
    the metadata inventory but are not interpreted as audio. Loads the capture
    into memory; intended for bounded probes rather than long multitrack sessions.
    """
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise WaveError(f"{path}: expected a little-endian RIFF WAVE file")
    if struct.unpack_from("<I", raw, 4)[0] + 8 != len(raw):
        raise WaveError(f"{path}: RIFF size does not match actual file length")
    fmt = data = fact = None
    chunks = []
    offset = 12
    while offset < len(raw):
        if len(raw) - offset < 8:
            raise WaveError(f"{path}: truncated chunk header")
        name, size = struct.unpack_from("<4sI", raw, offset)
        start = offset + 8
        end = start + size
        padded_end = end + (size % 2)
        if padded_end > len(raw):
            raise WaveError(f"{path}: truncated chunk or missing padding")
        chunk = raw[start:end]
        chunks.append({"id_hex": name.hex(), "size_bytes": size})
        if name == b"fmt ":
            if fmt is not None:
                raise WaveError(f"{path}: duplicate fmt chunk")
            fmt = chunk
        elif name == b"data":
            if data is not None:
                raise WaveError(f"{path}: multiple data chunks are unsupported")
            data = chunk
        elif name == b"fact":
            if fact is not None or len(chunk) < 4:
                raise WaveError(f"{path}: duplicate or truncated fact chunk")
            fact = struct.unpack_from("<I", chunk)[0]
        offset = padded_end
    if fmt is None or data is None or len(fmt) < 16:
        raise WaveError(f"{path}: missing or truncated fmt/data chunk")
    tag, channels, rate, byte_rate, block_align, bits = struct.unpack_from("<HHIIHH", fmt)
    original_tag = tag
    channel_mask = None
    if tag == 0xFFFE:
        if len(fmt) != 40 or struct.unpack_from("<H", fmt, 16)[0] != 22:
            raise WaveError(f"{path}: unsupported extensible fmt length")
        valid_bits, channel_mask = struct.unpack_from("<HI", fmt, 18)
        if valid_bits != bits:
            raise WaveError(f"{path}: reduced valid-bit widths are unsupported")
        guid = fmt[24:40]
        if guid[4:] != bytes.fromhex("00001000800000aa00389b71"):
            raise WaveError(f"{path}: unsupported extensible subformat GUID")
        tag = struct.unpack_from("<I", guid)[0]
        if channel_mask and channel_mask.bit_count() != channels:
            raise WaveError(f"{path}: channel mask does not match channel count")
    elif len(fmt) != 16 and not (len(fmt) == 18 and fmt[16:] == b"\0\0"):
        raise WaveError(f"{path}: unsupported fmt extension")
    if not ((tag == 1 and bits in (16, 24, 32)) or (tag == 3 and bits in (32, 64))):
        raise WaveError(f"{path}: unsupported encoding tag={tag}, bits={bits}")
    width = bits // 8
    if channels < 1 or rate < 1 or block_align != channels * width:
        raise WaveError(f"{path}: invalid channels, sample rate or block alignment")
    if byte_rate != rate * block_align:
        raise WaveError(f"{path}: inconsistent byte rate")
    if len(data) % block_align:
        raise WaveError(f"{path}: data ends inside a sample frame")
    frames = len(data) // block_align
    if frames == 0:
        raise WaveError(f"{path}: an empty capture is not a valid probe")
    if fact is not None and fact != frames:
        raise WaveError(f"{path}: fact sample count disagrees with data length")
    samples = [array("d") for _ in range(channels)]
    if tag == 1:
        scale = 1 << (bits - 1)
        for index, pos in enumerate(range(0, len(data), width)):
            value = int.from_bytes(data[pos:pos + width], "little", signed=True) / scale
            samples[index % channels].append(value)
    else:
        code = "<f" if bits == 32 else "<d"
        for index, (value,) in enumerate(struct.iter_unpack(code, data)):
            if not math.isfinite(value):
                raise WaveError(f"{path}: non-finite sample at frame {index // channels}, channel {index % channels}")
            samples[index % channels].append(value)
    return Wave(str(path), sha256(raw), sha256(data), original_tag,
                "pcm_signed" if tag == 1 else "ieee_float", bits, rate,
                channel_mask, samples, chunks)


def _residual(reference: array, candidate: array, rate: int) -> dict:
    peak = 0.0
    scaled_sum = 0.0
    first = peak_frame = None
    differences = 0
    for frame, (expected, actual) in enumerate(zip(reference, candidate)):
        delta = actual - expected
        if not math.isfinite(delta):
            raise WaveError("residual exceeds finite numeric range")
        magnitude = abs(delta)
        if magnitude:
            differences += 1
            if first is None:
                first = frame
            if magnitude > peak:
                scaled_sum = 1.0 + scaled_sum * (peak / magnitude) ** 2
                peak = magnitude
                peak_frame = frame
            else:
                scaled_sum += (magnitude / peak) ** 2
    rms = peak * math.sqrt(scaled_sum / len(reference)) if peak else 0.0
    return {
        "samples_different": differences,
        "first_different_frame": first,
        "first_different_seconds": first / rate if first is not None else None,
        "peak_absolute_residual": peak,
        "peak_residual_frame": peak_frame,
        "peak_residual_seconds": peak_frame / rate if peak_frame is not None else None,
        "rms_residual": rms,
        "reference_peak_absolute": max(abs(v) for v in reference),
        "candidate_peak_absolute": max(abs(v) for v in candidate),
    }


def compare(reference_path: Path | str, candidate_path: Path | str,
            peak_tolerance: float = 0.0, rms_tolerance: float = 0.0) -> dict:
    for name, value in (("peak", peak_tolerance), ("rms", rms_tolerance)):
        if not math.isfinite(value) or value < 0:
            raise WaveError(f"{name} tolerance must be finite and non-negative")
    reference = read_wave(reference_path)
    candidate = read_wave(candidate_path)
    issues = []
    for name in ("rate", "channels", "frames"):
        if getattr(reference, name) != getattr(candidate, name):
            issues.append({"field": name, "reference": getattr(reference, name),
                           "candidate": getattr(candidate, name)})
    if reference.channel_mask and candidate.channel_mask and reference.channel_mask != candidate.channel_mask:
        issues.append({"field": "channel_mask", "reference": reference.channel_mask,
                       "candidate": candidate.channel_mask})
    per_channel = []
    if not issues:
        for channel, (expected, actual) in enumerate(zip(reference.samples, candidate.samples)):
            result = _residual(expected, actual, reference.rate)
            result["channel_index"] = channel
            result["within_tolerance"] = (result["peak_absolute_residual"] <= peak_tolerance
                                          and result["rms_residual"] <= rms_tolerance)
            per_channel.append(result)
    passed = not issues and all(c["within_tolerance"] for c in per_channel)
    return {
        "schema": SCHEMA,
        "scope": COMPARISON_SCOPE,
        "status": "pass" if passed else "mismatch",
        "reference": reference.metadata(),
        "candidate": candidate.metadata(),
        "tolerances": {"units": "full_scale_normalized_sample_amplitude",
                       "peak_absolute": peak_tolerance, "rms": rms_tolerance,
                       "rule": "Both limits must hold separately for every channel; shape must match."},
        "transformations_applied": [],
        "file_bytes_equal": reference.file_sha256 == candidate.file_sha256,
        "audio_payload_bytes_equal": reference.data_sha256 == candidate.data_sha256,
        "decoded_samples_equal": (not issues and all(c["samples_different"] == 0 for c in per_channel)),
        "structural_mismatches": issues,
        "channel_layout_check": ("both_declared" if reference.channel_mask and candidate.channel_mask
                                 else "at_least_one_unspecified; compared_in_stored_channel_order"),
        "per_channel": per_channel,
    }


def _xorshift32(value: int) -> int:
    value ^= (value << 13) & 0xFFFFFFFF
    value ^= value >> 17
    value ^= (value << 5) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def generate(directory: Path | str) -> dict:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    wav_path = directory / "probe-48k-stereo-pcm24.wav"
    manifest_path = directory / "manifest.json"
    if wav_path.exists() or manifest_path.exists():
        raise WaveError("output already exists; choose a new directory to preserve evidence")
    amplitude = 1 << 21
    seeds = [0x13579BDF, 0x2468ACE1]
    states = seeds.copy()
    payload = bytearray()
    for frame in range(6 * RATE):
        section, local = divmod(frame, RATE)
        left = right = 0
        if section == 1:
            left = {13: amplitude, 47000: -amplitude // 4}.get(local, 0)
            right = {203: -amplitude // 2, 47000: amplitude // 8}.get(local, 0)
        elif section == 2:
            left = -amplitude + (2 * amplitude * local) // (RATE - 1)
            right = amplitude // 2 - (amplitude * local) // (RATE - 1)
        elif section == 3:
            left, right = SINE48[local % 48] * 32, SINE32[local % 32] * 32
        elif section == 4:
            states = [_xorshift32(state) for state in states]
            left, right = [(state & 0x1FFFFF) - (1 << 20) for state in states]
        payload.extend(left.to_bytes(3, "little", signed=True))
        payload.extend(right.to_bytes(3, "little", signed=True))
    fmt = struct.pack("<HHIIHH", 1, 2, RATE, RATE * 6, 6, 24)
    body = b"WAVE" + riff_chunk(b"fmt ", fmt) + riff_chunk(b"data", bytes(payload))
    wav = b"RIFF" + struct.pack("<I", len(body)) + body
    manifest = {
        "schema": SCHEMA,
        "scope": GENERATION_SCOPE,
        "generator_sha256": sha256(Path(__file__).read_bytes()),
        "file": wav_path.name,
        "file_sha256": sha256(wav),
        "audio_payload_sha256": sha256(payload),
        "encoding": "signed PCM24 little-endian",
        "sample_rate_hz": RATE,
        "channels": 2,
        "frames": 6 * RATE,
        "maximum_absolute_amplitude": 0.25,
        "sample_zero": "first stored frame; no pre-roll or automatic trimming",
        "noise": {"algorithm": "xorshift32 shifts 13,17,5; low21bits minus 2^20",
                  "channel_seeds": seeds},
        "segments": [
            {"name": name, "start_frame": i * RATE, "end_frame_exclusive": (i + 1) * RATE}
            for i, name in enumerate(("silence", "channel_distinct_impulses", "opposing_ramps",
                                      "integer_table_tones_L1000Hz_R1500Hz", "seeded_noise", "silence"))
        ],
    }
    encoded_manifest = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with wav_path.open("xb") as handle:
        handle.write(wav)
    with manifest_path.open("xb") as handle:
        handle.write(encoded_manifest)
    return {"schema": SCHEMA, "status": "generated", "scope": GENERATION_SCOPE,
            "wave_path": str(wav_path), "manifest_path": str(manifest_path),
            "file_sha256": sha256(wav), "manifest_sha256": sha256(encoded_manifest)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    generator = subcommands.add_parser("generate", help="Create a fresh six-second PCM24 probe and SHA manifest")
    generator.add_argument("output_directory", type=Path)
    comparator = subcommands.add_parser("compare", help="Compare stored samples at absolute frame positions")
    comparator.add_argument("reference", type=Path)
    comparator.add_argument("candidate", type=Path)
    comparator.add_argument("--peak-tolerance", type=float, default=0.0,
                            help="Maximum normalized absolute error; default 0. Both limits must pass.")
    comparator.add_argument("--rms-tolerance", type=float, default=0.0,
                            help="Maximum per-channel normalized RMS error; default 0. Both limits must pass.")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate(args.output_directory)
        else:
            result = compare(args.reference, args.candidate, args.peak_tolerance, args.rms_tolerance)
        code = 1 if result["status"] == "mismatch" else 0
    except (OSError, WaveError) as exc:
        scope = GENERATION_SCOPE if args.command == "generate" else COMPARISON_SCOPE
        result = {"schema": SCHEMA, "status": "error", "scope": scope, "error": str(exc)}
        code = 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
