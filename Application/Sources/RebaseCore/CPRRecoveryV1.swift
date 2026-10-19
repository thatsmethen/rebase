import Foundation

// Frozen semantic recovery profile: cpr-static-subset-v1.
// Derived verbatim from reviewed APP003 CPRProject.swift SHA256
// 75b82b2d3e0afadff279284d6f2872685fb2a3146ead0d7a08709eefe089e940.
// Preserve facts, defaults, stable IDs and visited objects for historical replay.
// New recovery features require a new profile; shared bounded mechanics remain
// in CPRProject.swift and must continue passing the pinned APP003 replay tests.

private indirect enum CPRAttribute {
    case integer(Int64), number(Double), text(String)
    case fields(Int, String?, [String: CPRAttribute])
    case list([CPRAttribute])
}

private final class CPRAttributeReader {
    private var consumed = 0
    func fields(_ reader: inout CPRCursor, depth: Int = 0) throws -> [String: CPRAttribute] {
        guard depth <= 32 else { throw CPRProjectError.unsupported("Attribute nesting exceeds 32 levels.") }
        let count = Int(try reader.u32())
        guard count <= 10_000 - consumed else { throw CPRProjectError.unsupported("More than 10000 attributes.") }
        consumed += count
        var result: [String: CPRAttribute] = [:]
        for _ in 0..<count {
            let name = try reader.nativeString()
            guard !name.isEmpty, result[name] == nil else { throw CPRProjectError.invalid("Empty or duplicate attribute name.") }
            switch try reader.u16() {
            case 1: result[name] = .integer(try reader.i64())
            case 4: result[name] = .number(try reader.number())
            case 8: result[name] = .text(try reader.nativeString())
            case 2: result[name] = try compound(&reader, depth: depth + 1)
            default: throw CPRProjectError.unsupported("Unrecognized native attribute type at byte \(reader.position - 2).")
            }
        }
        return result
    }
    private func compound(_ reader: inout CPRCursor, depth: Int) throws -> CPRAttribute {
        guard depth <= 32 else { throw CPRProjectError.unsupported("Attribute nesting exceeds 32 levels.") }
        switch try reader.u16() {
        case 20:
            let name = try reader.nativeString()
            _ = try reader.u64() // Native compound identity retained in original bytes; not a reference offset.
            return .fields(20, name, try fields(&reader, depth: depth))
        case 201:
            let count = Int(try reader.u32())
            guard count <= 10_000 - consumed else { throw CPRProjectError.unsupported("Excessive compound array.") }
            consumed += count
            return .list(try (0..<count).map { _ in try compound(&reader, depth: depth + 1) })
        case 6: return .fields(6, nil, try fields(&reader, depth: depth))
        default: throw CPRProjectError.unsupported("Unrecognized compound subtype at byte \(reader.position - 2).")
        }
    }
}

struct CPRRecoveryResult {
    var facts: [String] = []
    var metadata: [String] = []
    var tracks: [CPRRecoveredTrack] = []
    var objects: [CPRObjectRecord] = []
    var defaults: [String] = []
    var unsupported: [CPRUnsupportedItem] = []
    var project: Project?
}

final class CPRRecoveryV1 {
    let container: CPRContainer
    private let sourceSHA256: String
    private var result = CPRRecoveryResult()
    private var imported: [Track] = []
    private var active = Set<Int>()
    private var encounteredTracks = Set<Int>()
    private var unsupportedEvents = 0
    private var tempoIdentity: Int?
    private var fixedTempo: Double?
    private let knownTracks: [String: (Int, String)] = [
        "MFolderTrack": (0, "Folder"), "MDeviceTrackEvent": (0, "Device / routing"),
        "MAudioTrackEvent": (1, "Audio"), "MMidiTrackEvent": (4, "MIDI"),
        "MInstrumentTrackEvent": (4, "Instrument"), "MSamplerTrackEvent": (4, "Sampler"),
        "MDrumTrackEvent": (4, "Drum")]
    init(container: CPRContainer) { self.container = container; sourceSHA256 = container.sha256 }

