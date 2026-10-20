#!/usr/bin/env python3
"""Verify upstream bytes; explicit opt-out permits LGPL source modifications."""
import hashlib
import json
import os
from pathlib import Path

base = Path(__file__).resolve().parent
root = base / "soxr-0.1.3"
manifest = json.loads((base / "soxr-source-manifest.json").read_text())
errors = []
expected = {row["path"] for row in manifest["files"]}
actual = {str(p.relative_to(root)) for p in root.rglob("*")
          if p.is_file() or p.is_symlink()}
if actual != expected:
    errors.append("source entry set differs")
for row in manifest["files"]:
    path = root / row["path"]
    if "symlink" in row:
        if not path.is_symlink() or os.readlink(path) != row["symlink"]:
            errors.append(row["path"])
    elif path.is_symlink() or not path.is_file():
        errors.append(row["path"])
    elif hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        errors.append(row["path"])
if errors and os.environ.get("REBASE_SOXR_ALLOW_MODIFIED_SOURCE") != "1":
    raise SystemExit("SoXR source mismatch: " + ", ".join(errors))
print("Public SoXR source: " + ("explicit modified-source build" if errors else
      f"verified {len(expected)} pinned entries"))
