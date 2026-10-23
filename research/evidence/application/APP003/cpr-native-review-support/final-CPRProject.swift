import Foundation
import CryptoKit

public enum CPRProjectError: LocalizedError {
    case invalid(String)
    case unsupported(String)
    public var errorDescription: String? {
        switch self {
        case .invalid(let detail): return "Invalid CPR file: " + detail
        case .unsupported(let detail): return "Unsupported CPR content: " + detail
        }
    }
}

public struct CPRSection: Codable, Equatable {
    public let name: String
    public let className: String
    public let rootOffset: Int
    public let archiveOffset: Int
    public let archiveByteCount: Int
    public let archiveSHA256: String
}

public struct CPRUnsupportedItem: Codable, Equatable {
    public let category: String
    public let detail: String
    public let objectCount: Int?
}

public struct CPRRecoveredTrack: Codable, Equatable {
    public let name: String
    public let kind: String
    public let nativeClassName: String
    public let sourceOffset: Int
    public let importedTrackID: UUID?
}

public struct CPRObjectRecord: Codable, Equatable {
    public let className: String
    public let version: Int
    public let declarationOffset: Int
    public let objectOffset: Int
    public let identityOffset: Int
    public let payloadOffset: Int
    public let payloadByteCount: Int
    public let payloadSHA256: String
}

public struct CPRInspection: Codable, Equatable {
    public let schemaVersion: Int
    public let sourceName: String
    public let sourceSHA256: String
    public let sourceByteCount: Int
    public let sections: [CPRSection]
    public let recoveredFacts: [String]
    public let metadataFacts: [String]
    public let recoveredTracks: [CPRRecoveredTrack]
    public let nativeObjects: [CPRObjectRecord]
    public let applicationDefaults: [String]
    public let unsupported: [CPRUnsupportedItem]
    public let recoveredProject: Project?
    public var canImport: Bool { recoveredProject != nil }
    public var recoveredTrackCount: Int { recoveredProject?.tracks.count ?? 0 }
    public var recoveredClipCount: Int { recoveredProject?.tracks.flatMap(\.clips).count ?? 0 }
}

public struct CPRImportResult {
    public let project: Project
    public let report: CPRInspection
    public let originalRelativePath: String
}

/// Lossless container, with ARCH payloads retained as bytes rather than guessed
/// object semantics. Its size convention is fileLength - 12, unlike WAVE RIFF.
public struct CPRContainer {
    public let originalBytes: Data
    public let sections: [CPRSection]
    public var sha256: String { cprSHA256(originalBytes) }
}

/// Bounded original implementation based on the checked CPR container evidence.
/// Unknown native state is retained in the imported package's compatibility data.
public enum CPRProject {
    public static let maximumFileBytes = 268_435_456
    public static let originalRelativePath = "Compatibility/CPR/Original.cpr"
    public static let reportRelativePath = "Compatibility/CPR/ImportReport.json"
    private static let maximumSections = 4096
    private static let maximumNameBytes = 4096
    private static let maximumReportBytes = 8_388_608

