"""Authored receipt/pixel mutation controls; no native WPF or helper execution."""
import argparse
import copy
import json
import uuid
from pathlib import Path

from structure_window_gate import (CAPTURES, CHECKS, GENERATOR_FILES, INPUT, PAYLOADS, SCOPE, TABS,
                                   require_structure_fixture, require_structure_window, sha)
from test_documents_window_gate import coverage, png, set_path


def write_fixture(root):
    root.mkdir()
    cases = []
    for index, (name, stem) in enumerate((("small", "Small"), ("large", "Large"))):
        project_id, track_id = str(uuid.UUID(int=10 + index)), str(uuid.UUID(int=20 + index))
        payload = {"Project.json": json.dumps({"id": project_id, "tracks": [{"id": track_id, "clips": []}]}).encode(),
                   PAYLOADS[1]: ("Authored source bytes " + name).encode(), PAYLOADS[2]: ("Authored import report " + name).encode()}
        report = {"schemaVersion": 1, "sourceSHA256": sha(payload[PAYLOADS[1]]), "sourceByteCount": len(payload[PAYLOADS[1]]),
                  **{key: ["Authored " + key] for key in ("entries", "tracks", "issues", "lists", "nativeObjects", "resourceAssociations")},
                  "authored_padding": "large invented value" * (4000 if index else 1)}
        report_bytes = json.dumps(report, indent=2).encode()
        case = {"name": name, "root": stem + ".rebaseproj", "projectID": project_id, "trackID": track_id,
                "sourceSHA256": report["sourceSHA256"], "sourceBytes": report["sourceByteCount"], "reportSHA256": sha(report_bytes),
                "reportBytes": len(report_bytes), "reportFile": stem + ".structure.json", "manifestSHA256": sha(payload["Project.json"]),
                "counts": {key: 1 for key in ("entries", "tracks", "issues", "lists", "nativeObjects", "resourceAssociations")},
                "files": [{"path": relative, "bytes": len(payload[relative]), "sha256": sha(payload[relative])} for relative in PAYLOADS]}
        for relative, data in payload.items():
            path = root / case["root"] / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        (root / case["reportFile"]).write_bytes(report_bytes); cases.append(case)
    fixture = {"schema": "rebase.project-structure-fixtures.v1", "evidenceClass": "authored-synthetic-control",
               "scope": "No reference execution; authored validator controls only.", "cases": cases,
               "generatorSHA256": {name: sha(("Authored source " + name).encode()) for name in GENERATOR_FILES}}
    (root / "expected.json").write_bytes(json.dumps(fixture, indent=2).encode())
    return fixture


