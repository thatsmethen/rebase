#!/usr/bin/env python3
"""Create a deterministic, self-authored project for native app verification."""
import argparse
import json
import math
import random
import struct
import uuid
import wave
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    (root / 'Media').mkdir()
    rate = 48000
    seconds = 12
    rng = random.Random(151030)
    names = ['Pulse', 'Low Orbit', 'Glass Keys']
    tracks = []
    identity = lambda name: str(uuid.uuid5(uuid.NAMESPACE_URL, 'rebase-app-demo:' + name))
    for channel, name in enumerate(names):
        data = bytearray()
        for n in range(rate * seconds):
            t = n / rate
            beat = t % 0.5
            if channel == 0:
                kick = math.sin(2 * math.pi * (48 * beat + 4 * (1 - math.exp(-beat * 30)))) * math.exp(-beat * 22)
                hat = (rng.random() * 2 - 1) * math.exp(-(t % 0.25) * 140) * 0.28
                value = 0.31 * (kick + hat)
                left, right = value, value
            elif channel == 1:
                f = [55, 55, 65.4064, 49][int(t / 1.5) % 4]
                envelope = min(1, beat * 100) * math.exp(-beat * 4)
                value = 0.22 * envelope * (math.sin(2 * math.pi * f * t) + 0.2 * math.sin(2 * math.pi * 2 * f * t))
                left, right = value, value
            else:
                notes = [220, 261.6256, 329.6276, 391.9954]
                phase = t % 1.5
                envelope = min(1, phase * 20) * math.exp(-phase * 2.5)
                left = sum(math.sin(2 * math.pi * f * t) for f in notes) * 0.045 * envelope
                right = sum(math.sin(2 * math.pi * (f * 1.001) * t) for f in notes) * 0.045 * envelope
            data += struct.pack('<hh', round(left * 32767), round(right * 32767))
        path = f'Media/{name}.wav'
        with wave.open(str(root / path), 'wb') as wav:
            wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(data)
        clip = dict(id=identity(name + ':clip'), mediaPath=path, name=name,
                    position=0 if channel < 2 else 1.5, sourceOffset=0, duration=seconds)
        tracks.append(dict(id=identity(name), name=name, gainDB=-3 if channel == 2 else 0,
                           pan=0, isMuted=False, isSolo=False, clips=[clip]))
    project = dict(id=identity('project'), name='Studio Check', tempo=120, sampleRate=rate, tracks=tracks)
    (root / 'Project.json').write_text(json.dumps(project, indent=2) + '\n')
    print(root.resolve())

if __name__ == '__main__':
    main()