    func decode(sourceName: String) throws -> CPRRecoveryResult {
        for section in container.sections {
            // Unknown sections remain entirely opaque, without speculative header parsing.
            guard section.name == "Arrangement1" || section.name == "Metadata" else { continue }
            let archive = CPRArchive(data: container.originalBytes, section: section)
            let root = try archive.root(expectedClass: section.className)
            if section.name == "Metadata" {
                do { result.metadata = try metadata(archive, root) }
                catch CPRProjectError.unsupported(let message) {
                    result.unsupported.append(CPRUnsupportedItem(category: "Metadata variant", detail: message, objectCount: 1))
                }
            } else {
                guard section.className == "PArrangement", root.descriptor.version == 4 else {
                    result.unsupported.append(CPRUnsupportedItem(category: "Arrangement version", detail: "Only the structurally verified PArrangement version 4 path is decoded.", objectCount: 1))
                    continue
                }
                var reader = archive.body(root)
                guard let nativeRoot = try archive.readObject(&reader), nativeRoot.descriptor.className == "MRoot",
                      nativeRoot.descriptor.version == 6 else { throw CPRProjectError.unsupported("Expected MRoot version 6.") }
                var rootBody = archive.body(nativeRoot)
                _ = try rootBody.bytes(26) // Verified serialized event-base extent; no time/mode values inferred.
                guard let node = try archive.readObject(&rootBody) else { throw CPRProjectError.invalid("Missing counted arrangement track list.") }
                _ = try list(archive, node, depth: 0, track: nil)
                result.facts.append("Recovered \(result.tracks.count) named native track/folder objects from the counted arrangement hierarchy.")
                result.facts.append("\(imported.count) confirmed audio track names are available as editable track skeletons.")
            }
            result.objects.append(contentsOf: archive.objects.values.map(\.descriptor).sorted { $0.identityOffset < $1.identityOffset })
        }
        result.unsupported.append(CPRUnsupportedItem(category: "Native state preserved only",
            detail: "Clip/media events, MIDI and instrument content, plugins, mixer controls, routing, automation, tempo-event coordinates, signature maps and layouts remain in the preserved CPR. Imported audio tracks do not reproduce the source mix.", objectCount: nil))
        if unsupportedEvents > 0 {
            result.unsupported.append(CPRUnsupportedItem(category: "Unconverted event objects",
                detail: "Counted native event objects were identified but are not audio clips in the imported timeline.", objectCount: unsupportedEvents))
        }
        if !imported.isEmpty {
            result.defaults = ["Project name uses the source filename.", "48 kHz and 4/4 are application defaults; source metadata tags are not used as timing-map evidence.",
                "Recovered audio track skeletons start at 0 dB, centered, unmuted and unsoloed, using seconds timebase. Native mixer/timebase settings are not converted.",
                "Folders are flattened for imported audio tracks; their native identities/order remain in this report."]
            if fixedTempo == nil { result.defaults.append("120 BPM is an application default because no supported active fixed tempo was recovered.") }
            result.project = Project(id: stableID("project"), name: URL(fileURLWithPath: sourceName).deletingPathExtension().lastPathComponent,
                sampleRate: 48_000, tracks: imported,
                tempoMap: TempoMap(events: [TempoEvent(id: stableID(fixedTempo == nil ? "tempo-default" : "tempo-fixed"), beat: 0, bpm: fixedTempo ?? 120)]),
                signatureMap: SignatureMap(events: [SignatureEvent(id: stableID("signature-default"), beat: 0, numerator: 4, denominator: 4)]))
            try result.project?.validate()
        }
        return result
    }

    private func stableID(_ label: String) -> UUID {
        let text = String(cprSHA256(Data((sourceSHA256 + ":" + label).utf8)).prefix(32))
        let chars = Array(text)
        return UUID(uuidString: String(chars[0..<8]) + "-" + String(chars[8..<12]) + "-" + String(chars[12..<16]) + "-" + String(chars[16..<20]) + "-" + String(chars[20..<32]))!
    }

