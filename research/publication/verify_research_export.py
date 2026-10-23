#!/usr/bin/env python3
"""Verify distributed research copies, including declared privacy derivatives."""
from pathlib import Path
import hashlib
import json


def main():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((Path(__file__).parent / "research-export-manifest.json").read_text())
    seen = set()
    size = 0
    for item in manifest["included"]:
        relative = Path(item["published_path"])
        if relative.is_absolute() or ".." in relative.parts or str(relative) in seen:
            raise ValueError(f"Invalid or duplicate published path: {relative}")
        seen.add(str(relative))
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Unexpected symbolic link: {relative}")
        data = path.read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Published record changed: {relative}")
        size += len(data)
    if len(seen) != manifest["summary"]["included_count"] or size != manifest["summary"]["included_bytes"]:
        raise ValueError("Manifest totals do not match its entries")
    print(json.dumps({"verified_published_files": len(seen), "verified_bytes": size,
                      "omitted_artifacts_not_verified": len(manifest["excluded"])}))


if __name__ == "__main__":
    main()
