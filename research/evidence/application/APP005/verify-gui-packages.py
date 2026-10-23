#!/usr/bin/env python3
"""Read-only APP005 LoFi V3 package/export checks; no application execution.

snapshot --out historical-before.json
verify --package NAME.rebaseproj --historical-before BEFORE.json --out CHECK.json
       [--project-clock converted] [--allow-project-name-change]
       [--copied-from ORIGINAL.rebaseproj --source-check ORIGINAL-CHECK.json]
export --package COPY.rebaseproj --package-check COPY-CHECK.json
       --archive COPY.dawproject --rejected REJECTED.dawproject
       --historical-before BEFORE.json --out EXPORT-CHECK.json

Only the pinned LoFi factory fixture is accepted. Evidence is exclusive-create;
project/source/archive files are never written. GUI provenance remains separate.
"""
from collections import Counter
from pathlib import Path
import argparse
import copy
import datetime
import hashlib
import io
import json
import os
import runpy
import stat
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
HELPER = HERE.parent / "APP004/verify-gui-packages.py"
HELPER_SHA = "7f50390b48f444fee9b324fe8ccc832e41cc8cb78d25b6150a53b833819acf6c"
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == HELPER_SHA
helpers = runpy.run_path(str(HELPER), run_name="frozen_app004_read_helpers")
read, sha, require, strict_json, number, object_map, signature_values, VerificationError = (
    helpers[k] for k in ("read", "sha", "require", "strict_json", "number", "object_map", "signature_values", "VerificationError"))
FILES = ("Project.json", "Compatibility/CPR/ImportReport.json", "Compatibility/CPR/Original.cpr")
HISTORY = {
    "APP003": ("Classic House Recovery.rebaseproj", "Stereo Mastering Recovery.rebaseproj", "Stereo Mastering Copy.rebaseproj"),
    "APP004": ("Classic House Native.rebaseproj", "Concordant Signature Recovery.rebaseproj", "Converted Signature Copy.rebaseproj")}
FIXTURE = ROOT / "research/evidence/cubase-static/cpr-signature-001/fixtures/lofi-hip-hop-signature-v01.json"
FIXTURE_SHA = "c02452af0b257358622fe183b1f99382dd38471ae935e5fb840d483f133d6596"
SOURCE_SHA = "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495"
PROFILE = "cpr-static-subset-v3"
CONTRACT = "cubase-15.0.30.287-arm64-jump-map-v1"


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def package_inventory(package):
    package = resolve(package)
    require(package.is_dir() and package.resolve() == package, "Missing or redirected package.")
    actual = set()
    for path in package.rglob("*"):
        require(not path.is_symlink(), "Package contains symlink.")
        if path.is_file():
            actual.add(str(path.relative_to(package)))
    require(actual == set(FILES), "Expected exactly manifest/report/original and no copied media or extra files.")


def snapshot():
    pins = []
    for version, names in HISTORY.items():
        for name in names:
            package = HERE.parent / version / name
            package_inventory(package)
            for relative in FILES:
                read(package / relative, pins)
    return pins


def history(before, pins):
    record = strict_json(read(before, pins))
    require(record.get("id") == "APP005-HISTORICAL-SNAPSHOT" and record.get("status") == "passed", "Wrong before snapshot.")
    current = snapshot()
    require(current == record["historical_files"], "Historical APP003/APP004 package bytes changed.")
    return {"unchanged": True, "file_count": len(current), "files": current}


def prior_package_check(check_path, package, pins):
    previous = strict_json(read(check_path, pins))
    require(previous.get("id") == "APP005-PERSISTED-CHECK" and previous.get("status") == "passed", "Prior package check did not pass.")
    require(previous.get("command") == "verify", "Expected a package verification result.")
    for relative in FILES:
        path = str(resolve(package) / relative)
        matches = [p for p in previous["input_pins"] if p["path"] == path]
        require(matches and len({p["sha256"] for p in matches}) == 1, "Missing or conflicting prior package pin.")
        require(sha(read(path, pins)) == matches[0]["sha256"], "Package changed since its independent check.")


