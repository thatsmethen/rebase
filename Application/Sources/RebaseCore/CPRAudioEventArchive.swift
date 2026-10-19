import Foundation

/// Source records for the next recovery profile. This decoder establishes
/// archive relationships and stored fields only; it does not select a playback
/// timebase, infer seconds from metadata, or authorize a playable Clip.
struct CPRSourceAudioEvent: Equatable {
    let root: CPRObjectRecord
    let ancestorTracks: [CPRObjectRecord]
    let containingNode: CPRObjectRecord
    let containingDatum: CPRSourceDatum
    let trackIdentity: Int
    let trackName: String
    let event: CPRObjectRecord
    let eventWord: UInt16
    let startBits: UInt64
    let lengthBits: UInt64
    let offsetBits: UInt64
    let clip: CPRObjectRecord
    let clipName: String
    let clipDatum: CPRSourceDatum
    let clipChildren: [CPRObjectRecord]
    let path: CPRSourcePath
    let descriptorIdentifier: String
    let descriptorWord: UInt16
    let descriptorInteger: Int32
    let descriptorNumberBits: UInt64
    let attributes: [CPRSourceAttribute]
    let cluster: CPRSourceAudioCluster
    let historyWord: UInt16
    let priority: Int32
    let fadeIn: CPRObjectRecord?
    let fadeOut: CPRObjectRecord?
    let snapPointBits: UInt64
    let description: String
    let legacyLane: Int32
    let volumeBits: UInt32
    let lane: Int32
    let invertedWord: UInt16
    let volumeCurve: CPRObjectRecord
    let volumeCurveDatum: CPRSourceDatum
}

enum CPRSourceDatum: Equatable {
    case interfaces(tag: Int32, tempo: CPRObjectRecord?, signature: CPRObjectRecord?)
    case scalar(tag: Int32, bits: UInt64)
}

struct CPRSourcePath: Equatable {
    let object: CPRObjectRecord
    let filename: String
    let type: UInt32
    let descriptions: [String]
    let discriminator: Int32
    let word: UInt16
    let directory: String
}

struct CPRSourceAttribute: Equatable {
    enum Value: Equatable {
        case integer(Int64), numberBits(UInt64), text(String), object(CPRObjectRecord?)
    }
    let name: String
    let type: UInt16
    let value: Value
}

struct CPRSourceAudioFile: Equatable {
    let object: CPRObjectRecord
    let frameCount: UInt64
    let sampleSize: Int16
    let frameSize: Int16
    let channels: Int16
    let sampleRateBits: UInt32
    let path: CPRSourcePath
    let additionalPath: CPRSourcePath?
}

struct CPRSourceAudioSegment: Equatable {
    let object: CPRObjectRecord
    let stream: CPRObjectRecord
    // Native named reader/writer bind Offset, Length and Start. These remain
    // stored bits; source seek units and the playback interval are separate gates.
    let storedOffset: UInt64
    let storedLength: UInt64
    let storedStart: UInt64
}

struct CPRSourceAudioCluster: Equatable {
    let object: CPRObjectRecord
    let path: CPRSourcePath?
    let fileListWord: UInt16
    let files: [CPRSourceAudioFile]
    let segmentListWord: UInt16
    let segments: [CPRSourceAudioSegment]
}

