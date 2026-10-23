"""Independent accessor gain changes over retained mode1/mode2 state.

The new arithmetic is exact signed Float32 multiplication and stage ordering.
The prior independent access/rate models supply seek, budgets, filter state and
samples. No application accessor or candidate C computes expected values.
"""
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


BASE = HERE.parent / "APP016/accessor-state-oracle.py"
STAGE = HERE / "gain-order-stage-oracle.py"
base = load("gain_accessor_base", BASE)
stage = load("gain_stage", STAGE)


def rec(path):
    b = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def scenario(converter, source_rate, output_rate, source_format):
    source = base.samples(6000)
    available = converter == "mode2"
    backend = None
    if converter == "mode1":
        child = base.mode1.Model(source_rate, output_rate, 2)
    else:
        backend = base.public.PublicBackend(source_rate, output_rate, 2)
        child = base.public.model.Wrapper(source_rate, output_rate, 2, backend)
    operations = [("read", 129), ("gain", 0xbfa66666), ("read", 257),
                  ("gain", 0), ("read", 97), ("seek", 0), ("gain", 0x3f800000),
                  ("read", 193), ("gain", 0x80000000), ("read", 257),
                  ("gain", 0xbf400000), ("read", 129)]
    gain = 0x3e99999a
    position, first = 0, True
    steps = []
    for kind, argument in operations:
        if kind == "gain":
            gain = argument
            steps.append(dict(operation=kind, gain_bits=f"{gain:08x}",
                              source_position=position, first=first))
            continue
        if kind == "seek":
            mapped = base.seek(source_rate, output_rate, argument)
            position = mapped["source_frame"]
            steps.append(dict(operation=kind, requested=argument, returned=mapped["returned_frame"],
                              source_position=position, first=first, gain_bits=f"{gain:08x}"))
            continue
        old_first = first
        budget = base.budget(source_rate, output_rate, argument, first and available)
        first = False
        actual = min(budget, len(source)//2-position)
        terminal = old_first and actual < budget and actual == len(source)//2-position
        incoming = source[position*2:(position+actual)*2]
        if source_rate < output_rate:
            incoming = [stage.multiply(x, gain) for x in incoming]
        if converter == "mode1":
            out = [int(x,16) for x in child.process(actual, terminal, incoming)["output_f32_bits"]]
        else:
            out = child.process(incoming if actual else None, terminal)
        if source_rate > output_rate:
            if source_format == "pcm24":
                out = [int(base.format24.project(x)["output_f32_bits"],16) for x in out]
            out = [stage.multiply(x, gain) for x in out]
        position += actual
        steps.append(dict(operation="read", requested=argument, gain_bits=f"{gain:08x}",
                          budget=budget, actual=actual, returned=len(out)//2,
                          source_position=position, first_call=old_first, first=first,
                          terminal=terminal, output_f32_bits=[f"{x:08x}" for x in out],
                          nonzero_words=sum(bool(x&0x7fffffff) for x in out)))
    if backend:
        backend.close()
    return dict(name=f"{converter}-{source_rate}-{output_rate}-{source_format}",
                source_rate=source_rate, output_rate=output_rate, source_format=source_format,
                converter=converter, mode2_budget_available=available, initial_gain_bits="3e99999a",
                input_f32_bits=[f"{x:08x}" for x in source], steps=steps)


def main():
    scenarios = [scenario(mode, source, output, fmt)
                 for mode in ["mode1", "mode2"]
                 for source, output in [(44100,48000),(48000,44100)]
                 for fmt in ["float32", "pcm24"]]
    # Zero gain on upsampling need not immediately zero the returned buffer:
    # prior gained input remains in the retained filter/public-wrapper state.
    history_controls = []
    for row in scenarios:
        zero_reads = [s for s in row["steps"] if s["operation"] == "read" and int(s["gain_bits"],16)&0x7fffffff == 0]
        if row["source_rate"] < row["output_rate"]:
            assert any(s["nonzero_words"] for s in zero_reads)
        else:
            assert all(s["nonzero_words"] == 0 for s in zero_reads)
        history_controls.append(dict(scenario=row["name"], zero_gain_read_nonzero_words=[s["nonzero_words"] for s in zero_reads]))
    dependencies = [Path(__file__), BASE, STAGE, base.IEEE_PATH, base.MODE1_PATH,
                    base.PUBLIC_PATH, base.public.MODEL, base.public.LIBRARY, base.FORMAT_PATH]
    report = dict(schema_version=1, target_executions=0, candidate_expected_calls=0,
        scope="Fixed supplied rates/format and mutable accessor gain; independent retained-state arithmetic, not hosted backend selection.",
        inputs=[rec(x) for x in dependencies], scenarios=scenarios,
        history_order_discriminators=history_controls,
        counts=dict(scenarios=len(scenarios), reads=sum(s["operation"]=="read" for r in scenarios for s in r["steps"]),
                    sample_words=sum(len(s.get("output_f32_bits",[])) for r in scenarios for s in r["steps"])),
        limits=["Mode1 shares host sin/sqrt primitives; mode2 shares the pinned public SoXR backend but not candidate wrapper.",
                "Source inputs use an exact PCM24 lattice; only the downsample path re-quantizes filter outputs.",
                "Gain changes do not reset children, first-read flags or source cursors. Postterminal and changing-rate calls are outside these sequences."])
    destination = HERE / "accessor-gain-oracle.json"
    with destination.open("x") as f:
        json.dump(report, f, indent=2); f.write("\n")
    print(json.dumps(dict(**report["counts"], output=rec(destination))))


if __name__ == "__main__":
    main()
