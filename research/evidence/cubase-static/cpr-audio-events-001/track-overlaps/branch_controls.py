"""Numerical controls for authored overlap model, not a native runtime oracle.

The queue model is checked against a separate two-event interval oracle with
Fraction-derived rounded subtraction, and a maximum-priority envelope on
well-separated random endpoints where the native epsilon cannot prune spans.
"""
from pathlib import Path
from fractions import Fraction
from itertools import combinations, product
import hashlib
import json
import math
import random
import struct
import sys
sys.dont_write_bytecode = True
from normalizer_model import Range, normalize, values, EPSILON

H = Path(__file__).resolve().parent
bits = lambda x: struct.pack('>d', x).hex()
fraction = Fraction.from_float
epsilon = fraction(EPSILON)


def distance_at_least(a, b):
    # Exact rational difference followed by binary64 nearest/even rounding.
    return fraction(float(abs(fraction(a) - fraction(b)))) >= epsilon


def pair_oracle(a, b):
    def row(r, x, y):
        return [(r.event, r.ordinal, r.priority, x, y)] if x < y else []
    if a.end < b.start or not distance_at_least(a.end, b.start):
        return row(a, a.start, a.end) + row(b, max(a.end, b.start), b.end)
    a_wins = (a.priority, a.ordinal) > (b.priority, b.ordinal)
    if a_wins:
        tail = row(b, a.end, b.end) if b.end >= a.end and distance_at_least(b.end, a.end) else []
        return row(a, a.start, a.end) + tail
    prefix = row(a, a.start, b.start) if a.start < b.start and distance_at_least(a.start, b.start) else []
    tail = row(a, b.end, a.end) if a.end >= b.end and distance_at_least(a.end, b.end) else []
    return prefix + row(b, b.start, b.end) + tail


def coalesce(rows):
    out = []
    for r in rows:
        if out and out[-1][:3] == r[:3] and out[-1][4] == r[3]:
            out[-1] = out[-1][:4] + (r[4],)
        else:
            out.append(tuple(r))
    return out


def envelope_oracle(source):
    endpoints = sorted(set(x for r in source for x in [r.start, r.end]))
    out = []
    for a, b in zip(endpoints, endpoints[1:]):
        covering = [r for r in source if r.start <= a and r.end >= b]
        if covering:
            r = max(covering, key=lambda r: (r.priority, r.ordinal))
            out.append((r.event, r.ordinal, r.priority, a, b))
    return coalesce(out)


def encode(rows):
    return [dict(event=r[0], ordinal=r[1], priority=r[2], start_bits=bits(r[3]), end_bits=bits(r[4])) for r in rows]