/// The class/version and field ordering here are bound by the retained native
/// readers and independently parsed factory files. Opaque attribute objects are
/// retained as records, never declared inaudible or safe to ignore.
final class CPRAudioEventArchive {
    private struct DecodedClip {
        let name: String
        let datum: CPRSourceDatum
        let children: [CPRObjectRecord]
        let path: CPRSourcePath
        let identifier: String
        let word: UInt16
        let integer: Int32
        let numberBits: UInt64
        let attributes: [CPRSourceAttribute]
        let cluster: CPRSourceAudioCluster
        let historyWord: UInt16
    }
    private let archive: CPRArchive
    private var activeLists = Set<Int>()
    private var seenTracks = Set<Int>()
    private var seenEvents = Set<Int>()
    private var visitedLists = 0
    private var events: [CPRSourceAudioEvent] = []
    // A positive archive reference returns the same immutable object. Decode
    // each body once: re-reading it would register nested definitions twice.
    // Publish cache entries only after the complete body has been validated.
    private var clips: [Int: DecodedClip] = [:]
    private var clusters: [Int: CPRSourceAudioCluster] = [:]
    private var files: [Int: CPRSourceAudioFile] = [:]
    private var segments: [Int: CPRSourceAudioSegment] = [:]
    private var paths: [Int: CPRSourcePath] = [:]
    private var curveData: [Int: CPRSourceDatum] = [:]
    private let trackVersions = ["MFolderTrack": 0, "MDeviceTrackEvent": 0, "MAudioTrackEvent": 1,
        "MMidiTrackEvent": 4, "MInstrumentTrackEvent": 4, "MSamplerTrackEvent": 4, "MDrumTrackEvent": 4]

    private init(archive: CPRArchive) { self.archive = archive }

    static func read(container: CPRContainer) throws -> [CPRSourceAudioEvent] {
        guard let section = container.sections.first(where: { $0.name == "Arrangement1" }) else { return [] }
        let archive = CPRArchive(data: container.originalBytes, section: section)
        let arrangement = try archive.root(expectedClass: section.className)
        guard section.className == "PArrangement", arrangement.descriptor.version == 4 else {
            throw CPRProjectError.unsupported("Audio-event recovery requires PArrangement version 4.")
        }
        let decoder = CPRAudioEventArchive(archive: archive)
        var body = archive.body(arrangement)
        let root = try decoder.object(&body, name: "MRoot", version: 6)
        var fields = archive.body(root)
        _ = try fields.bytes(26)
        let list = try decoder.object(&fields, name: "MTrackList", version: 0)
        try decoder.visit(list, track: nil, root: root.descriptor, ancestors: [], depth: 0)
        return decoder.events
    }

    private func visit(_ list: CPRNativeObject, track: CPRNativeObject?, root: CPRObjectRecord,
                       ancestors: [CPRObjectRecord], depth: Int) throws {
        let id = list.descriptor.identityOffset
        guard depth <= 32, visitedLists < 10_000, activeLists.insert(id).inserted,
              list.descriptor.version == 0, ["MTrackList", "MListNode"].contains(list.descriptor.className) else {
            throw CPRProjectError.unsupported("Unsupported or cyclic audio-event track hierarchy.")
        }
        visitedLists += 1
        defer { activeLists.remove(id) }
        var body = archive.body(list)
        let name = try body.nativeString()
        let nodeDatum = try datum(&body)
        if list.descriptor.className == "MTrackList", try body.u16() != 0 {
            throw CPRProjectError.unsupported("Unverified audio-event track-list compatibility word.")
        }
        for _ in 0..<(try count(&body)) {
            guard let child = try archive.readObject(&body) else { throw CPRProjectError.invalid("Null counted track or event.") }
            if let version = trackVersions[child.descriptor.className] {
                guard child.descriptor.version == version, seenTracks.insert(child.descriptor.identityOffset).inserted else {
                    throw CPRProjectError.unsupported("Unverified or shared audio-event parent track.")
                }
                var childBody = archive.body(child)
                _ = try childBody.bytes(26)
                guard let node = try archive.readObject(&childBody) else { throw CPRProjectError.invalid("Track has no counted node.") }
                try visit(node, track: child, root: root, ancestors: ancestors + [child.descriptor], depth: depth + 1)
            } else if child.descriptor.className == "MAudioEvent", let track,
                      track.descriptor.className == "MAudioTrackEvent" {
                guard seenEvents.insert(child.descriptor.identityOffset).inserted else {
                    throw CPRProjectError.unsupported("A shared audio event cannot be assigned one source placement.")
                }
                events.append(try audioEvent(child, track: track, trackName: name, root: root,
                    ancestors: ancestors, containingNode: list.descriptor, containingDatum: nodeDatum))
            }
        }
        try finished(body, "audio-event track list")
    }

