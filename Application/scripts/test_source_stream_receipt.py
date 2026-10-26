#!/usr/bin/env python3
"""Challenge publication admission using a completed actual-worker receipt."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import unittest
import source_stream_gate as gate


class Controls(unittest.TestCase):
    baseline = short = long = snapshot = None
    short_sha = long_sha = None

    def setUp(self):
        self.value = copy.deepcopy(self.baseline)

    def validate(self):
        return gate.require_receipt(self.value, self.short, self.long, self.short_sha, self.long_sha,
                                    self.baseline["helper_sha256"], self.snapshot)

    def rejected(self):
        with self.assertRaises(gate.StreamError):
            self.validate()

    def row(self, suffix):
        return next(row for row in self.value["scenarios"] if row["case"].endswith(suffix))

    def test_actual_receipt_admitted(self): self.assertEqual(self.validate()["scenarios"], 85)
    def test_failed_status(self): self.value["status"] = "failed"; self.rejected()
    def test_changed_schema(self): self.value["schema"] += ".invalid"; self.rejected()
    def test_changed_helper(self): self.value["helper_sha256"] = "0" * 64; self.rejected()
    def test_changed_short_fixture(self): self.value["fixture_manifest_sha256"] = "0" * 64; self.rejected()
    def test_changed_long_fixture(self): self.value["long_fixture_manifest_sha256"] = "0" * 64; self.rejected()
    def test_false_gate(self): self.value["gates"]["worker_cancel"] = False; self.rejected()
    def test_numeric_gate(self): self.value["gates"]["worker_cancel"] = 1; self.rejected()
    def test_missing_gate(self): self.value["gates"].pop("source_revalidation"); self.rejected()
    def test_device_claim(self): self.value["playback_tested"] = True; self.rejected()
    def test_reference_claim(self): self.value["reference_execution"] = True; self.rejected()
    def test_empty_checks(self): self.value["checks"] = []; self.rejected()
    def test_duplicate_checks(self): self.value["checks"].append(self.value["checks"][0]); self.rejected()
    def test_missing_scenario(self): self.value["scenarios"].pop(); self.rejected()
    def test_repeated_scenario(self): self.value["scenarios"][-1] = self.value["scenarios"][0]; self.rejected()
    def test_unexpected_private_metadata(self): self.value["scenarios"][0]["ticketPath"] = "unreviewed"; self.rejected()
    def test_unexpected_top_level_private_path(self): self.value["ticketPath"] = "unreviewed"; self.rejected()
    def test_unexpected_top_level_capability(self): self.value["capability"] = "unreviewed"; self.rejected()
    def test_missing_top_level_scope(self): self.value.pop("scope"); self.rejected()
    def test_boolean_frame_count(self): self.value["scenarios"][0]["frames"] = True; self.rejected()
    def test_wrong_clock(self): self.value["scenarios"][0]["sample_rate"] = 32000; self.rejected()
    def test_missing_hash(self): self.value["scenarios"][0]["pcm_sha256"] = ""; self.rejected()
    def test_rewind_pcm_changed(self): self.row("-rewind")["pcm_sha256"] = "0" * 64; self.rejected()
    def test_partition_proof_changed(self): self.row("-partition")["normalized_proof_sha256"] = "0" * 64; self.rejected()
    def test_partition_order_changed(self): self.row("-partition")["logical_blocks_sha256"] = "0" * 64; self.rejected()
    def test_observed_logical_count_mismatch(self): self.value["scenarios"][0]["observed_logical_blocks"] += 1; self.rejected()
    def test_observed_logical_peak_mismatch(self): self.value["scenarios"][0]["observed_peak_logical_frames"] += 1; self.rejected()
    def test_missing_logical_digest(self): self.value["scenarios"][0].pop("logical_blocks_sha256"); self.rejected()
    def test_eof_nonempty_logical_digest(self): self.row("-eof")["logical_blocks_sha256"] = "0" * 64; self.rejected()
    def test_odd_position_changed(self): self.row("-odd")["start_frame"] = 2; self.rejected()
    def test_eof_extra_pcm(self): self.row("-eof")["records"] = 1; self.rejected()
    def test_long_tail_changed(self): self.row("-tail")["pcm_sha256"] = "0" * 64; self.rejected()
    def test_excessive_buffer(self): self.value["scenarios"][0]["peak_payload_bytes"] = 524289; self.rejected()
    def test_unbounded_logical_block(self): self.value["scenarios"][0]["producer_peak_logical_frames"] = 16000001; self.rejected()
    def test_false_empty_counters(self): self.value["scenarios"][0]["producer_logical_blocks"] = 0; self.rejected()
    def test_snapshot_oracle_mismatch(self):
        self.row("-odd")["pcm_sha256"] = "0" * 64; self.rejected()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--short-fixture", type=Path, required=True)
    parser.add_argument("--long-fixture", type=Path, required=True)
    parser.add_argument("--snapshot-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    Controls.baseline = json.loads(args.receipt.read_bytes())
    Controls.short = json.loads(args.short_fixture.read_bytes())
    Controls.long = json.loads(args.long_fixture.read_bytes())
    Controls.snapshot = json.loads(args.snapshot_receipt.read_bytes())
    Controls.short_sha, Controls.long_sha = sha(args.short_fixture), sha(args.long_fixture)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    with (args.output / "controls.log").open("w") as handle:
        result = unittest.TextTestRunner(stream=handle, verbosity=2).run(suite)
    report = {"schema": "rebase.source-stream-gate-controls.v1", "status": "passed" if result.wasSuccessful() else "failed",
        "scope": "Authored rejection mutations of an actual-worker receipt; instrument validation, not additional source or device behavior",
        "input_receipt_sha256": sha(args.receipt), "tests": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped), "gate_sha256": sha(Path(gate.__file__)),
        "harness_sha256": sha(Path(__file__)), "failed_cases": [test.id().split(".")[-1] for test, _ in result.failures + result.errors]}
    (args.output / "observation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
