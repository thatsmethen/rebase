"""Separate instruction wrapper calling pinned public SoXR directly via ctypes.

No candidate C or application bridge is loaded. This tests reconstruction and
public-backend integration, never proprietary SoXR binary/runtime equivalence.
"""
import ctypes as C
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MODEL = HERE / "mode2-wrapper-oracle.py"
spec = importlib.util.spec_from_file_location("instruction_wrapper", MODEL)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
LIBRARY = ROOT / "Application/.build-soxr/install/lib/libsoxr.0.1.2.dylib"
LIBRARY_SHA = "c614df97b2c3f3881fa694efc73a6d5152fe0288ac9396adb6bd7c8c8e5f895a"
assert hashlib.sha256(LIBRARY.read_bytes()).hexdigest() == LIBRARY_SHA
lib = C.CDLL(str(LIBRARY))


class IO(C.Structure):
    _fields_ = [("itype", C.c_int), ("otype", C.c_int), ("scale", C.c_double),
                ("e", C.c_void_p), ("flags", C.c_ulong)]


class Quality(C.Structure):
    _fields_ = [(x, C.c_double) for x in ["precision", "phase_response", "passband_end", "stopband_begin"]] + \
               [("e", C.c_void_p), ("flags", C.c_ulong)]


class Runtime(C.Structure):
    _fields_ = [(x, C.c_uint) for x in ["log2_min_dft_size", "log2_large_dft_size", "coef_size_kbytes", "num_threads"]] + \
               [("e", C.c_void_p), ("flags", C.c_ulong)]


lib.soxr_io_spec.argtypes, lib.soxr_io_spec.restype = [C.c_int, C.c_int], IO
lib.soxr_quality_spec.argtypes, lib.soxr_quality_spec.restype = [C.c_ulong, C.c_ulong], Quality
lib.soxr_runtime_spec.argtypes, lib.soxr_runtime_spec.restype = [C.c_uint], Runtime
lib.soxr_create.argtypes = [C.c_double, C.c_double, C.c_uint, C.POINTER(C.c_char_p),
                           C.POINTER(IO), C.POINTER(Quality), C.POINTER(Runtime)]
lib.soxr_create.restype = C.c_void_p
lib.soxr_process.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t),
                            C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
lib.soxr_process.restype = C.c_char_p
lib.soxr_delete.argtypes = [C.c_void_p]
lib.soxr_version.restype = C.c_char_p
lib.soxr_engine.argtypes, lib.soxr_engine.restype = [C.c_void_p], C.c_char_p


class PublicBackend:
    def __init__(self, source, output, channels):
        self.channels, self.calls = channels, []
        io, quality, runtime = lib.soxr_io_spec(0, 0), lib.soxr_quality_spec(6, 0), lib.soxr_runtime_spec(0)
        error = C.c_char_p()
        self.handle = lib.soxr_create(source, output, channels, C.byref(error),
                                      C.byref(io), C.byref(quality), C.byref(runtime))
        assert self.handle and not error.value
        self.engine = lib.soxr_engine(self.handle).decode()

    def process(self, samples, requested):
        values = None if samples is None else (C.c_uint32 * len(samples))(*samples)
        result = (C.c_uint32 * (requested * self.channels))()
        used, produced = C.c_size_t(), C.c_size_t()
        frames = 0 if samples is None else len(samples) // self.channels
        error = lib.soxr_process(self.handle, values, frames, C.byref(used),
                                 result, requested, C.byref(produced))
        assert not error, error
        assert used.value <= frames and produced.value <= requested
        output = list(result)[:produced.value * self.channels]
        self.calls.append(dict(
            input_frames=frames, null_input=samples is None,
            input_sha256=model.digest(samples or []),
            first_bits=[f"{v:08x}" for v in (samples or [])[:self.channels]],
            last_bits=[f"{v:08x}" for v in (samples or [])[-self.channels:]],
            requested=requested, used=used.value, produced=produced.value,
            output_sha256=model.digest(output)))
        return used.value, output

    def close(self):
        lib.soxr_delete(self.handle)


def case(source, output, pattern, blocks, terminal):
    backend = PublicBackend(source, output, 2)
    wrapper = model.Wrapper(source, output, 2, backend)
    initial = wrapper.snapshot()
    steps, offset = [], 0
    try:
        for i, n in enumerate(blocks):
            samples = model.input_samples(offset, n, 2, pattern) if n else None
            before = len(backend.calls)
            result = wrapper.process(samples, i == len(blocks) - 1)
            steps.append(dict(input_frames=n, final=i == len(blocks) - 1,
                              returned=len(result) // 2, output_sha256=model.digest(result),
                              snapshot=wrapper.snapshot(), backend_calls=backend.calls[before:]))
            offset += n
        return dict(name=f"{source}-{output}-{pattern}-{terminal}", policy="public",
                    source=source, output=output, channels=2, pattern=pattern,
                    initial=initial, steps=steps, engine=backend.engine)
    finally:
        backend.close()


def main():
    cases = []
    for source, output in [(44100, 48000), (48000, 44100), (44100, 44100)]:
        for pattern in ["impulse", "ramp", "nonzero-last", "alternating"]:
            cases.append(case(source, output, pattern, [8192, 1], "positive-final"))
            cases.append(case(source, output, pattern, [8192, 1, 0], "null-final"))
    cases.append(case(48000, 44100, "alternating", [30000, 30000, 30000, 1000], "compactions"))
    for source, output in [(8000, 192000), (192000, 8000)]:
        cases.append(case(source, output, "ramp", [1], "singleton"))
    result = dict(schema_version=1, evidence_class="independent-public-backend-wrapper-comparison",
                  target_execution=False, candidate_or_application_bridge_used=False,
                  library=dict(path=str(LIBRARY.relative_to(ROOT)), sha256=LIBRARY_SHA,
                               bytes=LIBRARY.stat().st_size, version=lib.soxr_version().decode()),
                  generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  instruction_model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
                  public_parameters=dict(io=[0, 0], quality=[6, 0], runtime=[0]),
                  limitations=["Same pinned public backend; not independent filter implementation.",
                               "No proprietary execution or bundled SoXR conformance claim.",
                               "Explicit partitions and one terminal call; no repeated flush claim."],
                  cases=cases)
    path = HERE / "mode2-public-oracle.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(cases=len(cases), bytes=path.stat().st_size,
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__ == "__main__":
    main()
