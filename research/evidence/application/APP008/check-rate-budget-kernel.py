"""Build/check only self-authored arithmetic against sealed analytical vectors.

Does not execute Cubase, read media, or test resampling. Retains optimized
candidate assembly and verifies the three original trace slices byte-for-byte.
"""
from pathlib import Path
import ctypes as C
import datetime
import hashlib
import json
import mmap
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EVIDENCE = ROOT / 'research/evidence/cubase-static/cpr-audio-events-001/rate-converter'
SOURCE = ROOT / 'Application/Sources/RebaseTimingDSP/cpr_rate_budget.c'
INCLUDE = SOURCE.parent / 'include'


def pin(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


class Result(C.Structure):
    _fields_ = [(name, C.c_int32) for name in ['source_frames', 'allowance_frames', 'adjusted_output_frames',
        'initial_source_ceiling', 'reverse_mapped_frames', 'correction_decrements']] + [
        ('search_evaluations', C.c_uint32), ('input_ratio_bits', C.c_uint64),
        ('output_ratio_bits', C.c_uint64), ('initial_product_bits', C.c_uint64)]


def main():
    oracle_path = EVIDENCE / 'analytical-count-controls.json'
    assert pin(oracle_path)['sha256'] == '5d9e87d6e0608e14808fc1142f3273c4cae3e96f9c41a84de63060e87d948c92'
    oracle = json.loads(oracle_path.read_text())
    assert len(oracle['budget_vectors']) == 240 and len(oracle['controls']) == 4
    library, assembly = HERE / 'rate-budget-kernel.dylib', HERE / 'rate-budget-kernel.arm64.s'
    flags = ['-O2', '-std=c11', '-fno-fast-math', '-ffp-contract=off', '-frounding-math', '-I', str(INCLUDE)]
    commands = [['clang', *flags, '-dynamiclib', str(SOURCE), '-o', str(library)],
                ['clang', *flags, '-S', str(SOURCE), '-o', str(assembly)]]
    for command in commands:
        subprocess.run(command, check=True)
    candidate = C.CDLL(str(library))
    calculate = candidate.rb_cpr_rate_read_budget
    calculate.argtypes = [C.c_uint32, C.c_uint32, C.c_int32, C.c_int, C.POINTER(Result)]
    calculate.restype = C.c_int
    columns = {'source_frames': 'returned_source_frames', 'allowance_frames': 'padding',
        'adjusted_output_frames': 'total_budget', 'initial_source_ceiling': 'initial_ceil',
        'reverse_mapped_frames': 'reverse_mapped_frames', 'correction_decrements': 'correction_decrements'}
    maximum_search = 0
    for vector in oracle['budget_vectors'] + oracle['controls']:
        result = Result()
        branch = int(vector['mode'] == 2 and vector['first'] and vector['available'])
        status = calculate(int(vector['source_f32_bits'], 16), int(vector['output_f32_bits'], 16),
                           vector['requested'], branch, C.byref(result))
        assert status == 0, (vector, status)
        for actual, expected in columns.items():
            assert getattr(result, actual) == vector[expected], (vector, actual, getattr(result, actual))
        for actual, expected in [('input_ratio_bits', 'input_ratio_f64_bits'),
                                 ('output_ratio_bits', 'output_ratio_f64_bits'),
                                 ('initial_product_bits', 'initial_product_f64_bits')]:
            assert getattr(result, actual) == int(vector[expected], 16), (vector, actual)
        maximum_search = max(maximum_search, result.search_evaluations)
        assert result.search_evaluations <= 33

    # Read original Mach-O bytes only; no loading or execution of that image.
    original = ROOT / 'research/targets/derived/Cubase15-arm64'
    slices = []
    with original.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
        assert struct.unpack_from('<I', image)[0] == 0xfeedfacf
        ncmds = struct.unpack_from('<I', image, 16)[0]
        offset, segments = 32, []
        for _ in range(ncmds):
            kind, size = struct.unpack_from('<II', image, offset)
            assert size >= 8
            if kind == 0x19:
                vm, vm_size, file_offset, file_size = struct.unpack_from('<QQQQ', image, offset + 24)
                segments.append((vm, vm_size, file_offset, file_size))
            offset += size
        for entry in ['10030a430', '100330d84', '100313bf8']:
            path = EVIDENCE / f'function-{entry}.arm64.bin'
            expected = path.read_bytes(); address = int(entry, 16)
            vm, _, file_offset, _ = next(s for s in segments if s[0] <= address and address + len(expected) <= s[0] + s[3])
            actual_offset = file_offset + address - vm
            assert image[actual_offset:actual_offset + len(expected)] == expected
            slices.append(dict(entry='0x' + entry, original_file_offset=actual_offset,
                               original_bytes_identical=True, slice=pin(path)))
        original_hash = hashlib.sha256(image).hexdigest()
        assert original_hash == 'dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
    asm = assembly.read_text()
    assert not re.search(r'\b(?:fmadd|fmsub|fnmadd|fnmsub)\b', asm)
    for instruction in ['fdiv', 'fmul', 'frintp', 'fcvtzs']:
        assert re.search(r'\b' + instruction + r'\b', asm), instruction
    report = dict(id='APP008-RATE-BUDGET-OPTIMIZED-CHECK',
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), status='passed',
        scope='Self-authored optimized count kernel versus independent exact-Fraction analytical controls; not sample resampling.',
        compiler=subprocess.check_output(['clang', '--version'], text=True).splitlines()[0], commands=commands,
        budget_vectors=240, extra_controls=4, maximum_search_evaluations=maximum_search,
        intermediate_bits_and_counts_match=True, original_source_sha256=original_hash, original_slices=slices,
        emitted_operations=dict(required=['fdiv', 'fmul', 'frintp', 'fcvtzs'], fused_multiply_add_absent=True,
            limit='Instruction presence check, not a formal compiler proof.'),
        pins=[pin(SOURCE), pin(INCLUDE / 'cpr_rate_budget.h'), pin(oracle_path), pin(library), pin(assembly), pin(Path(__file__))],
        target_executions=0, sample_resampling_tests=0)
    destination = HERE / 'rate-budget-kernel-check.json'
    with destination.open('x') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(status='passed', vectors=244, original_bytes=sum(s['slice']['bytes'] for s in slices),
                          maximum_search_evaluations=maximum_search, report=pin(destination))))


if __name__ == '__main__':
    main()
