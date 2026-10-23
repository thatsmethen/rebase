"""Analytical controls for bounded native interval and rate-seek arithmetic.

Runs self-authored rational arithmetic only. It does not run Cubase or decode
audio. Nearest/ties-even is an explicit oracle assumption, not an observed FPCR.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib, importlib.util, json, sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ORACLE = ROOT / 'research/evidence/cubase-static/cpr-map-clock-001/oracle-iterator/map_oracle.py'
spec = importlib.util.spec_from_file_location('retained_fraction_oracle', ORACLE)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)


def interval(start, offset, length, position, requested):
    # Deliberately excludes gaps, overlaps, invalid/negative values, overflow,
    # short reads, changing metadata and the multi-segment iterator path.
    assert all(isinstance(x, int) and 0 <= x < 1 << 53 for x in [start, offset, length, position, requested])
    assert 0 < requested <= (1 << 31)-1 and length > 0 and start <= position < start + length
    assert start + length < 1 << 53 and offset + length < 1 << 53
    count = min(requested, start + length - position)
    seek = position - start + offset
    return dict(start=start, offset=offset, length=length, position=position,
                requested=requested, source_seek=seek, source_count=count,
                source_half_open=[seek, seek+count], remainder=requested-count)


def seek(source_rate, output_rate, position):
    source_bits = ieee.encode(F(source_rate), p=24, eb=8)
    output_bits = ieee.encode(F(output_rate), p=24, eb=8)
    source = ieee.decode(source_bits, p=24, eb=8)
    output = ieee.decode(output_bits, p=24, eb=8)
    assert source > 0 and output > 0 and 0 <= position < 1 << 53
    ratio_bits = ieee.encode(source/output, p=24, eb=8)
    ratio = ieee.decode(ratio_bits, p=24, eb=8)
    widened = ieee.encode(ratio)
    product = ieee.op(ieee.encode(position), widened, 'mul')
    source_position = int(ieee.decode(product))  # FCVTZS, finite nonnegative domain.
    returned = int(ieee.decode(ieee.op(ieee.encode(source_position), widened, 'div')))
    if source_bits == output_bits:
        assert source_position == returned == position
    alternative = int(ieee.decode(ieee.op(ieee.encode(position), ieee.encode(source/output), 'mul')))
    return dict(source_rate=source_rate, output_rate=output_rate, requested_position=position,
                source_f32_bits=f'{source_bits:08x}', output_f32_bits=f'{output_bits:08x}',
                ratio_f32_bits=f'{ratio_bits:08x}', ratio_f64_bits=f'{widened:016x}',
                product_f64_bits=f'{product:016x}', stored_source_position=source_position,
                returned_output_position=returned, wrong_f64_ratio_source_position=alternative,
                distinguishes_f32_from_f64_ratio=source_position != alternative)


def main():
    intervals = [interval(*x) for x in [(0,0,1058400,0,1024), (0,0,677376,677000,1000),
        (100,7,123,100,40), (100,7,123,140,100), (100,7,123,222,2), (100,7,123,101,1)]]
    assert intervals[2]['source_half_open'] == [7,47]
    assert intervals[3]['source_half_open'] == [47,130] and intervals[3]['remainder'] == 17
    vectors = [seek(s,o,p) for s,o in [(44100,44100),(44100,48000),(48000,44100),(48000,96000)]
               for p in [0,1,44100,48000,1000001,1 << 40]]
    assert any(v['distinguishes_f32_from_f64_ratio'] for v in vectors)
    result = dict(scope='Analytical controls from native instruction sequences, not target runtime observations.',
        assumptions=['IEEE nearest/ties-even arithmetic; finite positive normal rates',
                     'Bounded nonnegative integers exactly representable in binary64',
                     'Single selected segment, valid Stream/accessor, full successful source read'],
        native_interval='10036d364..3f4 and10036d440..468',
        native_rate_seek='10036f8f8..954: f32 compare/divide, widen, i64-to-f64,multiply,FCVTZS,divide,FCVTZS',
        rational_helper=dict(path=str(ORACLE.relative_to(ROOT)),sha256=hashlib.sha256(ORACLE.read_bytes()).hexdigest()),
        intervals=intervals,rate_seek_vectors=vectors,
        nonclaims=['Remainder is outside the selected source interval; this oracle does not simulate all cluster padding/error states.',
                   'The differing-rate audio resampler and count conversion are not reconstructed.',
                   'Exact scalar/seconds conversion upstream of this integer stream API is a separate contract.'],
        target_execution_count=0)
    with (HERE/'interval-and-rate-vectors.json').open('x') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(intervals=len(intervals),rate_vectors=len(vectors),
                         f32_ratio_discriminators=sum(v['distinguishes_f32_from_f64_ratio'] for v in vectors))))


if __name__ == '__main__':
    main()