    @discardableResult
    private func list(_ archive: CPRArchive, _ object: CPRNativeObject, depth: Int,
                      track: (CPRNativeObject, String)?) throws -> String {
        let id = object.descriptor.identityOffset
        guard depth <= 32, !active.contains(id), object.descriptor.version == 0,
              ["MTrackList", "MListNode"].contains(object.descriptor.className) else {
            throw CPRProjectError.unsupported("Unsupported or cyclic native track-list layout.")
        }
        active.insert(id); defer { active.remove(id) }
        var reader = archive.body(object)
        let name = try reader.nativeString()
        let datum = try reader.i32()
        switch datum {
        case 0, 17:
            for _ in 0..<2 {
                if let datum = try archive.readObject(&reader), datum.descriptor.className == "MTempoTrackEvent" {
                    try tempo(archive, datum)
                }
            }
        case 1: _ = try reader.number()
        default: throw CPRProjectError.unsupported("Unverified track-list datum tag \(datum).")
        }
        if object.descriptor.className == "MTrackList", try reader.u16() != 0 {
            throw CPRProjectError.unsupported("Unverified track-list compatibility word.")
        }
        let count = Int(try reader.u32())
        guard count <= 10_000, count <= (reader.upper - reader.position) / 4 else {
            throw CPRProjectError.invalid("Invalid native track/event count.")
        }
        if let (source, kind) = track {
            let importedID = kind == "Audio" ? stableID("track-\(source.descriptor.identityOffset)") : nil
            result.tracks.append(CPRRecoveredTrack(name: name, kind: kind,
                nativeClassName: source.descriptor.className, sourceOffset: source.descriptor.objectOffset,
                importedTrackID: importedID))
            if let importedID { imported.append(Track(id: importedID, name: name)) }
        }
        for _ in 0..<count {
            guard let child = try archive.readObject(&reader) else { throw CPRProjectError.invalid("A counted track/event entry is null.") }
            if let (version, kind) = knownTracks[child.descriptor.className] {
                guard child.descriptor.version == version else {
                    throw CPRProjectError.unsupported("Unverified \(child.descriptor.className) version \(child.descriptor.version).")
                }
                guard encounteredTracks.insert(child.descriptor.identityOffset).inserted else {
                    throw CPRProjectError.unsupported("A track object is shared or cyclic; it is not duplicated into the project.")
                }
                var childBody = archive.body(child)
                _ = try childBody.bytes(26)
                guard let childList = try archive.readObject(&childBody) else { throw CPRProjectError.invalid("Track object has no list node.") }
                _ = try list(archive, childList, depth: depth + 1, track: (child, kind))
                // Remaining per-track state is deliberately opaque, including its mixer.
            } else if child.descriptor.className == "MTempoTrackEvent" {
                try tempo(archive, child)
            } else {
                unsupportedEvents += 1
                if child.descriptor.className == "MAudioEvent", track?.1 == "Audio" {
                    try audioReference(archive, child, trackName: name)
                }
            }
        }
        guard reader.position == reader.upper else {
            throw CPRProjectError.unsupported("Unconsumed native track-list bytes; no partial list is published.")
        }
        return name
    }

    private func audioReference(_ archive: CPRArchive, _ object: CPRNativeObject, trackName: String) throws {
        guard object.descriptor.version == 6 else { return } // Other event versions remain opaque.
        var event = archive.body(object)
        _ = try event.bytes(26) // Serialized MEvent fields; units are not yet established.
        guard let clip = try archive.readObject(&event), clip.descriptor.className == "PAudioClip",
              clip.descriptor.version == 4 else { return }
        var body = archive.body(clip)
        _ = try body.nativeString()
        switch try body.i32() {
        case 0, 17: _ = try archive.readObject(&body); _ = try archive.readObject(&body)
        case 1, 10: _ = try body.number()
        default: throw CPRProjectError.unsupported("Unverified audio-clip datum tag.")
        }
        let count = Int(try body.u32())
        guard count <= 10_000, count <= (body.upper - body.position) / 4 else {
            throw CPRProjectError.invalid("Invalid audio-clip child count.")
        }
        for _ in 0..<count {
            guard try archive.readObject(&body) != nil else { throw CPRProjectError.invalid("A counted audio-clip child is null.") }
        }
        guard let path = try archive.readObject(&body), path.descriptor.className == "FNPath",
              path.descriptor.version == 0 else { return }
        var fields = archive.body(path)
        let filename = try fields.nativeString()
        _ = try fields.u32() // Native type descriptor; no type identity inferred.
        for _ in 0..<3 { _ = try fields.nativeString() }
        let discriminator = try fields.i32()
        _ = try fields.u16()
        guard discriminator == 1 || discriminator == 2 else {
            result.unsupported.append(CPRUnsupportedItem(category: "Unresolved audio source",
                detail: "Track \(trackName) has a linked FNPath with an unsupported platform/path discriminator. Its original bytes are preserved.", objectCount: 1))
            return
        }
        let directory = try fields.nativeString()
        guard fields.position == fields.upper else { throw CPRProjectError.unsupported("Unconsumed FNPath fields.") }
        result.unsupported.append(CPRUnsupportedItem(category: "Unresolved audio source",
            detail: "Track \(trackName) references filename \(filename) in native directory \(directory). Media resolution and event time units are not established; no playable clip is created.", objectCount: 1))
    }

