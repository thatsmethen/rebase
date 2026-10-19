import Foundation

/// Exact saved setting. Curve bodies remain opaque; flags zero alone does not
/// certify effective hosted state or authorize rendering.
struct CPRSourceAutoFadeSetting: Equatable {
    let object: CPRObjectRecord
    let flags: UInt16
    let durationBits: UInt64
    let interpolators: [CPRObjectRecord?]
}

struct CPRSourceNumericAttribute: Equatable {
    enum Value: Equatable { case integer(Int64), object(CPRObjectRecord?) }
    let offset: Int
    let key: UInt32
    let type: UInt16
    let value: Value
}

struct CPRSourceTrackAutoFade: Equatable {
    let track: CPRObjectRecord
    let attributes: [CPRSourceNumericAttribute]
    let resource: CPRObjectRecord
    let trackWord: Int32
    let numberBits: UInt64
    let automation: CPRObjectRecord
    let localSetting: CPRSourceAutoFadeSetting?
    let localSettingTokenOffset: Int
}

struct CPRSourceAutoFadeArchive {
    let root: CPRObjectRecord
    let projectSetting: CPRSourceAutoFadeSetting?
    let projectSettingTokenOffset: Int
    let tracks: [Int: CPRSourceTrackAutoFade]
    let rootAttributes: [CPRSourceNumericAttribute]
    let objectListWord: UInt16
    let rootObjects: [CPRObjectRecord]
    let path: CPRObjectRecord
    let pool: CPRObjectRecord
    let marker: CPRObjectRecord?
    let keyedEvents: [Int16: CPRObjectRecord]
    let loudness: CPRObjectRecord?
    let records: [CPRObjectRecord]

    /// Source inheritance only, conditional on fresh normal restoration. A
    /// nonnull local setting overrides the project even when its flags are zero.
    /// Missing local AND project settings remains unknown: native can synthesize
    /// a default. Call-time state and callbacks are outside this reader.
    func effectiveSetting(forTrackIdentity identity: Int) -> CPRSourceAutoFadeSetting? {
        guard let track = tracks[identity] else { return nil }
        return track.localSetting ?? projectSetting
    }
}

/// Bounded forward decoding of saved track/root tails. This deliberately does
/// not change a recovery profile or declare other track attributes inaudible.
final class CPRAutoFadeArchive {
    private let roles: CPRClockRoles
    private var archive: CPRArchive { roles.archive }
    private var byObjectOffset: [Int: CPRNativeObject]
    private var settingCache: [Int: CPRSourceAutoFadeSetting] = [:]
    private var attributeCount = 0

    private init(roles: CPRClockRoles) throws {
        self.roles = roles
        var offsets: [Int: CPRNativeObject] = [:]
        for object in roles.archive.objects.values {
            guard offsets.updateValue(object, forKey: object.descriptor.objectOffset) == nil else {
                throw CPRProjectError.invalid("Duplicate registered auto-fade object offset.")
            }
        }
        byObjectOffset = offsets
    }

    static func read(container: CPRContainer) throws -> CPRSourceAutoFadeArchive {
        let decoder = try CPRAutoFadeArchive(roles: CPRClockRoles.resolve(container: container))
        try decoder.requireBaseVersions()
        return try decoder.read()
    }