    private func audioEvent(_ event: CPRNativeObject, track: CPRNativeObject, trackName: String,
                            root: CPRObjectRecord, ancestors: [CPRObjectRecord],
                            containingNode: CPRObjectRecord, containingDatum: CPRSourceDatum) throws -> CPRSourceAudioEvent {
        guard event.descriptor.version == 6 else { throw CPRProjectError.unsupported("Unverified audio-event version.") }
        var body = archive.body(event)
        let eventWord = try body.u16()
        let start = try numberBits(&body), length = try numberBits(&body), offset = try numberBits(&body)
        let clip = try object(&body, name: "PAudioClip", version: 4)
        let decoded = try audioClip(clip)
        guard try body.u32() == 0 else { throw CPRProjectError.unsupported("Audio-event numeric attributes are not yet decoded.") }
        let priority = try body.i32()
        let fadeIn = try archive.readObject(&body), fadeOut = try archive.readObject(&body)
        let snapPoint = try numberBits(&body), description = try body.nativeString()
        let legacyLane = try body.i32(), volume = try body.u32(), lane = try body.i32(), inverted = try body.u16()
        guard Float(bitPattern: volume).isFinite else { throw CPRProjectError.invalid("Nonfinite stored audio-event volume.") }
        let curve = try object(&body, name: "VolumeCurveDataNode", version: 0)
        let curveDatum = try volumeCurveDatum(curve)
        try finished(body, "audio event")
        return CPRSourceAudioEvent(root: root, ancestorTracks: ancestors, containingNode: containingNode,
            containingDatum: containingDatum, trackIdentity: track.descriptor.identityOffset, trackName: trackName,
            event: event.descriptor, eventWord: eventWord, startBits: start, lengthBits: length, offsetBits: offset,
            clip: clip.descriptor, clipName: decoded.name, clipDatum: decoded.datum, clipChildren: decoded.children, path: decoded.path,
            descriptorIdentifier: decoded.identifier, descriptorWord: decoded.word, descriptorInteger: decoded.integer,
            descriptorNumberBits: decoded.numberBits, attributes: decoded.attributes, cluster: decoded.cluster, historyWord: decoded.historyWord,
            priority: priority, fadeIn: fadeIn?.descriptor, fadeOut: fadeOut?.descriptor, snapPointBits: snapPoint,
            description: description, legacyLane: legacyLane, volumeBits: volume, lane: lane, invertedWord: inverted,
            volumeCurve: curve.descriptor, volumeCurveDatum: curveDatum)
    }

    private func audioClip(_ clip: CPRNativeObject) throws -> DecodedClip {
        let identity = clip.descriptor.identityOffset
        if let decoded = clips[identity] { return decoded }
        var cb = archive.body(clip)
        let name = try cb.nativeString(), clipDatum = try datum(&cb)
        var children: [CPRObjectRecord] = []
        for _ in 0..<(try count(&cb)) {
            guard let child = try archive.readObject(&cb) else { throw CPRProjectError.invalid("Null counted clip child.") }
            children.append(child.descriptor)
        }
        let path = try sourcePath(object(&cb, name: "FNPath", version: 0))
        let identifier = try cb.nativeString(), descriptorWord = try cb.u16(), descriptorInteger = try cb.i32()
        let descriptorNumber = try numberBits(&cb), attributes = try namedAttributes(&cb)
        let cluster = try audioCluster(object(&cb, name: "AudioCluster", version: 0))
        let historyWord = try cb.u16()
        guard historyWord == 1, try cb.u32() == 0 else {
            throw CPRProjectError.unsupported("Only the structurally verified empty audio edit history is decoded.")
        }
        try finished(cb, "audio clip")
        let result = DecodedClip(name: name, datum: clipDatum, children: children, path: path,
            identifier: identifier, word: descriptorWord, integer: descriptorInteger, numberBits: descriptorNumber,
            attributes: attributes, cluster: cluster, historyWord: historyWord)
        clips[identity] = result
        return result
    }

