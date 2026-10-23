#!/usr/bin/env python3
"""Self-authored exact rational IEEE rounding oracle; no native target execution.
Each recovered operation rounds independently to binary32 or binary64 with
round-to-nearest/ties-even. Only positive finite normal test vectors are used.
"""
from fractions import Fraction
import json, struct

def value(bits, width):
    fraction_bits, exponent_bits = (23, 8) if width == 32 else (52, 11)
    exponent = (bits >> fraction_bits) & ((1 << exponent_bits) - 1)
    mantissa = bits & ((1 << fraction_bits) - 1)
    assert 0 < exponent < (1 << exponent_bits) - 1 and bits >> (width-1) == 0
    return Fraction((1 << fraction_bits) + mantissa) * Fraction(2) ** (exponent - ((1 << (exponent_bits-1))-1) - fraction_bits)

def rounded_bits(x, width):
    assert x > 0
    precision, exponent_bits = (24, 8) if width == 32 else (53, 11)
    exponent = x.numerator.bit_length() - x.denominator.bit_length()
    if x < Fraction(2) ** exponent: exponent -= 1
    scaled = x / (Fraction(2) ** (exponent - precision + 1))
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    if remainder * 2 > scaled.denominator or (remainder * 2 == scaled.denominator and quotient % 2): quotient += 1
    if quotient == 1 << precision: quotient >>= 1; exponent += 1
    bias = (1 << (exponent_bits-1))-1
    assert 0 < exponent + bias < (1 << exponent_bits)-1
    return ((exponent + bias) << (precision-1)) | (quotient - (1 << (precision-1)))

def r64(x): return value(rounded_bits(x, 64), 64)
def bits64(x): return struct.unpack('>Q', struct.pack('>d', x))[0]

rows=[]
for bpm_bits, tick, seconds in [(0x42fd0000, 12345.6789012345, 123.456789012345),
 (0x42fd0001, 479999999999.5, 86400.0), (0x42b80000,480.0,1.0),
 (0x428c0000, 576000.0,600.0), (0x42820000,0.125,0.125),
 (0x41a00000,480.0,3.0), (0x43c80000,480.0,0.15)]:
    period_bits=rounded_bits(Fraction(60)/value(bpm_bits,32),32)
    period=value(period_bits,32)
    tick_bits=bits64(tick); seconds_bits=bits64(seconds)
    result_seconds=rounded_bits(r64(period*value(tick_bits,64))/480,64)
    result_ticks=rounded_bits(r64(value(seconds_bits,64)/period)*480,64)
    rows.append({'bpm_bits':f'{bpm_bits:08x}','period_bits':f'{period_bits:08x}',
      'input_tick_bits':f'{tick_bits:016x}','expected_seconds_bits':f'{result_seconds:016x}',
      'input_seconds_bits':f'{seconds_bits:016x}','expected_tick_bits':f'{result_ticks:016x}'})
print(json.dumps({'scope':'Analytical arithmetic oracle, not Cubase execution or project acceptance.', 'rounding':'Exact rational arithmetic, round-to-nearest ties-even after each specified operation.','vectors':rows},indent=2))
