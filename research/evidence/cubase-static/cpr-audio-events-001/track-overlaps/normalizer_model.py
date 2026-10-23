"""Authored value model of 10020e7c8; never runs target machine code.

Inputs must already be chronological, finite, nonnegative, positive ranges.
Only list values are modeled: object lifetimes, callbacks and allocation failure
are outside this contract. Every split preserves original event and ordinal.
"""
from dataclasses import dataclass, replace
import math
import struct

EPSILON = struct.unpack('>d', bytes.fromhex('3f1a36e2eb1c432d'))[0]
INITIAL_WATERMARK = struct.unpack('>d', bytes.fromhex('c14b774000000000'))[0]


@dataclass(eq=False)
class Range:
    event: int
    ordinal: int
    priority: int
    start: float
    end: float


def normalize(source, trace=None):
    """The input order is preserved, not repaired with a sort.

    This uses node identity while visiting a removed node's saved successor,
    matching 10020e988/10020ea1c; new tails are inserted after equal starts.
    trace, when supplied, records which native branch justified each mutation.
    """
    trace = [] if trace is None else trace
    assert len(source) <= 4096
    for i, r in enumerate(source):
        assert math.isfinite(r.start) and math.isfinite(r.end)
        assert 0 <= r.start < r.end <= 86400
        assert -(1 << 31) <= r.priority < (1 << 31)
        assert 0 <= r.ordinal < (1 << 31)
        assert i == 0 or source[i - 1].start <= r.start
    assert len({r.ordinal for r in source}) == len(source)
    pending = [replace(r) for r in source]
    result = []
    watermark = INITIAL_WATERMARK
    steps = 0

    def insert_after_equal_start(r):
        # 10020e9c8..ea00 / 10020eabc..eae0: scan backward from tail.
        i = len(pending)
        while i and pending[i - 1].start > r.start:
            i -= 1
        pending.insert(i, r)

    def publish(r, address):
        nonlocal watermark
        if r.start < watermark:
            trace.append({'pc': address, 'action': 'clamp', 'event': r.event})
            r.start = watermark
        if watermark < r.end:
            watermark = r.end
        if r.end - r.start > 0:
            result.append(replace(r))
            trace.append({'pc': address, 'action': 'publish', 'event': r.event})

    while pending:
        current = pending.pop(0)  # +18 head and 103101e50 unlink
        following = pending[0] if pending else None
        while following is not None:
            steps += 1
            if steps > 4_000_000:
                raise ValueError('defensive model work bound')
            # FABD is rounded binary64 subtraction followed by absolute value.
            if not (current.end >= following.start and
                    abs(current.end - following.start) >= EPSILON):
                publish(current, '0x10020e8a8')
                break
            higher_current = (following.priority < current.priority or
                following.priority == current.priority and following.ordinal < current.ordinal)
            if higher_current:
                # Save successor before unlink/reinsertion, not pending[0].
                index = pending.index(following)
                successor = pending[index + 1] if index + 1 < len(pending) else None
                pending.pop(index)
                if (following.end >= current.end and
                        abs(following.end - current.end) >= EPSILON):
                    following.start = current.end
                    insert_after_equal_start(following)
                    trace.append({'pc': '0x10020e9b4', 'action': 'trim-following-tail',
                                  'event': following.event})
                else:
                    trace.append({'pc': '0x10020ea04', 'action': 'discard-following',
                                  'event': following.event})
                following = successor
                if following is None:
                    publish(current, '0x10020eae8')
                    break
                continue
            # Following is stronger. Clone trailing current if >= epsilon.
            if current.end >= following.end and abs(current.end - following.end) >= EPSILON:
                tail = replace(current, start=following.end)
                insert_after_equal_start(tail)
                trace.append({'pc': '0x10020eab8', 'action': 'clone-current-tail',
                              'event': current.event})
            # Only a strictly earlier, epsilon-wide prefix survives.
            if current.start < following.start and abs(current.start - following.start) >= EPSILON:
                current.end = following.start
                publish(current, '0x10020eb58')
            else:
                trace.append({'pc': '0x10020eb54', 'action': 'discard-current-prefix',
                              'event': current.event})
            break
        else:
            publish(current, '0x10020ea38')
    return result


def values(ranges):
    return [(r.event, r.ordinal, r.priority, r.start, r.end) for r in ranges]