    private func volumeCurveDatum(_ curve: CPRNativeObject) throws -> CPRSourceDatum {
        let identity = curve.descriptor.identityOffset
        if let decoded = curveData[identity] { return decoded }
        var curveBody = archive.body(curve)
        _ = try curveBody.nativeString()
        let curveDatum = try datum(&curveBody)
        guard try curveBody.u32() == 0 else { throw CPRProjectError.unsupported("Nonempty audio-event volume curves are not yet decoded.") }
        try finished(curveBody, "audio-event volume curve")
        curveData[identity] = curveDatum
        return curveDatum
    }

    private func audioCluster(_ object: CPRNativeObject) throws -> CPRSourceAudioCluster {
        let identity = object.descriptor.identityOffset
        if let decoded = clusters[identity] { return decoded }
        var body = archive.body(object)
        let path = try archive.readObject(&body).map(sourcePath)
        let fileWord = try body.u16()
        var files: [CPRSourceAudioFile] = []
        for _ in 0..<(try count(&body)) {
            files.append(try audioFile(self.object(&body, name: "AudioFile", version: 1)))
        }
        let segmentWord = try body.u16()
        var segments: [CPRSourceAudioSegment] = []
        for _ in 0..<(try count(&body)) {
            let segment = try audioSegment(self.object(&body, name: "AClusterSegment", version: 0))
            // Native segment reader requests AudioStream. This subset accepts
            // only the concrete AudioFile already listed by this cluster.
            // Membership is per cluster, even when the segment body was cached.
            guard files.contains(where: { $0.object == segment.stream }) else {
                throw CPRProjectError.unsupported("Audio segment does not reference a file in this cluster.")
            }
            segments.append(segment)
        }
        try finished(body, "audio cluster")
        let result = CPRSourceAudioCluster(object: object.descriptor, path: path, fileListWord: fileWord, files: files,
                                           segmentListWord: segmentWord, segments: segments)
        clusters[identity] = result
        return result
    }

    private func audioFile(_ file: CPRNativeObject) throws -> CPRSourceAudioFile {
        let identity = file.descriptor.identityOffset
        if let decoded = files[identity] { return decoded }
        var fields = archive.body(file)
        let frames = try fields.u64(), sampleSize = Int16(bitPattern: try fields.u16())
        let frameSize = Int16(bitPattern: try fields.u16()), channels = Int16(bitPattern: try fields.u16())
        let rateBits = try fields.u32()
        guard Float(bitPattern: rateBits).isFinite else { throw CPRProjectError.invalid("Nonfinite declared audio sample rate.") }
        let path = try sourcePath(self.object(&fields, name: "FNPath", version: 0))
        let additional = try archive.readObject(&fields).map(sourcePath)
        try finished(fields, "audio file")
        let result = CPRSourceAudioFile(object: file.descriptor, frameCount: frames, sampleSize: sampleSize,
            frameSize: frameSize, channels: channels, sampleRateBits: rateBits, path: path, additionalPath: additional)
        files[identity] = result
        return result
    }

    private func audioSegment(_ segment: CPRNativeObject) throws -> CPRSourceAudioSegment {
        let identity = segment.descriptor.identityOffset
        if let decoded = segments[identity] { return decoded }
        var fields = archive.body(segment)
        let stream = try object(&fields, name: "AudioFile", version: 1)
        let result = CPRSourceAudioSegment(object: segment.descriptor, stream: stream.descriptor,
            storedOffset: try fields.u64(), storedLength: try fields.u64(), storedStart: try fields.u64())
        try finished(fields, "audio cluster segment")
        segments[identity] = result
        return result
    }

