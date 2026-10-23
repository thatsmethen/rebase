import Foundation
#if !REBASE_PORTABLE
import CryptoKit
#endif

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
    /// Absent only in historical schema-1 reports, which select the frozen v1
    /// interpretation. Serialization schema and recovery semantics are distinct.
    public let interpretationProfile: String?
    public let nativeClock: NativeTempoClock?
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
    /// Added by V5 only. A missing field in historical reports remains nil.
    public var audioSetup: CPRProjectAudioSetup? = nil
    public var canImport: Bool { recoveredProject != nil }
    public var recoveredTrackCount: Int { recoveredProject?.tracks.count ?? 0 }
    public var recoveredClipCount: Int { recoveredProject?.tracks.flatMap(\.clips).count ?? 0 }
    public var recoveredUnresolvedAudioEventCount: Int { recoveredProject?.unresolvedAudioEvents.count ?? 0 }
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
    public static let currentInterpretationProfile = "cpr-static-subset-v5"
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
        // Canonicalize the parent, never an existing destination. Publication
        // must retain the caller's final component and never follow/replace it.
        try requireNew(destination)
        let parent = try ProjectFileIO.canonicalRoot(destination.deletingLastPathComponent())
        try ProjectFileIO.requireRealDirectory(parent)
        let destination = parent.appendingPathComponent(destination.lastPathComponent)
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
        let staging = parent.appendingPathComponent(".rebase-cpr-" + UUID().uuidString)
        try ProjectFileIO.createNewDirectory(staging)
        // Cleanup owns only the directory successfully created by this call.
        defer { try? manager.removeItem(at: staging) }
        try ProjectFileIO.requireRealDirectory(staging)
        try ProjectFileIO.createNewDirectory(staging.appendingPathComponent("Media"))
        try ProjectFileIO.createNewDirectory(staging.appendingPathComponent("Compatibility"))
        try ProjectFileIO.createNewDirectory(staging.appendingPathComponent("Compatibility/CPR"))
        // These files are private until the completed sibling directory is
        // published. Avoid Foundation's Windows atomic-copy fallback here.
        try container.originalBytes.write(to: staging.appendingPathComponent(originalRelativePath), options: .withoutOverwriting)
        try reportBytes.write(to: staging.appendingPathComponent(reportRelativePath), options: .withoutOverwriting)
        try ProjectStore.save(project, to: staging)
        guard try ProjectStore.load(from: staging) == project,
              try Data(contentsOf: staging.appendingPathComponent(originalRelativePath)) == container.originalBytes,
              try Data(contentsOf: staging.appendingPathComponent(reportRelativePath)) == reportBytes,
              try compatibilityReport(from: staging) == report else {
            throw CPRProjectError.invalid("The staged project, preserved source, or import report failed its integrity check.")
        }
        try requireNew(destination)
        try ProjectFileIO.publishNewDirectory(staging, to: destination)
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
        _ = try interpretation(schemaVersion: report.schemaVersion, declaredProfile: report.interpretationProfile)
        let container = try readSource(sourceURL)
        guard report.sourceByteCount == container.originalBytes.count,
              report.sourceSHA256 == container.sha256, report.sections == container.sections else {
            throw CPRProjectError.invalid("The preserved CPR file does not match its import report.")
        }
        try report.recoveredProject?.validate()
        let fresh = try inspect(container: container, sourceName: report.sourceName,
                                schemaVersion: report.schemaVersion, declaredProfile: report.interpretationProfile)
        guard report == fresh else {
            throw CPRProjectError.invalid("The historical CPR import report no longer agrees with the supported source interpretation. Reimport the preserved source to refresh it.")
        }
        return report
    }

    private enum Interpretation { case v1, v2, v3, v4, v5 }

    private static func interpretation(schemaVersion: Int, declaredProfile: String?) throws -> Interpretation {
        guard schemaVersion == 1 || schemaVersion == 2 else {
            throw CPRProjectError.unsupported("Compatibility report schema \(schemaVersion) is not supported.")
        }
        guard let profile = declaredProfile ?? (schemaVersion == 1 ? "cpr-static-subset-v1" : nil) else {
            throw CPRProjectError.unsupported("Schema-2 compatibility reports require an interpretation profile.")
        }
        switch profile {
        case "cpr-static-subset-v1": return .v1
        case "cpr-static-subset-v2" where schemaVersion == 2: return .v2
        case "cpr-static-subset-v3" where schemaVersion == 2: return .v3
        case "cpr-static-subset-v4" where schemaVersion == 2: return .v4
        case "cpr-static-subset-v5" where schemaVersion == 2: return .v5
        default: throw CPRProjectError.unsupported("Compatibility interpretation profile \(profile) is not supported.")
        }
    }

    private static func inspect(container: CPRContainer, sourceName: String, schemaVersion: Int = 2,
                                declaredProfile: String? = currentInterpretationProfile) throws -> CPRInspection {
        let recovery: CPRRecoveryResult
        let nativeClock: NativeTempoClock?
        var audioSetup: CPRProjectAudioSetup?
        switch try interpretation(schemaVersion: schemaVersion, declaredProfile: declaredProfile) {
        case .v1:
            recovery = try CPRRecoveryV1(container: container).decode(sourceName: sourceName)
            nativeClock = nil
        case .v2:
            let decoded = try CPRRecoveryV2(container: container).decode(sourceName: sourceName)
            recovery = decoded.recovery; nativeClock = decoded.clock
        case .v3:
            let decoded = try CPRRecoveryV3(container: container).decode(sourceName: sourceName)
            recovery = decoded.recovery; nativeClock = decoded.clock
        case .v4:
            let decoded = try CPRRecoveryV4(container: container).decode(sourceName: sourceName)
            recovery = decoded.recovery; nativeClock = decoded.clock
        case .v5:
            let decoded = try CPRRecoveryV5(container: container).decode(sourceName: sourceName)
            recovery = decoded.recovery; nativeClock = decoded.clock; audioSetup = decoded.audioSetup
        }
        return CPRInspection(schemaVersion: schemaVersion, interpretationProfile: declaredProfile, nativeClock: nativeClock,
            sourceName: sourceName, sourceSHA256: container.sha256,
            sourceByteCount: container.originalBytes.count, sections: container.sections,
            recoveredFacts: recovery.facts, metadataFacts: recovery.metadata, recoveredTracks: recovery.tracks,
            nativeObjects: recovery.objects, applicationDefaults: recovery.defaults,
            unsupported: recovery.unsupported, recoveredProject: recovery.project, audioSetup: audioSetup)
    }

    static func readSource(_ source: URL) throws -> CPRContainer {
        let before = try FileManager.default.attributesOfItem(atPath: source.path)
        // A reused URL can cache a previous size after a deliberate file edit.
        // Refresh metadata before the bounded before/after identity check.
        var freshSource = source
        freshSource.removeAllCachedResourceValues()
        let values = try freshSource.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
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

func cprSHA256(_ data: Data) -> String {
    #if REBASE_PORTABLE
    return PortableSHA256.hexDigest(data)
    #else
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    #endif
}

struct CPRCursor {
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

extension CPRCursor {
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

struct CPRNativeObject {
    let descriptor: CPRObjectRecord
    var end: Int { descriptor.payloadOffset + descriptor.payloadByteCount }
}

/// Only the observed 32-bit class/reference envelope is supported. Positive
/// object references address an already registered payload-length field. Class
/// references address declaration tokens relative to this ARCH payload.
final class CPRArchive {
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

