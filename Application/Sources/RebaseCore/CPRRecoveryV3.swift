import Foundation

/// Adds only the byte-checked, branch-invariant one/two-point jump-map subset.
/// V1/V2 and fixed-clock descriptors remain historical interpretations. The
/// original CPR owns all unconverted state, including these auxiliary attrs.
final class CPRRecoveryV3 {
    let container: CPRContainer
    init(container: CPRContainer) { self.container = container }

    func decode(sourceName: String) throws -> (recovery: CPRRecoveryResult, clock: NativeTempoClock?) {
        var baseline = try CPRRecoveryV2(container: container).decode(sourceName: sourceName)
        guard baseline.clock == nil else { return baseline }
        do {
            let roles = try CPRClockRoles.resolve(container: container)
            guard let tempo = roles.tempo else { return baseline }
            let reader = CPRJumpMapReader(archive: roles.archive)
            guard let records = try reader.read(tempo) else { return baseline }
            let clock: NativeTempoClock
            do {
                clock = try NativeTempoClock(mapRecords: records, sourceSHA256: container.sha256,
                                             sourceObjectOffset: tempo.descriptor.identityOffset)
            } catch NativeTempoClockError.invalid(let message) {
                throw CPRProjectError.unsupported("The serialized jump map is outside the canonical timing subset: " + message)
            }
            if var project = baseline.recovery.project {
                let events = records.enumerated().map { index, record in
                    TempoEvent(id: stableID("native-map-v3-\(index)"), beat: record.beat,
                               bpm: record.displayBPM, curve: .jump)
                }
                project.tempoMap = TempoMap(events: events, nativeClock: clock)
                try project.validate()
                baseline.recovery.project = project
            }
            try merge(roles.objects, into: &baseline.recovery)
            baseline.recovery.facts.removeAll { $0.hasPrefix("The native tempo track selects its event map") }
            baseline.recovery.defaults.removeAll { $0.hasPrefix("120 BPM is an application default") }
            baseline.recovery.unsupported.removeAll { $0.category == "Tempo event map" }
            baseline.recovery.facts.append("Recovered \(records.count) native jump-tempo point\(records.count == 1 ? "" : "s"). The original periods and timing arithmetic are retained; tempo editing or DAWproject export requires an explicit timing conversion.")
            baseline.recovery.unsupported = baseline.recovery.unsupported.map { item in
                guard item.category == "Native state preserved only" else { return item }
                return CPRUnsupportedItem(category: item.category,
                    detail: item.detail.replacingOccurrences(of: "tempo-event coordinates, ", with: ""),
                    objectCount: item.objectCount)
            }
            baseline.clock = clock
        } catch CPRProjectError.unsupported(let message) {
            baseline.recovery.unsupported = baseline.recovery.unsupported.map { item in
                guard item.category == "Tempo event map" else { return item }
                return CPRUnsupportedItem(category: item.category,
                    detail: "The active tempo map is outside the supported import subset. Its inactive fixed BPM and metadata BPM are not substituted.",
                    objectCount: item.objectCount)
            }
            baseline.recovery.defaults = baseline.recovery.defaults.map { sentence in
                sentence == "120 BPM is an application default because no supported active fixed tempo was recovered."
                    ? "120 BPM is an application default because no supported native tempo clock was recovered."
                    : sentence
            }
            baseline.recovery.unsupported.append(CPRUnsupportedItem(category: "Native jump-tempo map",
                detail: message + " The map remains preserved only; no native map clock was attached.", objectCount: 1))
        }
        return baseline
    }

    private func stableID(_ label: String) -> UUID {
        let chars = Array(cprSHA256(Data((container.sha256 + ":" + label).utf8)).prefix(32))
        return UUID(uuidString: String(chars[0..<8])+"-"+String(chars[8..<12])+"-"+String(chars[12..<16])+"-"+String(chars[16..<20])+"-"+String(chars[20..<32]))!
    }
    private func merge(_ objects: [CPRObjectRecord], into result: inout CPRRecoveryResult) throws {
        var records: [Int: CPRObjectRecord] = [:]
        for record in result.objects + objects {
            if let previous = records[record.identityOffset], previous != record {
                throw CPRProjectError.invalid("Map recovery produced inconsistent native object identity.")
            }
            records[record.identityOffset] = record
        }
        result.objects = records.values.sorted { $0.identityOffset < $1.identityOffset }
    }
}

private final class CPRJumpMapReader {
    let archive: CPRArchive
    init(archive: CPRArchive) { self.archive = archive }

    func read(_ object: CPRNativeObject) throws -> [NativeTempoMapRecord]? {
        guard object.descriptor.className == "MTempoTrackEvent", object.descriptor.version == 3 else {
            throw CPRProjectError.unsupported("Only the verified version-3 tempo interface is supported.")
        }
        var body = archive.body(object)
        let count = Int(try body.u32())
        guard (1...2).contains(count) else {
            throw CPRProjectError.unsupported("Native jump maps currently require one or two records.")
        }
        var records: [NativeTempoMapRecord] = []
        for _ in 0..<count {
            let offset = body.position
            records.append(NativeTempoMapRecord(periodBits: try body.u32(), secondsBits: try body.u64(),
                tickBits: try body.u64(), kind: try body.u16(), sourceRecordOffset: offset))
        }
        _ = try body.u32() // Inactive fixed-mode value; retained verbatim in source.
        guard try body.u16() == 0 else { return nil }
        try trackAttributes(&body)
        for _ in 0..<count { try itemAttributes(&body) }
        try finished(body, "tempo object")
        return records
    }