    public static func readContainer(_ data: Data) throws -> CPRContainer {
        guard data.count >= 12, data.count <= maximumFileBytes else {
            throw CPRProjectError.invalid("File size must be 12 bytes through 256 MiB.")
        }
        var cursor = CPRCursor(data: data, lower: 0, upper: data.count)
        guard try cursor.bytes(4) == Data("RIFF".utf8) else {
            throw CPRProjectError.invalid("The RIFF signature is missing.")
        }
        guard try cursor.u32() == UInt32(data.count - 12), try cursor.bytes(4) == Data("NUND".utf8) else {
            throw CPRProjectError.invalid("The NUND header or big-endian file length is inconsistent.")
        }
        var sections: [CPRSection] = []
        var names = Set<String>()
        while cursor.position < cursor.upper {
            guard sections.count < maximumSections else {
                throw CPRProjectError.unsupported("More than 4096 root sections.")
            }
            let rootOffset = cursor.position
            guard try cursor.bytes(4) == Data("ROOT".utf8) else {
                throw CPRProjectError.unsupported("Expected a ROOT record at byte \(rootOffset); no scanning recovery was attempted.")
            }
            let rootLength = Int(try cursor.u32())
            let rootEnd = try cursor.endOfBytes(rootLength)
            var root = CPRCursor(data: data, lower: cursor.position, upper: rootEnd)
            let name = try root.string(maximumBytes: maximumNameBytes)
            let className = try root.string(maximumBytes: maximumNameBytes)
            guard root.position == root.upper, names.insert(name).inserted else {
                throw CPRProjectError.invalid("A ROOT record has trailing bytes or a duplicate name at byte \(rootOffset).")
            }
            cursor.position = rootEnd
            guard try cursor.bytes(4) == Data("ARCH".utf8) else {
                throw CPRProjectError.invalid("ROOT \(name) is not followed by ARCH.")
            }
            let archiveLength = Int(try cursor.u32())
            let archiveOffset = cursor.position
            let archiveEnd = try cursor.endOfBytes(archiveLength)
            let archiveHash = cprSHA256(data.subdata(in: archiveOffset..<archiveEnd))
            sections.append(CPRSection(name: name, className: className, rootOffset: rootOffset,
                archiveOffset: archiveOffset, archiveByteCount: archiveLength, archiveSHA256: archiveHash))
            cursor.position = archiveEnd
        }
        guard !sections.isEmpty else { throw CPRProjectError.invalid("The container has no ROOT/ARCH records.") }
        return CPRContainer(originalBytes: data, sections: sections)
    }

    public static func inspect(from source: URL) throws -> CPRInspection {
        let container = try readSource(source)
        return try inspect(container: container, sourceName: source.lastPathComponent)
    }

    public static func importProject(from source: URL, to destination: URL,
                                     allowPartial: Bool = false, expectedSHA256: String? = nil) throws -> CPRImportResult {
        try requireNew(destination)
        let container = try readSource(source)
        if let expectedSHA256, container.sha256 != expectedSHA256 {
            throw CPRProjectError.invalid("The source changed after review. Inspect it again before importing.")
        }
        let report = try inspect(container: container, sourceName: source.lastPathComponent)
        guard let project = report.recoveredProject else {
            throw CPRProjectError.unsupported("No editable project subset has been established for this CPR file. The source is unchanged.")
        }
        guard allowPartial || report.unsupported.isEmpty else {
            throw CPRProjectError.unsupported("Review the unsupported content before importing the supported subset.")
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let reportBytes = try encoder.encode(report)
        guard reportBytes.count <= maximumReportBytes else {
            throw CPRProjectError.unsupported("The compatibility report exceeds 8 MiB; no project was published.")
        }
        let manager = FileManager.default
        let staging = destination.deletingLastPathComponent().appendingPathComponent(".rebase-cpr-" + UUID().uuidString)
        defer { try? manager.removeItem(at: staging) }
        try manager.createDirectory(at: staging, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        try manager.createDirectory(at: staging.appendingPathComponent("Media"), withIntermediateDirectories: false)
        try manager.createDirectory(at: staging.appendingPathComponent("Compatibility/CPR"), withIntermediateDirectories: true)
        try container.originalBytes.write(to: staging.appendingPathComponent(originalRelativePath), options: .atomic)
        try reportBytes.write(to: staging.appendingPathComponent(reportRelativePath), options: .atomic)
        try ProjectStore.save(project, to: staging)
        _ = try ProjectStore.load(from: staging)
        guard cprSHA256(try Data(contentsOf: staging.appendingPathComponent(originalRelativePath))) == report.sourceSHA256 else {
            throw CPRProjectError.invalid("The preserved source failed its byte-integrity check.")
        }
        _ = try compatibilityReport(from: staging)
        try requireNew(destination)
        try manager.moveItem(at: staging, to: destination)
        return CPRImportResult(project: project, report: report, originalRelativePath: originalRelativePath)
    }

    /// Reads the historical import report and verifies its preserved source.
    /// The report describes the import baseline, not subsequent project edits.
    public static func compatibilityReport(from projectRoot: URL) throws -> CPRInspection? {
        let root = projectRoot.standardizedFileURL.resolvingSymlinksInPath()
        let reportURL = root.appendingPathComponent(reportRelativePath)
        let sourceURL = root.appendingPathComponent(originalRelativePath)
        let manager = FileManager.default
        let reportExists = manager.fileExists(atPath: reportURL.path)
        let sourceExists = manager.fileExists(atPath: sourceURL.path)
        guard reportExists || sourceExists else { return nil }
        guard reportExists && sourceExists,
              reportURL.resolvingSymlinksInPath() == reportURL,
              sourceURL.resolvingSymlinksInPath() == sourceURL,
              (try reportURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])).isRegularFile == true,
              (try reportURL.resourceValues(forKeys: [.fileSizeKey])).fileSize ?? Int.max <= maximumReportBytes else {
            throw CPRProjectError.invalid("The compatibility report or preserved source is missing, redirected, or oversized.")
        }
        let report = try JSONDecoder().decode(CPRInspection.self, from: Data(contentsOf: reportURL))
        let container = try readSource(sourceURL)
        guard report.schemaVersion == 1, report.sourceByteCount == container.originalBytes.count,
              report.sourceSHA256 == container.sha256, report.sections == container.sections else {
            throw CPRProjectError.invalid("The preserved CPR file does not match its import report.")
        }
        try report.recoveredProject?.validate()
        let fresh = try inspect(container: container, sourceName: report.sourceName)
        guard report == fresh else {
            throw CPRProjectError.invalid("The historical CPR import report no longer agrees with the supported source interpretation. Reimport the preserved source to refresh it.")
        }
        return report
    }

