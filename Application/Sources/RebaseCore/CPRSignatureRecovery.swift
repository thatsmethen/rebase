import Foundation

/// A projection of explicitly serialized origin meter, not a complete Reference
/// signature-track implementation. Contract: CPR-SIGNATURE-001 (static only).
struct CPRSignatureRecoveryResult {
    var signature: SignatureEvent?
    var facts: [String] = []
    var unsupported: [CPRUnsupportedItem] = []
    var objects: [CPRObjectRecord] = []
}

enum CPRSignatureRecovery {
    static func recover(container: CPRContainer) throws -> CPRSignatureRecoveryResult {
        var result = CPRSignatureRecoveryResult()
        var visitedArchive: CPRArchive?
        do {
            let roles = try CPRClockRoles.resolve(container:container)
            let archive = roles.archive
            visitedArchive = archive
            guard let signature = roles.signature else {
                throw CPRProjectError.unsupported("The shared track timing pair has no signature object.")
            }
            let meter = try origin(archive: archive, object: signature, result: &result)
            let hex = Array(cprSHA256(Data((container.sha256 + ":signature-origin-v2").utf8)).prefix(32))
            let id = UUID(uuidString: String(hex[0..<8])+"-"+String(hex[8..<12])+"-"+String(hex[12..<16])+"-"+String(hex[16..<20])+"-"+String(hex[20..<32]))!
            result.signature = SignatureEvent(id: id, beat: 0, numerator: meter.0, denominator: meter.1)
            result.facts.append("Recovered consistent origin signature \(meter.0)/\(meter.1) from shared track timing data. Compact and typed representations agree.")
        } catch CPRProjectError.unsupported(let message) {
            result.signature = nil
            result.unsupported.append(issue(message))
        }
        result.objects = visitedArchive?.objects.values.map(\.descriptor).sorted { $0.identityOffset < $1.identityOffset } ?? []
        return result
    }

    private static func issue(_ detail: String) -> CPRUnsupportedItem {
        CPRUnsupportedItem(category: "Signature state", detail: detail, objectCount: 1)
    }

    private static func origin(archive: CPRArchive, object: CPRNativeObject,
                               result: inout CPRSignatureRecoveryResult) throws -> (Int, Int) {
        var reader = archive.body(object)
        let count = try reader.i32()
        guard count > 0, count <= 10_000, Int(count) <= (reader.upper - reader.position) / 16 else {
            throw CPRProjectError.invalid("Invalid compact signature record count or extent.")
        }
        guard count == 1 else { throw CPRProjectError.unsupported("Multiple compact signature records require unresolved compatibility and selection semantics.") }
        let coordinate = try reader.i32()
        let compactNumerator = Int64(Int16(bitPattern: try reader.u16()))
        let compactDenominator = Int64(Int16(bitPattern: try reader.u16()))
        let extras = try (0..<4).map { _ in Int16(bitPattern: try reader.u16()) }
        guard coordinate == 0, extras == [0,0,0,8] else {
            throw CPRProjectError.unsupported("The compact signature must be the verified origin without additional subdivision/display state.")
        }
        let attributeCount = Int(try reader.u32())
        guard attributeCount <= 10_000, attributeCount <= (reader.upper-reader.position)/6 else {
            throw CPRProjectError.invalid("Invalid signature attribute count.")
        }
        var keys = Set<UInt32>()
        var typed: CPRNativeObject?
        var variations: CPRNativeObject?
        for _ in 0..<attributeCount {
            let key = try reader.u32()
            guard keys.insert(key).inserted else { throw CPRProjectError.invalid("Duplicate signature attribute key.") }
            let type = try reader.u16()
            switch (key, type) {
            case (0x53636f4c, 1), (0x53636f4c, 0x801):
                guard try reader.i64() == 0 else { throw CPRProjectError.unsupported("Nonzero signature track flags are not recovered.") }
            case (0x73687445, 1), (0x44494c54, 1):
                _ = try reader.i64()
                result.unsupported.append(issue("Native signature auxiliary attribute \(String(format: "%08x", key)) is retained in the original; its display/editor meaning is not reproduced."))
            case (0x69435654, 2), (0x69435654, 0x22):
                variations = try archive.readObject(&reader)
                guard variations != nil else { throw CPRProjectError.unsupported("Null variation collection is outside the supported explicit form.") }
            case (0x736b6c43, 2):
                typed = try archive.readObject(&reader)
            default:
                throw CPRProjectError.unsupported("Unsupported signature attribute \(String(format: "%08x", key)) / type \(type).")
            }
        }
        guard reader.position == reader.upper else { throw CPRProjectError.invalid("Trailing signature-track bytes.") }
        if let variations { try checkVariations(archive: archive, object: variations) }
        guard let typed, typed.descriptor.className == "FAttributes", typed.descriptor.version == 0 else {
            throw CPRProjectError.unsupported("No supported typed signature replacement container; compact/default signatures are not promoted.")
        }
        var fields = archive.body(typed)
        let decoded = try SignatureFields().read(&fields)
        guard fields.position == fields.upper else { throw CPRProjectError.invalid("Trailing signature attribute-container bytes.") }
        guard decoded.count == 1, case .list(let events)? = decoded["SignatureEvent"], events.count == 1,
              case .compound(20, "MTimeSignatureEvent", let event) = events[0] else {
            throw CPRProjectError.unsupported("Only one typed MTimeSignatureEvent in SignatureEvent is recovered.")
        }
        let allowed: Set<String> = ["Flags", "Start", "Length", "Offset", "Additional Attributes", "Bar", "Numerator", "Denominator", "Position", "SubNumerator1", "SubNumerator2", "SubNumerator3", "TimeSignatureDisplayFlags"]
        guard Set(event.keys).isSubset(of: allowed),
              case .integer(0)? = event["Bar"],
              case .integer(let numerator)? = event["Numerator"],
              case .integer(let denominator)? = event["Denominator"],
              (1...64).contains(numerator), [1,2,4,8,16].contains(denominator),
              case .integer(8)? = event["Flags"],
              case .number(0)? = event["Start"], case .number(1)? = event["Length"] else {
            throw CPRProjectError.unsupported("The typed signature requires exact Bar=0, integer meter in the application range, and the verified origin event fields.")
        }
        // Reader101730b84..c70 can remove the typed container based on an
        // unobserved product/version context. Agreement makes this projection
        // independent of that branch; contradictory sources stay unsupported.
        guard numerator == compactNumerator, denominator == compactDenominator else {
            throw CPRProjectError.unsupported("Compact and typed signature meters disagree; native compatibility selection is unresolved.")
        }
        if let position = event["Position"], case .integer = position {} else if event["Position"] != nil {
            throw CPRProjectError.unsupported("Coerced signature Position fields are not supported.")
        }
        if let offset = event["Offset"], case .number(0) = offset {} else if event["Offset"] != nil {
            throw CPRProjectError.unsupported("Nonzero or coerced signature offset is not recovered.")
        }
        for key in ["SubNumerator1", "SubNumerator2", "SubNumerator3"] {
            if let value = event[key], case .integer(0) = value {} else if event[key] != nil {
                throw CPRProjectError.unsupported("Compound signature subdivisions are not recovered.")
            }
        }
        if let display = event["TimeSignatureDisplayFlags"], case .integer(8) = display {} else if event["TimeSignatureDisplayFlags"] != nil {
            throw CPRProjectError.unsupported("Unsupported signature display flags.")
        }
        if let additional = event["Additional Attributes"] {
            guard case .compound(6, nil, let attributes) = additional else {
                throw CPRProjectError.unsupported("Unsupported additional signature attributes.")
            }
            // These are distinct opaque score attributes seen in the factory
            // templates. They do not supply any recovered musical-map values.
            guard Set(attributes.keys).isSubset(of: ["nCCS"]) else {
                throw CPRProjectError.unsupported("Unknown additional signature attributes may change restoration.")
            }
            if !attributes.isEmpty {
                result.unsupported.append(issue("Signature score/layout attributes remain preserved only; their engraving behavior is not recovered."))
            }
        }
        return (Int(numerator), Int(denominator))
    }