    private func trackAttributes(_ body: inout CPRCursor) throws {
        let count = Int(try body.u32())
        guard [2, 3, 6].contains(count) else {
            throw CPRProjectError.unsupported("Unverified tempo-track attribute count.")
        }
        var seen = Set<UInt32>()
        for _ in 0..<count {
            let key = try body.u32(), type = try body.u16()
            guard seen.insert(key).inserted else { throw CPRProjectError.invalid("Duplicate tempo-track attribute.") }
            switch key {
            case 0x69435654:
                guard type == 0x22 else { throw CPRProjectError.unsupported("Unverified tempo-variation attribute representation.") }
                try variation(&body)
            case 0x6b636f4c:
                guard type == 0x801, try body.i64() == 0 else {
                    throw CPRProjectError.unsupported("Unverified tempo-track lock state.")
                }
            case 0x73687445, 0x426c5454, 0x42755454, 0x44494c54:
                let values: [UInt32: Int64] = [0x73687445: -260498236, 0x426c5454: 55,
                                               0x42755454: 180, 0x44494c54: 1]
                guard type == 1, try body.i64() == values[key] else {
                    throw CPRProjectError.unsupported("Unverified auxiliary tempo-track attribute state.")
                }
            default:
                // In particular ThiD is excluded: native post-read code can
                // act on it. Unknowns are retained in Original.cpr, not skipped.
                throw CPRProjectError.unsupported("Unverified tempo-track attribute key.")
            }
        }
        let core: Set<UInt32> = [0x69435654, 0x6b636f4c]
        guard seen == core || seen == core.union([0x73687445]) ||
              seen == core.union([0x73687445, 0x426c5454, 0x42755454, 0x44494c54]) else {
            throw CPRProjectError.unsupported("Unverified tempo-track attribute combination.")
        }
    }

    private func variation(_ body: inout CPRCursor) throws {
        let collection = try object(&body, name: "MTrackVariationCollection", version: 0)
        var fields = archive.body(collection)
        guard try fields.i32() == 10, try fields.u16() == 2, try fields.u32() == 1 else {
            throw CPRProjectError.unsupported("Tempo maps require the verified singleton variation state.")
        }
        let variation = try object(&fields, name: "MTrackVariation", version: 0)
        try finished(fields, "variation collection")
        var item = archive.body(variation)
        _ = try item.nativeString() // A name does not select timing contents.
        guard try archive.readObject(&item) == nil, try item.i32() == 0 else {
            throw CPRProjectError.unsupported("Alternate tempo variation data is not converted.")
        }
        try finished(item, "variation")
    }

    private func itemAttributes(_ body: inout CPRCursor) throws {
        let count = try body.u32()
        if count == 0 { return }
        guard count == 1, try body.u32() == 0x5343436e, try body.u16() == 0x22 else {
            throw CPRProjectError.unsupported("Unverified per-item tempo attributes.")
        }
        let collection = try object(&body, name: "ScoreEventAttributeContainer", version: 1)
        var fields = archive.body(collection)
        guard try fields.i32() == 10, try fields.u16() == 1, try fields.u32() == 1 else {
            throw CPRProjectError.unsupported("Unverified score attribute collection state.")
        }
        let noteStart = fields.position
        guard let note = try archive.readObject(&fields), note.descriptor.objectOffset == noteStart,
              note.descriptor.className == "NoteData", [2, 3].contains(note.descriptor.version) else {
            throw CPRProjectError.unsupported("Unverified per-item NoteData representation.")
        }
        try finished(fields, "score attribute collection")
        var values = archive.body(note)
        if note.descriptor.version == 2 {
            guard try values.i32() == -1, try values.i32() == -1, try values.u16() == 0,
                  try values.u16() == 0, try values.bytes(1) == Data([0]) else {
                throw CPRProjectError.unsupported("Nondefault NoteData is outside the load-time timing subset.")
            }
        } else {
            guard try values.u32() == 5 else { throw CPRProjectError.unsupported("Unverified named NoteData field count.") }
            let expected: [String: Int64] = ["voiceIndexOnStave": -1, "staveIndex": -1,
                "isGraceNote": 0, "noteNameOptionalIsSet": 0, "noteName": 0]
            var names = Set<String>()
            for _ in 0..<5 {
                let name = try values.nativeString()
                guard names.insert(name).inserted else { throw CPRProjectError.invalid("Duplicate NoteData field.") }
                guard let value = expected[name], try values.u16() == 1, try values.i64() == value else {
                    throw CPRProjectError.unsupported("Unverified named NoteData field or value.")
                }
            }
        }
        try finished(values, "NoteData")
    }

    private func object(_ body: inout CPRCursor, name: String, version: Int) throws -> CPRNativeObject {
        let start = body.position
        guard let object = try archive.readObject(&body), object.descriptor.objectOffset == start,
              object.descriptor.className == name, object.descriptor.version == version else {
            throw CPRProjectError.unsupported("Expected a concrete \(name) version \(version) object.")
        }
        return object
    }
    private func finished(_ body: CPRCursor, _ label: String) throws {
        guard body.position == body.upper else { throw CPRProjectError.unsupported("Unconsumed \(label) bytes.") }
    }
}
