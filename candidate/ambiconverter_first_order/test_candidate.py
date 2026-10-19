"""Synthetic transcription checks. These never load or execute the VST target."""
import ctypes as C
from fractions import Fraction
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class Input(C.Structure):
    _fields_ = [("samples", C.c_void_p), ("frames", C.c_size_t)]


class Output(C.Structure):
    _fields_ = Input._fields_


class Options(C.Structure):
    _fields_ = [("direction", C.c_double), ("direction_present", C.c_uint32),
                ("bypass", C.c_uint32), ("input_silence_flags", C.c_uint64)]


def packed(x, width):
    return struct.pack("<f" if width == 32 else "<d", x)


def from_bits(bits, width):
    return struct.unpack("<f" if width == 32 else "<d",
                         bits.to_bytes(width // 8, "little"))[0]


def rounded_product(x, gain, width):
    """Independent exact rational multiplication and ties-to-even rounding.

    Only normal results or signed zero are used by these tests. This avoids
    using host multiplication as the expected answer to the C multiplication.
    """
    if x == 0:
        return packed(x, width)
    value = Fraction.from_float(x) * Fraction.from_float(gain)
    sign = int(value < 0)
    num, den = abs(value.numerator), value.denominator
    exponent = num.bit_length() - den.bit_length()
    if (num < den << exponent) if exponent >= 0 else (num << -exponent < den):
        exponent -= 1
    mantissa, bias = (24, 127) if width == 32 else (53, 1023)
    shift = mantissa - 1 - exponent
    if shift >= 0:
        num <<= shift
    else:
        den <<= -shift
    q, r = divmod(num, den)
    if 2 * r > den or (2 * r == den and q & 1):
        q += 1
    if q == 1 << mantissa:
        q >>= 1
        exponent += 1
    bits = (sign << (width - 1)) | ((exponent + bias) << (mantissa - 1))
    bits |= q - (1 << (mantissa - 1))
    return bits.to_bytes(width // 8, "little")


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / "candidate.dylib"
        shim = Path(cls.temp.name) / "fenv.c"
        shim.write_text("#include <fenv.h>\nint test_round(int down) { return "
                        "fesetround(down ? FE_DOWNWARD : FE_TONEAREST); }\n")
        subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-fno-fast-math", "-ffp-contract=off", "-frounding-math",
                        "-dynamiclib", str(HERE / "ambi_first_order.c"), str(shim),
                        "-o", str(lib)], check=True)
        cls.lib = C.CDLL(str(lib))
        for width in (32, 64):
            fn = getattr(cls.lib, f"ambi_first_order_f{width}")
            fn.argtypes = [C.POINTER(Input), C.c_size_t, C.POINTER(Output),
                           C.c_size_t, C.POINTER(Options)]
            fn.restype = C.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def fixture(self, width, values=None, p=0.0):
        values = values or [[0.25], [0.5], [-0.75], [1.0]]
        scalar = C.c_float if width == 32 else C.c_double
        sources = [(scalar * len(v))(*v) for v in values]
        outputs = [(scalar * len(v))(*([0.125] * len(v))) for v in values]
        ins = (Input * 4)(*(Input(C.addressof(a), len(a)) for a in sources))
        outs = (Output * 4)(*(Output(C.addressof(a), len(a)) for a in outputs))
        return sources, outputs, ins, outs, Options(p, 1, 0, 0)

    def call(self, width, fixture, ni=4, no=4):
        _, _, ins, outs, options = fixture
        return getattr(self.lib, f"ambi_first_order_f{width}")(ins, ni, outs, no,
                                                                C.byref(options))

    def test_unit_basis_permutations_and_exact_gains(self):
        for width, low, high in [(32, 0x3fb504f3, 0x3f3504f3),
                                 (64, 0x3ff6a09e667f3bcd, 0x3fe6a09e667f3bcc)]:
            for p, destinations, gain in [(0, [0, 3, 1, 2], low),
                                           (1, [0, 2, 3, 1], high)]:
                for source in range(4):
                    with self.subTest(width=width, p=p, source=source):
                        f = self.fixture(width, [[float(c == source)] for c in range(4)], p)
                        self.assertEqual(self.call(width, f), 0)
                        for c, output in enumerate(f[1]):
                            expected = (from_bits(gain, width) if source == 0 else 1.0)
                            if c != destinations[source]:
                                expected = 0.0
                            self.assertEqual(bytes(output), packed(expected, width))

    def test_threshold_neighbors_and_multiframe_rational_oracle(self):
        for width in (32, 64):
            for p in (0.0, math.nextafter(0.5, 0), 0.5, math.nextafter(0.5, 1), 1.0):
                values = [[0.1, -0.3, 1.0, -0.0, 0.0], [0.2, -0.4, 0.25, 0.5, 0.6],
                          [-0.7, 0.8, 0.125, -0.9, 1.0], [0.9, -0.8, 0.5, -1.0, 0.25]]
                f = self.fixture(width, values, p)
                self.assertEqual(self.call(width, f), 0)
                # Explicit destination equations, independently from C's scatter loop.
                source_at_destination = [0, 2, 3, 1] if p < 0.5 else [0, 3, 1, 2]
                gain_bits = {32: (0x3fb504f3, 0x3f3504f3),
                             64: (0x3ff6a09e667f3bcd, 0x3fe6a09e667f3bcc)}[width][p >= 0.5]
                for destination, source in enumerate(source_at_destination):
                    gain = from_bits(gain_bits, width) if destination == 0 else 1.0
                    expected = b"".join(rounded_product(x, gain, width) for x in f[0][source])
                    self.assertEqual(bytes(f[1][destination]), expected)

    def test_lower_sample_boundary_and_zero(self):
        for width, minimum in [(32, 2.0 ** -125), (64, 2.0 ** -1021)]:
            for p in (0, 1):
                f = self.fixture(width, [[minimum, -minimum, 0.0, -0.0]] * 4, p)
                self.assertEqual(self.call(width, f), 0)

    def assert_rejected_unchanged(self, width, f, expected, ni=4, no=4):
        before = [bytes(a) for a in f[1]]
        self.assertEqual(self.call(width, f, ni, no), expected)
        self.assertEqual([bytes(a) for a in f[1]], before)

    def test_rejects_unspecified_state_and_invalid_direction(self):
        for width in (32, 64):
            for field, value in [("direction_present", 0), ("direction_present", 2),
                                 ("bypass", 1), ("input_silence_flags", 1),
                                 ("input_silence_flags", 15), ("direction", -0.1),
                                 ("direction", -5e-324), ("direction", 1.01),
                                 ("direction", math.nan), ("direction", math.inf)]:
                f = self.fixture(width)
                setattr(f[4], field, value)
                self.assert_rejected_unchanged(width, f, 2)

    def test_rejects_bad_shape(self):
        for width in (32, 64):
            self.assert_rejected_unchanged(width, self.fixture(width), 1, ni=3)
            self.assert_rejected_unchanged(width, self.fixture(width), 1, no=5)
            for index, frames in [(0, 0), (1, 2), (0, 2 ** 31)]:
                f = self.fixture(width)
                f[2][index].frames = frames
                self.assert_rejected_unchanged(width, f, 1)
            f = self.fixture(width)
            f[3][0].samples = None
            self.assert_rejected_unchanged(width, f, 1)

    def test_rejects_aliases_and_partial_overlap(self):
        for width in (32, 64):
            for source, destination in [(0, 0), (1, 0)]:
                f = self.fixture(width)
                f[3][destination].samples = f[2][source].samples
                original = [bytes(a) for a in f[0]]
                self.assert_rejected_unchanged(width, f, 4)
                self.assertEqual([bytes(a) for a in f[0]], original)
            f = self.fixture(width, [[0.25, 0.5]] * 4)
            f[3][0].samples = f[2][0].samples + width // 8
            self.assert_rejected_unchanged(width, f, 4)

    def test_rejects_samples_before_any_output_write(self):
        for width, too_small in [(32, 2.0 ** -126), (64, 2.0 ** -1022)]:
            for value in (too_small, too_small / 2, 1.001, -1.001, math.inf, math.nan):
                f = self.fixture(width, [[0.25, 0.5]] * 4)
                f[0][3][1] = value  # Last sample detects partial-write mistakes.
                self.assert_rejected_unchanged(width, f, 3)

    def test_rejects_other_rounding_mode(self):
        try:
            self.assertEqual(self.lib.test_round(1), 0)
            for width in (32, 64):
                self.assert_rejected_unchanged(width, self.fixture(width), 5)
        finally:
            self.assertEqual(self.lib.test_round(0), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
