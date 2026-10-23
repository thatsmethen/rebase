#!/usr/bin/env python3
"""Recover complete regular files from the acquired prefix of this UDIF/HFS+ PKG.

Bounded decoder: raw/zlib/zero UDIF blocks, HFS+ primary extents, a flat XAR
package, and gzip-compressed ASCII-odc CPIO. Unsupported forms fail closed.
This never mounts an image, creates symlinks, or executes extracted code.
"""
from __future__ import annotations

import argparse
import bisect
from collections import OrderedDict
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import stat
import struct
import xml.etree.ElementTree as ET
import zlib

from fetch_reference import hash_region, save_json, validate_range


class MissingRange(Exception):
    pass


class Image:
    def __init__(self, downloads, destination):
        self.downloads = downloads
        self.destination = destination
        name = "Cubase_15.0.30_Installer_mac.dmg"
        state_bytes = (downloads / (name + ".download.json")).read_bytes()
        self.state = json.loads(state_bytes)
        self.source = self.state["source"]
        self.path = downloads / (name + ".part")
        if not self.path.exists():
            self.path = downloads / name
        self.intervals = []
        for segment in self.state["segments"]:
            if not segment["received"]:
                continue
            if hash_region(self.path, segment["start"], segment["received"]) != segment["sha256"]:
                raise ValueError("source segment differs from acquisition journal")
            start, end = segment["start"], segment["start"] + segment["received"]
            if self.intervals and self.intervals[-1][1] == start:
                self.intervals[-1][1] = end
            else:
                self.intervals.append([start, end])
        (destination / "source-acquisition-snapshot.json").write_bytes(state_bytes)
        (destination / "decoder-snapshot.py").write_bytes(Path(__file__).read_bytes())
        probes = downloads / "range-probes"
        footer = self.probe(probes, "dmg-footer", self.source["size"] - 512, 512)
        if footer[:4] != b"koly":
            raise ValueError("unsupported image footer")
        xml_offset, xml_length = struct.unpack_from(">QQ", footer, 216)
        metadata = self.probe(probes, "dmg-plist", xml_offset, xml_length)
        maps = plistlib.loads(metadata)["resource-fork"]["blkx"]
        selected = [item for item in maps if "Apple_HFS" in item["Name"]]
        if len(selected) != 1:
            raise ValueError("expected exactly one HFS partition")
        raw = selected[0]["Data"]
        if raw[:4] != b"mish":
            raise ValueError("unsupported block map signature")
        self.data_offset = struct.unpack_from(">Q", raw, 24)[0]
        count = struct.unpack_from(">I", raw, 200)[0]
        if len(raw) != 204 + 40 * count:
            raise ValueError("unexpected block map length")
        self.blocks = [struct.unpack_from(">IIQQQQ", raw, 204 + 40 * i) for i in range(count)]
        self.blocks = [block for block in self.blocks if block[3]]
        self.starts = [block[2] * 512 for block in self.blocks]
        if self.starts != sorted(set(self.starts)):
            raise ValueError("block map is not ordered and distinct")
        self.cache = OrderedDict()
        self.used = {}
        self.provenance = {
            "scope": "Recovered component files from partial official image; whole DMG SHA-256 unavailable.",
            "source": self.source,
            "acquisition_snapshot_sha256": hashlib.sha256(state_bytes).hexdigest(),
            "footer_sha256": hashlib.sha256(footer).hexdigest(),
            "dmg_plist_sha256": hashlib.sha256(metadata).hexdigest(),
            "format_reference": "https://developer.apple.com/library/archive/technotes/tn/tn1150.html",
            "decoder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "verified_local_intervals": self.intervals,
            "checks_not_completed": ["whole DMG checksum", "complete XAR payload checksum", "complete gzip CRC trailer"],
        }

    def probe(self, directory, name, start, length):
        data = (directory / (name + ".bin")).read_bytes()
        validate_range((directory / (name + ".headers")).read_bytes(), self.source, start, start + length - 1)
        if len(data) != length:
            raise ValueError("metadata range has unexpected length")
        return data

    def decoded_block(self, index):
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index]
        kind, comment, sector, sectors, offset, length = self.blocks[index]
        physical = self.data_offset + offset
        if kind in (0, 2):
            raw = bytes(sectors * 512)
            compressed = b""
        else:
            if not any(start <= physical and physical + length <= end for start, end in self.intervals):
                raise MissingRange(f"DMG bytes {physical}..{physical + length - 1} are not fully acquired")
            with self.path.open("rb") as handle:
                handle.seek(physical)
                compressed = handle.read(length)
            if len(compressed) != length:
                raise ValueError("source block is truncated")
            if kind == 0x80000005:
                decoder = zlib.decompressobj()
                raw = decoder.decompress(compressed, sectors * 512 + 1)
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError("incomplete or unexpected zlib block")
            elif kind == 1:
                raw = compressed
            else:
                raise ValueError(f"unsupported UDIF block type {kind:#x}")
        if len(raw) != sectors * 512:
            raise ValueError("decoded block length disagrees with sector count")
        self.used[index] = {"block_index": index, "type": hex(kind), "image_offset": physical,
                            "compressed_bytes": length, "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
                            "volume_offset": sector * 512, "decoded_bytes": len(raw),
                            "decoded_sha256": hashlib.sha256(raw).hexdigest()}
        self.cache[index] = raw
        while len(self.cache) > 4:
            self.cache.popitem(last=False)
        return raw

    def read(self, offset, length):
        result = bytearray()
        while length:
            index = bisect.bisect_right(self.starts, offset) - 1
            if index < 0:
                raise ValueError("volume read precedes first block")
            block = self.blocks[index]
            relative = offset - block[2] * 512
            count = min(length, block[3] * 512 - relative)
            if count <= 0:
                raise ValueError("gap in volume block map")
            data = self.decoded_block(index)
            result.extend(data[relative:relative + count])
            offset += count
            length -= count
        return bytes(result)

    def catalog(self):
        header = self.read(1024, 512)
        if header[:2] != b"H+":
            raise ValueError("expected HFS+ volume header")
        self.block_size = struct.unpack_from(">I", header, 40)[0]
        length = struct.unpack_from(">Q", header, 272)[0]
        if length > 64 * 1024 * 1024:
            raise ValueError("catalog exceeds decoder bound")
        extents = [struct.unpack_from(">II", header, 288 + i * 8) for i in range(8)]
        catalog = self.read_extents(extents, length)
        node_size = struct.unpack_from(">H", catalog, 32)[0]
        node_id = struct.unpack_from(">I", catalog, 24)[0]
        expected_records = struct.unpack_from(">I", catalog, 20)[0]
        if node_size not in (512, 1024, 2048, 4096, 8192, 16384, 32768):
            raise ValueError("unsupported catalog node size")
        records = []
        seen = set()
        count = 0
        while node_id:
            if node_id in seen or (node_id + 1) * node_size > len(catalog):
                raise ValueError("invalid or cyclic catalog node link")
            seen.add(node_id)
            node = catalog[node_id * node_size:(node_id + 1) * node_size]
            forward, backward, kind, height, number, reserved = struct.unpack_from(">IIbBHH", node)
            if kind != -1 or 2 * (number + 1) > node_size - 14:
                raise ValueError("invalid catalog leaf node")
            for i in range(number):
                pos = struct.unpack_from(">H", node, node_size - 2 - 2 * i)[0]
                key_length, parent, name_length = struct.unpack_from(">HIH", node, pos)
                if key_length != 6 + 2 * name_length or pos + 2 + key_length > node_size:
                    raise ValueError("malformed catalog key")
                name = node[pos + 8:pos + 8 + name_length * 2].decode("utf-16-be")
                record = node[pos + 2 + key_length:]
                record_type = struct.unpack_from(">h", record)[0]
                count += 1
                if record_type == 2:
                    records.append({"name": name, "parent_id": parent,
                                    "id": struct.unpack_from(">I", record, 8)[0],
                                    "length": struct.unpack_from(">Q", record, 88)[0],
                                    "extents": [list(struct.unpack_from(">II", record, 104 + j * 8)) for j in range(8)]})
            node_id = forward
        if count != expected_records:
            raise ValueError("catalog traversal record count mismatch")
        save_json(self.destination / "catalog-files.json", {"catalog_sha256": hashlib.sha256(catalog).hexdigest(),
                                                             "leaf_records": count, "files": records})
        return records

    def read_extents(self, extents, length):
        result = bytearray()
        for beginning, blocks in extents:
            count = min(length - len(result), blocks * self.block_size)
            if count:
                result.extend(self.read(beginning * self.block_size, count))
            if len(result) == length:
                return bytes(result)
        raise ValueError("fork needs unsupported overflow extents")


