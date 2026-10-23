"""Check this GUI export with integer arithmetic; never execute target code."""
from pathlib import Path, PurePosixPath
import datetime
import hashlib
import json
import stat
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = HERE / "LoFi Render QA.rebaseproj"
OUTPUT = HERE / "Lofi_Ambience_16_Vinyl_Crackle_LD-source-event.wav"
BEFORE = HERE / "gui-package-before.json"
REPORT = HERE / "gui-source-render-independent-check.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def signature(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def stable_read(path):
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode), str(path)
    data = path.read_bytes()
    assert signature(before) == signature(path.lstat()), str(path)
    assert len(data) == before.st_size
    return data


def pin(path, data):
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data), sha256=digest(data))


def wave(data):
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    assert struct.unpack_from("<I", data, 4)[0] == len(data) - 8
    chunks, bodies, pos = [], {}, 12
    while pos < len(data):
        assert pos + 8 <= len(data)
        name, count = struct.unpack_from("<4sI", data, pos)
        end = pos + 8 + count
        assert end + (count & 1) <= len(data) and name not in bodies
        bodies[name] = data[pos + 8:end]
        chunks.append(dict(id=name.decode("ascii"), header_offset=pos, bytes=count))
        if count & 1:
            assert data[end] == 0
        pos = end + (count & 1)
    assert pos == len(data)
    fmt = bodies[b"fmt "]
    assert len(fmt) in (16, 18)
    if len(fmt) == 18:
        assert struct.unpack_from("<H", fmt, 16)[0] == 0
    tag, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", fmt)
    assert align == channels * (bits // 8) and bits % 8 == 0
    assert byte_rate == rate * align and len(bodies[b"data"]) % align == 0
    frames = len(bodies[b"data"]) // align
    fact = None
    if b"fact" in bodies:
        assert len(bodies[b"fact"]) == 4
        fact = struct.unpack("<I", bodies[b"fact"])[0]
        assert fact == frames
    return bodies[b"data"], dict(format_tag=tag, channels=channels, sample_rate=rate,
        byte_rate=byte_rate, block_align=align, bits_per_sample=bits, frames=frames,
        fact_frames=fact, chunks=chunks, riff_size=len(data) - 8, exact_riff_end=True)


def unit_pcm24_bits(value):
    """Exact binary32 encoding of value / 2**23; integer-only, no FP helper."""
    assert -(1 << 23) <= value < (1 << 23)
    if value == 0:
        return 0
    magnitude = abs(value)
    top = magnitude.bit_length() - 1
    exponent = top - 23 + 127
    fraction = (magnitude << (23 - top)) & 0x7fffff
    return ((value < 0) << 31) | (exponent << 23) | fraction


def main():
    assert not REPORT.exists(), "Preserve the completed check; do not overwrite it."
    baseline_bytes = stable_read(BEFORE)
    baseline = json.loads(baseline_bytes)
    assert baseline["copy"] == str(PACKAGE.relative_to(ROOT))
    expected_paths = sorted(row["path"] for row in baseline["files"])
    assert len(expected_paths) == len(set(expected_paths)) == 5
    actual_paths = []
    for path in PACKAGE.rglob("*"):
        mode = path.lstat().st_mode
        assert not stat.S_ISLNK(mode), str(path)
        if stat.S_ISREG(mode):
            actual_paths.append(str(path.relative_to(PACKAGE)))
        else:
            assert stat.S_ISDIR(mode), str(path)
    assert sorted(actual_paths) == expected_paths
    package_data, package_checks = {}, []
    for expected in baseline["files"]:
        path = PACKAGE / expected["path"]
        data = stable_read(path)
        assert len(data) == expected["bytes"] and digest(data) == expected["sha256"]
        package_data[expected["path"]] = data
        package_checks.append(dict(**expected, unchanged=True))
    project = json.loads(package_data["Project.json"])
    assert len(project["cprMediaAttachments"]) == 1
    attachment = project["cprMediaAttachments"][0]
    relative = PurePosixPath(attachment["mediaPath"])
    assert not relative.is_absolute() and ".." not in relative.parts
    source_path = PACKAGE / str(relative)
    source_bytes = package_data[str(relative)]
    assert digest(source_bytes) == attachment["mediaSHA256"]
    original = package_data["Compatibility/CPR/Original.cpr"]
    assert digest(original) == attachment["sourceSHA256"]
    events = [event for track in project["tracks"] for event in track.get("unresolvedAudioEvents", [])
              if any(file["object"]["identityOffset"] == attachment["sourceFileIdentity"]
                     for file in event["files"])]
    assert len(events) == 1
    event = events[0]
    assert event["sourceSHA256"] == attachment["sourceSHA256"]
    assert OUTPUT.name == event["name"] + "-source-event.wav"
    assert len(event["files"]) == len(event["segments"]) == 1
    segment = event["segments"][0]
    assert segment["storedStart"] == segment["storedOffset"] == 0
    assert segment["storedLength"] == attachment["frameCount"] == 1058400
    assert segment["streamIdentity"] == attachment["sourceFileIdentity"]
    output_bytes = stable_read(OUTPUT)
    samples, source_header = wave(source_bytes)
    output_samples, output_header = wave(output_bytes)
    for header in (source_header, output_header):
        assert (header["sample_rate"], header["channels"], header["frames"]) == (44100, 2, 1058400)
    assert (source_header["format_tag"], source_header["bits_per_sample"]) == (1, 24)
    assert (output_header["format_tag"], output_header["bits_per_sample"]) == (3, 32)
    assert output_header["fact_frames"] == 1058400
    assert [chunk["id"] for chunk in output_header["chunks"]] == ["fmt ", "fact", "data"]
    assert (attachment["sampleRate"], attachment["channels"], attachment["bitsPerSample"],
            attachment["bytesPerFrame"]) == (44100, 2, 24, 6)
    # Controls discriminate /8388607, unsigned decoding, and signed endpoint errors.
    assert [unit_pcm24_bits(x) for x in (-8388608, -1, 0, 1, 8388607)] == [
        0xbf800000, 0xb4000000, 0, 0x34000000, 0x3f7ffffe]
    count = len(samples) // 3
    assert count == 2116800 and len(output_samples) == count * 4
    expected_payload = bytearray(count * 4)
    minima, maxima, zeros = [8388607] * 2, [-8388608] * 2, [0, 0]
    mismatches, examples = 0, []
    for index in range(count):
        offset = index * 3
        value = samples[offset] | samples[offset + 1] << 8 | samples[offset + 2] << 16
        if value & 0x800000:
            value -= 0x1000000
        expected = unit_pcm24_bits(value)
        actual = struct.unpack_from("<I", output_samples, index * 4)[0]
        struct.pack_into("<I", expected_payload, index * 4, expected)
        channel = index % 2
        minima[channel] = min(minima[channel], value)
        maxima[channel] = max(maxima[channel], value)
        zeros[channel] += value == 0
        if actual != expected:
            mismatches += 1
            if len(examples) < 8:
                examples.append(dict(sample_index=index, frame=index // 2, channel=channel,
                    signed24=value, expected_bits=f"{expected:08x}", actual_bits=f"{actual:08x}"))
    assert digest(expected_payload) == digest(output_samples) and mismatches == 0, examples
    # Catch concurrent changes during the full comparison as well as each initial read.
    for relative, data in package_data.items():
        assert stable_read(PACKAGE / relative) == data
    assert stable_read(OUTPUT) == output_bytes and stable_read(BEFORE) == baseline_bytes
    report = dict(schema_version=1, created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status="passed", classification="Independent application GUI-export arithmetic and custody check",
        script=pin(Path(__file__).resolve(), stable_read(Path(__file__).resolve())),
        baseline=pin(BEFORE, baseline_bytes), source_attachment=pin(source_path, source_bytes),
        output=pin(OUTPUT, output_bytes), original_cpr_sha256=digest(original),
        association=attachment["association"], selected_filename=attachment["selectedFilename"],
        source_file_identity=attachment["sourceFileIdentity"], event_id=event["id"],
        package=dict(path=str(PACKAGE.relative_to(ROOT)), exact_file_set=True,
                     files_verified_unchanged=5, files=package_checks),
        source_wave=source_header, output_wave=output_header,
        comparison=dict(rule="Sign-extend each little-endian 24-bit integer p; encode exact p/2^23 in binary32 using integer bit length, exponent and mantissa. Unity event gain.",
            implementation_independence="No application/C kernel/AVFoundation conversion or floating division reused.",
            frames=1058400, channels=2, samples_compared=count, mismatches=mismatches,
            first_mismatches=examples, every_output_bit_matches=True,
            output_payload_sha256=digest(output_samples), independently_expected_payload_sha256=digest(expected_payload),
            signed24_minimum_by_channel=minima, signed24_maximum_by_channel=maxima,
            zero_samples_by_channel=zeros),
        limitations=["The user-selected source is the synthetic fixture named Synthetic LoFi Format.wav; this is not recovered original Cubase media.",
                     "This verifies the application-produced file against its attachment at unity gain, not Cubase runtime audio or full-project rendering.",
                     "Nonunity gain, other formats/rates and audible output are outside this check."],
        proprietary_code_executed=False, cubase_runtime_comparisons=0)
    with REPORT.open("x") as out:
        json.dump(report, out, indent=2)
        out.write("\n")
    print(json.dumps(dict(report=pin(REPORT, REPORT.read_bytes()), samples=count,
                          mismatches=mismatches, package_files_unchanged=5, passed=True)))


if __name__ == "__main__":
    main()