def verify(args, pins):
    package = resolve(args.package)
    package_inventory(package)
    fixture_bytes = read(FIXTURE, pins)
    require(sha(fixture_bytes) == FIXTURE_SHA, "Independent fixture changed.")
    fixture = strict_json(fixture_bytes)
    require(fixture["tool"] == "cpr_probe/0.3" and fixture["target_executed"] is False, "Wrong fixture scope.")
    source = read(fixture["source"], pins)
    require(sha(source) == fixture["sha256"] == SOURCE_SHA and len(source) == fixture["bytes"], "Source pin differs.")
    original = read(package / FILES[2], pins)
    require(original == source, "Original.cpr differs from independently pinned LoFi source.")
    report_bytes = read(package / FILES[1], pins, limit=8_388_608)
    report = strict_json(report_bytes)
    project = strict_json(read(package / FILES[0], pins, limit=8_388_608))
    require(report["schemaVersion"] == 2 and report["interpretationProfile"] == PROFILE, "Wrong report schema/profile.")
    require(report["sourceSHA256"] == SOURCE_SHA and report["sourceByteCount"] == len(source)
            and report["sourceName"] == "LoFi Hip Hop.cpr", "Report source binding differs.")
    baseline = report["recoveredProject"]
    require(isinstance(baseline, dict), "No recovered baseline.")
    expected = copy.deepcopy(baseline)
    if args.project_clock == "converted":
        require(expected["tempoMap"].get("nativeClock") is not None, "Baseline had no clock to convert.")
        del expected["tempoMap"]["nativeClock"]
    if args.allow_project_name_change:
        expected["name"] = project["name"]
    require(project == expected, "Project differs beyond allowed name and explicit clock conversion.")
    objects = object_map(fixture, source)
    identities = set()
    structurally_compared = 0
    for obj in report["nativeObjects"]:
        identity, start, size = obj["identityOffset"], obj["payloadOffset"], obj["payloadByteCount"]
        require(identity not in identities and start == identity + 4 and number(source, ">I", identity) == size,
                "Duplicate object identity or invalid length framing.")
        identities.add(identity)
        require(0 <= start <= start + size <= len(source) and sha(source[start:start+size]) == obj["payloadSHA256"], "Object payload differs.")
        if identity in objects:
            structurally_compared += 1
            for left, right in (("className", "class"), ("version", "version"), ("declarationOffset", "class_declaration_offset"),
                                ("objectOffset", "offset"), ("payloadOffset", "body_offset"), ("payloadByteCount", "body_bytes")):
                require(obj[left] == objects[identity][right], "Fixture/report object framing differs.")
    tempo = objects[754]
    require(tempo["class"] == "MTempoTrackEvent" and tempo["version"] == 3 and tempo["body_offset"] == 758,
            "Wrong independent tempo object.")
    require(number(source, ">I", 758) == 2 and number(source, ">H", 810) == 0, "Wrong count/map-mode word.")
    records = []
    for at, wanted in [(762, (0x3f400000, 0, 0, 0)), (784, (0x3f000000, 0x4082c00000000000, 0x4117700000000000, 0))]:
        actual = struct.unpack_from(">IQQH", source, at)
        require(actual == wanted, "Direct period/anchor/kind bytes differ.")
        records.append(dict(periodBits=actual[0], secondsBits=actual[1], tickBits=actual[2], kind=actual[3], sourceRecordOffset=at))
    clock = dict(contract=CONTRACT, fixedBPMBits=0, mapRecords=records, sourceSHA256=SOURCE_SHA,
                 sourceObjectOffset=754, interpretationProfile=PROFILE)
    require(report.get("nativeClock") == baseline["tempoMap"].get("nativeClock") == clock, "Report/baseline descriptor differs from original bytes.")
    require(project["tempoMap"].get("nativeClock") == (None if args.project_clock == "converted" else clock), "Wrong current clock state.")
    events = project["tempoMap"]["events"]
    require([(e["beat"], e["bpm"], e["curve"]) for e in events] == [(0,80,"jump"),(800,120,"jump")]
            and project["tempo"] == 80 and project["sampleRate"] == 48000, "Wrong map projection or application sample-rate default.")
    tracks = project["tracks"]
    require(len(tracks) == 1 and tracks[0]["name"] == "Vinyl Crackle" and tracks[0]["clips"] == [], "Expected one empty recovered audio track.")
    track = tracks[0]
    require(track["gainDB"] == track["pan"] == 0 and not track["isMuted"] and not track["isSolo"]
            and track["automation"] == [] and track["timeBase"] == "seconds", "Unexpected recovered mixer/automation state.")
    audio_rows = [t for t in report["recoveredTracks"] if t["kind"] == "Audio"]
    require(len(audio_rows) == 1 and audio_rows[0]["sourceOffset"] == 197637
            and audio_rows[0]["importedTrackID"] == track["id"], "Recovered track/source identity mismatch.")
    require(any(u["category"] == "Unresolved audio source" and "vstsound://" in u["detail"]
                and "Lofi_Ambience_16_Vinyl_Crackle_LD.wav" in u["detail"] for u in report["unsupported"]), "Missing unresolved-source disclosure.")
    require(any("Recovered 2 native jump-tempo points" in f for f in report["recoveredFacts"]), "Missing map fact.")
    require(not any("120 BPM is an application default" in f for f in report["applicationDefaults"]), "False default-tempo claim.")
    signature, meter, _ = signature_values(source, objects)
    require(signature["size_offset"] in identities and meter == (4,4), "Wrong origin meter.")
    require([(s["beat"],s["numerator"],s["denominator"]) for s in project["signatureMap"]["events"]] == [(0,4,4)], "Saved meter differs.")
    if args.copied_from:
        require(args.source_check is not None, "Copy verification requires source check to prove original package unchanged.")
        prior_package_check(args.source_check, args.copied_from, pins)
        for relative, expected_bytes in [(FILES[1],report_bytes),(FILES[2],original)]:
            require(read(resolve(args.copied_from)/relative,pins) == expected_bytes, "Save As changed compatibility bytes.")
    return {"source_sha256":SOURCE_SHA,"source_byte_identical":True,"profile":PROFILE,
            "clock_state":args.project_clock,"descriptor":clock,"tempo_projection":[[0,80],[800,120]],
            "native_objects_hash_checked":len(identities),"objects_matched_to_independent_fixture":structurally_compared,
            "track_names":["Vinyl Crackle"],"clips":0,"meter":[4,4],"copied_from":str(args.copied_from) if args.copied_from else None}


