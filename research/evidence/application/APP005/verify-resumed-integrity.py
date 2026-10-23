#!/usr/bin/env python3
"""Recheck retained evidence and packages without modifying old records."""
from pathlib import Path
from types import SimpleNamespace
import datetime
import json
import re
import runpy
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
helpers = runpy.run_path(str(HERE / "verify-gui-packages.py"))
read, sha, require, strict_json = (helpers[k] for k in ("read", "sha", "require", "strict_json"))
pins = []


def main():
    output = HERE / (sys.argv[1] if len(sys.argv) == 2 else "resumed-integrity.json")
    require(output.parent == HERE and not output.exists(), "Output must be a new APP005 JSON file.")
    result = {"id": "APP005-RESUMED-INTEGRITY", "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "verifier_sha256": sha(Path(__file__).read_bytes()), "input_pins": pins,
              "limits": ["Read-only retained-output verification; no new test, application, build or Cubase execution.",
                         "Log success is not an independent rerun; binary/source release linkage remains pending the final snapshot."]}
    try:
        manifest_bytes = read(HERE.parent / "APP004/artifact-manifest.json", pins)
        require(sha(manifest_bytes) == "4a2166c5e0e77a82eb26f870d7e014634d9d6fdb14be97a00756c89bde7acab4", "APP004 manifest changed.")
        manifest = strict_json(manifest_bytes)
        require(len(manifest["files"]) == 107, "Unexpected historical manifest count.")
        for item in manifest["files"]:
            content = read(item["path"], pins)
            require(len(content) == item["bytes"] and sha(content) == item["sha256"], "Changed historical file: " + item["path"])
        result["APP004_manifest"] = {"sha256": sha(manifest_bytes), "checked_files": 107, "changed_files": []}
        log = read(HERE / "core-tests-final.log", pins).decode("utf-8")
        summaries = re.findall(r"Test run with (\d+) tests in (\d+) suites passed after", log)
        passed = re.findall(r"Test ([^\n]+?) passed after", log)
        passed = [name for name in passed if not name.startswith("run with ")]
        suites = re.findall(r"Suite ([^\n]+?) passed after", log)
        require(summaries == [("108", "16")] and len(passed) == len(set(passed)) == 108
                and len(suites) == len(set(suites)) == 16, "Final log lacks complete unique108/16 pass records.")
        require(not re.search(r"error:|Test .* failed|Suite .* failed|recorded an issue", log), "Final log contains failure diagnostics.")
        result["tests_log"] = {"passed_tests": 108, "passed_suites": 16, "unique_individual_pass_records": 108,
                               "scope": "Inspection of retained final log; no rerun."}
        before = HERE / "historical-packages-before.json"
        result["historical_packages"] = helpers["history"](before, pins)
        native = HERE / "LoFi Native Map.rebaseproj"
        converted = HERE / "LoFi Converted Copy.rebaseproj"
        native_check = HERE / "native-map-independent-check.json"
        converted_check = HERE / "converted-copy-independent-check.json"
        helpers["prior_package_check"](native_check, native, pins)
        helpers["prior_package_check"](converted_check, converted, pins)
        result["native_package"] = helpers["verify"](SimpleNamespace(package=native, project_clock="recovered",
            allow_project_name_change=False, copied_from=None, source_check=None), pins)
        result["converted_package"] = helpers["verify"](SimpleNamespace(package=converted, project_clock="converted",
            allow_project_name_change=True, copied_from=native, source_check=native_check), pins)
        export = HERE / "LoFi Converted Copy.dawproject"
        prior_export = strict_json(read(HERE / "converted-exchange-independent-check.json", pins))
        require(prior_export["status"] == "passed", "Prior export check failed.")
        export_pin = [p for p in prior_export["input_pins"] if p["path"] == str(export)]
        require(len(export_pin) == 1 and sha(read(export, pins)) == export_pin[0]["sha256"], "Export changed after prior check.")
        result["converted_export"] = helpers["export"](SimpleNamespace(package=converted, package_check=converted_check,
            archive=export, rejected=HERE / "Rejected Native Map.dawproject"), pins)
        result["status"] = "passed"
    except (Exception,) as error:
        result["status"] = "failed"
        result["error"] = str(error)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write("\n")
    print(result["status"], output, sha(output.read_bytes()))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
