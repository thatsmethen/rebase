"""Independent retained-accessor arithmetic and sample-call expectations.

No application accessor or candidate C computes expectations. Seek/budget use
integer/Fraction IEEE rounding; mode1 reuses the original independent tap model;
mode2 uses the original independent wrapper plus the pinned public backend.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IEEE_PATH = HERE.parent / "APP010/native-rate-mode0-oracle.py"
MODE1_PATH = HERE.parent / "APP013/mode1-oracle.py"
PUBLIC_PATH = HERE.parent / "APP012/mode2-public-oracle.py"
FORMAT_PATH = HERE / "accessor-pcm24-oracle.py"
ieee = load("accessor_ieee", IEEE_PATH)
mode1 = load("accessor_mode1", MODE1_PATH)
public = load("accessor_public", PUBLIC_PATH)
format24 = load("accessor_format", FORMAT_PATH)
rn, bits, f32, value32 = ieee.rn, ieee.bits, ieee.f32, ieee.sample_value


def record(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def seek(source, output, frame):
    if source == output:
        ratio, product, stored, quotient = F(1), F(frame), frame, F(frame)
    else:
        ratio = value32(f32(F(source, output)))
        product = rn(rn(frame) * ratio)
        stored = int(product)
        quotient = rn(rn(stored) / ratio)
    return dict(source_rate=source, output_rate=output, requested_frame=frame,
                ratio_bits=f"{f32(ratio):08x}", source_product_bits=f"{bits(product):016x}",
                source_frame=stored, returned_frame=int(quotient), quotient_bits=f"{bits(quotient):016x}")


def budget(source, output, request, allowance):
    if source == output:
        return request
    r = rn(F(output, source))
    extra = 2048 * (-(-r.numerator // r.denominator)) if allowance else 0
    total = request + extra
    product = rn(rn(F(source, output)) * total)
    count = -(-product.numerator // product.denominator)
    while int(rn(r * count)) > total:
        count -= 1
    return count


def samples(frames):
    # Every input is exactly on the PCM24 grid; channel-distinct and nonperiodic
    # over the tested short windows, with no implicit gain operation.
    return [f32(F(((frame * (37 if channel == 0 else 71) + channel * 19) % 4093) - 2046, 8192))
            for frame in range(frames) for channel in range(2)]


def scenario(name, source_rate, output_rate, source_frames, converter, source_format, available, operations):
    source = samples(source_frames)
    child = None
    backend = None
    first = True
    position = 0
    steps = []
    for kind, number in operations:
        if kind == "seek":
            mapping = seek(source_rate, output_rate, number)
            assert mapping["source_frame"] <= source_frames
            position = mapping["source_frame"]
            steps.append(dict(operation="seek", requested=number, returned=mapping["returned_frame"],
                              source_position=position, first=first))
            continue
        old_first = first
        converting = source_rate != output_rate
        requested = number
        count = budget(source_rate, output_rate, requested, first and available)
        if converting or source_format == "pcm24":
            first = False
        actual = min(count, source_frames - position)
        terminal = converting and actual == source_frames - position and old_first and actual < count
        input_bits = source[position * 2:(position + actual) * 2]
        if count == 0:
            output = []
        elif not converting:
            output = input_bits
        elif converter == "mode1":
            if child is None:
                child = mode1.Model(source_rate, output_rate, 2)
            result = child.process(actual, terminal, input_bits)
            output = [int(x, 16) for x in result["output_f32_bits"]]
        else:
            if child is None:
                backend = public.PublicBackend(source_rate, output_rate, 2)
                child = public.model.Wrapper(source_rate, output_rate, 2, backend)
            output = child.process(input_bits if actual else None, terminal)
        if source_format == "pcm24" and source_rate > output_rate:
            output = [int(format24.project(x)["output_f32_bits"], 16) for x in output]
        position += actual
        steps.append(dict(operation="read", requested=requested, budget=count, actual=actual,
                          first_call=old_first, first=first, terminal=terminal,
                          source_position=position, returned=len(output)//2,
                          output_f32_bits=[f"{x:08x}" for x in output]))
    if backend:
        backend.close()
    return dict(name=name, source_rate=source_rate, output_rate=output_rate, source_frames=source_frames,
                converter=converter, source_format=source_format, mode2_budget_available=available,
                input_f32_bits=[f"{x:08x}" for x in source], steps=steps)


def main():
    seeks = []
    for source, output in [(44100,48000),(48000,44100),(44100,32000),(44100,16000),(8000,192000),(192000,8000),(44100,44100)]:
        for frame in [0,1,2,7,127,8191,8192,8193,44100,48000,1058400,2**31-1,2**31,2**53-1,2**53]:
            seeks.append(seek(source, output, frame))
    assert seek(44100,48000,48000)["source_frame"] == 44099
    assert seek(44100,48000,48000)["returned_frame"] == 47998
    scenarios = [
        scenario("mode1-up-retained-nonsequential",44100,48000,1024,"mode1","float32",False,
                 [("read",129),("seek",200),("read",73),("seek",0),("read",97),("read",17)]),
        scenario("mode1-down-packed24",48000,44100,1024,"mode1","pcm24",False,
                 [("read",129),("seek",200),("read",73),("seek",0),("read",97)]),
        scenario("mode2-up-retained-nonsequential",44100,48000,6000,"mode2","float32",True,
                 [("read",129),("seek",1000),("read",257),("seek",0),("read",257)]),
        scenario("mode2-down-packed24",48000,44100,6000,"mode2","pcm24",True,
                 [("read",129),("seek",1000),("read",257),("seek",0),("read",257)]),
        scenario("mode1-zero-budget-consumes-first",8000,192000,16,"mode1","float32",False,
                 [("read",1),("seek",0),("read",24),("seek",0),("read",48)]),
        scenario("mode1-first-short-terminal",44100,48000,129,"mode1","float32",False,[("read",512)]),
        scenario("mode2-first-short-terminal",44100,48000,129,"mode2","float32",True,[("read",512)]),
        scenario("mode1-full-eof-is-not-terminal",8000,16000,129,"mode1","float32",False,[("read",258),("read",2)]),
        scenario("equal-float32-direct",44100,44100,32,"mode2","float32",True,[("seek",7),("read",11),("read",32)]),
        scenario("equal-pcm24-format-path",44100,44100,32,"mode1","pcm24",True,[("seek",7),("read",11),("read",32)]),
    ]
    report = dict(schema_version=1, scope="Independent retained seek/read sequences for an explicit fixed-rate/format accessor; no proprietary runtime or source-rate ownership claim.",
                  target_executions=0, candidate_expected_value_calls=0,
                  inputs=[record(p) for p in [Path(__file__),IEEE_PATH,MODE1_PATH,PUBLIC_PATH,
                                              public.MODEL,public.LIBRARY,FORMAT_PATH]],
                  arithmetic="Seek/budget: integer/Fraction IEEE rounding; mode1 taps: independent Fraction FMA plus explicitly shared host sin/sqrt; mode2: independent wrapper and pinned public library, shared backend only.",
                  seek_vectors=seeks, scenarios=scenarios,
                  counts=dict(seek_vectors=len(seeks),scenarios=len(scenarios),
                              read_calls=sum(s["operation"]=="read" for v in scenarios for s in v["steps"]),
                              sample_words=sum(len(s.get("output_f32_bits",[])) for v in scenarios for s in v["steps"])))
    destination=HERE/"accessor-state-oracle.json"
    with destination.open("x") as output:json.dump(report,output,indent=2);output.write("\n")
    print(json.dumps(dict(**report["counts"],output=record(destination))))


if __name__ == "__main__":
    main()
