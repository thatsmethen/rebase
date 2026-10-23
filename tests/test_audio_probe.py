"""Independent small WAV fixtures and injected defects test the instrument only."""

import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audio_probe.py"
spec = importlib.util.spec_from_file_location("audio_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def chunk(name, data):
    return name + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")


def wave_bytes(frames, bits=24, tag=1, rate=48000, extra=b"", extensible=False, mask=3):
    channels = len(frames[0])
    width = bits // 8
    if tag == 1:
        scale = 1 << (bits - 1)
        data = b"".join(int(value * scale).to_bytes(width, "little", signed=True)
                        for frame in frames for value in frame)
    else:
        data = b"".join(struct.pack("<f" if bits == 32 else "<d", value)
                        for frame in frames for value in frame)
    fmt = struct.pack("<HHIIHH", 0xFFFE if extensible else tag, channels,
                      rate, rate * width * channels, width * channels, bits)
    if extensible:
        fmt += struct.pack("<HHII", 22, bits, mask, tag) + bytes.fromhex("00001000800000aa00389b71")
    body = b"WAVE" + chunk(b"fmt ", fmt) + extra + chunk(b"data", data)
    return b"RIFF" + struct.pack("<I", len(body)) + body


class AudioProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.frames = [(0.0, 0.0), (0.25, 0.0), (0.0, -0.125), (0.125, 0.0625), (0.0, 0.0)]

    def write(self, name, frames=None, **kwargs):
        path = self.directory / name
        path.write_bytes(wave_bytes(self.frames if frames is None else frames, **kwargs))
        return path

    def test_self_control_and_metadata_only_difference(self):
        reference = self.write("reference.wav")
        self.assertTrue(probe.compare(reference, reference)["file_bytes_equal"])
        candidate = self.write("metadata.wav", extra=chunk(b"JUNK", b"abc"))
        report = probe.compare(reference, candidate)
        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["file_bytes_equal"])
        self.assertTrue(report["audio_payload_bytes_equal"])
        self.assertTrue(report["decoded_samples_equal"])

    def test_supported_encodings_and_extensible(self):
        reference = self.write("reference.wav", bits=16)
        for tag, bits in ((1, 16), (1, 24), (1, 32), (3, 32), (3, 64)):
            for extensible in (False, True):
                with self.subTest(tag=tag, bits=bits, extensible=extensible):
                    candidate = self.write("candidate.wav", tag=tag, bits=bits, extensible=extensible)
                    self.assertEqual(probe.compare(reference, candidate)["status"], "pass")

    def test_one_sample_delay_is_not_aligned_away(self):
        reference = self.write("reference.wav")
        delayed = self.write("delayed.wav", [(0, 0)] + self.frames[:-1])
        report = probe.compare(reference, delayed)
        self.assertEqual(report["status"], "mismatch")
        self.assertEqual(report["transformations_applied"], [])
        self.assertEqual(report["per_channel"][0]["first_different_frame"], 1)
        self.assertEqual(report["per_channel"][0]["first_different_seconds"], 1 / 48000)

    def test_swapped_channels_and_gain_are_detected(self):
        reference = self.write("reference.wav")
        for name, frames in (("swap", [tuple(reversed(frame)) for frame in self.frames]),
                             ("gain", [tuple(v * 0.5 for v in frame) for frame in self.frames])):
            with self.subTest(defect=name):
                report = probe.compare(reference, self.write(name + ".wav", frames))
                self.assertEqual(report["status"], "mismatch")
                self.assertFalse(report["decoded_samples_equal"])

    def test_shape_mismatches_cannot_be_hidden_by_large_tolerance(self):
        reference = self.write("reference.wav")
        cases = (("truncate", self.frames[:-1], {}, "frames"),
                 ("rate", self.frames, {"rate": 44100}, "rate"),
                 ("mono", [(f[0],) for f in self.frames], {}, "channels"))
        for name, frames, kwargs, field in cases:
            with self.subTest(defect=name):
                report = probe.compare(reference, self.write(name + ".wav", frames, **kwargs), 100, 100)
                self.assertEqual(report["status"], "mismatch")
                self.assertEqual(report["structural_mismatches"][0]["field"], field)
                self.assertEqual(report["per_channel"], [])

    def test_tolerances_and_residual_units_have_known_answers(self):
        reference = self.write("reference.wav", [(0.0,)] * 4)
        candidate = self.write("candidate.wav", [(0.25,), (0.0,), (0.0,), (0.0,)])
        report = probe.compare(reference, candidate, 0.25, 0.125)
        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["decoded_samples_equal"])
        self.assertEqual(report["per_channel"][0]["peak_absolute_residual"], 0.25)
        self.assertEqual(report["per_channel"][0]["rms_residual"], 0.125)
        self.assertEqual(probe.compare(reference, candidate, 0.249, 1)["status"], "mismatch")
        self.assertEqual(probe.compare(reference, candidate, 1, 0.124)["status"], "mismatch")
        for value in (-1, math.nan, math.inf):
            with self.subTest(tolerance=value), self.assertRaises(probe.WaveError):
                probe.compare(reference, candidate, value, 0)

    def test_nonfinite_float_samples_rejected(self):
        for bits in (32, 64):
            for value in (math.nan, math.inf, -math.inf):
                with self.subTest(bits=bits, value=value), self.assertRaises(probe.WaveError):
                    probe.read_wave(self.write("invalid.wav", [(value,)], tag=3, bits=bits))

    def test_malformed_and_unsupported_files_fail_closed(self):
        valid = wave_bytes(self.frames)
        inconsistent_rate = bytearray(valid)
        struct.pack_into("<I", inconsistent_rate, 28, 1)
        invalid_frame = valid[:-1]
        invalid_frame = invalid_frame[:4] + struct.pack("<I", len(invalid_frame) - 8) + invalid_frame[8:]
        unsupported_tag = bytearray(valid)
        struct.pack_into("<H", unsupported_tag, 20, 6)
        reduced_bits = bytearray(wave_bytes(self.frames, extensible=True))
        struct.pack_into("<H", reduced_bits, 38, 20)
        for name, data in (("short", b"RIFF"), ("riff_size", valid[:-1]),
                           ("trailing", valid + b"x"), ("byte_rate", inconsistent_rate),
                           ("chunk_size", invalid_frame), ("codec", unsupported_tag),
                           ("valid_bits", reduced_bits)):
            with self.subTest(defect=name), self.assertRaises(probe.WaveError):
                path = self.directory / "invalid.wav"
                path.write_bytes(data)
                probe.read_wave(path)

    def test_chunk_structure_and_fact_count_are_validated(self):
        fmt = struct.pack("<HHIIHH", 1, 2, 48000, 288000, 6, 24)
        cases = {
            "partial_frame": chunk(b"fmt ", fmt) + chunk(b"data", b"\0" * 5),
            "duplicate_data": chunk(b"fmt ", fmt) + 2 * chunk(b"data", b"\0" * 6),
            "duplicate_fmt": 2 * chunk(b"fmt ", fmt) + chunk(b"data", b"\0" * 6),
            "empty": chunk(b"fmt ", fmt) + chunk(b"data", b""),
            "missing_fmt": chunk(b"data", b"\0" * 6),
            "missing_data": chunk(b"fmt ", fmt),
            "wrong_fact_count": (chunk(b"fmt ", fmt) + chunk(b"fact", struct.pack("<I", 2))
                                 + chunk(b"data", b"\0" * 6)),
        }
        for name, chunks in cases.items():
            with self.subTest(defect=name), self.assertRaises(probe.WaveError):
                body = b"WAVE" + chunks
                path = self.directory / "invalid.wav"
                path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
                probe.read_wave(path)

    def test_declared_channel_layout_conflict_is_not_ignored(self):
        reference = self.write("reference.wav", extensible=True, mask=3)
        candidate = self.write("candidate.wav", extensible=True, mask=12)
        report = probe.compare(reference, candidate)
        self.assertEqual(report["status"], "mismatch")
        self.assertEqual(report["structural_mismatches"][0]["field"], "channel_mask")

    def test_float_headroom_is_preserved_and_numeric_overflow_fails_closed(self):
        reference = self.write("reference.wav", [(2.0,)], tag=3, bits=64)
        self.assertEqual(probe.compare(reference, reference)["status"], "pass")
        self.assertEqual(probe.read_wave(reference).samples[0][0], 2.0)
        reference = self.write("reference.wav", [(1e308,)], tag=3, bits=64)
        candidate = self.write("candidate.wav", [(-1e308,)], tag=3, bits=64)
        with self.assertRaises(probe.WaveError):
            probe.compare(reference, candidate)

    def test_integer_extremes_are_decoded_without_sign_or_scale_errors(self):
        for bits in (16, 24, 32):
            with self.subTest(bits=bits):
                maximum = ((1 << (bits - 1)) - 1) / (1 << (bits - 1))
                samples = probe.read_wave(self.write("extremes.wav", [(-1.0,), (maximum,)], bits=bits)).samples[0]
                self.assertEqual(list(samples), [-1.0, maximum])

    def test_generation_hashes_determinism_boundaries_and_no_overwrite(self):
        first = probe.generate(self.directory / "first")
        second = probe.generate(self.directory / "second")
        self.assertEqual(first["file_sha256"], second["file_sha256"])
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        manifest = json.loads(Path(first["manifest_path"]).read_text())
        self.assertEqual(first["scope"], probe.GENERATION_SCOPE)
        self.assertEqual(manifest["scope"], probe.GENERATION_SCOPE)
        audio = probe.read_wave(first["wave_path"])
        self.assertEqual(manifest["file_sha256"], audio.file_sha256)
        self.assertEqual(manifest["audio_payload_sha256"], audio.data_sha256)
        self.assertEqual(audio.frames, 288000)
        self.assertEqual(audio.rate, 48000)
        self.assertEqual(audio.samples[0][48013], 0.25)
        self.assertEqual(audio.samples[1][48203], -0.125)
        self.assertTrue(all(v == 0 for v in audio.samples[0][:48000]))
        self.assertTrue(all(v == 0 for v in audio.samples[1][-48000:]))
        self.assertLessEqual(max(abs(v) for channel in audio.samples for v in channel), 0.25)
        with self.assertRaises(probe.WaveError):
            probe.generate(self.directory / "first")

    def test_cli_json_and_exit_codes(self):
        reference = self.write("reference.wav")
        candidate = self.write("candidate.wav", [(0.0, 0.0)] * len(self.frames))
        for path, expected_code, status in ((reference, 0, "pass"), (candidate, 1, "mismatch"),
                                            (self.directory / "missing.wav", 2, "error")):
            with self.subTest(status=status):
                result = subprocess.run([sys.executable, str(SCRIPT), "compare", str(reference), str(path)],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, expected_code)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], status)
                self.assertEqual(report["scope"], probe.COMPARISON_SCOPE)
                self.assertNotEqual(report["scope"], probe.GENERATION_SCOPE)


if __name__ == "__main__":
    unittest.main()
