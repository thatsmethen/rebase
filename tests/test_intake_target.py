"""Synthetic fixture controls only. These tests make no claim about Cubase."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "intake_target.py"
SPEC = importlib.util.spec_from_file_location("intake_target", SCRIPT)
intake = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(intake)


class SyntheticBundleIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synthetic intake ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "Synthetic Test.app"
        self.contents = self.app / "Contents"
        self.macos = self.contents / "MacOS"
        self.macos.mkdir(parents=True)
        self.runner = self.macos / "Synthetic Runner"
        self.runner.write_bytes(b"synthetic executable fixture\x00\x01")
        self.resources = self.contents / "Resources"
        self.resources.mkdir()
        self.payload = self.resources / "sample.bin"
        self.payload.write_bytes(b"synthetic resource fixture\xff")
        self.plist = self.contents / "Info.plist"
        self.info = {
            "CFBundleExecutable": self.runner.name,
            "CFBundleName": "Synthetic Name",
            "CFBundleDisplayName": "Synthetic Display",
            "CFBundleShortVersionString": "0.0-fixture",
            "CFBundleVersion": "17-fixture",
            "CFBundleIdentifier": "example.synthetic.intake",
            "FixtureEdition": "Synthetic Edition",
        }
        self.save_plist()
        self.out = self.root / "new evidence output"

    def save_plist(self):
        self.plist.write_bytes(plistlib.dumps(self.info))

    def run_intake(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = intake.main([str(self.app), "--out", str(self.out), *extra])
        return result, stdout.getvalue(), stderr.getvalue()

    def assert_failure(self, expected):
        result, _, error = self.run_intake()
        self.assertNotEqual(result, 0)
        self.assertIn(expected, error)
        self.assertFalse(self.out.exists())

    def test_synthetic_hashes_identity_and_cli_paths_with_spaces(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.app), "--out", str(self.out),
             "--edition-key", "FixtureEdition"], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(manifest["metadata"]["edition"], "Synthetic Edition")
        self.assertEqual(manifest["metadata"]["name"], self.info["CFBundleName"])
        self.assertEqual(manifest["metadata"]["version"], "0.0-fixture")
        self.assertEqual(manifest["metadata"]["build"], "17-fixture")
        self.assertEqual(manifest["metadata"]["bundle_identifier"], self.info["CFBundleIdentifier"])
        self.assertTrue(manifest["recorded_at_utc"].endswith("+00:00"))
        self.assertEqual(manifest["tool_version"], intake.TOOL_VERSION)
        self.assertIn("python", manifest["host"])
        records = {entry["path"]: entry for entry in manifest["files"]}
        self.assertEqual(len(records), 3)
        for relative, record in records.items():
            data = (self.app / relative).read_bytes()
            self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(record["size"], len(data))
        self.assertEqual(manifest["main_executable"], records["Contents/MacOS/Synthetic Runner"])
        self.assertEqual(manifest["symlinks"], [])
        self.assertNotIn("synthetic executable fixture", (self.out / "manifest.json").read_text())
        self.assertEqual({p.name for p in self.out.iterdir()}, {"manifest.json"})

    def test_missing_optional_metadata_remains_unresolved(self):
        self.info = {"CFBundleExecutable": self.runner.name}
        self.save_plist()
        manifest, _ = intake.inventory(self.app)
        for field in ("edition", "edition_key", "name", "display_name", "version", "build", "bundle_identifier"):
            self.assertIsNone(manifest["metadata"][field])

    def test_missing_plist_fails(self):
        self.plist.unlink()
        self.assert_failure("Info.plist")

    def test_malformed_plist_fails(self):
        self.plist.write_bytes(b"not a property list")
        self.assert_failure("Malformed")

    def test_non_dictionary_plist_fails(self):
        self.plist.write_bytes(plistlib.dumps(["synthetic"]))
        self.assert_failure("dictionary")

    def test_non_string_metadata_fails(self):
        self.info["CFBundleVersion"] = 17
        self.save_plist()
        self.assert_failure("must be a string")

    def test_missing_executable_fails(self):
        del self.info["CFBundleExecutable"]
        self.save_plist()
        self.assert_failure("CFBundleExecutable")

    def test_executable_path_traversal_fails(self):
        for executable in ("../outside", "/bin/sh", "a/b", "a\\b", ".", "..", ""):
            with self.subTest(executable=executable):
                self.info["CFBundleExecutable"] = executable
                self.save_plist()
                self.assert_failure("CFBundleExecutable")

    def test_symlink_executable_fails_for_internal_and_external_targets(self):
        self.runner.unlink()
        outside = self.root / "outside secret"
        outside.write_bytes(b"must not be read")
        for target in (self.payload, outside):
            with self.subTest(target=target):
                self.runner.symlink_to(target)
                self.assert_failure("Declared executable")
                self.runner.unlink()

    def test_symlink_plist_is_rejected(self):
        outside = self.root / "outside.plist"
        self.plist.rename(outside)
        self.plist.symlink_to(outside)
        self.assert_failure("regular file")

    def test_symlink_macos_directory_is_rejected(self):
        outside = self.root / "outside MacOS"
        self.macos.rename(outside)
        self.macos.symlink_to(outside, target_is_directory=True)
        self.assert_failure("real directory")

    def test_other_symlinks_are_inventoried_without_reading_targets(self):
        outside = self.root / "outside directory"
        outside.mkdir()
        (outside / "secret.bin").write_bytes(b"never inventory this")
        links = {
            "internal": "sample.bin",
            "external": str(outside),
            "broken": str(self.root / "missing"),
            "cycle": ".",
        }
        for name, target in links.items():
            (self.resources / name).symlink_to(target)
        manifest, _ = intake.inventory(self.app)
        self.assertEqual(len(manifest["files"]), 3)
        self.assertEqual({entry["path"]: entry["target"] for entry in manifest["symlinks"]},
                         {"Contents/Resources/" + name: target for name, target in links.items()})

    def test_existing_output_refused_without_modification(self):
        self.out.mkdir()
        sentinel = self.out / "keep.txt"
        sentinel.write_text("retain this")
        result, _, error = self.run_intake()
        self.assertNotEqual(result, 0)
        self.assertIn("already exists", error)
        self.assertEqual(sentinel.read_text(), "retain this")
        self.assertEqual(list(self.out.iterdir()), [sentinel])

    def test_dangling_output_symlink_is_not_overwritten(self):
        self.out.symlink_to(self.root / "missing output")
        result, _, error = self.run_intake()
        self.assertNotEqual(result, 0)
        self.assertIn("already exists", error)
        self.assertTrue(self.out.is_symlink())

    def test_output_inside_bundle_is_rejected(self):
        self.out = self.resources / "evidence"
        self.assert_failure("outside the source")

    def test_symlink_bundle_is_rejected(self):
        link = self.root / "Alias.app"
        link.symlink_to(self.app, target_is_directory=True)
        self.app = link
        self.assert_failure("must not be a symlink")

    def test_file_change_while_hashing_fails_closed(self):
        original_read = os.read
        runner_inode = self.runner.stat().st_ino
        changed = False

        def changing_read(fd, size):
            nonlocal changed
            data = original_read(fd, size)
            if data and os.fstat(fd).st_ino == runner_inode and not changed:
                changed = True
                with self.runner.open("ab") as stream:
                    stream.write(b"changed while hashing")
            return data

        with mock.patch.object(intake.os, "read", side_effect=changing_read):
            self.assert_failure("Changed during intake")
        self.assertTrue(changed)

    def test_special_file_fails_closed(self):
        os.mkfifo(self.resources / "synthetic fifo")
        self.assert_failure("Unsupported special file")

    def test_same_size_change_with_restored_mtime_is_detected(self):
        original_read = os.read
        before = self.runner.stat()
        changed = False

        def changing_read(fd, size):
            nonlocal changed
            data = original_read(fd, size)
            if data and os.fstat(fd).st_ino == before.st_ino and not changed:
                changed = True
                self.runner.write_bytes(b"x" * before.st_size)
                os.utime(self.runner, ns=(before.st_atime_ns, before.st_mtime_ns))
            return data

        with mock.patch.object(intake.os, "read", side_effect=changing_read):
            self.assert_failure("Changed during intake")
        self.assertTrue(changed)

    def test_executable_replaced_by_symlink_during_read_is_detected(self):
        original_read = os.read
        runner_inode = self.runner.stat().st_ino
        outside = self.root / "unrelated secret"
        outside.write_bytes(b"do not read through replacement symlink")
        replaced = False

        def replacing_read(fd, size):
            nonlocal replaced
            self.assertNotEqual(os.fstat(fd).st_ino, outside.stat().st_ino)
            data = original_read(fd, size)
            if data and os.fstat(fd).st_ino == runner_inode and not replaced:
                replaced = True
                self.runner.unlink()
                self.runner.symlink_to(outside)
            return data

        with mock.patch.object(intake.os, "read", side_effect=replacing_read):
            self.assert_failure("Changed during intake")
        self.assertTrue(replaced)

    @unittest.skipUnless(shutil.which("file"), "optional file tool unavailable")
    def test_optional_inspection_is_separate_and_read_only(self):
        original = self.runner.read_bytes()
        result, _, error = self.run_intake("--inspect-file")
        self.assertEqual(result, 0, error)
        manifest = json.loads((self.out / "manifest.json").read_text())
        inspection = json.loads((self.out / "file-inspection.json").read_text())
        self.assertEqual(manifest["file_inspection"], "file-inspection.json")
        self.assertEqual(inspection["input"], "Contents/MacOS/Synthetic Runner")
        self.assertEqual(inspection["returncode"], 0)
        self.assertTrue(inspection["stdout"].strip())
        self.assertEqual(self.runner.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