    private func read() throws -> CPRSourceAutoFadeArchive {
        let roots = archive.objects.values.filter { $0.descriptor.className == "MRoot" }
        guard roots.count == 1, let root = roots.first, root.descriptor.version == 6 else {
            throw CPRProjectError.unsupported("Auto-fade recovery requires one counted MRoot version 6.")
        }
        // Capture only audio tracks registered by the verified counted walker,
        // before reading opaque ancillary object definitions in the tails.
        let audioTracks = archive.objects.values.filter { $0.descriptor.className == "MAudioTrackEvent" }
            .sorted { $0.descriptor.objectOffset < $1.descriptor.objectOffset }
        var tracks: [Int: CPRSourceTrackAutoFade] = [:]
        for object in audioTracks {
            guard object.descriptor.version == 1 else { throw CPRProjectError.unsupported("Unverified audio-track version.") }
            var reader = archive.body(object)
            _ = try reader.bytes(26)
            let node = try required(&reader, classes: ["MListNode": 0, "MTrackList": 0])
            guard roles.objects.contains(node.descriptor) else { throw CPRProjectError.invalid("Audio-track node is not in the counted hierarchy.") }
            let attributes = try numericAttributes(&reader)
            let resource = try required(&reader, classes: ["MAudioTrack": 0])
            let word = try reader.i32(), number = try reader.u64()
            let automation = try required(&reader, classes: ["MAutomationNode": 1])
            let localOffset = reader.position
            let local = try setting(&reader)
            try finished(reader, "audio-track tail")
            tracks[object.descriptor.identityOffset] = CPRSourceTrackAutoFade(track: object.descriptor,
                attributes: attributes, resource: resource.descriptor, trackWord: word, numberBits: number,
                automation: automation.descriptor, localSetting: local, localSettingTokenOffset: localOffset)
        }
        var reader = archive.body(root)
        _ = try reader.bytes(26)
        _ = try required(&reader, classes: ["MTrackList": 0])
        let attributes = try numericAttributes(&reader)
        let listWord = try reader.u16()
        let count = try boundedCount(&reader)
        var objects: [CPRObjectRecord] = []
        for _ in 0..<count {
            guard let object = try object(&reader) else { throw CPRProjectError.invalid("Null root object-list item.") }
            objects.append(object.descriptor)
        }
        let path = try required(&reader, classes: ["FNPath": 0])
        let pool = try required(&reader, classes: ["PPool": 5])
        let marker = try optional(&reader, classes: ["MMarkerTrackEvent": 0])
        let tempo = try optional(&reader, classes: ["MTempoTrackEvent": 3])
        let signature = try optional(&reader, classes: ["MSignatureTrackEvent": 3])
        guard tempo?.descriptor.identityOffset == roles.tempo?.descriptor.identityOffset,
              signature?.descriptor.identityOffset == roles.signature?.descriptor.identityOffset else {
            throw CPRProjectError.unsupported("Root timing references disagree with the counted shared clock roles.")
        }
        let settingOffset = reader.position
        let project = try setting(&reader)
        let keyedCount = Int(Int16(bitPattern: try reader.u16()))
        guard keyedCount >= 0, keyedCount <= 10_000, keyedCount <= (reader.upper - reader.position) / 6 else {
            throw CPRProjectError.invalid("Invalid root keyed-event count.")
        }
        var keyed: [Int16: CPRObjectRecord] = [:]
        for _ in 0..<keyedCount {
            let key = Int16(bitPattern: try reader.u16())
            guard keyed[key] == nil, let value = try object(&reader) else {
                throw CPRProjectError.invalid("Duplicate key or null root event reference.")
            }
            // Preserve the archive record without inventing its editor/render
            // role. The downstream rendering gate must assess retained state.
            keyed[key] = value.descriptor
        }
        let loudness = try object(&reader)
        try finished(reader, "root auto-fade tail")
        // Newly entered header declarations must not revise base versions.
        try requireBaseVersions()
        return CPRSourceAutoFadeArchive(root: root.descriptor, projectSetting: project,
            projectSettingTokenOffset: settingOffset, tracks: tracks, rootAttributes: attributes,
            objectListWord: listWord, rootObjects: objects, path: path.descriptor, pool: pool.descriptor,
            marker: marker?.descriptor, keyedEvents: keyed, loudness: loudness?.descriptor,
            records: archive.objects.values.map(\.descriptor).sorted { $0.identityOffset < $1.identityOffset })
    }

    private func object(_ reader: inout CPRCursor) throws -> CPRNativeObject? {
        // Counted traversal already registered these definitions. Re-entering
        // them through readObject would incorrectly register nested headers twice.
        if let known = byObjectOffset[reader.position] {
            guard known.end <= reader.upper else { throw CPRProjectError.invalid("Registered object crosses its containing tail.") }
            reader.position = known.end
            return known
        }
        let value = try archive.readObject(&reader)
        if let value { byObjectOffset[value.descriptor.objectOffset] = value }
        return value
    }

    private func optional(_ reader: inout CPRCursor, classes: [String: Int]) throws -> CPRNativeObject? {
        let value = try object(&reader)
        guard value.map({ classes[$0.descriptor.className] == $0.descriptor.version }) ?? true else {
            throw CPRProjectError.unsupported("Unverified object class/version in auto-fade tail.")
        }
        return value
    }

    private func required(_ reader: inout CPRCursor, classes: [String: Int]) throws -> CPRNativeObject {
        guard let value = try optional(&reader, classes: classes) else {
            throw CPRProjectError.invalid("Missing required object in auto-fade tail.")
        }
        return value
    }

