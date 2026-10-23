#!/usr/bin/env python3
"""Forward-authored overlap parser controls, not native-valid reference projects.

Reuses the sealed APP020 envelope writer, with independent files/clusters per
event and signed priorities. No vendor bytes or proprietary execution are used.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "APP020/generate_track_controls.py"
BASE_SHA = hashlib.sha256(BASE.read_bytes()).hexdigest()
spec = importlib.util.spec_from_file_location("sealed_symbolic_writer", BASE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def path(w, label, filename="Overlap Signal 0.wav"):
    with w.obj(label, "FNPath"):
        w.string(filename); w.u32(0)
        for _ in range(3): w.string("")
        w.u32(1); w.u16(0); w.string("/self-authored-overlap-controls/")


def clip(w, index):
    with w.obj(f"clip{index}", "PAudioClip", 4):
        w.string(f"Overlap source {index}"); w.u32(10); w.f64(1.0/base.RATE); w.u32(0)
        path(w, f"media-path{index}", f"Overlap Signal {index}.wav")
        w.string(""); w.u16(0); w.u32(0); w.f64(0)
        w.u32(2); base.named(w, "TransposeLock", 1, 1)
        w.string("StretchPreset"); w.u16(0x22)
        with w.obj(f"preset{index}", "ElastiquePreset"): pass
        with w.obj(f"cluster{index}", "AudioCluster"):
            w.u32(0); w.u16(2); w.u32(1)
            with w.obj(f"file{index}", "AudioFile", 1):
                w.u64(base.FRAMES); w.u16(24); w.u16(6); w.u16(2); w.f32(base.RATE)
                w.ref(f"media-path{index}"); w.u32(0)
            w.u16(1); w.u32(1)
            with w.obj(f"segment{index}", "AClusterSegment"):
                w.ref(f"file{index}"); w.u64(0); w.u64(base.FRAMES); w.u64(0)
        w.u16(1); w.u32(0)


def event(w, index, event):
    with w.obj(f"event{index}", "MAudioEvent", 6):
        w.u16(0); w.f64(event["ticks"]); w.f64(event["frames"]); w.f64(event["source_frame"])
        clip(w, index)
        w.u32(0); w.integer("i", event["priority"]); w.u32(0); w.u32(0); w.f64(0)
        w.string(event["name"]); w.u32(0); w.f32(1); w.u32(0); w.u16(0)
        with w.obj(f"curve{index}", "VolumeCurveDataNode"):
            w.string(""); w.u32(10); w.f64(1.0/base.RATE); w.u32(0)


base.path = path
base.event = event


def item(name, start, duration, offset, priority=1):
    return dict(name=name, ticks=start*960, frames=duration*base.RATE,
                source_frame=offset*base.RATE, priority=priority)


def sample(frame, channel, file_index):
    return ((frame * (7919 if channel == 0 else 104729)
             + channel * 12345 + file_index * 131071) & 0xfffff) - 524288


def wave(file_index):
    pcm = bytearray(base.FRAMES*6)
    for frame in range(base.FRAMES):
        for channel in range(2):
            at = frame*6+channel*3
            pcm[at:at+3] = (sample(frame, channel, file_index)&0xffffff).to_bytes(3,"little")
    return (b"RIFF"+struct.pack("<I",36+len(pcm))+b"WAVEfmt "
        +struct.pack("<IHHIIHH",16,1,2,base.RATE,base.RATE*6,6,24)
        +b"data"+struct.pack("<I",len(pcm))+pcm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(); args.out.mkdir(exist_ok=False)
    cases = [
        ("equal-crossing", [item("Earlier",1.5,4,2),item("Later",4.5,5,9)], 44100),
        ("nested-tail", [item("Outer",1,10,2,1),item("Inner",3,2,12,2)], 44100),
        ("covered-anchor", [item("Covered",1,2,2),item("Winner",1,4,9)], 44100),
        ("same-start-ties", [item("First",1,2,2),item("Second",1,3,6),item("Third",1,4,9)], 44100),
        ("signed-earlier-wins", [item("Positive",1,6,2,2147483647),item("Negative",3,6,9,-2147483648)], 44100),
        ("signed-later-wins", [item("Negative",1,6,2,-2147483648),item("Positive",3,6,9,2147483647)], 44100),
        ("repeated-splits", [item("Outer",1,12,1,0),item("Hole one",3,1,4,1),
                             item("Hole two",6,2,9,2),item("Hole three",10,1,15,3)], 44100),
        ("saved32k-original-offset", [
            dict(name="Original fractional origin",ticks=1,frames=44100,source_frame=1,priority=1),
            dict(name="Six frame cut",ticks=2,frames=6,source_frame=44100,priority=1)], 32000),
        ("covered-capacity", [item("Invalid covered",1,2,23),item("Winner",1,4,9)], 44100),
        ("reversed-starts", [item("Later start",3,4,2),item("Earlier start",1,6,9)], 44100),
    ]
    manifest = dict(schema_version=1, classification="self-authored parser and sample-composition controls",
        target_executed=False, native_validity_established=False, vendor_bytes_copied=0,
        source_rate=base.RATE, media_frames=base.FRAMES, controls=[], media=[],
        writer=dict(path=str(BASE),sha256=BASE_SHA),
        sample_rule="s24(f,c,i)=((f*(c==0?7919:104729)+c*12345+i*131071)&0xfffff)-524288; Float32=s24/8388608",
        limitations=["Ancillary MAudioTrack, MAutomationNode, PPool and ElastiquePreset bodies remain minimal opaque parser scaffolding.",
                     "These graphs and media are synthetic analytical controls, not native-valid projects or reference runtime output.",
                     "Each counted event has independent clip, cluster, file and media binding so covered contributors can be checked independently."])
    for name, events, rate in cases:
        raw, structure = base.make(events)
        data = bytearray(raw)
        setup = next(x for x in structure["objects"] if x["label"] == "setup")
        rate_offset = setup["payload_offset"] + 48
        assert struct.unpack_from(">f", data, rate_offset)[0] == base.RATE
        struct.pack_into(">f", data, rate_offset, rate)
        dest = args.out/(name+".cpr"); dest.write_bytes(data)
        manifest["controls"].append(dict(name=name, path=dest.name, bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), saved_rate=rate, events=events,
            structure=structure, saved_rate_offset=rate_offset))
    for index in range(max(len(events) for _, events, _ in cases)):
        raw = wave(index); dest = args.out/f"Overlap Signal {index}.wav"; dest.write_bytes(raw)
        manifest["media"].append(dict(index=index,path=dest.name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    manifest["generator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(dict(out=str(args.out),controls=len(cases),media=len(manifest["media"]))))


if __name__ == "__main__": main()
