#!/usr/bin/env python3
"""Check complete universal Mach-O code pages and embedded CMS binding.

This checks embedded hashes and CMS signature math, not bundle resources,
certificate trust/revocation, notarization, runtime behavior, or the full DMG.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys


def verify(path, output):
    raw = path.read_bytes()
    if raw[:4] != bytes.fromhex("cafebabe"):
        raise ValueError("this bounded verifier expects a big-endian FAT32 header")
    count = struct.unpack_from(">I", raw, 4)[0]
    if not 1 <= count <= 8 or 8 + count * 20 > len(raw):
        raise ValueError("invalid architecture count")
    output.mkdir(parents=True, exist_ok=False)
    verifier_bytes = Path(__file__).read_bytes()
    (output / "verifier-snapshot.py").write_bytes(verifier_bytes)
    results = []
    intervals = []
    for index in range(count):
        cpu, subtype, beginning, size, alignment = struct.unpack_from(">IIIII", raw, 8 + 20 * index)
        if beginning + size > len(raw) or any(beginning < high and beginning + size > low for low, high in intervals):
            raise ValueError("invalid or overlapping architecture slice")
        intervals.append((beginning, beginning + size))
        image = raw[beginning:beginning + size]
        if image[:4] != bytes.fromhex("cffaedfe"):
            raise ValueError("expected little-endian 64-bit Mach-O slice")
        commands, command_bytes = struct.unpack_from("<II", image, 16)
        position = 32
        signature = None
        for _ in range(commands):
            if position + 8 > 32 + command_bytes or position + 8 > len(image):
                raise ValueError("load command lies outside header")
            command, length = struct.unpack_from("<II", image, position)
            if length < 8 or position + length > min(len(image), 32 + command_bytes):
                raise ValueError("invalid load command size")
            if command == 0x1D:
                if signature is not None or length != 16:
                    raise ValueError("invalid or duplicate LC_CODE_SIGNATURE")
                signature = struct.unpack_from("<II", image, position + 8)
            position += length
        if position != 32 + command_bytes or signature is None:
            raise ValueError("missing signature or inconsistent load command count")
        signature_offset, signature_size = signature
        if signature_offset + signature_size > len(image):
            raise ValueError("signature lies outside slice")
        blob = image[signature_offset:signature_offset + signature_size]
        magic, length, entries = struct.unpack_from(">III", blob)
        if magic != 0xFADE0CC0 or length > len(blob) or 12 + 8 * entries > length:
            raise ValueError("invalid signature SuperBlob")
        children = {}
        for entry in range(entries):
            slot, offset = struct.unpack_from(">II", blob, 12 + 8 * entry)
            if offset + 8 > length or slot in children:
                raise ValueError("invalid signature child")
            child_length = struct.unpack_from(">I", blob, offset + 4)[0]
            if child_length < 8 or offset + child_length > length:
                raise ValueError("signature child exceeds container")
            children[slot] = blob[offset:offset + child_length]
        directory = children[0]
        if len(directory) < 64 or struct.unpack_from(">I", directory)[0] != 0xFADE0C02:
            raise ValueError("invalid CodeDirectory")
        version, flags, hash_offset, ident_offset, special_slots, code_slots, code_limit = struct.unpack_from(">7I", directory, 8)
        hash_size, hash_type, platform, page_exponent = struct.unpack_from(">4B", directory, 36)
        if version < 0x20300 or struct.unpack_from(">I", directory, 44)[0] != 0:
            raise ValueError("unsupported CodeDirectory version or scatter layout")
        extended_limit = struct.unpack_from(">Q", directory, 56)[0]
        if extended_limit:
            code_limit = extended_limit
        if hash_type != 2 or hash_size != 32 or not 1 <= page_exponent <= 20:
            raise ValueError("this verifier requires paged SHA-256 CodeDirectory slots")
        page_size = 1 << page_exponent
        if code_limit != signature_offset or code_slots != (code_limit + page_size - 1) // page_size:
            raise ValueError("code-page coverage does not end exactly at embedded signature")
        if hash_offset < special_slots * hash_size or hash_offset + code_slots * hash_size > len(directory):
            raise ValueError("CodeDirectory hash array exceeds blob")
        mismatch = []
        for page in range(code_slots):
            data = image[page * page_size:min((page + 1) * page_size, code_limit)]
            expected = directory[hash_offset + page * hash_size:hash_offset + (page + 1) * hash_size]
            if hashlib.sha256(data).digest() != expected:
                mismatch.append(page)
        architecture = {0x01000007: "x86_64", 0x0100000C: "arm64"}.get(cpu, hex(cpu))
        stem = output / architecture
        directory_path = Path(str(stem) + ".codedirectory.bin")
        directory_path.write_bytes(directory)
        cms = children[0x10000]
        if struct.unpack_from(">I", cms)[0] != 0xFADE0B01:
            raise ValueError("unsupported CMS wrapper")
        cms_path = Path(str(stem) + ".cms.der")
        cms_path.write_bytes(cms[8:])
        argv = ["openssl", "cms", "-verify", "-inform", "DER", "-in", str(cms_path),
                "-content", str(directory_path), "-noverify", "-binary", "-out", "/dev/null"]
        process = subprocess.run(argv, capture_output=True, text=True, check=False)
        result = {"architecture": architecture, "slice_offset": beginning, "slice_bytes": size,
                  "slice_sha256": hashlib.sha256(image).hexdigest(), "code_bytes_hashed": code_limit,
                  "page_size": page_size, "code_pages": code_slots, "mismatched_pages": mismatch,
                  "code_page_hashes_all_match": not mismatch, "cms_signature_math_valid": process.returncode == 0,
                  "codedirectory_sha256": hashlib.sha256(directory).hexdigest(),
                  "cms_sha256": hashlib.sha256(cms[8:]).hexdigest(),
                  "cms_check": {"argv": argv, "returncode": process.returncode,
                                "stdout": process.stdout, "stderr": process.stderr}}
        results.append(result)
    report = {"scope": __doc__, "path": str(path.resolve()), "file_sha256": hashlib.sha256(raw).hexdigest(),
              "verifier_sha256": hashlib.sha256(verifier_bytes).hexdigest(),
              "format_source": "https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/osfmk/kern/cs_blobs.h",
              "architectures": results}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.path, args.output)
    print(json.dumps(report, indent=2))
    sys.exit(0 if all(item["code_page_hashes_all_match"] and item["cms_signature_math_valid"]
                      for item in report["architectures"]) else 1)
