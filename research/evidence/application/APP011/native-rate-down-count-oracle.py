"""Independent count-only Fraction projection for the complete LoFi-sized input.

No candidate, target execution or sample output is involved. Per-call phase and
pending rules are checked against the separately generated sample oracle.
"""
from fractions import Fraction
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / "APP010/native-rate-mode0-oracle.py"
HELPER_SHA = "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == HELPER_SHA
spec = importlib.util.spec_from_file_location("ieee_count", HELPER)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)
rn = ieee.rn


def block(step, phase, pending, frames, below=False):
    if frames == 0:
        return phase, pending, 0
    count = 0
    if step >= 2:
        if phase < 0 and pending:
            phase = rn(step + phase)
            count += 1
        while phase.numerator // phase.denominator < frames - 1:
            phase = rn(step + phase)
            count += 1
        phase = rn(phase - frames)
        return phase, phase < 0, count
    delta = rn(step - 1)
    queued = False
    consumed = 0
    if phase < 1 and pending:
        phase = rn(phase + delta)
        if phase >= 1:
            if frames == 1:
                raise ValueError("lookahead")
            count += 1
            phase = rn(phase - 1)
            consumed = 1
        else:
            queued = True
    skipped = False
    if frames - consumed >= 2:
        left = frames - consumed - 1
        while True:
            if phase < 1:
                while True:
                    count += 1
                    phase = rn(delta + phase)
                    consumed += 1
                    left -= 1
                    if phase >= 1 or left == 0:
                        break
            skipped = phase >= 1
            if skipped:
                phase = rn(phase - 1)
                consumed += 1
                left -= 1
                if queued:
                    count += 1
                    queued = False
            if left <= 0:
                break
    if queued and below:
        count += 1
    if not skipped and consumed >= frames:
        raise ValueError("lookahead")
    return phase, not skipped, count


def main():
    oracle_path = HERE / "native-rate-down-oracle.json"
    oracle_bytes = oracle_path.read_bytes()
    assert hashlib.sha256(oracle_bytes).hexdigest() == "3938e9ce6332f9ce4155377f9f5c6d3a9c45afe173b61d11b08ef2c7923c204a"
    sample = json.loads(oracle_bytes)
    compared_calls = 0
    for vector in sample["vectors"] + sample["large_partition_vectors"]:
        initial = vector["initial_state"]
        step = ieee.value(int(initial["step_f64_bits"], 16))
        phase = ieee.value(int(initial["phase_f64_bits"], 16))
        pending = initial["pending"]
        for expected in vector["calls"]:
            try:
                phase, pending, count = block(step, phase, pending, expected["input_frames"],
                                              vector["layout"] == "below")
            except ValueError:
                assert expected.get("rejected_source_bounds")
                break
            assert count == expected["output_frames"]
            assert f"{ieee.bits(phase):016x}" == expected["state_after"]["phase_f64_bits"]
            assert pending == expected["state_after"]["pending"]
            compared_calls += 1
    vectors = []
    for output_rate in [32000, 16000]:
        step = rn(Fraction(44100, output_rate))
        phase, pending, remaining = Fraction(1), False, 1_058_400
        calls, total = [], 0
        while remaining:
            frames = 8191 if remaining == 8193 else min(remaining, 8192)
            phase, pending, count = block(step, phase, pending, frames)
            total += count
            remaining -= frames
            calls.append(dict(input_frames=frames, output_frames=count,
                              cumulative_output_frames=total,
                              phase_f64_bits=f"{ieee.bits(phase):016x}", pending=pending))
        vectors.append(dict(source_rate=44100, output_rate=output_rate, input_frames=1_058_400,
                            step_f64_bits=f"{ieee.bits(step):016x}", output_frames=total,
                            calls=calls))
    result = dict(schema_version=1,
                  scope="Analytical conditional mode0 ABOVE-layout frame counts under the application singleton-avoidance partition rule; no target execution.",
                  generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  ieee_helper_sha256=HELPER_SHA,
                  sample_oracle_sha256=hashlib.sha256(oracle_bytes).hexdigest(),
                  sample_oracle_call_checks=compared_calls, target_execution_count=0, vectors=vectors)
    destination = HERE / "native-rate-down-count-oracle.json"
    with destination.open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(dict(vectors=[(v["output_rate"], v["output_frames"]) for v in vectors],
                          sha256=hashlib.sha256(destination.read_bytes()).hexdigest())))


if __name__ == "__main__":
    main()