def main():
    reports = []
    trace = []
    labels = [
        ('crossing-later-equal-priority', [(0, 4, 1), (2, 6, 1)]),
        ('nested-later-equal-priority', [(0, 8, 1), (2, 4, 1)]),
        ('crossing-earlier-higher-priority', [(0, 4, 2), (2, 6, 1)]),
        ('nested-earlier-higher-priority', [(0, 8, 2), (2, 4, 1)]),
        ('same-start-later-equal', [(0, 8, 1), (0, 4, 1)]),
        ('same-range-later-equal', [(0, 4, 1), (0, 4, 1)]),
        ('signed-priority-min-max', [(0, 4, -2147483648), (2, 6, 2147483647)]),
        ('touching-higher-later', [(0, 2, 1), (2, 4, 2)]),
        ('three-nested-later-ties', [(0, 10, 1), (2, 8, 1), (4, 6, 1)]),
        ('chain-alternating-priorities', [(0, 6, 1), (2, 8, 3), (4, 10, 2), (6, 12, 4)]),
        ('reinsert-tail-after-equal-start', [(0, 4, 3), (2, 10, 1), (4, 8, 2)]),
        ('higher-current-removes-multiple', [(0, 10, 4), (2, 4, 2), (6, 12, 1)]),
    ]
    for label, triples in labels:
        source = [Range(i, i, p, float(a), float(b)) for i, (a, b, p) in enumerate(triples)]
        actions = []
        got = values(normalize(source, actions))
        expected = envelope_oracle(source)
        assert coalesce(got) == expected, label
        reports.append(dict(label=label, input=encode(values(source)), output=encode(got), trace=actions))
        trace.extend(actions)

    pair_hash = hashlib.sha256()
    pair_count = 0
    endpoints = sorted(set([0., math.nextafter(EPSILON, 0.), EPSILON,
        math.nextafter(EPSILON, math.inf), 2 * EPSILON, 3 * EPSILON,
        1., math.nextafter(1., 0.), math.nextafter(1., math.inf), 1. + EPSILON,
        2., 86400.]))
    windows = list(combinations(endpoints, 2))
    for (a, z), (b, y), priorities in product(windows, windows,
            [(-2147483648, 2147483647), (2, 1), (1, 1), (-1, 0), (0, -1)]):
        if a > b:
            continue
        source = [Range(0, 0, priorities[0], a, z), Range(1, 1, priorities[1], b, y)]
        got = values(normalize(source))
        expected = pair_oracle(*source)
        assert got == expected, (source, got, expected)
        pair_hash.update(json.dumps([encode(values(source)), encode(got)], sort_keys=True).encode())
        pair_count += 1

    for label, delta in [('below', math.nextafter(EPSILON, 0.)), ('at', EPSILON),
                         ('above', math.nextafter(EPSILON, math.inf))]:
        # End/start anchored at zero avoids subtraction hiding threshold ULPs.
        for kind, source in [
            ('overlap', [Range(0, 0, 1, 0., delta), Range(1, 1, 2, 0., 1.)]),
            ('prefix', [Range(0, 0, 1, 0., 1.), Range(1, 1, 2, delta, 1.)]),
        ]:
            actions = []
            got = values(normalize(source, actions))
            assert got == pair_oracle(*source)
            reports.append(dict(label=f'{kind}-{label}-epsilon', input=encode(values(source)),
                                output=encode(got), trace=actions))
            trace.extend(actions)

        # Directly adding EPSILON + nextafter(EPSILON) can lose the ULP at
        # the larger exponent. Choose endpoints whose actual subtraction is
        # exactly the requested neighboring epsilon bit pattern instead.
        current_end = EPSILON if label == 'at' else math.nextafter(EPSILON, math.inf)
        following_end = math.nextafter(2 * EPSILON, math.inf) if label == 'above' else 2 * EPSILON
        assert following_end - current_end == delta
        for winner in ['current', 'following']:
            if winner == 'current':
                source = [Range(0, 0, 2, 0., current_end), Range(1, 1, 1, 0., following_end)]
            else:
                source = [Range(0, 0, 1, 0., following_end), Range(1, 1, 2, 0., current_end)]
            actions = []
            got = values(normalize(source, actions))
            assert got == pair_oracle(*source)
            reports.append(dict(label=f'{winner}-wins-tail-{label}-epsilon',
                actual_tail_distance_bits=bits(following_end - current_end),
                input=encode(values(source)), output=encode(got), trace=actions))
            trace.extend(actions)

    # Independent geometric max-priority oracle, endpoints at least 1 apart.
    rng = random.Random(0x10020E7C8)
    multi_hash = hashlib.sha256()
    multi_count = 20000
    priorities = [-2147483648, -3, -1, 0, 1, 2, 2147483647]
    for case in range(multi_count):
        starts = sorted(rng.randrange(0, 64) for _ in range(rng.randrange(1, 33)))
        source = [Range(i, i, rng.choice(priorities), float(a), float(rng.randrange(a + 1, 96)))
                  for i, a in enumerate(starts)]
        got = values(normalize(source, trace))
        assert coalesce(got) == envelope_oracle(source), (case, source, got)
        assert all(x[4] <= y[3] for x, y in zip(got, got[1:])), case
        multi_hash.update(json.dumps([encode(values(source)), encode(got)], sort_keys=True).encode())

    # Native collector assigns ordinals in all-passing order. A copied tail
    # keeps that original ordinal even when it moves behind newer ranges.
    bound_source = [Range(i, i, 1, float(i), float(i + 2)) for i in range(4096)]
    bound_result = normalize(bound_source)
    assert len(bound_result) == 4096
    assert values(bound_result) == [(i, i, 1, float(i), float(i + (2 if i == 4095 else 1))) for i in range(4096)]
    data = dict(kind='authored analytical numerical models; zero proprietary target executions',
        epsilon_bits=bits(EPSILON), source_sha256='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb',
        controls=reports, threshold_pair_cases=pair_count, pair_stream_sha256=pair_hash.hexdigest(),
        maximum_priority_envelope_cases=multi_count, envelope_stream_sha256=multi_hash.hexdigest(),
        bound_4096_events_passed=True, actions_covered=sorted(set(t['action'] for t in trace)),
        passed=True, limits=['Separate mathematical oracles corroborate authored branch translation, not native execution.',
          'Chronological finite positive input only; unsorted data is rejected, not sorted.',
          'No fades, object lifecycle, allocation failure, dynamic getter mutation, or hosted mixing contract.',
          'No application acceptance or runtime comparison is claimed by this research output.'])
    (H / 'branch-controls.json').write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({k: data[k] for k in ['threshold_pair_cases', 'maximum_priority_envelope_cases', 'actions_covered', 'passed']}))


if __name__ == '__main__':
    main()