    private func tempo(_ archive: CPRArchive, _ object: CPRNativeObject) throws {
        if tempoIdentity == object.descriptor.identityOffset { return }
        guard tempoIdentity == nil else { throw CPRProjectError.unsupported("Multiple distinct tempo objects cannot be assigned an authoritative project role.") }
        guard object.descriptor.version == 3 else { throw CPRProjectError.unsupported("Unverified tempo-track version.") }
        var reader = archive.body(object)
        let count = Int(try reader.u32())
        guard count > 0, count <= 10_000, reader.upper - reader.position >= 6,
              count <= (reader.upper - reader.position - 6) / 22 else {
            throw CPRProjectError.invalid("Invalid tempo record count.")
        }
        for _ in 0..<count {
            guard try reader.floatNumber() > 0 else { throw CPRProjectError.invalid("A reciprocal tempo record is not positive.") }
            _ = try reader.number(); _ = try reader.number(); _ = try reader.u16()
        }
        let value = try reader.floatNumber()
        let fixedEnabled = try reader.u16() != 0
        tempoIdentity = object.descriptor.identityOffset
        if fixedEnabled {
            guard (20...400).contains(value) else { throw CPRProjectError.unsupported("Active fixed tempo is outside the application's 20–400 BPM range.") }
            fixedTempo = value
            result.facts.append("Recovered active fixed tempo: \(value) BPM from MTempoTrackEvent's float32 value and nonzero 16-bit mode.")
        } else {
            result.facts.append("The native tempo track selects its event map (\(count) serialized records); its stored fixed BPM is inactive.")
            result.unsupported.append(CPRUnsupportedItem(category: "Tempo event map",
                detail: "The active tempo map's coordinate units and interpolation are not yet converted. Its inactive fixed BPM and metadata BPM are not substituted.", objectCount: count))
        }
        // Trailing native attributes remain opaque; the native read/getter contract
        // establishes fixed mode independently of these attributes.
    }

    private func metadata(_ archive: CPRArchive, _ object: CPRNativeObject) throws -> [String] {
        guard object.descriptor.className == "StMedia::PAttributes", object.descriptor.version == 0 else {
            throw CPRProjectError.unsupported("Unverified metadata root class/version.")
        }
        var reader = archive.body(object)
        let fields = try CPRAttributeReader().fields(&reader)
        guard reader.position == reader.upper, fields.count == 1, case .list(let entries)? = fields["PAttr"] else {
            throw CPRProjectError.unsupported("Unverified metadata attribute layout.")
        }
        var names = Set<String>(), facts: [String] = []
        for entry in entries {
            guard case .fields(20, "StMedia::PStringIDMediaAttribute", let values) = entry,
                  case .text(let id)? = values["ID"], case .integer(let type)? = values["Type"],
                  case .integer? = values["Flags"], names.insert(id).inserted else {
                throw CPRProjectError.invalid("Invalid metadata identity/type fields.")
            }
            switch type {
            case 1: guard case .integer? = values["Long"] else { throw CPRProjectError.invalid("Metadata integer type disagreement.") }
            case 4:
                guard case .number(let value)? = values["Float"] else { throw CPRProjectError.invalid("Metadata float type disagreement.") }
                if id == "AudioSampleRate" || id == "MusicalTempo" { facts.append("Metadata \(id): \(value) (descriptive tag; not authoritative project state).") }
            case 8:
                guard case .text(let value)? = values["String"] else { throw CPRProjectError.invalid("Metadata string type disagreement.") }
                if id == "ProjectName", !value.isEmpty { facts.append("Metadata ProjectName: \(value.prefix(256))") }
            case 2:
                guard case .fields(_, let className, let rational)? = values["Object"] else { throw CPRProjectError.unsupported("Unverified metadata object type.") }
                if id == "MusicalSignature", className == "CmRational",
                   case .integer(let numerator)? = rational["Numerator"], case .integer(let denominator)? = rational["Denominator"] {
                    facts.append("Metadata MusicalSignature: \(numerator)/\(denominator) (descriptive tag; not an arrangement signature map).")
                }
            default: throw CPRProjectError.unsupported("Unverified metadata value type \(type).")
            }
        }
        return facts
    }
}
