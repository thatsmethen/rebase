#!/usr/bin/env python3
"""Prepare independent Rebase rate controls without altering preserved CPR."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "research/evidence/application/APP010/LoFi Rate QA.rebaseproj"
BASELINE = ROOT / "research/evidence/application/APP010/gui-package-before.json"


def digest(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    baseline = json.loads(BASELINE.read_text())
    for row in baseline["files"]:
        assert digest(SOURCE / row["path"]) == {k: row[k] for k in ["bytes", "sha256"]}
    controls = []
    for name, rate in [
        ("LoFi Downsample QA", 32000),
        ("LoFi High Ratio Downsample QA", 16000),
        ("LoFi Equal Rate QA", 44100),
    ]:
        destination = OUT / (name + ".rebaseproj")
        shutil.copytree(SOURCE, destination)
        path = destination / "Project.json"
        manifest = json.loads(path.read_text())
        manifest["name"] = name
        manifest["sampleRate"] = rate
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        files = [{"path": str(p.relative_to(destination)), **digest(p)}
                 for p in sorted(destination.rglob("*")) if p.is_file()]
        for row in files:
            if row["path"] != "Project.json":
                expected = next(r for r in baseline["files"] if r["path"] == row["path"])
                assert row == expected
        controls.append({
            "copy": str(destination.relative_to(ROOT)), "source_rate": 44100,
            "project_rate": rate, "files": files,
        })
    with (OUT / "gui-package-baselines.json").open("x") as stream:
        json.dump({
            "construction": "Exact copy of accepted APP010 synthetic-media package; only independent Rebase Project.json name/sampleRate changed. CPR, import report and media remain byte-identical.",
            "source": str(SOURCE.relative_to(ROOT)),
            "source_baseline": {"path": str(BASELINE.relative_to(ROOT)), **digest(BASELINE)},
            "controls": controls,
        }, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"prepared_controls": len(controls), "unchanged_cpr_report_media": True}))


if __name__ == "__main__":
    main()
