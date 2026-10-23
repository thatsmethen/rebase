import Foundation
#if REBASE_PORTABLE

/// A bounded review projection, never a second copy of the recovered project.
public struct PortableCPRReview: Encodable {
    public let reviewID: String
    public let sourceName: String
    public let sourceSHA256: String
    public let sourceByteCount: Int
    public let interpretationProfile: String
    public let historical: Bool
    public let canImport: Bool
    public let recoveredTrackCount: Int
    public let recoveredClipCount: Int
    public let unresolvedEventCount: Int
    public let totalItems: Int
    public let offset: Int
    public let nextOffset: Int?
    public let items: [Item]
    public struct Item: Encodable, Equatable {
        public let section: String
        public let label: String
        public let detail: String
    }
}

struct PortableCPRReviewError: LocalizedError {
    let code: String
    let message: String
    var errorDescription: String? { message }
}

/// The report is immutable for the lifetime of its token. Source bytes are
/// rechecked by the core importer, and historical reports by frozen replay.
struct PortableCPRReviewSnapshot {
    static let maximumReportBytes = 8_388_608
    static let maximumPageBytes = 131_072
    static let maximumPageItems = 32
    let report: CPRInspection
    let reviewID: String
    let historical: Bool
    private let profile: String
    private let items: [PortableCPRReview.Item]
    private let itemSizes: [Int]
    private let pageOverhead: Int

    init(report: CPRInspection, historical: Bool) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard try encoder.encode(report).count <= Self.maximumReportBytes else {
            throw PortableCPRReviewError(code: "reviewTooLarge", message: "The CPR report exceeds 8 MiB; no review or import was accepted.")
        }
        guard !report.sourceName.isEmpty, report.sourceName.utf8.count <= 4096,
              report.sourceSHA256.utf8.count == 64,
              report.sourceSHA256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              (12...CPRProject.maximumFileBytes).contains(report.sourceByteCount),
              let profile = report.interpretationProfile ?? (report.schemaVersion == 1 ? "cpr-static-subset-v1" : nil),
              !profile.isEmpty, profile.utf8.count <= 128 else {
            throw PortableCPRReviewError(code: "reviewInvalid", message: "The CPR review identity is invalid.")
        }
        self.report = report; self.historical = historical
        let token = UUID().uuidString
        self.reviewID = token; self.profile = profile
        var rows: [PortableCPRReview.Item] = []
        rows += report.recoveredFacts.map { .init(section: "recovered", label: "Recovered project data", detail: $0) }
        rows += report.recoveredTracks.map { track in
            let recovered = report.recoveredProject?.tracks.first { $0.id == track.importedTrackID }
            let status: String
            if let recovered {
                status = recovered.unresolvedAudioEvents.isEmpty ? "Empty track restored" : "\(recovered.unresolvedAudioEvents.count) unresolved audio events"
            } else { status = "Not restored" }
            return .init(section: "tracks", label: track.name, detail: "\(track.kind) · \(status)")
        }
        rows += report.unsupported.map {
            .init(section: "unresolved", label: $0.category,
                  detail: $0.detail + ($0.objectCount.map { " (\($0) objects)" } ?? ""))
        }
        rows += report.applicationDefaults.map { .init(section: "defaults", label: "Recovered project setting", detail: $0) }
        rows += report.metadataFacts.map { .init(section: "metadata", label: "Descriptive source metadata", detail: $0) }
        self.items = rows
        encoder.outputFormatting = [.sortedKeys]
        self.itemSizes = try rows.map { try encoder.encode($0).count }
        // The longest valid offsets reserve enough envelope space for every
        // page. Oversized individual rows reject the entire review up front.
        self.pageOverhead = try encoder.encode(PortableCPRReview(
            reviewID: token, sourceName: report.sourceName, sourceSHA256: report.sourceSHA256,
            sourceByteCount: report.sourceByteCount, interpretationProfile: profile,
            historical: historical, canImport: !historical && report.canImport,
            recoveredTrackCount: report.recoveredTrackCount, recoveredClipCount: report.recoveredClipCount,
            unresolvedEventCount: report.recoveredUnresolvedAudioEventCount,
            totalItems: rows.count, offset: rows.count, nextOffset: rows.count, items: [])).count
        guard pageOverhead <= Self.maximumPageBytes,
              itemSizes.allSatisfy({ $0 <= Self.maximumPageBytes - pageOverhead }) else {
            throw PortableCPRReviewError(code: "reviewTooLarge", message: "A CPR review item exceeds the 128 KiB page limit; no content was hidden or truncated.")
        }
    }

    func page(offset: Int) throws -> PortableCPRReview {
        guard offset >= 0, (items.isEmpty ? offset == 0 : offset < items.count) else {
            throw PortableCPRReviewError(code: "reviewOffset", message: "Choose an offset within this CPR review.")
        }
        var end = offset, bytes = pageOverhead
        while end < items.count, end - offset < Self.maximumPageItems {
            let size = itemSizes[end] + (end == offset ? 0 : 1)
            if size > Self.maximumPageBytes - bytes { break }
            bytes += size; end += 1
        }
        guard items.isEmpty || end > offset else {
            throw PortableCPRReviewError(code: "reviewTooLarge", message: "A CPR review item cannot fit in a page.")
        }
        let page = PortableCPRReview(reviewID: reviewID, sourceName: report.sourceName,
            sourceSHA256: report.sourceSHA256, sourceByteCount: report.sourceByteCount,
            interpretationProfile: profile, historical: historical, canImport: !historical && report.canImport,
            recoveredTrackCount: report.recoveredTrackCount, recoveredClipCount: report.recoveredClipCount,
            unresolvedEventCount: report.recoveredUnresolvedAudioEventCount,
            totalItems: items.count, offset: offset, nextOffset: end < items.count ? end : nil,
            items: Array(items[offset..<end]))
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        guard try encoder.encode(page).count <= Self.maximumPageBytes else {
            throw PortableCPRReviewError(code: "reviewTooLarge", message: "The encoded CPR review exceeds its page limit.")
        }
        return page
    }
}
#endif
