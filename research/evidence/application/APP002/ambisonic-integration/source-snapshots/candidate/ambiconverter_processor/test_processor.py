#!/usr/bin/env python3
"""Original candidate only; source bytes and exact-rational arithmetic are oracles.

No target code is loaded/executed. --output-dir retains a new immutable evidence
directory. Tables are read independently from the pinned target's Mach-O data.
"""
import argparse
import ctypes as C
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import struct
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EVIDENCE = ROOT / 'research/evidence/cubase-static'


class State(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ('abi_version','channels','precision','direction_table','bypass','reserved')] + [
        ('maximum_frames', C.c_size_t), ('scratch', C.c_void_p), ('scratch_bytes', C.c_size_t)]


class Point(C.Structure):
    _fields_ = [('sample_offset', C.c_int32), ('value', C.c_double)]


class Queue(C.Structure):
    _fields_ = [('parameter_id', C.c_uint32), ('point_count', C.c_int32),
                ('last_point_result', C.c_int32), ('points', C.POINTER(Point))]


class Bus(C.Structure):
    _fields_ = [('channels', C.c_uint32), ('frame_capacity', C.c_size_t),
                ('planes', C.POINTER(C.c_void_p)), ('silence_flags', C.c_uint64)]


class Report(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ('disposition','staged_all_inputs','successful_parameter_updates')]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bits_value(bits, width):
    return struct.unpack('<f' if width == 32 else '<d', bits.to_bytes(width//8, 'little'))[0]


def fraction_bits(value, width, negative_zero=False):
    """Exact rational to IEEE normal-or-zero, round-to-nearest ties-to-even."""
    if not value:
        return (int(negative_zero) << (width-1)).to_bytes(width//8, 'little')
    sign = int(value < 0)
    num, den = abs(value.numerator), value.denominator
    exponent = num.bit_length() - den.bit_length()
    if Fraction(num, den) < Fraction(2) ** exponent:
        exponent -= 1
    precision, bias = (24,127) if width == 32 else (53,1023)
    scale = precision - 1 - exponent
    if scale >= 0:
        num <<= scale
    else:
        den <<= -scale
    q, r = divmod(num, den)
    if r * 2 > den or (r * 2 == den and q & 1):
        q += 1
    if q == 1 << precision:
        q >>= 1
        exponent += 1
    assert 1-bias <= exponent <= bias
    bits = sign << (width-1) | (exponent+bias) << (precision-1) | q-(1 << (precision-1))
    return bits.to_bytes(width//8, 'little')


def product_bytes(value, gain, width):
    return fraction_bits(Fraction.from_float(value) * Fraction.from_float(gain), width,
                         negative_zero=math.copysign(1, value) < 0)


def read_source_tables():
    path = EVIDENCE / 'ambisonic/vstambiconverter.arm64.macho'
    data = path.read_bytes()
    assert sha(data) == 'e8341c6b31ac6b65cf7e8c18bdfbaa18ac24b20160b4287dc385b202eb29b883'
    assert struct.unpack_from('<I', data)[0] == 0xfeedfacf
    segments, cursor = [], 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, cursor)
        assert size >= 8 and cursor+size <= len(data)
        if command == 0x19:
            va, _, offset, length = struct.unpack_from('<QQQQ', data, cursor+24)
            segments.append((va, offset, length))
        cursor += size
    def raw(address, length):
        offsets = [off+address-va for va,off,size in segments if va <= address and address+length <= va+size]
        assert len(offsets) == 1
        return data[offsets[0]:offsets[0]+length]
    all_tables = raw(0x18d15c, 388)
    assert sha(all_tables) == 'c49accecf95f469477a7f57bcc31e6e35ff5d51ee1ff63479b9268bb5a3fc874'
    maps = [list(struct.unpack('<16I', raw(address,64))) for address in (0x18d15c,0x18d19c)]
    gains64 = [list(struct.unpack('<16Q', raw(address,128))) for address in (0x18d1e0,0x18d260)]
    gains32 = [[int.from_bytes(fraction_bits(Fraction.from_float(bits_value(x,64)),32),'little') for x in row] for row in gains64]
    return maps, {32:gains32,64:gains64}, {'path':str(path),'sha256':sha(data),'table_sha256':sha(all_tables)}


class Fixture:
    def __init__(self, owner, width=32, channels=4, frames=5, values=None):
        self.width, self.channels, self.frames = width, channels, frames
        scalar = C.c_float if width == 32 else C.c_double
        values = values if values is not None else [[((c+1)*0.03125)*(-1 if f%2 else 1) for f in range(frames)] for c in range(channels)]
        self.inputs = [(scalar*frames)(*row) for row in values]
        self.outputs = [(scalar*frames)(*([0.3125+c*0.015625]*frames)) for c in range(channels)]
        self.input_ptrs = (C.c_void_p*channels)(*[C.addressof(x) for x in self.inputs])
        self.output_ptrs = (C.c_void_p*channels)(*[C.addressof(x) for x in self.outputs])
        self.scratch = (scalar*(channels*frames))()
        self.state = State()
        self.input = Bus(channels,frames,self.input_ptrs,0)
        self.output = Bus(channels,frames,self.output_ptrs,0xabcdef)
        self.report = Report(99,99,99)
        assert owner.lib.ambip_init(C.byref(self.state),channels,width,frames,C.addressof(self.scratch),C.sizeof(self.scratch)) == 0

    def output_bytes(self):
        return [C.string_at(self.output_ptrs[c],self.frames*self.width//8) for c in range(self.channels)]


class ProcessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps, cls.gains, cls.source_record = read_source_tables()
        cls.temp = tempfile.TemporaryDirectory(prefix='ambip-candidate-')
        library = Path(cls.temp.name)/'candidate.dylib'
        shim = Path(cls.temp.name)/'environment.c'
        shim.write_text('''#include <fenv.h>
#include <stdint.h>
#if defined(__x86_64__)
#include <xmmintrin.h>
#endif
int set_round_down(int yes) { return fesetround(yes ? FE_DOWNWARD : FE_TONEAREST); }
uint64_t fp_control(void) {
#if defined(__aarch64__)
 uint64_t x; __asm__ volatile("mrs %0, fpcr":"=r"(x)); return x;
#elif defined(__x86_64__)
 return _mm_getcsr();
#else
 return UINT64_MAX;
#endif
}
void set_fp_control(uint64_t x) {
#if defined(__aarch64__)
 __asm__ volatile("msr fpcr, %0"::"r"(x));
#elif defined(__x86_64__)
 _mm_setcsr((unsigned)x);
#else
 (void)x;
#endif
}
''')
        cls.compile_argv = ['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-frounding-math',
                            '-dynamiclib',str(HERE/'ambi_processor.c'),str(shim),'-o',str(library)]
        result = subprocess.run(cls.compile_argv,capture_output=True,text=True)
        assert result.returncode == 0, result.stderr
        cls.lib = C.CDLL(str(library))
        cls.lib.ambip_init.argtypes = [C.POINTER(State),C.c_uint32,C.c_uint32,C.c_size_t,C.c_void_p,C.c_size_t]
        for width in (32,64):
            fn = getattr(cls.lib,f'ambip_process_f{width}')
            fn.argtypes = [C.POINTER(State),C.POINTER(Bus),C.POINTER(Bus),C.c_size_t,C.POINTER(Queue),C.c_size_t,C.POINTER(Report)]
            fn.restype = C.c_int
        cls.lib.fp_control.restype = C.c_uint64
        cls.lib.set_fp_control.argtypes = [C.c_uint64]
        cls.environment = {'machine':platform.machine(),'initial_fp_control_hex':hex(cls.lib.fp_control())}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def call(self, fixture, queues=(), frames=None, input_present=True, output_present=True, width=None):
        points, packed_queues = [], []
        for id_, values, result in queues:
            p = (Point*len(values))(*(Point(offset,value) for offset,value in values))
            points.append(p)
            packed_queues.append(Queue(id_,len(values),result,p))
        q = (Queue*len(packed_queues))(*packed_queues)
        return getattr(self.lib,f'ambip_process_f{width or fixture.width}')(C.byref(fixture.state),
            C.byref(fixture.input) if input_present else None, C.byref(fixture.output) if output_present else None,
            fixture.frames if frames is None else frames, q,len(q),C.byref(fixture.report))

    def assert_operator(self, f, direction, original=None):
        original = original or [list(row) for row in f.inputs]
        inverse = [self.maps[direction][:f.channels].index(j) for j in range(f.channels)]
        for destination, source in enumerate(inverse):
            gain = bits_value(self.gains[f.width][direction][destination],f.width)
            expected = b''.join(product_bytes(x,gain,f.width) for x in original[source])
            self.assertEqual(f.output_bytes()[destination],expected,(f.width,f.channels,direction,destination))

    def reject_unchanged(self, f, code, **kwargs):
        before = (bytes(f.state), f.output_bytes(), f.output.silence_flags, bytes(f.report), [bytes(x) for x in f.inputs])
        self.assertEqual(self.call(f,**kwargs),code)
        self.assertEqual((bytes(f.state), f.output_bytes(), f.output.silence_flags, bytes(f.report), [bytes(x) for x in f.inputs]),before)

    def test_all_channel_basis_vectors_exact_coefficients(self):
        for width in (32,64):
            for n in (4,9,16):
                for direction in (0,1):
                    for source in range(n):
                        f=Fixture(self,width,n,3,[[0.125 if c==source else 0.0]*3 for c in range(n)])
                        self.assertEqual(self.call(f,[(2,[(2,float(direction))],0)]),0)
                        self.assert_operator(f,direction)
                        self.assertEqual(f.report.disposition,1)
                        self.assertEqual(f.output.silence_flags,0)

    def test_multiframe_signed_zero_and_rational_product_rounding(self):
        for width in (32,64):
            for n in (4,9,16):
                for direction in (0,1):
                    values=[[0.1+c/64,-0.3-c/64,1.0,-0.0,0.0,1.75] for c in range(n)]
                    f=Fixture(self,width,n,6,values)
                    self.assertEqual(self.call(f,[(2,[(0,float(direction))],0)]),0)
                    self.assert_operator(f,direction)

    def test_direction_and_bypass_thresholds_are_different(self):
        for width in (32,64):
            for p in (0,math.nextafter(0.5,0),0.5,math.nextafter(0.5,1),1):
                f=Fixture(self,width,9)
                self.assertEqual(self.call(f,[(2,[(0,1-p),(4,p)],0)]),0)
                self.assertEqual(f.state.direction_table,int(p>=0.5))
                self.assert_operator(f,int(p>=0.5))
                f=Fixture(self,width,9)
                self.assertEqual(self.call(f,[(1,[(0,1-p),(4,p)],0)]),0)
                self.assertEqual(f.state.bypass,int(p>0.5))
                if p>0.5:self.assertEqual(f.output_bytes(),[bytes(x) for x in f.inputs])
                else:self.assert_operator(f,0)

    def test_queue_last_successful_updates_persist_and_offsets_are_ignored(self):
        for width in (32,64):
            f=Fixture(self,width,16)
            self.assertEqual(self.call(f,[(2,[(0,0),(4,1)],0),(1,[(4,1)],0)],frames=0,input_present=False,output_present=False),0)
            self.assertEqual((f.state.direction_table,f.state.bypass,f.report.disposition),(1,1,0))
            self.assertEqual(f.output.silence_flags,0xabcdef)
            self.assertEqual(self.call(f,[(1,[(0,0)],1),(2,[(0,0)],1),(999,[],0)]),0)
            self.assertEqual((f.state.direction_table,f.state.bypass),(1,1))
            self.assertEqual(f.output_bytes(),[bytes(x) for x in f.inputs])
            self.assertEqual(self.call(f,[(1,[(0,0)],0),(2,[(4,0)],0),(2,[(0,1)],0)]),0)
            self.assert_operator(f,1)
            self.assertEqual(f.report.successful_parameter_updates,3)
            # Additional observed early exits consume state but do not touch output.
            self.assertEqual(self.call(f,[(2,[(0,0)],0)],input_present=False,output_present=False),0)
            self.assertEqual((f.state.direction_table,f.report.disposition),(0,0))
            f.input.channels=0
            self.assertEqual(self.call(f,[(2,[(0,1)],0)],output_present=False),0)
            self.assertEqual((f.state.direction_table,f.report.disposition),(1,0))

    def test_empty_failed_and_invalid_parameter_boundaries(self):
        for width in (32,64):
            for p in (-0.1,1.01,math.inf,math.nan):
                self.reject_unchanged(Fixture(self,width),3,queues=[(2,[(0,p)],0)])
            self.reject_unchanged(Fixture(self,width),3,queues=[(1,[],0)])
            f=Fixture(self,width)
            self.assertEqual(self.call(f,[(2,[(0,math.nan)],1)]),0)
            self.assert_operator(f,0)

    def test_silence_skip_preserves_output_bytes_and_propagates_entire_mask(self):
        for width in (32,64):
            for n in (4,9,16):
                for mask in (1,1<<(n-1),(1<<n)-1,1<<63):
                    values=[[0.0,-0.0,0.0] if mask&(1<<c) else [0.125,-0.25,0.5] for c in range(n)]
                    f=Fixture(self,width,n,3,values); f.input.silence_flags=mask
                    before=f.output_bytes()
                    self.assertEqual(self.call(f,[(2,[(0,1)],0)]),0)
                    self.assertEqual(f.report.disposition,3)
                    self.assertEqual(f.output_bytes(),before)
                    self.assertEqual(f.output.silence_flags,mask)
                    self.assertEqual(self.call(f,[(1,[(0,1)],0)]),0)
                    self.assertEqual(f.report.disposition,2)
                    self.assertEqual(f.output_bytes(),[bytes(x) for x in f.inputs])
                    self.assertEqual(f.output.silence_flags,mask)
            f=Fixture(self,width);f.input.silence_flags=1
            self.reject_unchanged(f,7,queues=[(2,[(0,1)],0)])

    def test_bypass_preserves_finite_bits_and_copy_loop_boundaries(self):
        for width in (32,64):
            maxfinite=(0x7f7fffff if width==32 else 0x7fefffffffffffff)
            patterns=[0,1,1<<(width-1),(1<<(width-1))|1,maxfinite,maxfinite|(1<<(width-1))]
            for frames in (1,3,4,5,7,8,9):
                values=[[bits_value(patterns[(c+f)%len(patterns)],width) for f in range(frames)] for c in range(16)]
                f=Fixture(self,width,16,frames,values)
                original=[bytes(x) for x in f.inputs]
                f.output_ptrs[7]=f.input_ptrs[7]
                self.assertEqual(self.call(f,[(1,[(0,1)],0)]),0)
                self.assertEqual(f.output_bytes(),original)
                self.assertEqual(f.report.staged_all_inputs,0)

    def test_full_and_mixed_corresponding_aliases_stage_all_inputs(self):
        for width in (32,64):
            for n in (4,9,16):
                for direction in (0,1):
                    for aliases in (range(n),[0],[n-1]):
                        f=Fixture(self,width,n)
                        original=[list(x) for x in f.inputs]
                        for c in aliases:f.output_ptrs[c]=f.input_ptrs[c]
                        self.assertEqual(self.call(f,[(2,[(0,float(direction))],0)]),0)
                        self.assertEqual(f.report.staged_all_inputs,1)
                        self.assert_operator(f,direction,original)

    def test_unsupported_aliases_rejected_before_state_or_output_writes(self):
        for width in (32,64):
            for case in ('cross','partial','duplicate-input','duplicate-output','scratch'):
                f=Fixture(self,width,16,5)
                if case=='cross':f.output_ptrs[1]=f.input_ptrs[0]
                if case=='partial':f.output_ptrs[0]=f.input_ptrs[0]+width//8
                if case=='duplicate-input':f.input_ptrs[1]=f.input_ptrs[0]
                if case=='duplicate-output':f.output_ptrs[1]=f.output_ptrs[0]
                if case=='scratch':f.output_ptrs[0]=C.addressof(f.scratch)
                # Do not read beyond a partially overlapped declared allocation.
                if case=='partial':
                    before=(bytes(f.state),[bytes(x) for x in f.inputs],[bytes(x) for x in f.outputs])
                    self.assertEqual(self.call(f,[(2,[(0,1)],0)]),4)
                    self.assertEqual((bytes(f.state),[bytes(x) for x in f.inputs],[bytes(x) for x in f.outputs]),before)
                else:self.reject_unchanged(f,4,queues=[(2,[(0,1)],0)])

    def test_configuration_shape_precision_and_capacity(self):
        for width in (32,64):
            f=Fixture(self,width)
            self.reject_unchanged(f,1,width=64 if width==32 else 32)
            self.reject_unchanged(f,2,frames=f.frames+1)
            self.reject_unchanged(f,2,output_present=False)
            f.input.frame_capacity-=1;self.reject_unchanged(f,2)
            f=Fixture(self,width);f.output.channels=3;self.reject_unchanged(f,2)
            for channels,precision,capacity,bytes_ in [(3,width,5,C.sizeof(f.scratch)),(4,16,5,C.sizeof(f.scratch)),(4,width,0,C.sizeof(f.scratch)),(4,width,5,1)]:
                state=bytes(f.state)
                self.assertEqual(self.lib.ambip_init(C.byref(f.state),channels,precision,capacity,C.addressof(f.scratch),bytes_),1)
                self.assertEqual(bytes(f.state),state)

    def test_numeric_domain_boundaries_and_finite_products(self):
        for width,lower,upper in [(32,0x02000000,0x7dffffff),(64,0x0040000000000000,0x7fbfffffffffffff)]:
            for bits in (lower,upper):
                for direction in (0,1):
                    x=bits_value(bits,width)
                    f=Fixture(self,width,16,2,[[x,-x]]*16)
                    self.assertEqual(self.call(f,[(2,[(0,float(direction))],0)]),0)
                    self.assert_operator(f,direction)
            for bits in (1,lower-1,upper+1):
                f=Fixture(self,width,16,2);f.inputs[15][1]=bits_value(bits,width)
                self.reject_unchanged(f,5,queues=[(2,[(0,1)],0)])
            for value in (math.inf,math.nan):
                f=Fixture(self,width,16,2);f.inputs[15][1]=value
                self.reject_unchanged(f,5)

    def test_fp_mode_rejection_and_bitcopy_separation(self):
        original=self.lib.fp_control()
        for width in (32,64):
            f=Fixture(self,width)
            try:
                self.assertEqual(self.lib.set_round_down(1),0)
                self.reject_unchanged(f,6,queues=[(2,[(0,1)],0)])
                self.assertEqual(self.call(f,[(1,[(0,1)],0)]),0)
                self.assertEqual(f.output_bytes(),[bytes(x) for x in f.inputs])
            finally:self.lib.set_fp_control(original)
            f=Fixture(self,width)
            try:
                flush_bit=24 if platform.machine() in ('arm64','aarch64') else 15
                self.lib.set_fp_control(original | (1<<flush_bit))
                self.reject_unchanged(f,6)
            finally:self.lib.set_fp_control(original)

    def test_higher_order_nonidentity_is_not_replaced_by_inverse_standard(self):
        for width in (32,64):
            f=Fixture(self,width,9,1,[[0.125 if c==4 else 0.0] for c in range(9)])
            self.assertEqual(self.call(f),0)
            first=[list((C.c_float if width==32 else C.c_double).from_buffer_copy(x).value for _ in [0]) for x in f.output_bytes()]
            g=Fixture(self,width,9,1,first)
            self.assertEqual(self.call(g,[(2,[(0,1)],0)]),0)
            expected=product_bytes(0.125,bits_value(self.gains[width][0][6],width),width)
            self.assertEqual(g.output_bytes()[4],expected)
            self.assertNotEqual(g.output_bytes()[4],struct.pack('<f' if width==32 else '<d',0.125))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if args.output_dir:
        args.output_dir.mkdir(parents=True,exist_ok=False)
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ProcessorTests)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    source_files=[HERE/'ambi_processor.h',HERE/'ambi_processor.c',Path(__file__)]
    report={'scope':'Synthetic original-candidate checks against pinned raw tables and exact-rational arithmetic; no target execution or application integration.',
            'at_utc':datetime.now(timezone.utc).isoformat(),'status':'pass' if result.wasSuccessful() else 'fail',
            'test_methods':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'target_executed':False,'application_modified':False,
            'source_record':getattr(ProcessorTests,'source_record',None),
            'environment':getattr(ProcessorTests,'environment',None),
            'compile_argv':getattr(ProcessorTests,'compile_argv',None),
            'files':[{'path':str(p),'sha256':sha(p.read_bytes())} for p in source_files],
            'test_log':stream.getvalue()}
    if args.output_dir:
        (args.output_dir/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
        (args.output_dir/'test-output.txt').write_text(stream.getvalue())
        for path in source_files:(args.output_dir/path.name).write_bytes(path.read_bytes())
    print(stream.getvalue(),end='')
    print(json.dumps({k:report[k] for k in ('status','test_methods','failures','errors','target_executed')}))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