    private func sourcePath(_ object: CPRNativeObject) throws -> CPRSourcePath {
        guard object.descriptor.className == "FNPath", object.descriptor.version == 0 else {
            throw CPRProjectError.unsupported("Unverified audio source path object.")
        }
        let identity = object.descriptor.identityOffset
        if let decoded = paths[identity] { return decoded }
        var fields = archive.body(object)
        let filename = try fields.nativeString(), type = try fields.u32()
        var descriptions: [String] = []
        for _ in 0..<3 { descriptions.append(try fields.nativeString()) }
        let discriminator = try fields.i32(), word = try fields.u16(), directory = try fields.nativeString()
        try finished(fields, "audio source path")
        let result = CPRSourcePath(object: object.descriptor, filename: filename, type: type, descriptions: descriptions,
                                  discriminator: discriminator, word: word, directory: directory)
        paths[identity] = result
        return result
    }

    private func namedAttributes(_ body: inout CPRCursor) throws -> [CPRSourceAttribute] {
        var values: [CPRSourceAttribute] = [], seen = Set<String>()
        for _ in 0..<(try count(&body)) {
            let name = try body.nativeString(), type = try body.u16()
            guard !name.isEmpty, seen.insert(name).inserted else { throw CPRProjectError.invalid("Empty or duplicate audio-clip attribute.") }
            let value: CPRSourceAttribute.Value
            switch type {
            case 1: value = .integer(try body.i64())
            case 4: value = .numberBits(try numberBits(&body))
            case 8: value = .text(try body.nativeString())
            case 0x12, 0x22, 0x92, 0xa2: value = .object(try archive.readObject(&body)?.descriptor)
            default: throw CPRProjectError.unsupported("Unverified audio-clip attribute representation.")
            }
            values.append(CPRSourceAttribute(name: name, type: type, value: value))
        }
        return values
    }

    private func datum(_ body: inout CPRCursor) throws -> CPRSourceDatum {
        let tag = try body.i32()
        switch tag {
        case 0, 17:
            let tempo = try archive.readObject(&body), signature = try archive.readObject(&body)
            guard tempo.map({ $0.descriptor.className == "MTempoTrackEvent" && $0.descriptor.version == 3 }) ?? true,
                  signature.map({ $0.descriptor.className == "MSignatureTrackEvent" && $0.descriptor.version == 3 }) ?? true else {
                throw CPRProjectError.unsupported("Unverified audio datum interface roles.")
            }
            return .interfaces(tag: tag, tempo: tempo?.descriptor, signature: signature?.descriptor)
        case 1, 10: return .scalar(tag: tag, bits: try numberBits(&body))
        default: throw CPRProjectError.unsupported("Unverified audio source datum tag.")
        }
    }
    private func numberBits(_ body: inout CPRCursor) throws -> UInt64 {
        let bits = try body.u64()
        guard Double(bitPattern: bits).isFinite else { throw CPRProjectError.invalid("Nonfinite stored audio-event field.") }
        return bits
    }
    private func count(_ body: inout CPRCursor) throws -> Int {
        let value = Int(try body.u32())
        guard value <= 10_000, value <= (body.upper - body.position) / 4 else {
            throw CPRProjectError.invalid("Excessive or truncated counted audio source records.")
        }
        return value
    }
    private func object(_ body: inout CPRCursor, name: String, version: Int) throws -> CPRNativeObject {
        guard let object = try archive.readObject(&body), object.descriptor.className == name,
              object.descriptor.version == version else {
            throw CPRProjectError.unsupported("Expected \(name) version \(version) in audio source records.")
        }
        return object
    }
    private func finished(_ body: CPRCursor, _ name: String) throws {
        guard body.position == body.upper else { throw CPRProjectError.unsupported("Unconsumed \(name) bytes.") }
    }
}
