"""Explicit candidate identity for read-only private package audits.

No network, binary execution, source edits, or inferred successful candidate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate configuration/receipt field")
            result[key] = value
        return result
    def bad_constant(_):
        raise ValueError("Nonfinite configuration/receipt value")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=bad_constant)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def positive(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError("Expected positive integer: " + name)


COUNT_KEYS = {"host_controls", "wpf_checks", "session_checks", "audition_checks", "audition_scenarios",
              "stream_checks", "stream_scenarios", "managed_reader_checks", "managed_reader_workers",
              "window_gate_checks", "window_gate_workers", "documents_gate_checks", "documents_window_checks", "documents_phases", "structure_gate_checks", "structure_window_checks", "shared_tests", "dependency_tests", "shared_subsets"}


def validate_counts(counts):
    if not isinstance(counts, dict) or set(counts) != COUNT_KEYS:
        raise ValueError("Missing or unknown expected-count field")
    for key in COUNT_KEYS - {"shared_tests", "dependency_tests", "shared_subsets"}:
        positive(counts[key], key)
    for key in ("shared_tests", "dependency_tests"):
        row = counts[key]
        if not isinstance(row, dict) or set(row) != {"count", "executed", "skipped", "failures"}:
            raise ValueError("Expected complete count/executed/skipped/failures totals")
        if any(type(value) is not int or value < 0 for value in row.values()):
            raise ValueError("Expected explicit nonnegative test counts")
        if row["count"] != row["executed"] + row["skipped"] or row["executed"] == 0 or row["failures"] != 0:
            raise ValueError("Expected successful executed tests with consistent totals")
    if not isinstance(counts["shared_subsets"], dict) or not counts["shared_subsets"]:
        raise ValueError("Expected explicit shared suite coverage")
    for key, value in counts["shared_subsets"].items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]+", key):
            raise ValueError("Invalid shared suite name")
        positive(value, key)
    return counts


class Context:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        if len(raw) > 65536:
            raise ValueError("Audit configuration is too large")
        self.config = config = decode(raw)
        required = {"schema", "repository", "source_commit", "run_id", "evidence", "archive", "workflow",
                    "output", "expected_counts", "pefile_directory", "privacy_rules", "additional_privacy_rules",
                    "path_baseline_audit", "path_baseline_review", "structure_fixture"}
        if not isinstance(config, dict) or set(config) != required or config["schema"] != "rebase.private-package-audit-config.v1":
            raise ValueError("Unexpected audit configuration schema")
        if not isinstance(config["source_commit"], str) or not re.fullmatch("[0-9a-f]{40}", config["source_commit"]):
            raise ValueError("Explicit full source commit required")
        positive(config["run_id"], "run_id")
        self.commit, self.run_id = config["source_commit"], config["run_id"]
        self.counts = validate_counts(config["expected_counts"])
        self.root = Path(config["repository"]).resolve(strict=True)
        self.local = (self.root / ".local").resolve(strict=True)
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", TZ="UTC")
        actual = subprocess.check_output(["git", "rev-parse", "--verify", self.commit + "^{commit}"],
                                         cwd=self.root, env=self.env, text=True).strip()
        if actual != self.commit:
            raise ValueError("Commit is not available as an exact commit object")
        for key in ("evidence", "archive", "workflow", "pefile_directory", "privacy_rules", "additional_privacy_rules",
                    "path_baseline_audit", "path_baseline_review", "structure_fixture"):
            value = Path(config[key]).resolve(strict=True)
            if not value.is_relative_to(self.local):
                raise ValueError("Audit inputs must stay in the canonical ignored local directory")
            setattr(self, key, value)
        if not self.evidence.is_dir() or not self.pefile_directory.is_dir() or not self.archive.is_file():
            raise ValueError("Wrong audit input type")
        if self.archive.suffix.lower() != ".zip" or len(list(self.archive.parent.glob("*.zip"))) != 1:
            raise ValueError("Expected one unambiguous ZIP in its download directory")
        self.output = Path(config["output"]).resolve()
        if not self.output.is_relative_to(self.local) or self.output in (self.local, self.evidence, self.archive.parent):
            raise ValueError("Output must be a separate ignored local directory")
        self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        seal = self.output / "audit-inputs.json"
        encoded = json.dumps(config, sort_keys=True, indent=2).encode() + b"\n"
        if seal.exists():
            if seal.read_bytes() != encoded:
                raise ValueError("Refusing to reuse an output directory for different audit inputs")
        else:
            self.write_once(seal, encoded)

    def source(self, relative):
        if not isinstance(relative, str) or relative.startswith("/") or ".." in relative.split("/"):
            raise ValueError("Invalid committed source path")
        return subprocess.check_output(["git", "show", self.commit + ":" + relative], cwd=self.root, env=self.env)

    def paths(self, *prefixes):
        return subprocess.check_output(["git", "ls-tree", "-r", "--name-only", self.commit, *prefixes],
                                       cwd=self.root, env=self.env, text=True).splitlines()

    def bind_gates(self):
        source_root = self.output / "source-bound-gates"
        directory = source_root / "Application/scripts"
        directory.mkdir(parents=True, exist_ok=True)
        rows = []
        for path in self.paths("Application/scripts"):
            if not path.endswith(".py") or len(Path(path).parts) != 3:
                continue
            data = self.source(path)
            target = directory / Path(path).name
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError("Previously materialized gate differs from audited commit")
            else:
                self.write_once(target, data)
            rows.append({"path": path, "sha256": digest(data)})
        if not rows:
            raise ValueError("No committed audit gates")
        # Preserve the source-relative fixture dependency used by the complete
        # source-stream window proof gate. Never consult the working copy.
        auxiliary = "Application/Tests/Fixtures/SourceAuditionModes/expected.json"
        data = self.source(auxiliary)
        target = source_root / auxiliary
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError("Previously materialized gate fixture differs from audited commit")
        else:
            self.write_once(target, data)
        rows.append({"path": auxiliary, "sha256": digest(data)})
        sys.path.insert(0, str(directory))
        sys.path.insert(0, str(self.pefile_directory))
        return directory, rows

    @staticmethod
    def write_once(path, data):
        with Path(path).open("xb") as handle:
            handle.write(data)

    def write_json(self, name, value):
        self.write_once(self.output / name, json.dumps(value, indent=2, allow_nan=False).encode() + b"\n")


def load():
    if not __debug__:
        raise RuntimeError("Audit assertions must not be disabled")
    parser = argparse.ArgumentParser(description="Read-only, source-bound audit of a downloaded Windows package")
    parser.add_argument("--config", type=Path, required=True)
    return Context(parser.parse_args().config)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def validate_shared_command_exits(commands):
    """The committed runner deliberately refuses a second example render."""
    if not isinstance(commands, list) or not commands:
        raise ValueError("Missing shared commands")
    names = []
    for command in commands:
        if not isinstance(command, dict) or not isinstance(command.get("name"), str):
            raise ValueError("Invalid shared command")
        name = command["name"]
        names.append(name)
        expected = 1 if name == "example-overwrite-refusal" else 0
        if type(command.get("exit_code")) is not int or command["exit_code"] != expected:
            raise ValueError("Unexpected shared command exit")
    if len(set(names)) != len(names) or names.count("example-overwrite-refusal") != 1:
        raise ValueError("Missing or duplicate expected overwrite refusal")
