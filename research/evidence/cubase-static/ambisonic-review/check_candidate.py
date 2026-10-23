#!/usr/bin/env python3
"""Independent boundary/rejection checks of original candidate C, not Cubase."""
import ctypes as C
import hashlib
import itertools
import json
import pathlib
import struct
import subprocess
import tempfile

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[3]
CANDIDATE = ROOT / 'candidate/ambiconverter_first_order'

class In(C.Structure):
    _fields_ = [('samples', C.c_void_p), ('frames', C.c_size_t)]

class Out(C.Structure):
    _fields_ = In._fields_

class Options(C.Structure):
    _fields_ = [('direction', C.c_double), ('direction_present', C.c_uint32),
                ('bypass', C.c_uint32), ('input_silence_flags', C.c_uint64)]

def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

initial = {n: hash_file(CANDIDATE / n) for n in ('ambi_first_order.c', 'ambi_first_order.h')}
checks = []
with tempfile.TemporaryDirectory() as temp:
    libpath = pathlib.Path(temp) / 'independent-candidate.dylib'
    command = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-fast-math',
               '-ffp-contract=off', '-frounding-math', '-dynamiclib',
               str(CANDIDATE / 'ambi_first_order.c'), '-o', str(libpath)]
    compile_result = subprocess.run(command, text=True, capture_output=True)
    assert compile_result.returncode == 0, compile_result.stderr
    compiled_sha = hash_file(libpath)
    lib = C.CDLL(str(libpath))
    for width in (32, 64):
        fn = getattr(lib, f'ambi_first_order_f{width}')
        fn.argtypes = [C.POINTER(In), C.c_size_t, C.POINTER(Out), C.c_size_t, C.POINTER(Options)]
        fn.restype = C.c_int
        scalar = C.c_float if width == 32 else C.c_double
        size = width // 8
        fmt = '<f' if width == 32 else '<d'

        def fixture(frames=9):
            arrays = [(scalar * frames)(*([0.25] * frames)) for _ in range(8)]
            ins = (In * 4)(*(In(C.addressof(a), frames) for a in arrays[:4]))
            outs = (Out * 4)(*(Out(C.addressof(a), frames) for a in arrays[4:]))
            return arrays, ins, outs, Options(0.0, 1, 0, 0)

        def call(f):
            return fn(f[1], 4, f[2], 4, C.byref(f[3]))

        # Every pair among the eight buffers, not only corresponding in/out pairs.
        for left, right in itertools.combinations(range(8), 2):
            f = fixture()
            descriptors = [*f[1], *f[2]]
            descriptors[right].samples = descriptors[left].samples
            before = [bytes(a) for a in f[0]]
            result = call(f)
            assert result == 4, (width, left, right, result)
            assert before == [bytes(a) for a in f[0]], (width, left, right, 'write on rejection')
        checks.append({'name': 'all_28_exact_alias_pairs_rejected_atomically', 'precision': width, 'passed': True})

        # Misalignment is rejected before any sample access or write.
        for i in range(8):
            f = fixture()
            descriptors = [*f[1], *f[2]]
            descriptors[i].samples += 1
            before = [bytes(a) for a in f[0]]
            assert call(f) == 1
            assert before == [bytes(a) for a in f[0]]
        checks.append({'name': 'all_8_misaligned_buffer_positions_rejected_atomically', 'precision': width, 'passed': True})

        # Exact endpoint bits and their immediate neighbors; corrupt the final input sample.
        low, high = (0x01000000, 0x3f800000) if width == 32 else (0x0020000000000000, 0x3ff0000000000000)
        for bits, accepted in ((low-1, False), (low, True), (high, True), (high+1, False)):
            for sign in (0, 1 << (width-1)):
                f = fixture()
                f[0][3][-1] = struct.unpack(fmt, (bits | sign).to_bytes(size, 'little'))[0]
                before = [bytes(a) for a in f[0][4:]]
                status = call(f)
                assert status == (0 if accepted else 3), (width, bits, sign, status)
                if not accepted:
                    assert before == [bytes(a) for a in f[0][4:]]
        checks.append({'name': 'exact_sample_domain_endpoints_and_adjacent_bits', 'precision': width, 'passed': True})

        # Distinct signed-zero bit patterns detect accidental channel reversal or sign erasure.
        for frames in (1, 2, 3, 4, 7, 8, 9, 15, 16, 17):
            for p, source_order in ((0.0, (0, 2, 3, 1)), (0.5, (0, 3, 1, 2))):
                f = fixture(frames)
                f[3].direction = p
                for channel in range(4):
                    for sample in range(frames):
                        f[0][channel][sample] = -0.0 if ((sample + channel) % 3 == 0) else 0.0
                expected = [bytes(f[0][channel]) for channel in source_order]
                assert call(f) == 0
                assert expected == [bytes(a) for a in f[0][4:]], (width, frames, p)
        checks.append({'name': 'signed_zero_permutation_across_10_frame_lengths', 'precision': width, 'passed': True})

        # Generic textbook sqrt(0.5) is not an acceptable replacement for the retained double.
        f = fixture(1)
        f[0][0][0] = 1.0
        f[3].direction = 0.5
        assert call(f) == 0
        reverse_bits = 'f304353f' if width == 32 else 'cc3b7f669ea0e63f'
        assert bytes(f[0][4]).hex() == reverse_bits
        checks.append({'name': 'exact_reverse_gain_at_threshold', 'precision': width, 'expected_le_hex': reverse_bits, 'passed': True})

assert initial == {n: hash_file(CANDIDATE / n) for n in initial}, 'Candidate changed during review run'
report = {
    'scope': 'Independent tests executed original candidate code only. No Cubase/VST target code loaded or executed.',
    'status': 'passed', 'target_executed': False, 'candidate_executed': True,
    'candidate_source_sha256': initial,
    'compile_command': command, 'compile_return_code': compile_result.returncode,
    'compile_stdout': compile_result.stdout, 'compile_stderr': compile_result.stderr,
    'compiled_candidate_sha256': compiled_sha, 'compiled_artifact_retained': False,
    'test_source_sha256': hash_file(pathlib.Path(__file__)),
    'checks': checks,
    'limitations': ['These checks are not a target oracle, product conformance, host integration, or runtime bit-fidelity evidence.',
                    'Caller-provided storage validity remains a C API precondition; malformed unmapped pointers were not dereferenced.'],
}
(OUT / 'candidate-checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': 'passed', 'check_groups': len(checks), 'target_executed': False}))