def authored(fixture, fixture_bytes, helper, image):
    def state(lock, name, revision, dirty=False, undo=False, redo=False, project=None):
        return {"state_sha256": sha(("Authored state " + name).encode()), "project_sha256": sha((project or name).encode()),
                "revision": revision, "dirty": dirty, "needs_save_as": False, "can_undo": undo, "can_redo": redo,
                "track_id": lock["trackID"], "clip_id": None}
    rows = []
    for name, lock, revision in zip(("clean", "dirty", "large"), (fixture["cases"][0], fixture["cases"][0], fixture["cases"][1]), (90, 91, 93)):
        s = state(lock, name, revision, name == "dirty", name == "dirty")
        pages = (lock["reportBytes"] + 65535) // 65536
        snapshot = {"project_id": lock["projectID"], "revision": revision, "source_sha256": lock["sourceSHA256"],
                    "source_bytes": lock["sourceBytes"], "manifest_sha256": lock["manifestSHA256"], "report_sha256": lock["reportSHA256"],
                    "report_bytes": lock["reportBytes"], "entries": 1, "tracks": 1, "issues": 1, "lists": 1,
                    "native_objects": 1, "resource_associations": 1}
        row = {"name": name, "before": copy.deepcopy(s), "opened": copy.deepcopy(s), "after": copy.deepcopy(s),
               "commands": {"inspectProjectStructure": 1, "projectStructurePage": pages - 1, "closeProjectStructure": 1},
               "page_count": pages, "snapshot": snapshot, "report_sha256": lock["reportSHA256"], "report_bytes": lock["reportBytes"]}
        if name == "clean":
            row.update(visited_sections=list(TABS), read_only={"is_read_only": True, "provider_read_only": True, "write_rejected": True,
                       "before_sha256": lock["reportSHA256"], "after_sha256": lock["reportSHA256"]})
        if name == "large":
            row["scroll"] = {"before_offset": 0, "after_offset": 500, "viewport_height": 200, "extent_height": 700,
                             "first_visible_line": 40, "last_visible_line": 50, "last_source_line": 50,
                             "json_sha256": lock["reportSHA256"], "json_bytes": lock["reportBytes"], "read_only": True}
        rows.append(row)
    captures = []
    for name, section, lock in zip(CAPTURES, ("Tracks", "Complete JSON"), fixture["cases"]):
        controls = [{"name": "sections", "x": 18, "y": 100, "width": 608, "height": 270},
                    {"name": "content", "x": 20, "y": 140, "width": 604, "height": 228},
                    {"name": "close", "x": 540, "y": 385, "width": 84, "height": 30}]
        controls += [{"name": "tab-" + tab, "x": 20 + i * 115, "y": 102, "width": 110, "height": 32} for i, tab in enumerate(TABS)]
        for row in controls: row.update(visible=True, enabled=True)
        captures.append({"file": name, "sha256": sha(image), "alpha_coverage": coverage(count=644 * 442),
                         "bounds": {"outer_width_dip": 660, "outer_height_dip": 480, "width_dip": 644, "height_dip": 442,
                                    "dpi_scale_x": 1, "dpi_scale_y": 1, "pixel_width": 644, "pixel_height": 442},
                         "controls": controls, "selected_section": section, "scope": SCOPE, "report_sha256": lock["reportSHA256"],
                         "report_bytes": lock["reportBytes"], "frame_excluded": True})
    custody = [{"name": lock["name"], "path": item["path"], "bytes": item["bytes"], "original_sha256": item["sha256"], "copy_sha256": item["sha256"]}
               for lock in fixture["cases"] for item in lock["files"]]
    return {"outcome": "passed", "checks": ["existing-check", *CHECKS], "project_structure": {
        "tested": True, "fixture_sha256": sha(fixture_bytes), "helper_sha256": helper, "cases": rows, "captures": captures, "custody": custody,
        "after_undo": state(fixture["cases"][0], "undo", 92, redo=True, project="clean"),
        "physical_input_tested": False, "native_file_pickers_tested": False, "playback_tested": False, "input_evidence": INPUT}}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    fixture_root = out / "authored-fixtures"; fixture = write_fixture(fixture_root)
    fixture_files = {p.relative_to(fixture_root): p.read_bytes() for p in fixture_root.rglob("*") if p.is_file()}
    evidence = out / "authored-pixels"; evidence.mkdir(); image = png(644, 442)
    helper = sha(b"Authored helper identity, not executed")
    baseline = authored(fixture, fixture_files[Path("expected.json")], helper, image)
    checks = []
    result = {"schema": "rebase.structure-window-gate-controls.v1", "outcome": "failed", "checks": checks,
              "evidence_class": "authored-receipt-and-pixel-mutation-controls", "native_wpf_executed": False,
              "helper_executed": False, "physical_input_tested": False, "visual_acceptance_claimed": False,
              "gate_sha256": sha(Path(__file__).with_name("structure_window_gate.py").read_bytes()),
              "instrument_sha256": sha(Path(__file__).read_bytes())}
    def run(name, mutate=None, accept=False, pixels=None, fixture_mutate=None, expected_generator=None):
        value = copy.deepcopy(baseline)
        if mutate: mutate(value)
        for relative, data in fixture_files.items(): (fixture_root / relative).write_bytes(data)
        if fixture_mutate: fixture_mutate(fixture_root)
        for index, file in enumerate(CAPTURES):
            data = pixels if pixels is not None and index == 0 else image
            (evidence / file).write_bytes(data)
            if pixels is not None and index == 0: value["project_structure"]["captures"][0]["sha256"] = sha(data)
        observed = "accepted"
        try: require_structure_window(value, evidence, fixture_root, helper, expected_generator or fixture["generatorSHA256"])
        except ValueError: observed = "rejected"
        passed = observed == ("accepted" if accept else "rejected")
        checks.append({"name": name, "observed": observed, "passed": passed})
        if not passed: raise AssertionError(name + " unexpectedly " + observed)
    try:
        run("valid-authored-control", accept=True)
        def change(name, path, replacement): run(name, lambda v: set_path(v, path, replacement))
        for key in ("tested",): change("missing-" + key, ["project_structure", key], False)
        for key in ("physical_input_tested", "native_file_pickers_tested", "playback_tested"):
            change("unsupported-" + key, ["project_structure", key], True)
        for key in ("fixture_sha256", "helper_sha256"):
            change("unbound-" + key, ["project_structure", key], "f" * 64)
        change("false-input-claim", ["project_structure", "input_evidence"], "physical input")
        change("failed-native-journey", ["outcome"], "failed")
        run("missing-label", lambda v: v["checks"].pop())
        run("duplicate-label", lambda v: v["checks"].append(CHECKS[0]))
        run("reordered-labels", lambda v: v["checks"].reverse())
        run("extra-receipt-field", lambda v: v["project_structure"].update(unmeasured=True))
        run("missing-phase", lambda v: v["project_structure"]["cases"].pop())
        for index in range(3):
            prefix = ["project_structure", "cases", index]
            for label, path, value in (("page-count", ["page_count"], 0), ("report-hash", ["report_sha256"], "f" * 64),
                 ("report-bool-bytes", ["report_bytes"], True), ("inspection-count", ["commands", "inspectProjectStructure"], 0),
                 ("missing-cleanup", ["commands", "closeProjectStructure"], 0), ("unfetched-page", ["commands", "projectStructurePage"], 99),
                 ("opened-revision-drift", ["opened", "revision"], 99), ("closed-state-drift", ["after", "state_sha256"], "f" * 64),
                 ("changed-selection", ["after", "track_id"], str(uuid.UUID(int=99))), ("invented-event", ["after", "clip_id"], str(uuid.UUID(int=99))),
                 ("snapshot-source", ["snapshot", "source_sha256"], "f" * 64), ("snapshot-count", ["snapshot", "tracks"], 2),
                 ("snapshot-manifest", ["snapshot", "manifest_sha256"], "f" * 64), ("snapshot-revision", ["snapshot", "revision"], 88)):
                change(str(index) + "-" + label, prefix + path, value)
        change("clean-has-history", ["project_structure", "cases", 0, "before", "can_undo"], True)
        change("dirty-lost-flag", ["project_structure", "cases", 1, "before", "dirty"], False)
        change("undo-lost-project", ["project_structure", "after_undo", "project_sha256"], "f" * 64)
        change("undo-lost-redo", ["project_structure", "after_undo", "can_redo"], False)
        change("undo-extra-revision", ["project_structure", "after_undo", "revision"], 93)
        change("missing-tab", ["project_structure", "cases", 0, "visited_sections"], list(TABS[:-1]))
        for key in ("is_read_only", "provider_read_only", "write_rejected"):
            change("editable-json-" + key, ["project_structure", "cases", 0, "read_only", key], False)
        change("changed-json", ["project_structure", "cases", 0, "read_only", "after_sha256"], "f" * 64)
        for key, value in (("after_offset", 0), ("last_visible_line", 49), ("viewport_height", 10), ("extent_height", 701.5),
                           ("json_sha256", "f" * 64), ("json_bytes", True), ("read_only", False), ("before_offset", float("nan"))):
            change("scroll-" + key, ["project_structure", "cases", 2, "scroll", key], value)
        run("missing-custody", lambda v: v["project_structure"]["custody"].pop())
        change("custody-changed-copy", ["project_structure", "custody", 1, "copy_sha256"], "f" * 64)
        change("custody-changed-original", ["project_structure", "custody", 3, "original_sha256"], "f" * 64)
        change("custody-bool-bytes", ["project_structure", "custody", 3, "bytes"], True)
        for index in range(2):
            prefix = ["project_structure", "captures", index]
            for label, path, value in (("wrong-file", ["file"], "../outside.png"), ("wrong-report", ["report_sha256"], "f" * 64),
                ("wrong-tab", ["selected_section"], "Overview"), ("false-scope", ["scope"], "effective routing"), ("frame-claim", ["frame_excluded"], False),
                ("wrong-DPI", ["bounds", "dpi_scale_x"], 1.5), ("bool-pixels", ["bounds", "pixel_width"], True),
                ("not-minimum", ["bounds", "outer_width_dip"], 930), ("clipped-close", ["controls", 2, "x"], 620),
                ("hidden-tab", ["controls", 3, "visible"], False), ("disabled-close", ["controls", 2, "enabled"], False),
                ("tiny-report", ["controls", 1, "height"], 50), ("nan-coordinate", ["controls", 1, "x"], float("nan")),
                ("unbound-histogram", ["alpha_coverage", "alpha_255_pixels"], 0), ("nonopaque-root", ["alpha_coverage", "root_background_alpha"], 254)):
                change(str(index) + "-" + label, prefix + path, value)
        for label, field, value in (("tiny-tab-width", "width", 1), ("tiny-tab-height", "height", 1),
                                     ("tab-outside-section", "x", 0), ("tab-over-report", "y", 150)):
            change(label, ["project_structure", "captures", 0, "controls", 3, field], value)
        run("all-tabs-overlap", lambda v: [row.update(x=20,y=102) for row in v["project_structure"]["captures"][0]["controls"][3:]])
        def wrap(value):
            rows = value["project_structure"]["captures"][0]["controls"]
            rows[1].update(y=174,height=194)
            rows[6].update(x=20,y=137);rows[7].update(x=135,y=137)
        run("wrapped-tab-headers-remain-usable", wrap, accept=True)
        run("missing-capture", lambda v: v["project_structure"]["captures"].pop())
        run("missing-alpha", lambda v: v["project_structure"]["captures"][0].pop("alpha_coverage"))
        run("alpha254-measured", lambda v: v["project_structure"]["captures"][0].update(alpha_coverage=coverage(254,644*442)), accept=True, pixels=png(644,442,254))
        run("alpha253-refused", lambda v: v["project_structure"]["captures"][0].update(alpha_coverage=coverage(253,644*442)), pixels=png(644,442,253))
        run("transparent-pixel", lambda v: v["project_structure"]["captures"][0].update(alpha_coverage=coverage(count=644*442, first_alpha=0)), pixels=png(644,442,first_alpha=0))
        run("wrong-pixel-size", pixels=png(643,442))
        run("wrong-PNG-DPI", pixels=png(644,442,dpi=4000))
        run("invalid-filter", pixels=png(644,442,filter_byte=5))
        run("truncated-PNG", pixels=image[:-1])
        run("trailing-PNG", pixels=image+b"extra")
        run("CRC-mismatch", pixels=image[:-1]+bytes([image[-1]^1]))
        run("changed-fixture-source", fixture_mutate=lambda p: (p / "Small.rebaseproj" / PAYLOADS[1]).write_bytes(b"changed"))
        run("changed-full-report", fixture_mutate=lambda p: (p / "Large.structure.json").write_bytes(b"changed"))
        run("changed-manifest", fixture_mutate=lambda p: (p / "Small.rebaseproj/Project.json").write_bytes(b"changed"))
        run("duplicate-fixture-JSON", fixture_mutate=lambda p: (p / "expected.json").write_bytes(b'{"cases":[],"cases":[]}'))
        run("wrong-generator", expected_generator={key:"f"*64 for key in GENERATOR_FILES})
        result["outcome"] = "passed"
    finally:
        for relative, data in fixture_files.items(): (fixture_root / relative).write_bytes(data)
        for file in CAPTURES: (evidence / file).write_bytes(image)
        (out / "authored-baseline.json").write_bytes((json.dumps(baseline,indent=2)+"\n").encode())
        result["control_count"] = len(checks)
        log = ("\n".join(row["name"]+": "+row["observed"] for row in checks)+"\n").encode()
        (out / "controls.log").write_bytes(log); result["controls_log_sha256"] = sha(log)
        (out / "observation.json").write_bytes((json.dumps(result,indent=2)+"\n").encode())
    print(json.dumps({"outcome": result["outcome"], "control_count": len(checks), "native_wpf_executed": False}))


if __name__ == "__main__": main()
