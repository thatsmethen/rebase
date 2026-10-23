"""High-ratio converter/ring boundary oracle; exact Fraction arithmetic only."""
from fractions import Fraction
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HELPER = HERE / "native-rate-mode0-oracle.py"
EXPECTED_HELPER = "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == EXPECTED_HELPER
spec = importlib.util.spec_from_file_location("mode0_ieee_fraction", HELPER)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)

phase = Fraction(1)
step = ieee.rn(Fraction(8000, 192000))
previous = [Fraction(0), Fraction(0)]
output_hash, input_hash = hashlib.sha256(), hashlib.sha256()
produced = 0
blocks = []
checkpoints = []
for frame in range(8195):
    current = [Fraction(frame % 127 - 63, 128), Fraction((frame * 17) % 131 - 65, 256)]
    for sample in current:
        input_hash.update(ieee.f32(sample).to_bytes(4, "little"))
    while phase < 1:
        complement = ieee.rn(1 - phase)
        pair = []
        for old, new in zip(previous, current):
            product = ieee.rn(phase * new)
            encoded = ieee.f32(ieee.rn(complement * old + product))
            output_hash.update(encoded.to_bytes(4, "little"))
            pair.append(f"{encoded:08x}")
        if produced in [0, 1, 8191, 8192, 16383, 16384, 32767, 32768, 196584, 196585, 196656]:
            checkpoints.append(dict(output_frame=produced, channel_bits=pair))
        produced += 1
        phase = ieee.rn(step + phase)
    phase = ieee.rn(phase - 1)
    previous = current
    if frame in [8191, 8194]:
        blocks.append(dict(input_end=frame + 1, cumulative_output_frames=produced,
                           phase_f64_bits=f"{ieee.bits(phase):016x}"))

result = dict(
    schema_version=1,
    scope="Independent exact-rational mode0 sample oracle for two source blocks and repeated 32768-frame ring wrap; no candidate or target execution.",
    generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    ieee_helper_sha256=EXPECTED_HELPER,
    source_rate=8000, output_rate=192000, input_frames=8195, channels=2,
    input_rule="L=(frame%127-63)/128; R=((frame*17)%131-65)/256; exactly representable Float32 values",
    input_interleaved_f32le_sha256=input_hash.hexdigest(),
    output_frames=produced, output_interleaved_f32le_sha256=output_hash.hexdigest(),
    source_blocks=blocks, checkpoints=checkpoints,
    target_execution_count=0)
destination = HERE / "native-rate-mode0-ring-oracle.json"
with destination.open("x") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(dict(output_frames=produced,
                      output_sha256=output_hash.hexdigest(),
                      artifact_sha256=hashlib.sha256(destination.read_bytes()).hexdigest())))
