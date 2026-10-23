"""Verify original-image custody; never execute the target."""
from pathlib import Path
import hashlib, json, re, struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def envelope(path):
    item = json.loads(path.read_text())
    assert not item.get("isError", False), path
    return item.get("structuredContent") or json.loads(item["content"][0]["text"])


rows, sources, records, duplicate_paths = [], {}, {}, []
for directory in sorted(HERE.glob("pass[0-9]*")):
    derivation = json.loads((directory / "derivation.json").read_text())
    source = Path(derivation["source"])
    if source not in sources:
        sources[source] = source.read_bytes()
    original = sources[source]
    assert hashlib.sha256(original).hexdigest() == derivation["source_sha256"]
    for item in derivation["derivatives"]:
        address = int(item["entry"], 16)
        ident = item["entry"][2:]
        raw = (directory / item["raw_file"]).read_bytes()
        length = item["length"]
        offset = item["source_file_offset"]
        assert raw == original[offset:offset + length]
        assert hashlib.sha256(raw).hexdigest() == item["raw_sha256"]
        native = (directory / item["original_native_disassembly"]).read_text()
        assert hashlib.sha256(native.encode()).hexdigest() == item["native_stdout_sha256"]
        words = {int(a, 16): int(w, 16) for a, w in re.findall(
            r"^([0-9a-f]+):\s+([0-9a-f]{8})\s", native, re.M)}
        assert len(words) == length // 4
        for location, word in words.items():
            assert struct.unpack_from("<I", raw, location - address)[0] == word
        row = dict(entry=item["entry"], directory=str(directory.relative_to(ROOT)),
                   source_file_offset=offset, source_bytes=length,
                   raw_sha256=item["raw_sha256"], native_words=len(words))
        analysis = directory / f"function-{ident}.json"
        if analysis.exists():
            readback = envelope(directory / f"bytes-{ident}.json")["raw_result"]
            assert readback["complete"] and readback["returned_bytes"] == length
            assert bytes.fromhex(readback["bytes_hex"]) == raw
            value = envelope(analysis)["raw_result"]["value"]
            locations = [int(line.split(":")[0], 16) for line in value["assembly"]]
            assert len(set(locations)) == len(locations)
            assert all(location in words for location in locations)
            close = envelope(directory / f"close-{ident}.json")["result"]
            snapshot = directory / f"snapshot-{ident}.json"
            assert Path(close["path"]) == snapshot and snapshot.stat().st_size == close["bytes"]
            bundle = envelope(directory / f"bundle-{ident}.json")["result"]["records"]
            for record in bundle:
                key = record["evidence_id"]
                if key in records:
                    first = json.loads(json.dumps(records[key]))
                    other = json.loads(json.dumps(record))
                    first_path = first["subject"].pop("local_path")
                    other_path = other["subject"].pop("local_path")
                    assert first == other
                    assert Path(first_path).read_bytes() == Path(other_path).read_bytes()
                    duplicate_paths.append(dict(evidence_id=key, retained=first_path,
                                                duplicate=other_path,
                                                only_difference="subject.local_path"))
                else:
                    records[key] = record
            row.update(rea_instruction_addresses=len(locations), readback_exact=True,
                       snapshot_present=True,
                       evidence_ids=[record["evidence_id"] for record in bundle],
                       warnings=[line for line in value["pseudocode"].splitlines()
                                 if "WARNING" in line])
        else:
            row.update(rea_instruction_addresses=0, evidence_ids=[],
                       scope="Native original-image disassembly only")
        rows.append(row)

totals = dict(function_intervals=len(rows),
              unique_entry_addresses=len({row["entry"] for row in rows}),
              source_bytes=sum(row["source_bytes"] for row in rows),
              native_words=sum(row["native_words"] for row in rows),
              rea_dossiers=sum("readback_exact" in row for row in rows),
              rea_instruction_addresses=sum(row["rea_instruction_addresses"] for row in rows),
              unique_evidence_records=len(records))
result = dict(source_sha256=derivation["source_sha256"], functions=rows, totals=totals,
              duplicate_record_paths=duplicate_paths,
              passed=True, target_execution=False,
              scope="Original bytes/native words and REA readbacks/addresses. Metadata intervals "
                    "are not proved reachable bodies. Raw slices omit external code, globals, "
                    "RTTI and unwind context; pseudocode is not compilable original source.")
(HERE / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(totals))
