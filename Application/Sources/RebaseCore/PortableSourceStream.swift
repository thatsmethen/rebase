import Foundation
#if REBASE_PORTABLE

/// Local-process transport of the shared playback output. Nothing here runs on
/// a device callback, reconstructs new DSP, or changes project/source bytes.
public enum PortableSourceStream {
    public static let maximumMetadataBytes = 8_388_608
    public static let maximumTicketBytes = 33_554_432
    public static let maximumChunkFrames = 65_536
    static let maximumLogicalFrames = 16_000_000

    public struct Receipt: Encodable {
        public let generation: UUID
        public let revision: UInt64
        public let eventID: UUID
        public let mode: String
        public let ticketPath: String
        public let ticketSHA256: String
        public let capability: UUID
        public let proofSHA256: String
        public let sampleRate: Double
        public let startFrame: Int64
        public let totalFrames: Int64
        public let frames: Int64
        public let maximumChunkFrames = PortableSourceStream.maximumChunkFrames
    }

    struct Proof: Encodable {
        let schema = "rebase.source-stream-proof.v1"
        let revision: UInt64
        let eventID: UUID
        let name: String
        let mode: String
        let sourceKind: String
        let clockRole: String
        let projectSampleRate: Double
        let currentNativeClock: NativeTempoClock?
        let preservedNativeClock: NativeTempoClock?
        let projectManifestSHA256: String
        let currentProjectSHA256: String
        let importReportSHA256: String
        let sourceSHA256: String
        let mediaSHA256: String
        let sampleRate: Double
        let sourceSampleRate: Double
        let frames: Int64
        let startFrame: Int64
        let totalFrames: Int64
        let channels = 2
        let timelineRange: PortableSourceAuditionManifest.Range?
        let savedProjectAudioSetup: CPRProjectAudioSetup?
        let sourceTrack: PortableSourceAuditionManifest.Track?
    }

    private struct Ticket: Codable {
        let schema: String
        let generation: UUID
        let capability: UUID
        let revision: UInt64
        let eventID: UUID
        let mode: String
        let startSeconds: Double
        let rewindAtEnd: Bool
        let rootPath: String
        let projectData: Data
        let proofData: Data
        let projectManifestSHA256: String
        let importReportSHA256: String
    }
    private struct Startup: Decodable {
        let schema: String
        let ticketPath: String
        let ticketSHA256: String
        let capability: UUID
        let generation: UUID
        let maximumChunkFrames: Int?
    }
    private struct Admission: Encodable {
        let schema = "rebase.source-stream-admission.v1"
        let generation: UUID
        let revision: UInt64
        let eventID: UUID
        let mode: String
        let sampleRate: Double
        let startFrame: Int64
        let totalFrames: Int64
        let frames: Int64
        let channels = 2
        let maximumChunkFrames: Int
        let proofSHA256: String
        let proof: Proof
    }
    private struct PCM: Encodable {
        let generation: UUID
        let sequence: UInt64
        let absoluteFrame: Int64
        let frames: Int
        let logicalBlock: UInt64
        let logicalOffset: Int
        let logicalFrames: Int
        let sha256: String
    }
    private struct End: Encodable {
        let generation: UUID
        let nextSequence: UInt64
        let nextAbsoluteFrame: Int64
        let frames: Int64
        let pcmSHA256: String
        let peakLogicalFrames: Int
        let peakPayloadFrames: Int
        let emittedLogicalBlocks: UInt64
    }
    private struct Failed: Encodable {
        let generation: UUID?
        let code: String
        let message: String
        let lastSequence: UInt64?
        let lastAbsoluteFrame: Int64?
    }
    struct Failure: Swift.Error, LocalizedError {
        let code: String
        var errorDescription: String? { Self.message(code) }
        static func message(_ code: String) -> String {
            switch code {
            case "startup": return "The source stream startup request is invalid."
            case "ticket": return "The source stream ticket is invalid, changed or unavailable."
            case "sourceChanged": return "The saved source, project, report or attached media changed. Prepare the source again."
            case "preparation": return "The selected source cannot be prepared with the requested playback mode."
            case "producer": return "The shared source producer did not deliver its declared audio."
            default: return "The source stream output could not be delivered."
            }
        }
    }

