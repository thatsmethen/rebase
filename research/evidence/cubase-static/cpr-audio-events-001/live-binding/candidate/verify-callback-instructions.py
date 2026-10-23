"""Verify callback oracle's original instruction words without target execution."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import runpy
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
verifier = HERE / "verify-mode1-instructions.py"
with contextlib.redirect_stdout(io.StringIO()):
    context = runpy.run_path(str(verifier))
root, original = context["ROOT"], context["original"]
study = root / "research/evidence/cubase-static/cpr-audio-events-001/live-binding"
records = []
for folder, address in [
    ("pass1", "101f2c440"), ("pass2", "101f2cd84"), ("pass2", "101f2d0dc"),
    ("pass3", "101f2cd44"), ("pass3", "101f2cd68"), ("pass3", "101f2cc1c"),
    ("pass3", "101f2cc94"), ("pass3", "101f2ccb8"), ("pass4", "101f17eb8"),
    ("pass5", "101ef386c"), ("pass5", "101ef38c4"),
    ("pass5", "101f16534"), ("pass5", "1037dffcc"),
    ("pass11", "102fc7564"), ("pass12", "102fc756c"),
]:
    path = study / folder / f"native-{address}.txt"
    count = 0
    for match in re.finditer(r"^([0-9a-f]+): ([0-9a-f]{8})\s", path.read_text(), re.M):
        address, word = (int(x, 16) for x in match.groups())
        assert original(address, 4) == struct.pack("<I", word)
        count += 1
    assert count
    records.append(dict(path=str(path.relative_to(root)),
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        original_instruction_words_verified=count))
print(json.dumps(dict(source_sha256=context["source_sha"],
    source_verifier_sha256=hashlib.sha256(verifier.read_bytes()).hexdigest(),
    instructions=sum(x["original_instruction_words_verified"] for x in records),
    original_bytes=sum(x["original_instruction_words_verified"] * 4 for x in records),
    records=records), indent=2))
