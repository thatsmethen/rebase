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


def passing_stream_receipt():
    return {"schema": "rebase.native-bounded-stream-controls.v1", "status": "passed", "checks": 100,
        "physical_playback_tested": False, "oracle_cases": 28, "cancel_race_cycles": 40, "fault_injection_cases": 9,
        "status_race_cycles": 300, "status_samples": 300, "pause_final_race_cycles": 200,
        "long_stream_frames": 32_004_240, "duration_admission_frames": 16_588_800_000,
        "long_fnv1a64": "9856751957304272980", "long_source_peak_frames": 8192, "long_endpoint_peak_frames": 8192,
        "source_queue_bound_frames": 65_536, "endpoint_queue_bound_frames": 8192, "fixed_pcm_storage_bound_bytes": 622_592,
        "max_pcm_storage_case": {"source_capacity_frames": 65_536, "endpoint_capacity_frames": 4096,
            "rolling_input_frames": 4096, "pending_output_frames": 4096, "bytes": 622_592},
        "gates": dict.fromkeys(("snapshot_exact", "canonical_partitions", "coherent_status_publication",
            "identity_bits", "exact_eof", "zero_output_not_eof", "deferred_eof_clock_completion",
            "maximum_block_owned_copy", "bounded_backpressure",
            "starvation_fault", "u64_duration_mapping", "cancel_join_barrier", "pause_freezes_position",
            "pause_final_drain_race", "stop_reset_failure_retry", "converter_failures", "allocation_failures",
            "failed_startup_unpublished", "long_incremental_hash"), True)}


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

    def test_ctest_requires_all_three_executed_suites(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.xml"
            entries = ('<testcase name="native_audio_portable_lifecycle"/><testcase name="native_audio_rate_conversion"/>'
                       '<testcase name="native_audio_bounded_stream"/>')
            path.write_text('<testsuite>' + entries + '</testsuite>', encoding="utf-8")
            self.assertEqual(GATE.validate_test_xml(path), {"count": 3, "skipped": 0, "failures": 0})
            for bad in (entries.replace('native_audio_rate_conversion', 'native_audio_portable_lifecycle'),
                        entries.replace('native_audio_rate_conversion"/>', 'native_audio_rate_conversion"><skipped/></testcase>'),
                        entries.replace('native_audio_rate_conversion"/>', 'native_audio_rate_conversion"><failure/></testcase>'),
                        '<testcase name="native_audio_portable_lifecycle"/>', entries + '<testcase name="unrelated"/>'):
                path.write_text('<testsuite>' + bad + '</testsuite>', encoding="utf-8")
                with self.assertRaises(ValueError):
                    GATE.validate_test_xml(path)

    def test_bounded_stream_control_admitted(self):
        self.assertEqual(GATE.validate_stream_controls(passing_stream_receipt())["oracle_cases"], 28)

    def test_bounded_stream_missing_changed_or_boolean_fields_rejected(self):
        baseline = passing_stream_receipt()
        for key in baseline:
            with self.subTest(missing=key):
                value = copy.deepcopy(baseline); del value[key]
                with self.assertRaises(ValueError): GATE.validate_stream_controls(value)
        for key, initial in baseline.items():
            if type(initial) is int:
                for changed in (0, True, -1, None):
                    with self.subTest(field=key, changed=changed):
                        value = copy.deepcopy(baseline); value[key] = changed
                        with self.assertRaises(ValueError): GATE.validate_stream_controls(value)
        for key, changed in (("status", "failed"), ("schema", "other"), ("physical_playback_tested", True)):
            with self.subTest(field=key):
                value = copy.deepcopy(baseline); value[key] = changed
                with self.assertRaises(ValueError): GATE.validate_stream_controls(value)

    def test_bounded_stream_missing_or_false_gates_rejected(self):
        for key in passing_stream_receipt()["gates"]:
            for mutation in ("missing", False, 1):
                with self.subTest(gate=key, mutation=mutation):
                    value = passing_stream_receipt()
                    if mutation == "missing": del value["gates"][key]
                    else: value["gates"][key] = mutation
                    with self.assertRaises(ValueError): GATE.validate_stream_controls(value)

    def test_bounded_stream_hash_and_paired_storage_rejected(self):
        for changed in (None, "0", 9856751957304272980, "9856751957304272981"):
            value = passing_stream_receipt(); value["long_fnv1a64"] = changed
            with self.assertRaises(ValueError): GATE.validate_stream_controls(value)
        for key in passing_stream_receipt()["max_pcm_storage_case"]:
            for mutation in ("missing", True, 0, -1, None, 8192):
                with self.subTest(field=key, mutation=mutation):
                    value = passing_stream_receipt()
                    if mutation == "missing": del value["max_pcm_storage_case"][key]
                    else: value["max_pcm_storage_case"][key] = mutation
                    with self.assertRaises(ValueError): GATE.validate_stream_controls(value)
        # Scheduling changes observation counts and queue peaks, never limits.
        value = passing_stream_receipt(); value.update(status_samples=1, long_source_peak_frames=4096, long_endpoint_peak_frames=4096)
        GATE.validate_stream_controls(value)
        for key in ("long_source_peak_frames", "long_endpoint_peak_frames"):
            value = passing_stream_receipt(); value[key] = 8193
            with self.assertRaises(ValueError): GATE.validate_stream_controls(value)


if __name__ == "__main__":
    unittest.main()
