import Foundation

/// A fresh, immutable view of the preserved source. It never replaces the
/// frozen import report or describes subsequent application edits.
public struct CPRProjectStructureSnapshot {
    public static let maximumReportBytes = 8_388_608
    public let projectID: UUID
    public let projectManifestSHA256: String
    public let importReportSHA256: String
    public let report: CPRNativeProjectBindingReport
    public let reportBytes: Data
    public let reportSHA256: String

    public static func inspect(in root: URL, expectedProjectID: UUID,
                               expectedManifestSHA256: String? = nil) throws -> Self {
        let before = try ProjectStore.loadSnapshot(from: root)
        let digest = cprSHA256(before.manifest)
        guard before.project.id == expectedProjectID,
              expectedManifestSHA256.map({ $0 == digest }) ?? true else {
            throw CPRProjectError.invalid("The saved project changed. Reopen it before inspecting its source structure.")
        }
        guard try CPRProject.compatibilityReport(from: root) != nil else {
            throw CPRProjectError.unsupported("This project has no preserved CPR source to inspect.")
        }
        let importReportHash = try frozenReportHash(in: root)
        guard let report = try CPRNativeProjectBindings.inspectPreserved(in: root) else {
            throw CPRProjectError.unsupported("This project has no preserved CPR source to inspect.")
        }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let bytes = try encoder.encode(report)
        guard bytes.count <= maximumReportBytes else {
            throw CPRProjectError.unsupported("The saved structure report exceeds 8 MiB. No partial report was accepted.")
        }
        let result = Self(projectID: expectedProjectID, projectManifestSHA256: digest,
            importReportSHA256: importReportHash, report: report, reportBytes: bytes, reportSHA256: cprSHA256(bytes))
        try result.verify(in: root)
        return result
    }

    /// Check every continuation against the preserved source and frozen report;
    /// the immutable JSON bytes are never reconstructed from partial UI rows.
    public func verify(in root: URL) throws {
        guard cprSHA256(try ProjectFileIO.readManifest(in: root)) == projectManifestSHA256,
              try Self.frozenReportHash(in: root) == importReportSHA256,
              let baseline = try CPRProject.compatibilityReport(from: root),
              baseline.sourceSHA256 == report.sourceSHA256,
              baseline.sourceByteCount == report.sourceByteCount,
              try Self.frozenReportHash(in: root) == importReportSHA256,
              cprSHA256(try ProjectFileIO.readManifest(in: root)) == projectManifestSHA256 else {
            throw CPRProjectError.invalid("The saved project or its preserved source changed. Inspect its structure again.")
        }
    }

    private static func frozenReportHash(in root: URL) throws -> String {
        let canonical = try ProjectFileIO.canonicalRoot(root)
        let url = canonical.appendingPathComponent(CPRProject.reportRelativePath)
        let manager = FileManager.default
        guard ProjectFileIO.samePath(url, try ProjectFileIO.canonicalRoot(url)),
              try !ProjectFileIO.isLinkOrReparsePoint(url) else {
            throw CPRProjectError.invalid("The preserved import report was redirected.")
        }
        let before = try manager.attributesOfItem(atPath: url.path)
        guard before[.type] as? FileAttributeType == .typeRegular,
              let size = (before[.size] as? NSNumber)?.intValue,
              (1...maximumReportBytes).contains(size) else {
            throw CPRProjectError.invalid("The preserved import report must remain a regular file of at most 8 MiB.")
        }
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        let bytes = try file.read(upToCount: size + 1) ?? Data()
        let after = try manager.attributesOfItem(atPath: url.path)
        guard bytes.count == size, (after[.size] as? NSNumber)?.intValue == size,
              before[.systemFileNumber] as? NSNumber == after[.systemFileNumber] as? NSNumber,
              before[.modificationDate] as? Date == after[.modificationDate] as? Date else {
            throw CPRProjectError.invalid("The preserved import report changed while it was being read.")
        }
        return cprSHA256(bytes)
    }
}

#if REBASE_PORTABLE
/// Byte paging preserves the entire typed report, including opaque entries,
/// raw saved numbers and unresolved conditions. UTF-8 is decoded after joining.
public struct PortableProjectStructurePage: Encodable {
    public let reviewID: String
    public let revision: UInt64
    public let projectID: UUID
    public let projectManifestSHA256: String
    public let sourceSHA256: String
    public let sourceByteCount: Int
    public let reportSHA256: String
    public let reportByteCount: Int
    public let offset: Int
    public let nextOffset: Int?
    public let bytesBase64: String
}

struct PortableProjectStructureReview {
    static let maximumPageBytes = 65_536
    let reviewID = UUID().uuidString
    let revision: UInt64
    let root: URL
    let snapshot: CPRProjectStructureSnapshot

    func page(offset: Int) throws -> PortableProjectStructurePage {
        let bytes = snapshot.reportBytes
        guard offset >= 0, offset < bytes.count, offset % Self.maximumPageBytes == 0 else {
            throw PortableCPRReviewError(code: "structureOffset", message: "Choose a valid saved structure page boundary.")
        }
        let end = min(bytes.count, offset + Self.maximumPageBytes)
        return .init(reviewID: reviewID, revision: revision, projectID: snapshot.projectID,
            projectManifestSHA256: snapshot.projectManifestSHA256,
            sourceSHA256: snapshot.report.sourceSHA256, sourceByteCount: snapshot.report.sourceByteCount,
            reportSHA256: snapshot.reportSHA256, reportByteCount: bytes.count,
            offset: offset, nextOffset: end < bytes.count ? end : nil,
            bytesBase64: bytes.subdata(in: offset..<end).base64EncodedString())
    }
}
#endif