    private static func inspect(container: CPRContainer, sourceName: String) throws -> CPRInspection {
        let recovery = try CPRRecovery(container: container).decode(sourceName: sourceName)
        return CPRInspection(schemaVersion: 1, sourceName: sourceName, sourceSHA256: container.sha256,
            sourceByteCount: container.originalBytes.count, sections: container.sections,
            recoveredFacts: recovery.facts, metadataFacts: recovery.metadata, recoveredTracks: recovery.tracks,
            nativeObjects: recovery.objects, applicationDefaults: recovery.defaults,
            unsupported: recovery.unsupported, recoveredProject: recovery.project)
    }

    private static func readSource(_ source: URL) throws -> CPRContainer {
        let before = try FileManager.default.attributesOfItem(atPath: source.path)
        let values = try source.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
        guard values.isRegularFile == true, let size = values.fileSize, size <= maximumFileBytes else {
            throw CPRProjectError.unsupported("Choose a regular CPR file of at most 256 MiB.")
        }
        let file = try FileHandle(forReadingFrom: source)
        defer { try? file.close() }
        let bytes = try file.read(upToCount: maximumFileBytes + 1) ?? Data()
        let after = try FileManager.default.attributesOfItem(atPath: source.path)
        guard bytes.count == size, (after[.size] as? NSNumber)?.intValue == size,
              before[.systemFileNumber] as? NSNumber == after[.systemFileNumber] as? NSNumber,
              before[.modificationDate] as? Date == after[.modificationDate] as? Date else {
            throw CPRProjectError.invalid("The source changed while it was being read.")
        }
        return try readContainer(bytes)
    }

    private static func requireNew(_ destination: URL) throws {
        guard !FileManager.default.fileExists(atPath: destination.path),
              (try? destination.resourceValues(forKeys: [.isSymbolicLinkKey])) == nil else {
            throw CPRProjectError.invalid("Choose a new destination; existing files and projects are never replaced.")
        }
    }
}