    private static func checkVariations(archive: CPRArchive, object: CPRNativeObject) throws {
        guard object.descriptor.className == "MTrackVariationCollection", object.descriptor.version == 0 else {
            throw CPRProjectError.unsupported("Unsupported signature variation collection class/version.")
        }
        var fields = archive.body(object)
        guard try fields.i32() == 10, try fields.u16() == 2, try fields.i32() == 1,
              let variation = try archive.readObject(&fields), fields.position == fields.upper,
              variation.descriptor.className == "MTrackVariation", variation.descriptor.version == 0 else {
            throw CPRProjectError.unsupported("Only one explicitly bounded signature variation is recovered.")
        }
        var body = archive.body(variation)
        _ = try body.nativeString()
        guard try archive.readObject(&body) == nil, try body.i32() == 0, body.position == body.upper else {
            throw CPRProjectError.unsupported("An alternate signature variation list or selector is not recovered.")
        }
    }
}

private indirect enum SignatureField {
    case integer(Int64), number(Double), text(String)
    case compound(Int, String?, [String: SignatureField]), list([SignatureField])
}

private final class SignatureFields {
    private var budget = 10_000
    func read(_ cursor: inout CPRCursor, depth: Int = 0) throws -> [String: SignatureField] {
        guard depth <= 32 else { throw CPRProjectError.unsupported("Signature attributes exceed nesting limit.") }
        let count = Int(try cursor.u32())
        guard count <= budget else { throw CPRProjectError.unsupported("Signature attributes exceed count limit.") }
        budget -= count
        var values: [String: SignatureField] = [:]
        for _ in 0..<count {
            let name = try cursor.className() // Exact ASCII property identity, no BOM normalization.
            guard values[name] == nil else { throw CPRProjectError.invalid("Duplicate named signature attribute.") }
            switch try cursor.u16() {
            case 1: values[name] = .integer(try cursor.i64())
            case 4: values[name] = .number(try cursor.number())
            case 8: values[name] = .text(try cursor.nativeString())
            case 2: values[name] = try compound(&cursor, depth: depth + 1)
            default: throw CPRProjectError.unsupported("Unsupported typed signature attribute.")
            }
        }
        return values
    }
    private func compound(_ cursor: inout CPRCursor, depth: Int) throws -> SignatureField {
        guard depth <= 32 else { throw CPRProjectError.unsupported("Signature compounds exceed nesting limit.") }
        switch try cursor.u16() {
        case 6: return .compound(6, nil, try read(&cursor, depth: depth))
        case 20:
            let name = try cursor.className()
            _ = try cursor.u64() // Opaque typed identity, not an archive reference.
            return .compound(20, name, try read(&cursor, depth: depth))
        case 201:
            let count = Int(try cursor.u32())
            guard count <= budget else { throw CPRProjectError.unsupported("Signature compound array exceeds count limit.") }
            budget -= count
            return .list(try (0..<count).map { _ in try compound(&cursor, depth: depth + 1) })
        default: throw CPRProjectError.unsupported("Unsupported signature compound subtype.")
        }
    }
}
