"""Authored receipt controls; these do not run WASAPI or measure device output."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("native_ci", Path(__file__).with_name("run-windows-native-audio-ci.py"))
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def passing_rate_receipt():
    names = ("identity-bits", "44100-to-48000", "48000-to-44100", "8000-to-192000",
             "192000-to-8000", "short-empty-downsample", "fractional-frame-count", "seek-phase-preserved",
             "pause-reset-drain", "allocation-failure", "converter-failure", "capacity-rejection",
             "environment-rejection", "zero-isolation-tail-drain")
    record = {"schema": 1, "suite": "native-audio-rate-conversion", "checks": 100, "failures": 0,
            "wasapi_compiled": False, "playback_tested": False, "audible_output_measured": False,
            "soxr_version": "libsoxr-0.1.3",
            "profile": {"recipe": 6, "channels": 2, "linear_phase": True, "runtime_threads": 1,
                        "implicit_os_conversion": False},
            "cases": [{"name": name, "failures": 0, "source_rate": 48000,
                       "endpoint_rate": 44100, "source_frames": 100, "endpoint_frames": 92} for name in names]}
    indexed = {case["name"]: case for case in record["cases"]}
    indexed["identity-bits"].update(endpoint_rate=48000, endpoint_frames=100)
    for name, rates in {"44100-to-48000": (44100, 48000), "48000-to-44100": (48000, 44100),
                        "8000-to-192000": (8000, 192000), "192000-to-8000": (192000, 8000),
                        "fractional-frame-count": (44100, 48000)}.items():
        indexed[name].update(source_rate=rates[0], endpoint_rate=rates[1],
                             endpoint_frames=(100 * rates[1] + rates[0] // 2) // rates[0])
    for name in ("short-empty-downsample", "allocation-failure", "converter-failure", "capacity-rejection",
                 "environment-rejection"):
        indexed[name]["endpoint_frames"] = 0
    return record


class NativeEvidenceGate(unittest.TestCase):
    def test_accepted_control(self):
        self.assertIsNotNone(GATE.validate_rate_controls(passing_rate_receipt()))

    def test_missing_execution_or_false_device_claim(self):
        mutations = {"schema": True, "suite": "other", "checks": 0, "failures": 1,
                     "wasapi_compiled": True, "playback_tested": True, "audible_output_measured": True,
                     "soxr_version": "unknown"}
        for key, value in mutations.items():
            with self.subTest(field=key):
                record = passing_rate_receipt()
                record[key] = value
                with self.assertRaises(ValueError):
                    GATE.validate_rate_controls(record)
        for key in passing_rate_receipt():
            with self.subTest(missing=key):
                record = passing_rate_receipt()
                del record[key]
                with self.assertRaises((ValueError, TypeError)):
                    GATE.validate_rate_controls(record)

    def test_changed_profile(self):
        for key, value in {"recipe": 4, "channels": 1, "linear_phase": False, "runtime_threads": 0,
                           "implicit_os_conversion": True}.items():
            with self.subTest(field=key):
                record = passing_rate_receipt()
                record["profile"][key] = value
                with self.assertRaises(ValueError):
                    GATE.validate_rate_controls(record)

    def test_case_coverage_and_measurements(self):
        for mutation in ("empty", "missing", "duplicate", "failed", "negative", "boolean", "null",
                         "changed_rate", "changed_count", "rejected_output"):
            with self.subTest(mutation=mutation):
                record = passing_rate_receipt()
                if mutation == "empty": record["cases"] = []
                elif mutation == "missing": record["cases"].pop()
                elif mutation == "duplicate": record["cases"][-1] = copy.deepcopy(record["cases"][0])
                elif mutation == "failed": record["cases"][0]["failures"] = 1
                elif mutation == "negative": record["cases"][0]["endpoint_frames"] = -1
                elif mutation == "boolean": record["cases"][0]["source_rate"] = True
                elif mutation == "null": record["cases"][0] = None
                elif mutation == "changed_rate": record["cases"][1]["source_rate"] = 48000
                elif mutation == "changed_count": record["cases"][1]["endpoint_frames"] += 1
                elif mutation == "rejected_output": record["cases"][5]["endpoint_frames"] = 1
                with self.assertRaises(ValueError):
                    GATE.validate_rate_controls(record)

    def test_ctest_requires_both_executed_suites(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.xml"
            entries = '<testcase name="native_audio_portable_lifecycle"/><testcase name="native_audio_rate_conversion"/>'
            path.write_text('<testsuite>' + entries + '</testsuite>', encoding="utf-8")
            self.assertEqual(GATE.validate_test_xml(path), {"count": 2, "skipped": 0, "failures": 0})
            for bad in (entries.replace('native_audio_rate_conversion', 'native_audio_portable_lifecycle'),
                        entries.replace('native_audio_rate_conversion"/>', 'native_audio_rate_conversion"><skipped/></testcase>'),
                        entries.replace('native_audio_rate_conversion"/>', 'native_audio_rate_conversion"><failure/></testcase>'),
                        '<testcase name="native_audio_portable_lifecycle"/>', entries + '<testcase name="unrelated"/>'):
                path.write_text('<testsuite>' + bad + '</testsuite>', encoding="utf-8")
                with self.assertRaises(ValueError):
                    GATE.validate_test_xml(path)


if __name__ == "__main__":
    unittest.main()