private func cprSHA256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private struct CPRCursor {
    let data: Data
    var position: Int
    let upper: Int
    init(data: Data, lower: Int, upper: Int) { self.data = data; self.position = lower; self.upper = upper }
    func endOfBytes(_ count: Int) throws -> Int {
        guard count >= 0, position <= upper, count <= upper - position else {
            throw CPRProjectError.invalid("A record extends beyond its enclosing region at byte \(position).")
        }
        return position + count
    }
    mutating func bytes(_ count: Int) throws -> Data {
        let end = try endOfBytes(count)
        let result = data.subdata(in: position..<end)
        position = end
        return result
    }
    mutating func u32() throws -> UInt32 {
        try bytes(4).reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
    }
    mutating func string(maximumBytes: Int) throws -> String {
        let count = Int(try u32())
        guard count > 0, count <= maximumBytes, let value = String(data: try bytes(count), encoding: .utf8),
              !value.contains("\0") else { throw CPRProjectError.invalid("Invalid bounded UTF-8 root name.") }
        return value
    }
}

private extension CPRCursor {
    mutating func u16() throws -> UInt16 { try bytes(2).reduce(UInt16(0)) { ($0 << 8) | UInt16($1) } }
    mutating func u64() throws -> UInt64 { try bytes(8).reduce(UInt64(0)) { ($0 << 8) | UInt64($1) } }
    mutating func i32() throws -> Int32 { Int32(bitPattern: try u32()) }
    mutating func i64() throws -> Int64 { Int64(bitPattern: try u64()) }
    mutating func number() throws -> Double {
        let value = Double(bitPattern: try u64())
        guard value.isFinite else { throw CPRProjectError.invalid("A native numeric field is nonfinite at byte \(position - 8).") }
        return value
    }
    mutating func floatNumber() throws -> Double {
        let value = Float(bitPattern: try u32())
        guard value.isFinite else { throw CPRProjectError.invalid("A native float field is nonfinite at byte \(position - 4).") }
        return Double(value)
    }
    /// Class registry keys use the native raw-byte reader, not the user-visible
    /// string decoder. Never normalize a BOM into a different class identity.
    mutating func className() throws -> String {
        let count = Int(try u32())
        guard count > 1, count <= 4097 else { throw CPRProjectError.unsupported("Invalid or oversized native class name.") }
        let value = try bytes(count)
        guard value.last == 0, value.dropLast().allSatisfy({ $0 > 0 && $0 < 0x80 }),
              let text = String(data: value.dropLast(), encoding: .ascii) else {
            throw CPRProjectError.unsupported("Native class keys must be unchanged ASCII with one terminal NUL.")
        }
        return text
    }
    mutating func nativeString() throws -> String {
        let count = Int(try u32())
        guard count <= 50_000 else { throw CPRProjectError.unsupported("A native string exceeds the verified 50000-byte reader bound.") }
        var value = try bytes(count)
        var isUTF8 = false
        if !value.isEmpty {
            if value.suffix(4) == Data([0, 0xef, 0xbb, 0xbf]) { value.removeLast(4); isUTF8 = true }
            else if value.last == 0 { value.removeLast() }
            else { throw CPRProjectError.invalid("An archive string is not terminated at byte \(position).") }
            if value.prefix(3) == Data([0xef, 0xbb, 0xbf]) { value.removeFirst(3); isUTF8 = true }
        }
        guard isUTF8 || value.allSatisfy({ $0 < 0x80 }) else {
            throw CPRProjectError.unsupported("An unmarked non-ASCII native string needs an unverified legacy code page.")
        }
        guard !value.contains(0), let text = String(data: value, encoding: .utf8) else {
            throw CPRProjectError.invalid("Invalid UTF-8 archive string.")
        }
        return text
    }
}

private struct CPRNativeObject {
    let descriptor: CPRObjectRecord
    var end: Int { descriptor.payloadOffset + descriptor.payloadByteCount }
}

