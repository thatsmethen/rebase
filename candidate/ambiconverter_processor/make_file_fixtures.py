#!/usr/bin/env python3
"""Self-authored WAV fixtures; expected products use pinned source tables as data.

No Cubase code executes. Exact-rational rounding is shared with test_processor's
independent oracle, not with the C candidate or the application's WAV writer.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
from test_processor import read_source_tables, bits_value, product_bytes


def wave(channels, width, payload):
    rate = 96000
    frame_bytes = channels * width // 8
    return (b'RIFF' + struct.pack('<I', 36 + len(payload)) + b'WAVEfmt ' +
            struct.pack('<IHHIIHH', 16, 3, channels, rate, rate * frame_bytes,
                        frame_bytes, width) + b'data' + struct.pack('<I', len(payload)) + payload)


def generate(directory):
    directory.mkdir(parents=True, exist_ok=False)
    maps, gains, source_record = read_source_tables()
    records = []
    frames = 8209
    for channels, width in ((9, 64), (16, 32)):
        one = 0x3f800000 if width == 32 else 0x3ff0000000000000
        fraction_bits = 23 if width == 32 else 52
        sign = 1 << (width - 1)
        payload = bytearray()
        expected = [bytearray(), bytearray()]
        for frame in range(frames):
            active = 1 if frame == frames - 1 else frame % channels
            exponent = (frame // channels) % 8
            zero = sign if frame % 3 == 0 else 0
            inputs = [zero] * channels
            inputs[active] = one + 1 if frame == frames - 1 else (one - (exponent << fraction_bits)) | (sign if frame % 2 else 0)
            for value in inputs:
                payload.extend(value.to_bytes(width // 8, 'little'))
            for direction in (0, 1):
                output = [None] * channels
                for channel, bits in enumerate(inputs):
                    destination = maps[direction][channel]
                    output[destination] = product_bytes(bits_value(bits, width), bits_value(gains[width][direction][destination], width), width)
                expected[direction].extend(b''.join(output))
        files = [(f'basis-{channels}ch-f{width}-source.wav', wave(channels, width, payload), 'self-authored input')]
        for direction in (0, 1):
            files.append((f'basis-{channels}ch-f{width}-expected-table-{"AB"[direction]}.wav',
                          wave(channels, width, expected[direction]), 'static-contract expected output; not native capture'))
        for name, data, role in files:
            path = directory / name
            path.write_bytes(data)
            records.append({'path': str(path.resolve()), 'sha256': hashlib.sha256(data).hexdigest(),
                            'bytes': len(data), 'role': role, 'channels': channels, 'precision': width,
                            'sample_rate': 96000, 'frames': frames})
    manifest = {'at_utc': datetime.now(timezone.utc).isoformat(), 'target_executed': False,
                'oracle': 'exact rational products, IEEE nearest-even; raw pinned tables read as data',
                'source_record': source_record, 'files': records}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'files': len(records), 'manifest': str((directory / 'manifest.json').resolve())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    generate(parser.parse_args().output_dir)