def one(node, path):
    found = node.findall(path)
    require(len(found) == 1, "Expected one XML node: " + path)
    return found[0]


def attributes(node, expected):
    require(node.attrib == expected, "Unexpected XML attributes: " + node.tag)


def export(args,pins):
    prior_package_check(args.package_check,args.package,pins)
    project = strict_json(read(resolve(args.package)/FILES[0],pins))
    require(project["tempoMap"].get("nativeClock") is None, "Native clock still attached.")
    require(not os.path.lexists(resolve(args.rejected)), "Rejected export destination exists.")
    data = read(args.archive,pins,limit=8_388_608)
    members=[]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos=archive.infolist()
        require(len(infos)==2 and {i.filename for i in infos}=={"project.xml","metadata.xml"}, "Unexpected ZIP inventory.")
        for item in infos:
            require(not item.is_dir() and not stat.S_ISLNK(item.external_attr >> 16) and not item.flag_bits&1
                    and item.file_size<=1_048_576, "Unsupported ZIP member.")
            body=archive.read(item)
            require(len(body)==item.file_size and b"<!DOCTYPE" not in body.upper() and b"<!ENTITY" not in body.upper(), "Unsafe or truncated XML.")
            members.append({"name":item.filename,"sha256":sha(body),"bytes":len(body),"crc32":f"{item.CRC:08x}"})
        require(archive.testzip() is None,"ZIP CRC failed.")
        xml=ET.fromstring(archive.read("project.xml"));metadata=ET.fromstring(archive.read("metadata.xml"))
    require(xml.tag=="Project","Wrong XML root.");attributes(xml,{"version":"1.0"})
    tags={"Project":1,"Application":1,"Transport":1,"Tempo":1,"TimeSignature":1,"Structure":1,
          "Track":1,"Channel":1,"Mute":1,"Pan":1,"Volume":1,"Arrangement":1,"Lanes":2,"Clips":1,
          "TempoAutomation":1,"Target":2,"RealPoint":2,"TimeSignatureAutomation":1,"TimeSignaturePoint":1}
    require(Counter(n.tag for n in xml.iter())==tags,"Unexpected XML nodes/content.")
    attributes(one(xml,"Application"),{"name":"Rebase","version":"1"})
    attributes(one(xml,"Transport/Tempo"),{"id":"tempo","unit":"bpm","value":"80.0"})
    attributes(one(xml,"Transport/TimeSignature"),{"id":"signature","numerator":"4","denominator":"4"})
    attributes(one(xml,"Structure/Track"),{"id":"track0","name":"Vinyl Crackle","contentType":"audio","loaded":"true"})
    channel=one(xml,"Structure/Track/Channel")
    attributes(channel,{"id":"channel0","role":"regular","audioChannels":"2","solo":"false"})
    attributes(one(channel,"Mute"),{"value":"false"});attributes(one(channel,"Pan"),{"id":"pan0","unit":"normalized","value":"0.5"})
    attributes(one(channel,"Volume"),{"id":"gain0","unit":"decibel","value":"0.0"})
    arrangement=one(xml,"Arrangement");attributes(arrangement,{"name":project["name"],"comment":"Rebase.sampleRate=48000.0"})
    lanes=one(arrangement,"Lanes");attributes(lanes,{"timeUnit":"seconds"});attributes(one(lanes,"Lanes"),{"track":"track0"})
    clips=one(lanes,"Lanes/Clips");require(not list(clips) and clips.attrib=={},"Unexpected clips.")
    tempo=one(arrangement,"TempoAutomation");attributes(tempo,{"timeUnit":"beats","unit":"bpm"})
    attributes(one(tempo,"Target"),{"parameter":"tempo"})
    require([p.attrib for p in tempo.findall("RealPoint")]==[
        {"time":"0.0","value":"80.0","interpolation":"hold"},
        {"time":"800.0","value":"120.0","interpolation":"hold"}],"Wrong exported tempo points.")
    meter=one(arrangement,"TimeSignatureAutomation");attributes(meter,{"timeUnit":"beats"})
    attributes(one(meter,"Target"),{"parameter":"signature"});attributes(one(meter,"TimeSignaturePoint"),{"time":"0.0","numerator":"4","denominator":"4"})
    require(metadata.tag=="MetaData" and len(list(metadata))==1 and one(metadata,"Title").text==project["name"],"Wrong metadata title.")
    return {"members":members,"crc_passed":True,"tempo_points":[[0,80,"hold"],[800,120,"hold"]],
            "native_clock_absent":True,"track_names":["Vinyl Crackle"],"clips":0,"media_members":0,
            "rejected_destination_absent":str(resolve(args.rejected)),"limits":"No receiving DAW or XSD validator executed; no native-clock equivalence claimed after explicit conversion."}


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("snapshot").add_argument("--out",required=True,type=Path)
    for command in ["verify","export"]:
        p=commands.add_parser(command);p.add_argument("--package",required=True,type=Path)
        p.add_argument("--historical-before",required=True,type=Path);p.add_argument("--out",required=True,type=Path)
        if command=="verify":
            p.add_argument("--project-clock",choices=["recovered","converted"],default="recovered")
            p.add_argument("--allow-project-name-change",action="store_true")
            p.add_argument("--copied-from",type=Path);p.add_argument("--source-check",type=Path)
        else:
            for flag in ["package-check","archive","rejected"]:p.add_argument("--"+flag,required=True,type=Path)
    args=parser.parse_args();out=resolve(args.out)
    require(not os.path.lexists(out) and not any(p.endswith(".rebaseproj") for p in out.parts),"Invalid/existing evidence output.")
    result={"id":"APP005-HISTORICAL-SNAPSHOT" if args.command=="snapshot" else "APP005-PERSISTED-CHECK",
            "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"command":args.command,
            "verifier_sha256":sha(Path(__file__).read_bytes()),"helper_sha256":HELPER_SHA,"input_pins":[],
            "limits":["Read-only persisted-byte checks; no application or Cubase execution.","GUI action provenance, native lifecycle proof and runtime conformance are separate."]}
    try:
        if args.command=="snapshot":result["historical_files"]=snapshot()
        else:
            result["checks"]=(verify if args.command=="verify" else export)(args,result["input_pins"])
            result["historical_packages"]=history(args.historical_before,result["input_pins"])
        result["status"]="passed"
    except (VerificationError,OSError,ValueError,KeyError,TypeError,struct.error,zipfile.BadZipFile,ET.ParseError) as error:
        result["status"]="failed";result["error"]=str(error)
    with out.open("x") as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write("\n")
    print(result["status"],out,sha(out.read_bytes()))
    return 0 if result["status"]=="passed" else 1


if __name__=="__main__":sys.exit(main())
