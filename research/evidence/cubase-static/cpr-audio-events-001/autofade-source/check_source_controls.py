"""Bounded mutations challenge structural ownership; all copies stay in memory."""
from pathlib import Path
import hashlib
import json
import struct
import probe_source as p

base = p.ROOT / "research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/Cubase 15.app/Contents/Project Templates/Cubase Pro"
fixtures = json.loads((p.HERE / "source-forward-probe.json").read_text())["fixtures"]
results = []
for baseline in fixtures:
    data = (base / (baseline["fixture"] + ".cpr")).read_bytes()
    assert hashlib.sha256(data).hexdigest() == baseline["source_sha256"]
    setting = baseline["project"]["setting"]
    track = baseline["tracks"][0]
    descriptor = setting["object"]
    cases = [
        ("project_flags_nonzero", setting["flags_offset"], ">H", 1, "nonzero_flags"),
        ("project_duration_nonfinite", setting["duration_offset"], ">Q", 0x7ff8000000000000, "reject"),
        ("setting_unknown_version", descriptor["size_offset"]-2, ">H", 1, "reject"),
        ("negative_root_attribute_count", baseline["root_attribute_tail"]["count_offset"], ">i", -1, "reject"),
        ("unsupported_root_attribute_type", baseline["root_attribute_tail"]["fields"][0]["offset"]+4, ">H", 0x100, "reject"),
        ("local_setting_wrong_class", track["local"]["token"]["offset"], ">I", track["resource"]["relative_object_identity"], "reject"),
        ("local_setting_unknown_reference", track["local"]["token"]["offset"], ">I", 0x7fffffff, "reject"),
        ("loudness_wrong_class", baseline["loudness"]["offset"], ">I", track["resource"]["relative_object_identity"], "reject"),
        ("negative_keyed_event_count", baseline["root_event_table"]["offset"], ">h", -1, "reject"),
        ("track_word_remains_opaque", track["word_offset"], ">i", track["word"]+1, "raw_word"),
    ]
    for name, offset, fmt, value, expected in cases:
        mutated = bytearray(data)
        struct.pack_into(fmt, mutated, offset, value)
        try:
            actual = p.inspect(bytes(mutated))
        except (ValueError, struct.error) as error:
            assert expected == "reject", (name, str(error))
            outcome = dict(rejected=True, reason=str(error))
        else:
            assert expected != "reject", name
            if expected == "nonzero_flags":
                assert actual["tracks"][0]["effective_flags"] == 1
                assert not actual["tracks"][0]["zero_flag_bypass"]
            elif expected == "raw_word":
                assert actual["tracks"][0]["word"] == value
                assert actual["tracks"][0]["zero_flag_bypass"]
            outcome = dict(rejected=False, effective_flags=actual["tracks"][0]["effective_flags"],
                           zero_flag_bypass=actual["tracks"][0]["zero_flag_bypass"],
                           opaque_track_word=actual["tracks"][0]["word"])
        results.append(dict(fixture=baseline["fixture"], name=name, changed_offset=offset,
            original_bytes=data[offset:offset+struct.calcsize(fmt)].hex(),
            changed_bytes=mutated[offset:offset+struct.calcsize(fmt)].hex(),
            mutated_sha256=hashlib.sha256(mutated).hexdigest(), expected=expected,
            outcome=outcome, passed=True))
with (p.HERE / "source-controls.json").open("x") as output:
    json.dump(dict(target_executed=False, original_sources_unchanged=True,
        count=len(results), controls=results,
        limits="These are parser and zero-flag classification controls, not measured audio tests."), output, indent=2)
    output.write("\n")
print(json.dumps(dict(controls=len(results), passed=True)))
