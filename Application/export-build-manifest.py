#!/usr/bin/env python3
"""Export relative build provenance; leave the original local manifest intact."""
import hashlib
import json
from pathlib import Path
import re
import sys

source, destination = map(Path, sys.argv[1:])
raw = source.read_bytes()
record = json.loads(raw)
build_root = source.resolve().parent
old_library = record["library"]["path"]
for key in ("library", "compile_commands", "configured_header"):
    record[key]["path"] = Path(record[key]["path"]).resolve().relative_to(build_root).as_posix()
for key in ("dependencies", "load_commands"):
    record[key] = record[key].replace(old_library, record["library"]["path"])
record["compiler"] = "\n".join(line for line in record["compiler"].splitlines()
                                  if not line.startswith("InstalledDir:"))
record["sdk_path"] = Path(record["sdk_path"]).name
record["publication"] = {
    "path_policy": "Build artifacts are relative to the build directory; SDK basename only; compiler installation directory omitted.",
    "local_manifest_sha256": hashlib.sha256(raw).hexdigest(),
    "local_manifest_included": False,
}
public = json.dumps(record, indent=2, sort_keys=True) + "\n"
if re.search(r"/(?:Users|home)/|/(?:private/)?var/folders/", public):
    raise SystemExit("Personal filesystem path remains in public build manifest")
destination.write_text(public)