class ODC:
    def __init__(self, destination, maximum):
        self.destination = destination
        self.maximum = maximum
        self.buffer = bytearray()
        self.pending = self.current = None
        self.records = []
        self.total = 0
        self.trailer = False

    def feed(self, data):
        self.total += len(data)
        if self.total > self.maximum:
            raise ValueError("unpacked stream exceeds configured bound")
        self.buffer.extend(data)
        while self.buffer and not self.trailer:
            if self.current is None:
                if self.pending is None:
                    if len(self.buffer) < 76:
                        return
                    header = bytes(self.buffer[:76])
                    del self.buffer[:76]
                    if header[:6] != b"070707":
                        raise ValueError("unsupported CPIO encoding; expected ASCII odc")
                    mode = int(header[18:24], 8)
                    links = int(header[36:42], 8)
                    if stat.S_ISREG(mode) and links != 1:
                        raise ValueError("hard-linked CPIO files require an unsupported reconstruction rule")
                    name_size, size = int(header[59:65], 8), int(header[65:76], 8)
                    if not 1 <= name_size <= 8192 or size > self.maximum:
                        raise ValueError("CPIO name or file size exceeds bound")
                    self.pending = mode, name_size, size
                mode, name_size, size = self.pending
                if len(self.buffer) < name_size:
                    return
                name_bytes = bytes(self.buffer[:name_size])
                del self.buffer[:name_size]
                if name_bytes[-1:] != b"\0" or b"\0" in name_bytes[:-1]:
                    raise ValueError("malformed CPIO filename")
                name = name_bytes[:-1].decode("utf-8")
                if name == "TRAILER!!!":
                    self.trailer = True
                    return
                clean = PurePosixPath(name)
                if clean.is_absolute() or ".." in clean.parts:
                    raise ValueError("unsafe CPIO path")
                target = self.destination.joinpath(*clean.parts)
                handle = None
                if stat.S_ISREG(mode):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    partial = Path(str(target) + ".part")
                    if target.exists() or partial.exists():
                        raise ValueError("extracted path already exists; use a fresh output directory")
                    handle = partial.open("xb")
                self.current = {"path": str(clean), "mode": mode, "declared_bytes": size,
                                "received_bytes": 0, "digest": hashlib.sha256(),
                                "head": b"", "handle": handle, "target": target}
                self.pending = None
            current = self.current
            count = min(len(self.buffer), current["declared_bytes"] - current["received_bytes"])
            chunk = bytes(self.buffer[:count])
            del self.buffer[:count]
            current["digest"].update(chunk)
            current["head"] = (current["head"] + chunk)[:16]
            if current["handle"]:
                current["handle"].write(chunk)
            current["received_bytes"] += count
            if current["received_bytes"] != current["declared_bytes"]:
                return
            if current["handle"]:
                current["handle"].close()
                Path(str(current["target"]) + ".part").rename(current["target"])
            record = {key: current[key] for key in ("path", "mode", "declared_bytes", "received_bytes")}
            record.update({"sha256": current["digest"].hexdigest(), "first_bytes_hex": current["head"].hex(),
                           "regular_file_written": stat.S_ISREG(current["mode"]), "complete_declared_file_bytes": True})
            self.records.append(record)
            self.current = None

    def finish(self):
        partial = None
        if self.current:
            current = self.current
            if current["handle"]:
                current["handle"].close()
            partial = {key: current[key] for key in ("path", "declared_bytes", "received_bytes")}
            partial["status"] = "incomplete; never promoted to component filename"
        return {"complete_records": self.records, "partial_record": partial,
                "cpio_trailer_seen": self.trailer, "unpacked_bytes_consumed": self.total}


