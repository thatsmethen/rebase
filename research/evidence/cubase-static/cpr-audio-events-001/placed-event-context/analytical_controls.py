"""Conditional arithmetic controls; never native execution or target outputs."""
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def bits(x):
    return struct.pack('>d', x).hex()


def fixed_inverse(tick, bpm):
    # The pinned fixed-clock contract supplies its Float32 divide, then two
    # separate Float64 operations. This is not Double(60)/Double(bpm).
    period = float(f32(60.0 / f32(bpm)))
    return (period * tick) / 480.0


def jump_inverse(tick):
    # Supplied canonical two-point state, not a claim about arbitrary archives.
    if tick >= 384000.0:
        return ((tick - 384000.0) * float(f32(0.5))) / 480.0 + 600.0
    return ((tick - 0.0) * float(f32(0.75))) / 480.0 + 0.0


rows = []
for mode, tick, frames, offset in [
    ('fixed126.5', 480.0, 44100.0, 22050.0),
    ('fixed126.5', 1265.0, 1058400.0, 0.0),
    ('jump80to120', 0.0, 1058400.0, 0.0),
    ('jump80to120', 3840.0, 44100.0, 22050.0),
    ('jump80to120', 383520.0, 44100.0, 1.0),
    ('jump80to120', 384000.0, 44100.0, 22050.0),
    ('jump80to120', 384480.0, 44100.0, 22050.0),
]:
    period = 1.0 / 44100.0
    origin = 0.0
    start = (fixed_inverse(tick + origin, 126.5) if mode.startswith('fixed')
             else jump_inverse(tick + origin)) / 1.0
    length = (frames * period) / 1.0
    source_offset = -0.0 if offset == 0 else -(((-offset) * period) / 1.0)
    end = start + length
    wrong_start = tick * period
    assert bits(source_offset) == '8000000000000000' if offset == 0 else source_offset > 0
    if tick:
        assert start != wrong_start
    rows.append(dict(clock=mode, raw_start=tick, raw_length=frames, raw_offset=offset,
        clip_period_bits=bits(period), start_bits=bits(start), length_bits=bits(length),
        offset_bits=bits(source_offset), end_bits=bits(end), start_seconds=start,
        length_seconds=length, source_offset_seconds=source_offset,
        rejected_shortcut_start_bits=bits(wrong_start)))

result = dict(evidence_class='analytical supplied-state controls', target_executed=False,
    observations_of_target_output=0, cases=rows, passed=True,
    limitations=['Host Python binary64 arithmetic used only for these finite controls; '
                 'these are not an independent full IEEE rounding oracle.',
                 'Fixed and map clock operations are reused from sealed contracts; '
                 'no new generalized map, source rate, or host lifecycle claim.',
                 'Builder snapping and channel-reader quantization are separate.'])
(HERE/'analytical-controls.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(dict(passed=True, cases=len(rows))))
