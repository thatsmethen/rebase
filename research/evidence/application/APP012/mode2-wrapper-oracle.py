"""Instruction-derived mode2 wrapper oracle; no candidate C is imported.

Count operations use exact Fraction arithmetic with explicit IEEE binary64
nearest/ties-even rounding. Sample copying is modelled as integer Float32 bits.
The spying backend is deliberately not a resampler. Public SoXR comparisons
may inject a separate backend into this same independently authored wrapper.
"""
from fractions import Fraction
from pathlib import Path
import array
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORK = HERE.parents[3]
HELPER = HERE.parent / "APP010/native-rate-mode0-oracle.py"
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == \
    "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4"
spec = importlib.util.spec_from_file_location("independent_ieee", HELPER)
ieee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ieee)
rn, bits, f32 = ieee.rn, ieee.bits, ieee.f32


def ceil(x):
    return -(-x.numerator // x.denominator)


def digest(samples):
    raw = array.array("I", samples)
    if sys.byteorder != "little":
        raw.byteswap()
    return hashlib.sha256(raw.tobytes()).hexdigest()


PATTERN = [[f32(Fraction(i - 63, 128)),
            f32(Fraction((i * 17) % 131 - 65, 256))] for i in range(16637)]


def input_samples(start, frames, channels, pattern="ramp"):
    result = []
    for index in range(start, start + frames):
        if pattern == "impulse":
            values = [0x3f000000 if index == 0 else 0,
                      0xbe800000 if index == 1 else 0]
        elif pattern == "alternating":
            values = [0x3f000000 if index % 2 == 0 else 0xbf000000,
                      0xbe800000 if index % 2 == 0 else 0x3e800000]
        elif pattern == "nonzero-last":
            values = [0x3ec00000 if index == 8192 else 0,
                      0xbec00000 if index == 8192 else 0]
        else:
            values = PATTERN[index % 16637]
        result.extend(values[:channels])
    return result


class Spy:
    def __init__(self, channels, policy="full"):
        self.channels, self.policy = channels, policy
        self.calls = []
        self.sequence = 0

    def process(self, samples, requested):
        available = 0 if samples is None else len(samples) // self.channels
        # Lag controls never pretend to be a public SoXR sample model.
        used = available
        produced = requested
        if self.policy == "lag":
            used = max(0, available - min(7, available)) if samples is not None else 0
            produced = max(0, requested - 3)
        if self.policy == "zero":
            produced = 0
        output = []
        for frame in range(produced):
            # Distinct normal, exactly represented bits, bounded away from NaN.
            for channel in range(self.channels):
                output.append(0x3e000000 + ((self.sequence + frame) % 65521) * 2 + channel)
        self.sequence += produced
        self.calls.append(dict(
            input_frames=available, null_input=samples is None,
            input_sha256=digest(samples or []),
            first_bits=[f"{v:08x}" for v in (samples or [])[:self.channels]],
            last_bits=[f"{v:08x}" for v in (samples or [])[-self.channels:]],
            requested=requested, used=used, produced=produced,
            output_sha256=digest(output)))
        return used, output


class Wrapper:
    def __init__(self, source, output, channels, backend):
        self.source, self.output, self.channels = source, output, channels
        self.ratio = rn(Fraction(output, source))
        self.delay = ceil(self.ratio) * 2048
        self.discard = self.delay
        self.output_capacity = ceil(rn(rn(65536 * self.ratio + self.delay) + 1024))
        self.input = [0] * (65536 * channels)
        self.output_storage = [0] * (self.output_capacity * channels)
        self.input_end = self.input_consumed = self.pending_input = 0
        self.output_read, self.output_end = 0, self.delay
        self.cumulative_input = self.cumulative_visible = self.total_returned = 0
        self.cumulative_ideal = Fraction(0)
        self.backend_calls = self.backend_input_used = self.backend_output_produced = 0
        self.finished = False
        self.backend = backend
        self.events = []

    def snapshot(self):
        return dict(
            ratio_bits=f"{bits(self.ratio):016x}",
            cumulative_ideal_bits=f"{bits(self.cumulative_ideal):016x}",
            cumulative_input=self.cumulative_input, cumulative_visible=self.cumulative_visible,
            total_returned=self.total_returned, backend_calls=self.backend_calls,
            backend_input_used=self.backend_input_used,
            backend_output_produced=self.backend_output_produced,
            channels=self.channels, delay=self.delay, discard=self.discard,
            input_capacity=65536, output_capacity=self.output_capacity,
            input_end=self.input_end, input_consumed=self.input_consumed,
            pending_input=self.pending_input, output_read=self.output_read,
            output_end=self.output_end, finished=int(self.finished), failed=0)

    def child(self, samples, frames, requested):
        ch = self.channels
        if self.input_end + frames >= 65536 and self.input_consumed:
            assert self.input_consumed <= self.input_end
            keep = self.input_end - self.input_consumed
            self.input[:keep * ch] = self.input[self.input_consumed * ch:self.input_end * ch]
            self.input_end, self.input_consumed = keep, 0
            self.events.append("input_compaction")
        if self.output_end + requested >= self.output_capacity // 2 and self.output_read:
            assert self.output_read <= self.output_end, "native unsigned compaction outside bounded domain"
            keep = self.output_end - self.output_read
            self.output_storage[:keep * ch] = \
                self.output_storage[self.output_read * ch:self.output_end * ch]
            self.output_end, self.output_read = keep, 0
            self.events.append("output_compaction")
        assert self.input_end + frames <= 65536
        assert self.output_end + requested <= self.output_capacity
        assert self.output_read + requested <= self.output_capacity
        if samples is not None:
            self.input[self.input_end * ch:(self.input_end + frames) * ch] = samples
        if samples is None or not frames:
            offered = None
            self.pending_input = 0
        else:
            offered = self.input[self.input_consumed * ch:
                                 (self.input_consumed + self.pending_input + frames) * ch]
        used, produced_samples = self.backend.process(offered, requested)
        produced = len(produced_samples) // ch
        assert 0 <= used <= (len(offered) // ch if offered is not None else 0)
        assert 0 <= produced <= requested
        self.output_storage[self.output_end * ch:(self.output_end + produced) * ch] = produced_samples
        self.pending_input += frames - used
        self.input_consumed += used
        self.output_end += produced
        result = self.output_storage[self.output_read * ch:(self.output_read + requested) * ch]
        self.input_end += frames
        self.output_read += requested
        if self.input_end == self.input_consumed:
            self.input_end = self.input_consumed = 0
        if self.output_read == self.output_end:
            self.output_read = self.output_end = 0
        self.backend_calls += 1
        self.backend_input_used += used
        self.backend_output_produced += produced
        return result

    def requested(self, frames):
        ideal = rn(frames * self.ratio)
        base = int(ideal)
        drift = rn(rn(self.cumulative_ideal + ideal) -
                   (self.cumulative_visible + base))
        return ideal, base + int(drift > 1), drift

    def positive(self, samples, frames):
        ideal, requested, drift = self.requested(frames)
        requested = max(1, requested)
        self.events.append(dict(frames=frames, requested=requested,
                                drift_bits=f"{bits(drift):016x}",
                                drift_exact_one=drift == 1))
        result = self.child(samples, frames, requested)
        if self.discard >= requested:
            self.discard -= requested
            result = []
            contribution = Fraction(0)
        elif self.discard:
            result = result[self.discard * self.channels:]
            contribution = rn(ideal - self.discard)
            self.discard = 0
        else:
            contribution = ideal
        self.cumulative_input += frames
        self.cumulative_visible += len(result) // self.channels
        self.cumulative_ideal = rn(self.cumulative_ideal + contribution)
        return result

    def process(self, samples, final=False):
        assert not self.finished
        frames = 0 if samples is None else len(samples) // self.channels
        assert 0 <= frames <= 65408 and (frames or final)
        # Native zero-final skips child but retains w28 calculated before that
        # branch. Accepted reachable controls assert it is zero; no invention
        # of samples for an out-of-domain nonzero phantom count.
        if frames:
            result = self.positive(samples, frames)
        else:
            assert self.requested(0)[1] == 0, "zero-final precomputed native return is nonzero"
            result = []
        if final:
            saved_input = self.cumulative_input
            padding_frames = int(rn(Fraction(self.delay) / self.ratio))
            last = samples[-self.channels:] if frames else [0] * self.channels
            padding = last * padding_frames
            # Padding length can exceed the public per-call bound in extreme
            # downsampling; native recursion splits it at 65408.
            while len(padding) // self.channels > 65408:
                result += self.positive(padding[:65408 * self.channels], 65408)
                padding = padding[65408 * self.channels:]
            result += self.positive(padding, len(padding) // self.channels)
            self.cumulative_input = saved_input
            remaining = int(rn(saved_input * self.ratio)) - self.cumulative_visible
            if remaining > 0:
                result += self.child(None, 0, remaining)
            self.finished = True
        self.total_returned += len(result) // self.channels
        return result


def make_case(name, source, output, channels, blocks, policy="full", final=True, pattern="ramp"):
    spy = Spy(channels, policy)
    wrapper = Wrapper(source, output, channels, spy)
    initial = wrapper.snapshot()
    steps, offset = [], 0
    for i, count in enumerate(blocks):
        samples = input_samples(offset, count, channels, pattern) if count else None
        call_start = len(spy.calls)
        event_start = len(wrapper.events)
        produced = wrapper.process(samples, final and i == len(blocks) - 1)
        steps.append(dict(input_frames=count, final=final and i == len(blocks) - 1,
                          returned=len(produced) // channels, output_sha256=digest(produced),
                          output_prefix_bits=[f"{v:08x}" for v in produced[:16]],
                          output_suffix_bits=[f"{v:08x}" for v in produced[-16:]],
                          snapshot=wrapper.snapshot(), backend_calls=spy.calls[call_start:],
                          events=wrapper.events[event_start:]))
        offset += count
    return dict(name=name, source=source, output=output, channels=channels,
                policy=policy, pattern=pattern, initial=initial, steps=steps)


def count_only(source, output, total, block_frames=8192):
    """Independent ledger: no buffers, backend, or candidate count operation."""
    ratio = rn(Fraction(output, source))
    delay = ceil(ratio) * 2048
    discard, consumed, visible, ideal_sum, returned = delay, 0, 0, Fraction(0), 0
    steps = []

    def add(n):
        nonlocal discard, consumed, visible, ideal_sum
        ideal = rn(n * ratio)
        base = int(ideal)
        request = max(1, base + int(rn(rn(ideal_sum + ideal) - (visible + base)) > 1))
        lost = min(discard, request)
        new_visible = request - lost
        contribution = Fraction(0) if discard >= request else rn(ideal - lost)
        discard -= lost
        consumed += n
        visible += new_visible
        ideal_sum = rn(ideal_sum + contribution)
        return new_visible

    remaining = total
    while remaining:
        n = min(remaining, block_frames)
        result = add(n)
        remaining -= n
        if remaining == 0:
            saved = consumed
            pad = int(rn(Fraction(delay) / ratio))
            while pad:
                part = min(pad, 65408)
                result += add(part)
                pad -= part
            consumed = saved
            result += max(0, int(rn(saved * ratio)) - visible)
        returned += result
        steps.append(dict(input_frames=n, returned=result,
                          cumulative_input=consumed, cumulative_visible=visible,
                          cumulative_ideal_bits=f"{bits(ideal_sum):016x}", discard=discard))
    if total == 0:
        pad = int(rn(Fraction(delay) / ratio))
        while pad:
            part = min(pad, 65408)
            returned += add(part)
            pad -= part
        consumed = 0
    return dict(source=source, output=output, input_frames=total, block_frames=block_frames,
                final_policy="last-positive-call-final-or-null-zero-final",
                returned_frames=returned, final_cumulative_input=consumed,
                final_cumulative_visible=visible, final_discard=discard,
                final_cumulative_ideal_bits=f"{bits(ideal_sum):016x}", steps=steps)


def main():
    cases = []
    for source, output in [(44100, 48000), (48000, 44100), (48000, 48000),
                           (8000, 192000), (192000, 8000)]:
        for frames in [0, 1, 7, 2047, 2048, 2049, 8192]:
            cases.append(make_case(f"{source}-{output}-{frames}-terminal", source, output, 2, [frames]))
        cases.append(make_case(f"{source}-{output}-zero-final", source, output, 2, [8192, 8192, 0]))
    cases += [
        make_case("strict-drift-one", 8000, 12000, 1, [4096, 1, 1, 1, 1, 1, 0]),
        make_case("discard-equal-boundary", 48000, 48000, 1, [2047, 1, 1], final=False),
        make_case("discard-cross-boundary", 48000, 48000, 1, [2047, 2], final=False),
        make_case("both-compactions-lag", 48000, 44100, 2, [30000, 30000, 30000, 1000], "lag"),
        make_case("requested-not-produced-zero-storage", 48000, 48000, 2, [2048, 4], "zero", final=False),
        make_case("maximum-positive-block", 44100, 48000, 2, [65408]),
        make_case("multiple-maximum-blocks", 48000, 44100, 2, [65408, 65408, 17]),
    ]
    assert any(e.get("drift_exact_one") for c in cases for s in c["steps"]
               for e in s["events"] if isinstance(e, dict))
    assert "input_compaction" in cases[-4]["steps"][2]["events"]
    result = dict(schema_version=1, evidence_class="analytical-original-instruction-model",
                  target_execution=False, candidate_used_to_generate_expectations=False,
                  generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  ieee_helper_sha256=hashlib.sha256(HELPER.read_bytes()).hexdigest(),
                  native_addresses=["0x1003141bc", "0x100315000", "0x100315438"],
                  scope="Float32 mono/stereo successful backend domain; one terminal call; explicit per-call partitions",
                  limitations=["Spy samples do not model SoXR or Cubase.",
                               "Public backend comparison is separate.",
                               "Application failure/poison policy is stricter than native ignored errors."],
                  cases=cases,
                  full_source_counts=[count_only(44100, rate, 1058400)
                                      for rate in [48000, 32000, 16000, 44100]])
    path = HERE / "mode2-wrapper-oracle.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(path=str(path), cases=len(cases), bytes=path.stat().st_size,
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__ == "__main__":
    main()
