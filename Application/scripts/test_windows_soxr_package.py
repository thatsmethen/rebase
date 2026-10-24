#!/usr/bin/env python3
"""Authored package-validator controls; no native PE execution or audio claim."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import unittest
import zipfile

import windows_soxr_package as package

COMMIT = "1" * 40


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pe(dll):
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HH", data, 132, 0x8664, 1)
    struct.pack_into("<HH", data, 148, 112, 0x2000 if dll else 0)
    struct.pack_into("<H", data, 152, 0x20b)
    return bytes(data)


class Controls(unittest.TestCase):
    app_source = None
    output = None

    def setUp(self):
        self.work = self.output / self._testMethodName
        self.work.mkdir()
        self.app = self.work / "Application"
        (self.app / "ThirdParty").mkdir(parents=True)
        source = self.app_source / "ThirdParty/soxr-0.1.3"
        # Git for Windows may store the one source link as exact link text.
        shutil.copytree(source, self.app / "ThirdParty/soxr-0.1.3", symlinks=True)
        for link in (self.app / "ThirdParty/soxr-0.1.3").rglob("*"):
            if link.is_symlink():
                target = os.readlink(link)
                link.unlink()
                link.write_bytes(target.encode("utf-8"))
        shutil.copyfile(self.app_source / "ThirdParty/soxr-source-manifest.json",
                        self.app / "ThirdParty/soxr-source-manifest.json")
        (self.app / "scripts").mkdir()
        for name in ("build-windows-soxr.py", "windows-soxr-probe.c"):
            shutil.copyfile(self.app_source / "scripts" / name, self.app / "scripts" / name)
        self.native = self.work / "native"
        self.native.mkdir()
        self.stage = self.work / "stage"
        self.stage.mkdir()
        self.probe = {"schema": "rebase.soxr-plumbing.v1", "status": "passed",
                      "scope": "Authored plumbing record for package-instrument controls",
                      "source_rate": 48000, "output_rate": 44100, "channels": 2,
                      "input_frames": 4800, "output_frames": 4410, "finite": True,
                      "peak": 0.8, "energy": 0.6, "maximum_channel_error": 0}
        self.report = {"schema": "rebase.windows-soxr.v1", "status": "passed", "platform": "Windows",
                       "architecture": "AMD64", "commit": COMMIT, "source_version": "0.1.3",
                       "source_manifest_sha256": package.MANIFEST_SHA256, "source_entries_verified": 138,
                       "options": dict(package.OPTIONS), "configured_features": dict(package.FEATURES),
                       "optimization": "-O3 -DNDEBUG; fast math disabled; FP contraction disabled",
                       "msvc_runtime": "MultiThreadedDLL (CMP0091 NEW)",
                       "windows_exports": "SOXR_DLL explicitly enabled for clang's GNU frontend",
                       "compile_command_count": 9, "commands": [], "artifacts": []}
        for name in package.COMMANDS:
            self.report["commands"].append({"name": name, "exit_code": 0, "log": name + ".log"})
            (self.native / (name + ".log")).write_text("Authored instrument control; not executed on Windows\n")
        for name, data in zip(package.ARTIFACTS, (pe(True), b"!<arch>\n" + b"authored-import-library" * 8, pe(False))):
            path = self.native / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.report["artifacts"].append({"path": name, "bytes": len(data), "sha256": sha(data)})
        self.save()

    def save(self):
        (self.native / "conformance.json").write_text(json.dumps(self.report))
        data = json.dumps(self.probe)
        (self.native / "soxr-conformance.json").write_text(data)
        (self.native / "probe.log").write_text(data + "\n")

    def validate(self, commit=COMMIT):
        return package.validate_soxr_build(self.app, self.native, commit)

    def rejected(self):
        with self.assertRaises((RuntimeError, OSError, ValueError)):
            self.validate()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_valid_receipt_and_no_validation_writes(self):
        before = sorted(str(p.relative_to(self.native)) for p in self.native.rglob("*"))
        receipt = self.validate()
        self.assertEqual(receipt["source_entries_verified"], 138)
        self.assertEqual(receipt["application_commit"], COMMIT)
        self.assertEqual(receipt["artifacts"], self.report["artifacts"])
        self.assertNotIn(str(self.work), json.dumps(receipt))
        self.assertEqual(before, sorted(str(p.relative_to(self.native)) for p in self.native.rglob("*")))
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_complete_deterministic_source_archive_and_exact_notices(self):
        receipt = package.stage_soxr(self.app, self.native, self.stage, COMMIT)
        self.assertEqual(len(receipt["packaged_files"]), 7)
        for row in receipt["packaged_files"]:
            path = self.stage / row["path"]
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_size, row["bytes"])
            self.assertEqual(sha(path.read_bytes()), row["sha256"])
        archive_path = self.stage / receipt["source_archive"]["path"]
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(len(archive.infolist()), 141)
            for info in archive.infolist():
                self.assertEqual(stat.S_IFMT(info.external_attr >> 16), stat.S_IFREG)
                self.assertNotIn("..", info.filename.split("/"))
            manifest = json.loads((self.app / "ThirdParty/soxr-source-manifest.json").read_bytes())
            for row in manifest["files"]:
                data = archive.read("soxr-0.1.3/" + row["path"])
                self.assertEqual(data, row["symlink"].encode() if "symlink" in row
                                 else (self.app / "ThirdParty/soxr-0.1.3" / row["path"]).read_bytes())
            for name in ("build-windows-soxr.py", "windows-soxr-probe.c"):
                self.assertEqual(archive.read("rebuild/" + name), (self.app / "scripts" / name).read_bytes())
        for name in ("COPYING.LGPL", "LICENCE", "AUTHORS"):
            self.assertEqual((self.stage / package.NOTICES / name).read_bytes(),
                             (self.app / "ThirdParty/soxr-0.1.3" / name).read_bytes())
        second = self.work / "second-stage"
        second.mkdir()
        repeated = package.stage_soxr(self.app, self.native, second, COMMIT)
        self.assertEqual(receipt, repeated)
        self.assertEqual(archive_path.read_bytes(), (second / receipt["source_archive"]["path"]).read_bytes())
        self.assertEqual(receipt["source_archive"]["symlink_entries"],
                         [{"path": "inst-check-soxr-lsr", "target": "inst-check-soxr", "representation": "regular link-text"}])

    def test_none_is_exact_local_commit_not_wildcard(self):
        with self.assertRaises(RuntimeError): self.validate(None)
        self.report["commit"] = None
        self.save()
        self.assertIsNone(self.validate(None)["application_commit"])
        self.rejected()

    def test_wrong_commit(self):
        self.report["commit"] = "2" * 40; self.save(); self.rejected()

    def test_missing_commit(self):
        del self.report["commit"]; self.save(); self.rejected()

    def test_failed_status(self):
        self.report["status"] = "failed"; self.save(); self.rejected()

    def test_wrong_platform(self):
        self.report["platform"] = "Darwin"; self.save(); self.rejected()

    def test_wrong_architecture(self):
        self.report["architecture"] = "ARM64"; self.save(); self.rejected()

    def test_wrong_version(self):
        self.report["source_version"] = "0.1.2"; self.save(); self.rejected()

    def test_report_manifest_pin(self):
        self.report["source_manifest_sha256"] = "0" * 64; self.save(); self.rejected()

    def test_manifest_changed_even_with_self_consistent_report(self):
        path = self.app / "ThirdParty/soxr-source-manifest.json"
        path.write_bytes(path.read_bytes() + b"\n")
        self.report["source_manifest_sha256"] = sha(path.read_bytes()); self.save(); self.rejected()

    def test_changed_source(self):
        path = self.app / "ThirdParty/soxr-0.1.3/src/soxr.c"
        path.write_bytes(path.read_bytes() + b"\n"); self.rejected()

    def test_missing_source(self):
        (self.app / "ThirdParty/soxr-0.1.3/AUTHORS").unlink(); self.rejected()

    def test_extra_source(self):
        (self.app / "ThirdParty/soxr-0.1.3/extra.txt").write_text("extra"); self.rejected()

    def test_changed_link_text(self):
        (self.app / "ThirdParty/soxr-0.1.3/inst-check-soxr-lsr").write_text("../outside"); self.rejected()

    def test_source_count(self):
        self.report["source_entries_verified"] = 137; self.save(); self.rejected()

    def test_static_library_profile(self):
        self.report["options"]["BUILD_SHARED_LIBS"] = "OFF"; self.save(); self.rejected()

    def test_changed_simd_feature(self):
        self.report["configured_features"]["WITH_CR32S"] = 1; self.save(); self.rejected()

    def test_changed_runtime(self):
        self.report["msvc_runtime"] = "MultiThreaded"; self.save(); self.rejected()

    def test_missing_compilation_units(self):
        self.report["compile_command_count"] = 8; self.save(); self.rejected()

    def test_missing_command(self):
        self.report["commands"].pop(); self.save(); self.rejected()

    def test_failed_command(self):
        self.report["commands"][3]["exit_code"] = 1; self.save(); self.rejected()

    def test_boolean_exit_code(self):
        self.report["commands"][3]["exit_code"] = False; self.save(); self.rejected()

    def test_reordered_commands(self):
        self.report["commands"].reverse(); self.save(); self.rejected()

    def test_log_path_escape(self):
        self.report["commands"][0]["log"] = "../outside.log"; self.save(); self.rejected()

    def test_missing_log(self):
        (self.native / "build.log").unlink(); self.rejected()

    def test_successful_silent_probe_build_matches_observed_ci(self):
        # Run 40044766254 produced exactly zero stdout/stderr bytes for the
        # successful clang-cl probe-build command. A missing file still rejects.
        (self.native / "probe-build.log").write_bytes(b"")
        self.assertEqual(self.report["commands"][-2]["exit_code"], 0)
        self.assertEqual(self.validate()["status"], "passed")

    def test_empty_probe_output_still_rejects(self):
        (self.native / "probe.log").write_bytes(b""); self.rejected()

    def test_truncated_json(self):
        (self.native / "conformance.json").write_text('{"status":'); self.rejected()

    def test_duplicate_json_field(self):
        path = self.native / "conformance.json"
        path.write_text(path.read_text()[:-1] + ',"status":"passed"}'); self.rejected()

    def test_nonobject_json(self):
        (self.native / "conformance.json").write_text("[]"); self.rejected()

    def test_probe_differs_from_log(self):
        (self.native / "probe.log").write_text('{}'); self.rejected()

    def test_wrong_flushed_count(self):
        self.probe["output_frames"] = 4409; self.save(); self.rejected()

    def test_nonfinite_measurement(self):
        self.probe["peak"] = float("nan"); self.save(); self.rejected()

    def test_wrong_channel_measurement(self):
        self.probe["maximum_channel_error"] = 1e-5; self.save(); self.rejected()

    def test_artifact_tamper(self):
        path = self.native / package.ARTIFACTS[0]
        path.write_bytes(path.read_bytes() + b"tampered"); self.rejected()

    def test_missing_artifact(self):
        (self.native / package.ARTIFACTS[1]).unlink(); self.rejected()

    def test_missing_artifact_record(self):
        self.report["artifacts"].pop(); self.save(); self.rejected()

    def test_duplicate_artifact(self):
        self.report["artifacts"][1] = copy.deepcopy(self.report["artifacts"][0]); self.save(); self.rejected()

    def test_artifact_path_escape(self):
        for name in ("../soxr.dll", "/soxr.dll", "C:/soxr.dll", "install\\bin\\soxr.dll", "install//bin/soxr.dll"):
            with self.subTest(name=name):
                self.report["artifacts"][0]["path"] = name; self.save(); self.rejected()

    def test_truncated_pe_even_with_updated_digest(self):
        path = self.native / package.ARTIFACTS[0]
        data = pe(True)[:180]; path.write_bytes(data)
        self.report["artifacts"][0].update(bytes=len(data), sha256=sha(data)); self.save(); self.rejected()

    def test_wrong_pe_architecture_even_with_updated_digest(self):
        path = self.native / package.ARTIFACTS[0]
        data = bytearray(pe(True)); struct.pack_into("<H", data, 132, 0xaa64); path.write_bytes(data)
        self.report["artifacts"][0].update(bytes=len(data), sha256=sha(data)); self.save(); self.rejected()

    def test_truncated_import_library_even_with_updated_digest(self):
        path = self.native / package.ARTIFACTS[1]
        data = b"!<arch>\n"; path.write_bytes(data)
        self.report["artifacts"][1].update(bytes=len(data), sha256=sha(data)); self.save(); self.rejected()

    def test_existing_dll_refused_without_overwrite(self):
        path = self.stage / "soxr.dll"; path.write_bytes(b"existing")
        with self.assertRaises(RuntimeError): package.stage_soxr(self.app, self.native, self.stage, COMMIT)
        self.assertEqual(path.read_bytes(), b"existing")
        self.assertFalse((self.stage / "ThirdPartyNotices").exists())

    def test_existing_notices_refused_without_overwrite(self):
        path = self.stage / package.NOTICES; path.mkdir(parents=True)
        with self.assertRaises(RuntimeError): package.stage_soxr(self.app, self.native, self.stage, COMMIT)
        self.assertFalse((self.stage / "soxr.dll").exists())

    @unittest.skipIf(os.name == "nt", "link creation privilege is not assumed; Windows reparse checks are source-reviewed")
    def test_artifact_symlink_refused(self):
        path = self.native / package.ARTIFACTS[0]
        target = self.work / "outside.dll"; path.rename(target); path.symlink_to(target); self.rejected()

    @unittest.skipIf(os.name == "nt", "link creation privilege is not assumed; Windows reparse checks are source-reviewed")
    def test_source_symlink_to_matching_bytes_refused(self):
        path = self.app / "ThirdParty/soxr-0.1.3/AUTHORS"
        target = self.work / "authors"; path.rename(target); path.symlink_to(target); self.rejected()

    @unittest.skipIf(os.name == "nt", "link creation privilege is not assumed; Windows reparse checks are source-reviewed")
    def test_output_root_symlink_refused(self):
        alias = self.work / "alias"; alias.symlink_to(self.native, target_is_directory=True)
        with self.assertRaises(RuntimeError): package.validate_soxr_build(self.app, alias, COMMIT)

    @unittest.skipIf(os.name == "nt", "link creation privilege is not assumed; Windows reparse checks are source-reviewed")
    def test_stage_parent_symlink_refused_without_writes(self):
        target = self.work / "outside-notices"; target.mkdir()
        (self.stage / "ThirdPartyNotices").symlink_to(target, target_is_directory=True)
        with self.assertRaises(RuntimeError): package.stage_soxr(self.app, self.native, self.stage, COMMIT)
        self.assertFalse((self.stage / "soxr.dll").exists())
        self.assertEqual(list(target.iterdir()), [])

    @unittest.skipIf(os.name == "nt", "link creation privilege is not assumed; Windows reparse checks are source-reviewed")
    def test_pinned_source_symlink_archived_as_regular_text(self):
        path = self.app / "ThirdParty/soxr-0.1.3/inst-check-soxr-lsr"
        path.unlink(); path.symlink_to("inst-check-soxr")
        receipt = package.stage_soxr(self.app, self.native, self.stage, COMMIT)
        with zipfile.ZipFile(self.stage / receipt["source_archive"]["path"]) as archive:
            info = archive.getinfo("soxr-0.1.3/inst-check-soxr-lsr")
            self.assertEqual(stat.S_IFMT(info.external_attr >> 16), stat.S_IFREG)
            self.assertEqual(archive.read(info), b"inst-check-soxr")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh directory for retained authored controls")
    parser.add_argument("--app", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    Controls.app_source, Controls.output = args.app.resolve(), args.output.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    with (args.output / "controls.log").open("w") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    receipt = {"schema": "rebase.windows-soxr-package-controls.v1", "status": "passed" if result.wasSuccessful() else "failed",
               "scope": "Authored validator/package controls using synthetic PE and build evidence; no native PE execution or audio fidelity claim",
               "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "helper_sha256": sha(Path(package.__file__).read_bytes()),
               "harness_sha256": sha(Path(__file__).read_bytes()),
               "failed_cases": [test.id().split(".")[-1] for test, _ in result.failures + result.errors]}
    (args.output / "observation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