def inspect(args):
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    image = Image(args.downloads.resolve(), destination)
    packages = [record for record in image.catalog() if record["name"] == "Cubase 15.pkg"]
    if len(packages) != 1:
        raise ValueError("expected exactly one Cubase package")
    package = packages[0]
    extents = [extent for extent in package["extents"] if extent[1]]
    if len(extents) != 1 or extents[0][1] * image.block_size < package["length"]:
        raise ValueError("this decoder requires one complete package extent")
    package_start = extents[0][0] * image.block_size
    xar_header = image.read(package_start, 28)
    magic, header_size, version, compressed_length, plain_length, checksum_kind = struct.unpack(">4sHHQQI", xar_header)
    if magic != b"xar!" or version != 1 or header_size != 28 or compressed_length > 1024 * 1024:
        raise ValueError("unsupported XAR header")
    toc = zlib.decompress(image.read(package_start + header_size, compressed_length))
    if len(toc) != plain_length:
        raise ValueError("XAR TOC size mismatch")
    (destination / "package-toc.xml").write_bytes(toc)
    tree = ET.fromstring(toc)
    selected = None
    for directory in tree.find("toc").findall("file"):
        if directory.findtext("name") == "Cubase 15.app.pkg":
            for item in directory.findall("file"):
                if item.findtext("name") == "Payload":
                    selected = item.find("data")
    if selected is None or selected.find("encoding").get("style") != "application/octet-stream":
        raise ValueError("unsupported or missing application payload")
    payload_offset = header_size + compressed_length + int(selected.findtext("offset"))
    payload_length = int(selected.findtext("length"))
    if payload_offset + payload_length > package["length"]:
        raise ValueError("payload extends beyond package extent")
    gzip = zlib.decompressobj(31)
    cpio = ODC(destination / "components", args.max_unpacked_bytes)
    consumed = 0
    reason = None
    try:
        while consumed < payload_length:
            length = min(64 * 1024, payload_length - consumed)
            data = image.read(package_start + payload_offset + consumed, length)
            consumed += len(data)
            while data:
                decoded = gzip.decompress(data, 4 * 1024 * 1024)
                cpio.feed(decoded)
                data = gzip.unconsumed_tail
            if gzip.eof:
                break
    except MissingRange as exc:
        reason = str(exc)
    finally:
        result = cpio.finish()
    result.update({"gzip_compressed_bytes_consumed": consumed, "gzip_stream_complete": gzip.eof,
                   "payload_declared_bytes": payload_length, "stop_reason": reason,
                   "scope": image.provenance["scope"]})
    image.provenance["source_blocks_consumed"] = list(image.used.values())
    image.provenance["xar_payload"] = {"package_volume_offset": package_start,
                                       "package_file_offset": payload_offset, "declared_bytes": payload_length}
    save_json(destination / "derivation.json", image.provenance)
    save_json(destination / "components.json", result)
    mach_magic = {"feedface", "cefaedfe", "feedfacf", "cffaedfe", "cafebabe", "bebafeca", "cafebabf", "bfbafeca"}
    recovered = [record for record in result["complete_records"]
                 if record["regular_file_written"] and record["first_bytes_hex"][:8] in mach_magic]
    return {"output": str(destination), "complete_records": len(result["complete_records"]),
            "complete_macho_components": recovered, "partial_record": result["partial_record"],
            "stop_reason": reason, "gzip_stream_complete": gzip.eof}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=Path("research/targets/downloads"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-unpacked-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    args = parser.parse_args()
    print(json.dumps(inspect(args), indent=2))


if __name__ == "__main__":
    main()