    struct OwnedTicket {
        let receipt: Receipt
        let url: URL
        let inode: NSNumber?
        let device: NSNumber?
        func removeIfOwned() {
            guard let inode, let device,
                  let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
                  attributes[.type] as? FileAttributeType == .typeRegular,
                  attributes[.systemFileNumber] as? NSNumber == inode,
                  attributes[.systemNumber] as? NSNumber == device,
                  let bytes = try? PortableSourceStream.readRegular(url, limit: maximumTicketBytes),
                  PortableSHA256.hexDigest(bytes) == receipt.ticketSHA256 else { return }
            try? FileManager.default.removeItem(at: url)
        }
    }

    static func encode<T: Encodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return try encoder.encode(value)
    }
    private static func nativePath(_ url: URL) throws -> String {
        try url.withUnsafeFileSystemRepresentation {
            guard let value = $0 else { throw Failure(code: "ticket") }
            return String(cString: value)
        }
    }
    private static func url(_ path: String) throws -> URL {
        guard !path.isEmpty, !path.contains("\0") else { throw Failure(code: "ticket") }
        let url = URL(fileURLWithPath: path).standardizedFileURL
        guard ProjectFileIO.samePath(url, try ProjectFileIO.canonicalRoot(url)) else { throw Failure(code: "ticket") }
        return url
    }
    private static func realAncestors(_ url: URL) throws {
        var parent = url.deletingLastPathComponent()
        while true {
            try ProjectFileIO.requireRealDirectory(parent)
            // A bridged Foundation URL can append ".." when deleting the
            // root's last component. The root itself has just been checked.
            if parent.pathComponents.count <= 1 { break }
            let next = parent.deletingLastPathComponent()
            if ProjectFileIO.samePath(next, parent) { break }
            parent = next
        }
    }
    static func readRegular(_ url: URL, limit: Int) throws -> Data {
        try realAncestors(url)
        guard ProjectFileIO.samePath(url, try ProjectFileIO.canonicalRoot(url)),
              try !ProjectFileIO.isLinkOrReparsePoint(url) else { throw Failure(code: "ticket") }
        let before = try FileManager.default.attributesOfItem(atPath: url.path)
        guard before[.type] as? FileAttributeType == .typeRegular,
              let count = (before[.size] as? NSNumber)?.intValue, (1...limit).contains(count) else {
            throw Failure(code: "ticket")
        }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let bytes = try handle.read(upToCount: count + 1) ?? Data()
        let after = try FileManager.default.attributesOfItem(atPath: url.path)
        guard bytes.count == count, after[.type] as? FileAttributeType == .typeRegular,
              before[.size] as? NSNumber == after[.size] as? NSNumber,
              before[.systemFileNumber] as? NSNumber == after[.systemFileNumber] as? NSNumber,
              before[.systemNumber] as? NSNumber == after[.systemNumber] as? NSNumber,
              before[.modificationDate] as? Date == after[.modificationDate] as? Date,
              try !ProjectFileIO.isLinkOrReparsePoint(url) else { throw Failure(code: "ticket") }
        return bytes
    }

    private static func verify(_ info: CPRSourceEventPlaybackInfo, project: Project, root: URL,
                               manifestSHA: String, reportBytes: Data) throws {
        guard PortableSHA256.hexDigest(try ProjectFileIO.readManifest(in: root)) == manifestSHA,
              try readRegular(root.appendingPathComponent(CPRProject.reportRelativePath), limit: maximumMetadataBytes) == reportBytes else {
            throw Failure(code: "sourceChanged")
        }
        let verified = try ProjectStore.verifiedCPRSourceEvent(info.eventID, in: project, at: root)
        guard verified.container.sha256 == info.sourceSHA256 else { throw Failure(code: "sourceChanged") }
        for (id, digest) in info.sourceTrack?.events.map({ ($0.eventID, $0.mediaSHA256) }) ?? [(info.eventID, info.mediaSHA256)] {
            guard let event = project.unresolvedAudioEvents.first(where: { $0.id == id }),
                  let attachment = project.attachedMedia(for: event), attachment.mediaSHA256 == digest else {
                throw Failure(code: "sourceChanged")
            }
            let media = try CPRAudioMediaValidation.attachedURL(attachment.mediaPath, root: root)
            try realAncestors(media)
            guard PortableSHA256.hexDigest(try CPRAudioMediaValidation.snapshot(media)) == digest else {
                throw Failure(code: "sourceChanged")
            }
        }
    }

    private static func prepare(project: Project, projectData: Data, root: URL, revision: UInt64,
                                eventID: UUID, mode: CPRSourceEventPlaybackMode, startSeconds: Double,
                                rewindAtEnd: Bool, manifestSHA: String, reportSHA: String? = nil)
        throws -> (CPRSourceAudition.Prepared, Proof, Data) {
        guard startSeconds.isFinite, startSeconds >= 0 else { throw Failure(code: "preparation") }
        try realAncestors(root.appendingPathComponent(ProjectStore.manifestName))
        try ProjectFileIO.requireRealDirectory(root)
        try project.validate()
        try ProjectStore.validateNativeClockProvenance(project, at: root)
        guard PortableSHA256.hexDigest(try ProjectFileIO.readManifest(in: root)) == manifestSHA else {
            throw Failure(code: "sourceChanged")
        }
        let reportBytes = try readRegular(root.appendingPathComponent(CPRProject.reportRelativePath), limit: maximumMetadataBytes)
        guard reportSHA.map({ $0 == PortableSHA256.hexDigest(reportBytes) }) ?? true,
              let report = try CPRProject.compatibilityReport(from: root) else { throw Failure(code: "sourceChanged") }
        let prepared = try CPRSourceAudition.prepare(eventID: eventID, in: project, at: root, mode: mode)
        let info = prepared.info
        guard info.frameCount > 0, info.sampleRate.isFinite, info.sampleRate.rounded() == info.sampleRate,
              (8_000...192_000).contains(info.sampleRate), info.frameCount <= Int64(info.sampleRate) * 86_400,
              info.eventID == eventID, info.mode == mode,
              (info.sourceTrack?.events.count ?? 1) <= 4096,
              (info.sourceTrack?.fragments.count ?? 0) <= 16_384 else { throw Failure(code: "preparation") }
        let rounded = try prepared.startFrame(at: startSeconds)
        let start = rewindAtEnd && rounded == info.frameCount ? 0 : rounded
        let clockRole: String
        switch mode {
        case .sourceRate: clockRole = "source-rate"
        case .nativeTimelineSourceRate: clockRole = "source-clock-unconverted"
        case .nativeTimelineProjectClock: clockRole = "current-project-clock-unconverted"
        case .nativeTimelineSavedProjectClock, .nativeTrackSavedProjectClock: clockRole = "saved-project-clock-unconverted"
        case .nativeMode0ProjectRate, .nativeMode1ProjectRate, .nativeMode2ProjectRate: clockRole = "current-project-rate-converted"
        }
        let proof = Proof(revision: revision, eventID: eventID, name: info.name, mode: mode.rawValue,
            sourceKind: info.sourceTrack == nil ? "event" : "track", clockRole: clockRole,
            projectSampleRate: project.sampleRate, currentNativeClock: project.tempoMap.nativeClock,
            preservedNativeClock: report.nativeClock, projectManifestSHA256: manifestSHA,
            currentProjectSHA256: PortableSHA256.hexDigest(projectData), importReportSHA256: PortableSHA256.hexDigest(reportBytes),
            sourceSHA256: info.sourceSHA256, mediaSHA256: info.mediaSHA256, sampleRate: info.sampleRate,
            sourceSampleRate: info.sourceSampleRate, frames: info.frameCount - start, startFrame: start,
            totalFrames: info.frameCount, timelineRange: info.timelineRange.map(PortableSourceAuditionManifest.Range.init),
            savedProjectAudioSetup: info.savedProjectAudioSetup, sourceTrack: info.sourceTrack.map(PortableSourceAuditionManifest.Track.init))
        let proofData = try encode(proof)
        guard proofData.count <= maximumMetadataBytes else { throw Failure(code: "preparation") }
        try verify(info, project: project, root: root, manifestSHA: manifestSHA, reportBytes: reportBytes)
        return (prepared, proof, reportBytes)
    }

    static func issue(project: Project, root: URL, revision: UInt64, eventID: UUID,
                      mode: CPRSourceEventPlaybackMode, startSeconds: Double, rewindAtEnd: Bool,
                      manifestSHA: String, destination: URL) throws -> OwnedTicket {
        let destination = try url(try nativePath(destination))
        try realAncestors(destination)
        guard !ProjectFileIO.samePath(destination, root), !ProjectFileIO.contains(destination, in: root),
              (try? FileManager.default.attributesOfItem(atPath: destination.path)) == nil else { throw Failure(code: "ticket") }
        let projectData = try ProjectStore.encodedManifest(project)
        let (prepared, proof, _) = try prepare(project: project, projectData: projectData, root: root,
            revision: revision, eventID: eventID, mode: mode, startSeconds: startSeconds,
            rewindAtEnd: rewindAtEnd, manifestSHA: manifestSHA)
        _ = prepared // Preparation owns no output queue; released before reply.
        let generation = UUID(), capability = UUID(), proofData = try encode(proof)
        // Prove the entire admission fits before publishing its ticket. No fields
        // are dropped to fit the bound, including fully covered contributors.
        _ = try record(kind: 1, metadata: admission(proof, generation: generation, chunkFrames: maximumChunkFrames))
        let ticket = Ticket(schema: "rebase.source-stream-ticket.v1", generation: generation, capability: capability,
            revision: revision, eventID: eventID, mode: mode.rawValue, startSeconds: startSeconds,
            rewindAtEnd: rewindAtEnd, rootPath: try nativePath(root), projectData: projectData, proofData: proofData,
            projectManifestSHA256: manifestSHA, importReportSHA256: proof.importReportSHA256)
        let data = try encode(ticket)
        guard data.count <= maximumTicketBytes else { throw Failure(code: "ticket") }
        let stage = destination.deletingLastPathComponent().appendingPathComponent(".rebase-source-ticket-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: stage) }
        try data.write(to: stage, options: .withoutOverwriting)
        guard try readRegular(stage, limit: maximumTicketBytes) == data else { throw Failure(code: "ticket") }
        try realAncestors(destination)
        try ProjectFileIO.publishNewFile(stage, to: destination)
        let attributes = try FileManager.default.attributesOfItem(atPath: destination.path)
        let receipt = Receipt(generation: generation, revision: revision, eventID: eventID, mode: mode.rawValue,
            ticketPath: try nativePath(destination), ticketSHA256: PortableSHA256.hexDigest(data), capability: capability,
            proofSHA256: PortableSHA256.hexDigest(proofData), sampleRate: proof.sampleRate,
            startFrame: proof.startFrame, totalFrames: proof.totalFrames, frames: proof.frames)
        let owned = OwnedTicket(receipt: receipt, url: destination,
            inode: attributes[.systemFileNumber] as? NSNumber, device: attributes[.systemNumber] as? NSNumber)
        do {
            guard try readRegular(destination, limit: maximumTicketBytes) == data else { throw Failure(code: "ticket") }
            return owned
        } catch { owned.removeIfOwned(); throw error }
    }

    private static func admission(_ proof: Proof, generation: UUID, chunkFrames: Int) throws -> Admission {
        let digest = PortableSHA256.hexDigest(try encode(proof))
        return Admission(generation: generation, revision: proof.revision, eventID: proof.eventID, mode: proof.mode,
            sampleRate: proof.sampleRate, startFrame: proof.startFrame, totalFrames: proof.totalFrames,
            frames: proof.frames, maximumChunkFrames: chunkFrames, proofSHA256: digest, proof: proof)
    }
    private static func record<T: Encodable>(kind: UInt16, metadata: T, payload: Data = Data()) throws -> Data {
        let bytes = try encode(metadata)
        guard bytes.count <= maximumMetadataBytes, payload.count <= maximumChunkFrames * 8,
              kind == 2 || payload.isEmpty else { throw Failure(code: "producer") }
        var result = Data("RBAS".utf8)
        func append<Integer: FixedWidthInteger>(_ value: Integer) {
            var value = value.littleEndian; withUnsafeBytes(of: &value) { result.append(contentsOf: $0) }
        }
        append(UInt16(1)); append(kind); append(UInt32(bytes.count)); append(UInt32(payload.count))
        result.append(bytes); result.append(payload); return result
    }

    // Startup is deliberately flat: reject duplicate/unknown keys and lexical
    // non-integer chunk bounds before Foundation can normalize JSON numbers.
    private static func validateStartup(_ data: Data) throws {
        let bytes = Array(data); var index = 0
        func whitespace() { while index < bytes.count && [9, 10, 13, 32].contains(bytes[index]) { index += 1 } }
        func consume(_ value: UInt8) throws {
            whitespace(); guard index < bytes.count && bytes[index] == value else { throw Failure(code: "startup") }
            index += 1
        }
        func string() throws -> String {
            whitespace(); let start = index
            try consume(34)
            var escaped = false
            while index < bytes.count {
                let value = bytes[index]; index += 1
                if escaped { escaped = false }
                else if value == 92 { escaped = true }
                else if value == 34 { return try JSONDecoder().decode(String.self, from: Data(bytes[start..<index])) }
            }
            throw Failure(code: "startup")
        }
        let required: Set<String> = ["schema", "ticketPath", "ticketSHA256", "capability", "generation"]
        var keys = Set<String>()
        try consume(123)
        while true {
            let key = try string()
            guard (required.contains(key) || key == "maximumChunkFrames"), keys.insert(key).inserted else { throw Failure(code: "startup") }
            try consume(58)
            if key == "maximumChunkFrames" {
                whitespace(); let start = index
                while index < bytes.count && (48...57).contains(bytes[index]) { index += 1 }
                guard index > start, bytes[start] != 48 || index == start + 1 else { throw Failure(code: "startup") }
            } else { _ = try string() }
            whitespace()
            guard index < bytes.count else { throw Failure(code: "startup") }
            if bytes[index] == 125 { index += 1; break }
            try consume(44)
        }
        whitespace()
        guard index == bytes.count, required.isSubset(of: keys) else { throw Failure(code: "startup") }
    }

    /// Emits records synchronously with natural pipe backpressure. The caller
    /// owns cancellation/pipe lifetime; stdin EOF after startup is not cancel.
    /// Return zero only after the complete explicit EOF record is delivered.
    @discardableResult
    public static func produce(startup bytes: Data, output: (Data) throws -> Void) -> Int32 {
        var generation: UUID?, lastSequence: UInt64?, nextFrame: Int64?
        var phase = "startup"
        do {
            guard bytes.count <= PortableSession.maximumRequestBytes else { throw Failure(code: "startup") }
            try validateStartup(bytes)
            let startup = try JSONDecoder().decode(Startup.self, from: bytes)
            generation = startup.generation
            let chunkFrames = startup.maximumChunkFrames ?? maximumChunkFrames
            guard startup.schema == "rebase.source-stream-start.v1", (1...maximumChunkFrames).contains(chunkFrames),
                  startup.ticketSHA256.count == 64,
                  startup.ticketSHA256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { throw Failure(code: "startup") }
            phase = "ticket"
            let ticketURL = try url(startup.ticketPath)
            let data = try readRegular(ticketURL, limit: maximumTicketBytes)
            guard PortableSHA256.hexDigest(data) == startup.ticketSHA256 else { throw Failure(code: "ticket") }
            let ticket = try JSONDecoder().decode(Ticket.self, from: data)
            let root = try url(ticket.rootPath)
            guard ticket.schema == "rebase.source-stream-ticket.v1", ticket.generation == startup.generation,
                  ticket.capability == startup.capability,
                  !ProjectFileIO.contains(ticketURL, in: root), !ProjectFileIO.samePath(ticketURL, root),
                  !ticket.projectData.isEmpty, ticket.projectData.count <= ProjectFileIO.maximumManifestBytes,
                  !ticket.proofData.isEmpty, ticket.proofData.count <= maximumMetadataBytes,
                  let mode = CPRSourceEventPlaybackMode(rawValue: ticket.mode) else { throw Failure(code: "ticket") }
            let project = try JSONDecoder().decode(Project.self, from: ticket.projectData)
            guard try ProjectStore.encodedManifest(project) == ticket.projectData else { throw Failure(code: "ticket") }
            phase = "sourceChanged"
            let (prepared, proof, _) = try prepare(project: project, projectData: ticket.projectData, root: root,
                revision: ticket.revision, eventID: ticket.eventID, mode: mode, startSeconds: ticket.startSeconds,
                rewindAtEnd: ticket.rewindAtEnd, manifestSHA: ticket.projectManifestSHA256, reportSHA: ticket.importReportSHA256)
            guard try encode(proof) == ticket.proofData,
                  try readRegular(ticketURL, limit: maximumTicketBytes) == data else { throw Failure(code: "sourceChanged") }
            phase = "preparation"
            let cursor = try prepared.cursor(from: proof.startFrame)
            // Cursor initialization may preroll. Recheck custody afterward,
            // before claiming the complete admitted snapshot to the receiver.
            let reportBytes = try readRegular(root.appendingPathComponent(CPRProject.reportRelativePath), limit: maximumMetadataBytes)
            guard PortableSHA256.hexDigest(reportBytes) == ticket.importReportSHA256 else { throw Failure(code: "sourceChanged") }
            try verify(prepared.info, project: project, root: root, manifestSHA: ticket.projectManifestSHA256, reportBytes: reportBytes)
            phase = "output"
            try output(record(kind: 1, metadata: admission(proof, generation: startup.generation, chunkFrames: chunkFrames)))
            nextFrame = proof.startFrame
            var sequence: UInt64 = 0, logicalBlock: UInt64 = 0
            var peakLogical = 0, peakPayload = 0
            var digest = PortableSHA256.Hasher()
            phase = "producer"
            while let block = try cursor.nextPlaybackBlock() {
                guard block.frameCount > 0, block.frameCount <= maximumLogicalFrames,
                      block.left.count == block.frameCount, block.right.count == block.frameCount,
                      Int64(block.frameCount) <= proof.totalFrames - nextFrame!,
                      block.left.allSatisfy(\.isFinite), block.right.allSatisfy(\.isFinite) else { throw Failure(code: "producer") }
                peakLogical = max(peakLogical, block.frameCount)
                var offset = 0
                while offset < block.frameCount {
                    let count = min(chunkFrames, block.frameCount - offset)
                    var payload = Data(); payload.reserveCapacity(count * 8)
                    for index in offset..<(offset + count) {
                        var left = block.left[index].bitPattern.littleEndian
                        var right = block.right[index].bitPattern.littleEndian
                        withUnsafeBytes(of: &left) { payload.append(contentsOf: $0) }
                        withUnsafeBytes(of: &right) { payload.append(contentsOf: $0) }
                    }
                    let meta = PCM(generation: startup.generation, sequence: sequence, absoluteFrame: nextFrame!,
                        frames: count, logicalBlock: logicalBlock, logicalOffset: offset,
                        logicalFrames: block.frameCount, sha256: PortableSHA256.hexDigest(payload))
                    phase = "output"; try output(record(kind: 2, metadata: meta, payload: payload)); phase = "producer"
                    digest.update(payload); lastSequence = sequence; sequence += 1
                    nextFrame! += Int64(count); offset += count; peakPayload = max(peakPayload, count)
                }
                logicalBlock += 1
            }
            guard nextFrame == proof.totalFrames, cursor.isAtEnd,
                  digest.byteCount == UInt64(proof.frames) * 8 else { throw Failure(code: "producer") }
            phase = "output"
            try output(record(kind: 3, metadata: End(generation: startup.generation, nextSequence: sequence,
                nextAbsoluteFrame: nextFrame!, frames: proof.frames, pcmSHA256: digest.hexDigest(),
                peakLogicalFrames: peakLogical, peakPayloadFrames: peakPayload, emittedLogicalBlocks: logicalBlock)))
            return 0
        } catch {
            let code = (error as? Failure)?.code ?? phase
            let failure = Failed(generation: generation, code: code, message: Failure.message(code),
                lastSequence: lastSequence, lastAbsoluteFrame: nextFrame)
            if let record = try? record(kind: 4, metadata: failure) { try? output(record) }
            return 1
        }
    }
}
#endif
