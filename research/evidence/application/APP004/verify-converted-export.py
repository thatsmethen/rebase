#!/usr/bin/env python3
"""Independent persisted APP004 exchange-file check; no application execution."""
from collections import Counter
from pathlib import Path
import datetime
import io
import json
import os
import runpy
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
HELPER = HERE / "verify-gui-packages.py"
helpers = runpy.run_path(str(HELPER), run_name="package_verification_helpers")
read, sha, require = (helpers[k] for k in ("read", "sha", "require"))
pins = []


def one(node, path):
    found = node.findall(path)
    require(len(found) == 1, f"Expected one XML node: {path}")
    return found[0]


def attributes(node, expected):
    require(node.attrib == expected, f"Unexpected attributes on {node.tag}: {node.attrib}")


def main():
    output = HERE / "converted-exchange-independent-check.json"
    require(not output.exists(), "Refusing to overwrite evidence.")
    previous = helpers["strict_json"](read(HERE / "converted-copy-independent-check.json", pins))
    require(previous["status"] == "passed", "Prior persisted-package verification did not pass.")
    project_path = HERE / "Converted Signature Copy.rebaseproj/Project.json"
    project_bytes = read(project_path, pins)
    prior_pin = [p for p in previous["input_pins"] if p["path"] == str(project_path)]
    require(len(prior_pin) == 1 and sha(project_bytes) == prior_pin[0]["sha256"],
            "Project changed after its independent package check.")
    project = helpers["strict_json"](project_bytes)
    require(project["tempoMap"].get("nativeClock") is None, "Exported project still has a native clock.")
    require(project["tempo"] == 126.5 and len(project["tracks"]) == 1, "Unexpected project tempo/track count.")
    require(project["tracks"][0]["name"] == "Bongos" and not project["tracks"][0]["clips"],
            "Unexpected project track name or clips.")
    meter = project["signatureMap"]["events"]
    require(len(meter) == 1 and meter[0]["beat"] == 0 and (meter[0]["numerator"], meter[0]["denominator"]) == (7, 8),
            "Unexpected project meter.")
    rejected = HERE / "Rejected Native Clock.dawproject"
    require(not os.path.lexists(rejected), "Rejected export destination exists, including as a broken symlink.")
    archive_path = HERE / "Converted Signature Copy.dawproject"
    archive_bytes = read(archive_path, pins, limit=8_388_608)
    entries = []
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        infos = archive.infolist()
        require(len(infos) == 2 and {item.filename for item in infos} == {"project.xml", "metadata.xml"},
                "Expected exactly two XML ZIP members and no media.")
        for item in infos:
            require(not item.is_dir() and item.file_size <= 1_048_576 and not item.flag_bits & 1,
                    "Unsupported ZIP member size/type/encryption.")
            data = archive.read(item)
            require(len(data) == item.file_size, "ZIP member size mismatch.")
            require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(), "DTD/entity declaration is unsupported.")
            entries.append({"name": item.filename, "bytes": len(data), "sha256": sha(data), "crc32": f"{item.CRC:08x}"})
        require(archive.testzip() is None, "ZIP CRC verification failed.")
        xml = ET.fromstring(archive.read("project.xml"))
        metadata = ET.fromstring(archive.read("metadata.xml"))
    require(xml.tag == "Project", "Wrong XML root.")
    attributes(xml, {"version": "1.0"})
    expected_tags = {"Project": 1, "Application": 1, "Transport": 1, "Tempo": 1, "TimeSignature": 1,
                     "Structure": 1, "Track": 1, "Channel": 1, "Mute": 1, "Pan": 1, "Volume": 1,
                     "Arrangement": 1, "Lanes": 2, "Clips": 1, "TempoAutomation": 1, "Target": 2,
                     "RealPoint": 1, "TimeSignatureAutomation": 1, "TimeSignaturePoint": 1}
    require(Counter(node.tag for node in xml.iter()) == expected_tags, "Unexpected XML nodes, clips, audio or automation content.")
    attributes(one(xml, "Application"), {"name": "Rebase", "version": "1"})
    tempo = one(xml, "Transport/Tempo")
    attributes(tempo, {"id": "tempo", "unit": "bpm", "value": "126.5"})
    signature = one(xml, "Transport/TimeSignature")
    attributes(signature, {"id": "signature", "numerator": "7", "denominator": "8"})
    track = one(xml, "Structure/Track")
    attributes(track, {"id": "track0", "name": "Bongos", "contentType": "audio", "loaded": "true"})
    channel = one(track, "Channel")
    attributes(channel, {"id": "channel0", "role": "regular", "audioChannels": "2", "solo": "false"})
    attributes(one(channel, "Mute"), {"value": "false"})
    attributes(one(channel, "Pan"), {"id": "pan0", "unit": "normalized", "value": "0.5"})
    attributes(one(channel, "Volume"), {"id": "gain0", "unit": "decibel", "value": "0.0"})
    arrangement = one(xml, "Arrangement")
    attributes(arrangement, {"name": project["name"], "comment": "Rebase.sampleRate=48000.0"})
    lanes = one(arrangement, "Lanes")
    attributes(lanes, {"timeUnit": "seconds"})
    lane = one(lanes, "Lanes")
    attributes(lane, {"track": track.attrib["id"]})
    clips = one(lane, "Clips")
    require(not list(clips) and clips.attrib == {}, "Expected an empty Clips element.")
    tempo_points = one(arrangement, "TempoAutomation")
    attributes(tempo_points, {"timeUnit": "beats", "unit": "bpm"})
    attributes(one(tempo_points, "Target"), {"parameter": tempo.attrib["id"]})
    attributes(one(tempo_points, "RealPoint"), {"time": "0.0", "value": "126.5", "interpolation": "hold"})
    signature_points = one(arrangement, "TimeSignatureAutomation")
    attributes(signature_points, {"timeUnit": "beats"})
    attributes(one(signature_points, "Target"), {"parameter": signature.attrib["id"]})
    attributes(one(signature_points, "TimeSignaturePoint"), {"time": "0.0", "numerator": "7", "denominator": "8"})
    require(metadata.tag == "MetaData" and len(list(metadata)) == 1 and one(metadata, "Title").text == project["name"],
            "Metadata title differs from persisted project.")
    historical = helpers["compare_history"](HERE / "historical-packages-before.json", pins)
    result = {
        "id": "APP004-INDEPENDENT-CONVERTED-EXCHANGE-CHECK", "status": "passed",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verifier": {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__).read_bytes()),
                     "helper_path": str(HELPER), "helper_sha256": sha(HELPER.read_bytes())},
        "input_pins": pins,
        "persisted_project_scope": {"unchanged_since_package_check": True, "native_clock_absent": True,
                                    "tempo_bpm": 126.5, "meter": [7, 8], "track_names": ["Bongos"], "clip_count": 0},
        "archive_xml_scope": {"members": entries, "zip_crc_checks_passed": True, "transport_bpm": 126.5,
                              "tempo_point": {"beat": 0, "bpm": 126.5, "interpolation": "hold"},
                              "transport_meter": [7, 8], "signature_point": {"beat": 0, "meter": [7, 8]},
                              "track_count": 1, "track_names": ["Bongos"], "clip_count": 0,
                              "audio_element_count": 0, "media_member_count": 0,
                              "arrangement_time_unit": "seconds", "automation_time_unit": "beats",
                              "track_and_parameter_references_resolve": True},
        "rejected_destination_scope": {"path": str(rejected), "absent_including_broken_symlink": True,
                                       "limit": "Absence at inspection time; rejection action and alert provenance are parent-owned GUI evidence."},
        "historical_packages": historical,
        "limits": ["No Cubase execution, Cubase import/export interoperability test, or reference runtime comparison.",
                   "No media, clips or audible mix are present; this verifies a one-track empty project exchange subset.",
                   "XML was parsed and its exact expected subset checked; no external XSD validator or receiving DAW was run.",
                   "The historical import report records source/native interpretation; the exchanged current project uses explicitly converted application timing."]}
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print("passed", output, sha(output.read_bytes()))


if __name__ == "__main__":
    main()