/// Only the observed 32-bit class/reference envelope is supported. Positive
/// object references address an already registered payload-length field. Class
/// references address declaration tokens relative to this ARCH payload.
private final class CPRArchive {
    let data: Data
    let start: Int
    let end: Int
    private var classes: [Int: (String, Int, Int)] = [:]
    private(set) var objects: [Int: CPRNativeObject] = [:]
    init(data: Data, section: CPRSection) {
        self.data = data; start = section.archiveOffset; end = start + section.archiveByteCount
    }
    func body(_ object: CPRNativeObject) -> CPRCursor {
        CPRCursor(data: data, lower: object.descriptor.payloadOffset, upper: object.end)
    }
    func root(expectedClass: String) throws -> CPRNativeObject {
        var reader = CPRCursor(data: data, lower: start, upper: end)
        guard let object = try readObject(&reader), object.descriptor.className == expectedClass,
              reader.position == end else { throw CPRProjectError.invalid("ARCH root class or extent does not match ROOT.") }
        return object
    }
    private func declaration(at offset: Int, reader: inout CPRCursor) throws -> (String, Int, Int) {
        let name = try reader.className()
        guard !name.isEmpty, name.utf8.count <= 4096, classes.count < 10_000 else {
            throw CPRProjectError.unsupported("Invalid or excessive class declarations.")
        }
        let version = Int(try reader.u16())
        let descriptor = (name, version, offset)
        if let existing = classes[offset - start] {
            guard existing == descriptor else { throw CPRProjectError.invalid("Conflicting class declaration identity.") }
        }
        classes[offset - start] = descriptor
        return descriptor
    }
    func readObject(_ reader: inout CPRCursor) throws -> CPRNativeObject? {
        let objectOffset = reader.position
        for _ in 0..<64 {
            let tokenOffset = reader.position
            let token = try reader.u32()
            let descriptor: (String, Int, Int)
            if token == 0xffff_ffff || token == 0xffff_fffe {
                descriptor = try declaration(at: tokenOffset, reader: &reader)
                if token == 0xffff_fffe { continue }
            } else if token & 0x8000_0000 != 0 {
                let relative = Int(token & 0x7fff_ffff)
                if let known = classes[relative] { descriptor = known }
                else {
                    guard relative < tokenOffset - start, relative <= end - start - 4 else {
                        throw CPRProjectError.unsupported("Uncached class references must address a previous concrete declaration.")
                    }
                    let offset = start + relative
                    var referenced = CPRCursor(data: data, lower: offset, upper: end)
                    let marker = try referenced.u32()
                    guard marker == 0xffff_ffff else {
                        throw CPRProjectError.unsupported("Uncached base-class chains are not interpreted as concrete declarations.")
                    }
                    descriptor = try declaration(at: offset, reader: &referenced)
                }
            } else {
                if token == 0 { return nil }
                guard let object = objects[Int(token)] else {
                    throw CPRProjectError.invalid("Unknown object identity at byte \(tokenOffset).")
                }
                return object
            }
            let identityOffset = reader.position
            let size = Int(try reader.u32())
            let payload = reader.position
            let objectEnd = try reader.endOfBytes(size)
            guard objects.count < 10_000, objects[identityOffset - start] == nil else {
                throw CPRProjectError.unsupported("Excessive or duplicate archive object identity.")
            }
            let record = CPRObjectRecord(className: descriptor.0, version: descriptor.1,
                declarationOffset: descriptor.2, objectOffset: objectOffset, identityOffset: identityOffset,
                payloadOffset: payload, payloadByteCount: size,
                payloadSHA256: cprSHA256(data.subdata(in: payload..<objectEnd)))
            let object = CPRNativeObject(descriptor: record)
            objects[identityOffset - start] = object
            reader.position = objectEnd
            return object
        }
        throw CPRProjectError.unsupported("More than 64 consecutive base-class declarations.")
    }
}

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

private struct CPRRecoveryResult {
    var facts: [String] = []
    var metadata: [String] = []
    var tracks: [CPRRecoveredTrack] = []
    var objects: [CPRObjectRecord] = []
    var defaults: [String] = []
    var unsupported: [CPRUnsupportedItem] = []
    var project: Project?
}

private final class CPRRecovery {
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