    private func numericAttributes(_ reader: inout CPRCursor) throws -> [CPRSourceNumericAttribute] {
        let count = try boundedCount(&reader)
        guard count <= 10_000 - attributeCount else { throw CPRProjectError.unsupported("Excessive numeric attributes.") }
        attributeCount += count
        var result: [CPRSourceNumericAttribute] = [], keys = Set<UInt32>()
        for _ in 0..<count {
            let offset = reader.position, key = try reader.u32(), type = try reader.u16()
            guard keys.insert(key).inserted else { throw CPRProjectError.invalid("Duplicate numeric attribute key.") }
            let value: CPRSourceNumericAttribute.Value
            switch type {
            case 1, 0x801: value = .integer(try reader.i64())
            case 2, 0x12, 0x22, 0x92: value = .object(try object(&reader)?.descriptor)
            case 8: value = .object(try required(&reader, classes: ["CmString": 0]).descriptor)
            default: throw CPRProjectError.unsupported("Unverified numeric attribute representation in auto-fade tail.")
            }
            result.append(CPRSourceNumericAttribute(offset: offset, key: key, type: type, value: value))
        }
        return result
    }

    private func setting(_ reader: inout CPRCursor) throws -> CPRSourceAutoFadeSetting? {
        guard let object = try optional(&reader, classes: ["MAutoFadeSetting": 0]) else { return nil }
        if let cached = settingCache[object.descriptor.identityOffset] { return cached }
        var body = archive.body(object)
        let flags = try body.u16(), duration = try body.u64()
        var curves: [CPRObjectRecord?] = []
        for _ in 0..<4 {
            curves.append(try optional(&body, classes: ["MLinearInterpolator": 0])?.descriptor)
        }
        try finished(body, "auto-fade setting")
        let result = CPRSourceAutoFadeSetting(object: object.descriptor, flags: flags,
            durationBits: duration, interpolators: curves)
        settingCache[object.descriptor.identityOffset] = result
        return result
    }

    private func boundedCount(_ reader: inout CPRCursor) throws -> Int {
        let count = Int(try reader.i32())
        guard count >= 0, count <= 10_000, count <= (reader.upper - reader.position) / 4 else {
            throw CPRProjectError.invalid("Invalid bounded auto-fade list count.")
        }
        return count
    }

    private func finished(_ reader: CPRCursor, _ description: String) throws {
        guard reader.position == reader.upper else { throw CPRProjectError.unsupported("Unconsumed \(description) bytes.") }
    }

    /// Resolve raw declarations only at registered object header boundaries.
    /// Base versions are stream-global here; both must be observed, and every
    /// declaration/reference encountered must agree with the bounded contract.
    private func requireBaseVersions() throws {
        var versions: [String: Set<Int>] = [:]
        for object in archive.objects.values {
            let record = object.descriptor
            var header = CPRCursor(data: archive.data, lower: record.objectOffset, upper: record.identityOffset)
            var concrete = false
            for _ in 0..<64 {
                let token = try header.u32()
                var declaration: CPRCursor
                if token == 0xffff_fffe || token == 0xffff_ffff {
                    declaration = header
                } else if token & 0x8000_0000 != 0 {
                    let at = archive.start + Int(token & 0x7fff_ffff)
                    guard at < record.objectOffset, at >= archive.start, at < archive.end else {
                        throw CPRProjectError.unsupported("Unverified auto-fade class reference.")
                    }
                    declaration = CPRCursor(data: archive.data, lower: at, upper: archive.end)
                    let marker = try declaration.u32()
                    guard marker == 0xffff_ffff || marker == 0xffff_fffe else {
                        throw CPRProjectError.invalid("Class reference does not target a raw declaration.")
                    }
                } else { throw CPRProjectError.invalid("Registered definition has no class header.") }
                let name = try declaration.className(), version = Int(try declaration.u16())
                versions[name, default: []].insert(version)
                if token == 0xffff_fffe { header = declaration; continue }
                if token == 0xffff_ffff { header = declaration }
                guard name == record.className, version == record.version,
                      header.position == record.identityOffset else {
                    throw CPRProjectError.invalid("Concrete object header does not match its registered descriptor.")
                }
                concrete = true
                break
            }
            guard concrete else { throw CPRProjectError.unsupported("Excessive base-class header chain.") }
        }
        guard versions["MEvent"] == [1], versions["MTrackEvent"] == [2] else {
            throw CPRProjectError.unsupported("Auto-fade tails require observed MEvent v1 and MTrackEvent v2 base declarations.")
        }
    }
}
