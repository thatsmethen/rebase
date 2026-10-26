import Foundation
#if REBASE_PORTABLE

/// Versioned local-process protocol. This is not a network service.
public struct PortableSessionRequest: Codable {
    public var protocolVersion: Int
    public var id: UInt64
    public var command: String
    public var expectedRevision: UInt64?
    public var path: String?
    public var paths: [String]?
    public var clipID: UUID?
    public var trackID: UUID?
    public var value: Double?
    public var duration: Double?
    public var snap: String?
    public var discardChanges: Bool?
    public var asCopy: Bool?
    public var reviewID: String?
    public var sourceSHA256: String?
    public var allowPartial: Bool?
    public var reviewOffset: Int?
    public var parameter: String?
    public var pointID: UUID?
    public var time: Double?
    public var interpolation: String?
    public var enabled: Bool?
    public var mode: String?
    public var startSeconds: Double?
    public var rewindAtEnd: Bool?
    enum CodingKeys: String, CodingKey {
        case protocolVersion = "protocol"
        case id, command, expectedRevision, path, paths, clipID, trackID, value, duration, snap, discardChanges, asCopy
        case reviewID, sourceSHA256, allowPartial, reviewOffset
        case parameter, pointID, time, interpolation, enabled, mode, startSeconds, rewindAtEnd
    }
}

public struct PortableSessionState: Encodable {
    public let revision: UInt64
    public let dirty: Bool
    public let path: String?
    public let needsSaveAs: Bool
    public let project: Project?
    public let selection: Selection
    public let canUndo: Bool
    public let canRedo: Bool
    public struct Selection: Encodable { public let trackID: UUID?; public let clipID: UUID? }
}

public struct PortableSessionReply: Encodable {
    public let protocolVersion = 1
    public let id: UInt64?
    public let ok: Bool
    public let state: PortableSessionState
    public let render: Render?
    public let waveform: Waveform?
    public let ruler: Ruler?
    public let cprReview: PortableCPRReview?
    public var sourceInspection: SourceInspection? = nil
    public var sourceStream: PortableSourceStream.Receipt? = nil
    public let error: Failure?
    public struct SourceInspection: Encodable {
        public let revision: UInt64
        public let eventID: UUID
        public let sourceSHA256: String
        public let availabilityScope = "preparation-only"
        public let maximumFrames = PortableSession.maximumSourceAuditionFrames
        public let modes: [SourceMode]
    }
    public struct SourceMode: Encodable {
        public let mode: String
        public let available: Bool
        public let reason: String?
        public let liveAvailable: Bool
        public let snapshotExportAvailable: Bool
        public let liveReason: String?
        public let snapshotExportReason: String?
        public let sampleRate: Double?
        public let frames: Int64?
        public let sourceSampleRate: Double?
        public let mediaSHA256: String?
        public let timelineRange: PortableSourceAuditionManifest.Range?
        public let savedProjectAudioSetup: CPRProjectAudioSetup?
        public let contributorCount: Int?
        public let fragmentCount: Int?
    }
    public struct Ruler: Encodable {
        public let revision: UInt64
        public let duration: Double
        public let pixelsPerSecond: Double
        public let ticks: [MusicalRulerTick]
    }
    public struct Waveform: Encodable {
        public let revision: UInt64
        public let clipID: UUID
        public let sampleRate: Double
        public let sourceStartFrame: Int64
        public let sourceFrames: Int64
        public let mediaSHA256: String
        public let peaks: [Float]
    }
    public struct Render: Encodable {
        public let path: String
        public let revision: UInt64
        public let sampleRate: Double
        public let frames: Int64
        public let channels: Int
        public let wavBytes: Int
        public let sha256: String
        public let kind: String
        public let eventID: UUID?
        public let sourceSHA256: String?
        public let mediaSHA256: String?
        public var mode: String? = nil
        public var manifestPath: String? = nil
        public var manifestSHA256: String? = nil
        public var manifestBytes: Int? = nil
        public var startFrame: Int64? = nil
        public var totalFrames: Int64? = nil
    }
    public struct Failure: Encodable { public let code: String; public let message: String }
    enum CodingKeys: String, CodingKey { case protocolVersion = "protocol"; case id, ok, state, render, waveform, ruler, cprReview, sourceInspection, sourceStream, error }
}

/// Complete, ephemeral audition provenance. Stored beside a newly rendered WAV,
/// never inside the imported package and never substituted for its import report.
public struct PortableSourceAuditionManifest: Encodable {
    public struct Range: Encodable {
        public let contract: String
        public let position: Double
        public let duration: Double
        public let offset: Double
        init(_ range: CPRSourceEventTimelineRange) {
            contract = range.contract; position = range.position; duration = range.duration; offset = range.offset
        }
    }
    public struct Contributor: Encodable {
        public let eventID: UUID
        public let eventIdentity: Int
        public let sourceOrdinal: Int
        public let priority: Int32
        public let sourceSampleRate: Double
        public let mediaSHA256: String
        public let canonicalStart: Double
        public let canonicalEnd: Double
        public let range: Range?
        init(_ event: CPRSourceTrackPlaybackInfo.Event) {
            eventID = event.eventID; eventIdentity = event.eventIdentity; sourceOrdinal = event.sourceOrdinal
            priority = event.priority; sourceSampleRate = event.sourceSampleRate; mediaSHA256 = event.mediaSHA256
            canonicalStart = event.canonicalStart; canonicalEnd = event.canonicalEnd; range = event.range.map(Range.init)
        }
    }
    public struct Fragment: Encodable {
        public let eventID: UUID
        public let eventIdentity: Int
        public let sourceOrdinal: Int
        public let range: Range
        init(_ fragment: CPRSourceTrackPlaybackInfo.Fragment) {
            eventID = fragment.eventID; eventIdentity = fragment.eventIdentity
            sourceOrdinal = fragment.sourceOrdinal; range = Range(fragment.range)
        }
    }
    public struct Track: Encodable {
        public let contract: String
        public let freshRootMode: UInt32
        public let trackIdentity: Int
        public let events: [Contributor]
        public let fragments: [Fragment]
        public let snappedEmptyFragmentCount: Int
        init(_ track: CPRSourceTrackPlaybackInfo) {
            contract = track.contract; freshRootMode = track.freshRootMode; trackIdentity = track.trackIdentity
            events = track.events.map(Contributor.init); fragments = track.fragments.map(Fragment.init)
            snappedEmptyFragmentCount = track.snappedEmptyFragmentCount
        }
    }
    public let schema = "rebase.source-audition-manifest.v1"
    public let revision: UInt64
    public let eventID: UUID
    public let name: String
    public let mode: String
    public let sourceKind: String
    public let clockRole: String
    public let projectSampleRate: Double
    public let currentNativeClock: NativeTempoClock?
    public let preservedNativeClock: NativeTempoClock?
    public let projectManifestSHA256: String
    public let currentProjectSHA256: String
    public let importReportSHA256: String
    public let sourceSHA256: String
    public let mediaSHA256: String
    public let sampleRate: Double
    public let sourceSampleRate: Double
    public let frames: Int64
    public let startFrame: Int64
    public let totalFrames: Int64
    public let channels = 2
    public let maximumFrames = PortableSession.maximumSourceAuditionFrames
    public let timelineRange: Range?
    public let savedProjectAudioSetup: CPRProjectAudioSetup?
    public let sourceTrack: Track?
    public let wavFileName: String
    public let wavBytes: Int
    public let wavSHA256: String
}

/// Serialized document owner for a native host. The host sends intents; all
/// edits, validation, undo, timing and mixing use the same application sources.
public final class PortableSession {
    public static let maximumRequestBytes = 65_536
    /// Bounds growth through individual protocol edits, without truncating or
    /// rejecting an existing larger lane when it is opened or reduced.
    public static let maximumEditableAutomationPoints = 4_096
    public static let maximumSourceAuditionFrames: Int64 = 32_000_000
    public static let maximumSourceAuditionManifestBytes = 8_388_608
    private var project: Project?
    private var savedProject: Project?
    private var root: URL?
    private var isScratch = false
    private var manifestDigest: String?
    private var selection = ProjectSelection()
    private var history = ProjectEditHistory()
    private var revision: UInt64 = 0
    private var lastRequestID: UInt64?
    private var ownedScratch: [URL] = []
    private struct ReviewedCPR {
        let snapshot: PortableCPRReviewSnapshot
        let source: URL?
        let historicalRoot: URL?
    }
    private var reviewedCPR: ReviewedCPR?
    private var pendingSourceStream: PortableSourceStream.OwnedTicket?
    private let importedSnapshotLoader: (URL) throws -> (project: Project, manifest: Data)
    public init() { importedSnapshotLoader = { try ProjectStore.loadSnapshot(from: $0) } }
    // A readback dependency permits deterministic verification of the
    // publication-success/readback-failure boundary without filesystem races.
    init(importedSnapshotLoader: @escaping (URL) throws -> (project: Project, manifest: Data)) {
        self.importedSnapshotLoader = importedSnapshotLoader
    }
    deinit {
        pendingSourceStream?.removeIfOwned()
        for url in ownedScratch { try? FileManager.default.removeItem(at: url) }
    }

    private var state: PortableSessionState {
        PortableSessionState(revision: revision, dirty: project != savedProject,
            path: isScratch ? nil : root.flatMap { try? nativePath($0) }, needsSaveAs: isScratch,
            project: project, selection: .init(trackID: selection.trackID, clipID: selection.clipID),
            canUndo: history.canUndo, canRedo: history.canRedo)
    }
    private struct SessionError: LocalizedError {
        let code: String
        let message: String
        var errorDescription: String? { message }
    }
    private func failure(_ code: String, _ message: String) -> SessionError { .init(code: code, message: message) }

    public func process(_ bytes: Data) -> Data {
        let previousRevision = revision, previousSelection = selection
        defer {
            if revision != previousRevision || selection != previousSelection {
                pendingSourceStream?.removeIfOwned(); pendingSourceStream = nil
            }
        }
        var id: UInt64?
        let reply: PortableSessionReply
        do {
            guard bytes.count <= Self.maximumRequestBytes else { throw failure("requestTooLarge", "The request exceeds 64 KiB.") }
            let request = try JSONDecoder().decode(PortableSessionRequest.self, from: bytes)
            id = request.id
            guard request.protocolVersion == 1 else { throw failure("protocol", "Unsupported session protocol.") }
            guard lastRequestID.map({ request.id > $0 }) ?? true else { throw failure("requestOrder", "Request identifiers must increase.") }
            lastRequestID = request.id
            if request.command != "state" {
                guard request.expectedRevision == revision else { throw failure("staleRevision", "The project changed. Refresh its state before retrying.") }
            }
            if request.command == "prepareSourceStream" {
                guard let current = project, let root, let manifestDigest else { throw failure("noProject", "Open a project first.") }
                try checkSourceUnchanged(root)
                guard let eventID = request.clipID else { throw failure("selection", "Choose a source event.") }
                guard let mode = CPRSourceEventPlaybackMode(rawValue: request.mode ?? "sourceRate") else { throw failure("sourceMode", "Choose a supported source playback mode.") }
                let next = try PortableSourceStream.issue(project: current, root: root, revision: revision,
                    eventID: eventID, mode: mode, startSeconds: request.startSeconds ?? 0,
                    rewindAtEnd: request.rewindAtEnd ?? false, manifestSHA: manifestDigest,
                    destination: requiredURL(request.path))
                pendingSourceStream?.removeIfOwned(); pendingSourceStream = next
                reply = .init(id: id, ok: true, state: state, render: nil, waveform: nil, ruler: nil,
                    cprReview: nil, sourceStream: next.receipt, error: nil)
            } else if request.command == "inspectSourceEvent" {
                let inspection = try inspectSourceEvent(request)
                reply = .init(id: id, ok: true, state: state, render: nil, waveform: nil, ruler: nil,
                    cprReview: nil, sourceInspection: inspection, error: nil)
            } else if request.command == "waveform" {
                let envelope = try waveform(request)
                reply = .init(id: id, ok: true, state: state, render: nil, waveform: envelope, ruler: nil, cprReview: nil, error: nil)
            } else if request.command == "ruler" {
                let projection = try ruler(request)
                reply = .init(id: id, ok: true, state: state, render: nil, waveform: nil, ruler: projection, cprReview: nil, error: nil)
            } else if ["inspectCPR", "cprReviewPage", "cancelCPRReview", "cprImportReport"].contains(request.command) {
                let review = try reviewCPR(request)
                reply = .init(id: id, ok: true, state: state, render: nil, waveform: nil, ruler: nil, cprReview: review, error: nil)
            } else {
                let render = try execute(request)
                reply = .init(id: id, ok: true, state: state, render: render, waveform: nil, ruler: nil, cprReview: nil, error: nil)
            }
        } catch {
            reply = .init(id: id, ok: false, state: state, render: nil, waveform: nil, ruler: nil, cprReview: nil,
                error: .init(code: (error as? SessionError)?.code ?? (error as? PortableCPRReviewError)?.code ?? (error as? PortableSourceStream.Failure)?.code ?? "operationFailed", message: error.localizedDescription))
        }
        // Validated models contain only finite numbers and bounded strings.
        // The host treats an encoding failure as a failed protocol exchange.
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return (try? encoder.encode(reply)) ?? Data("{\"protocol\":1,\"ok\":false,\"error\":{\"code\":\"encoding\",\"message\":\"Unable to encode session state.\"}}".utf8)
    }

    private func reviewCPR(_ request: PortableSessionRequest) throws -> PortableCPRReview? {
        switch request.command {
        case "inspectCPR":
            reviewedCPR = nil
            let source = try requiredURL(request.path)
            let snapshot = try PortableCPRReviewSnapshot(report: CPRProject.inspect(from: source), historical: false)
            let page = try snapshot.page(offset: 0)
            reviewedCPR = .init(snapshot: snapshot, source: source, historicalRoot: nil)
            return page
        case "cprImportReport":
            reviewedCPR = nil
            guard let root, project != nil else { throw failure("noProject", "Open a project first.") }
            try checkSourceUnchanged(root)
            guard let report = try CPRProject.compatibilityReport(from: root) else {
                throw failure("noCPRReport", "This project has no retained CPR import report.")
            }
            try checkSourceUnchanged(root)
            let snapshot = try PortableCPRReviewSnapshot(report: report, historical: true)
            let page = try snapshot.page(offset: 0)
            reviewedCPR = .init(snapshot: snapshot, source: nil, historicalRoot: root)
            return page
        case "cprReviewPage":
            let cached = try matchingReview(request.reviewID)
            if let historicalRoot = cached.historicalRoot {
                guard try CPRProject.compatibilityReport(from: historicalRoot) == cached.snapshot.report else {
                    reviewedCPR = nil
                    throw failure("reviewChanged", "The retained CPR report changed. Reopen its verified report.")
                }
            }
            guard let offset = request.reviewOffset else { throw failure("reviewOffset", "A review page offset is required.") }
            return try cached.snapshot.page(offset: offset)
        case "cancelCPRReview":
            _ = try matchingReview(request.reviewID)
            reviewedCPR = nil
            return nil
        default: throw failure("command", "Unknown review command.")
        }
    }

    private func matchingReview(_ token: String?) throws -> ReviewedCPR {
        guard let token, let cached = reviewedCPR, token == cached.snapshot.reviewID else {
            throw failure("reviewToken", "This CPR review is no longer current. Inspect the source again.")
        }
        return cached
    }

    private func importReviewedCPR(_ request: PortableSessionRequest) throws {
        let cached = try matchingReview(request.reviewID)
        guard !cached.snapshot.historical, let source = cached.source else {
            throw failure("reviewReadOnly", "A historical import report cannot authorize another import. Inspect a source file first.")
        }
        guard request.sourceSHA256 == cached.snapshot.report.sourceSHA256,
              source.lastPathComponent == cached.snapshot.report.sourceName,
              cached.snapshot.report.interpretationProfile == CPRProject.currentInterpretationProfile else {
            throw failure("reviewSource", "The source identity or interpretation does not match this CPR review. Inspect it again.")
        }
        guard cached.snapshot.report.canImport else {
            throw failure("unsupportedCPR", "No editable project subset has been established for this source.")
        }
        guard request.allowPartial == true else {
            throw failure("partialImportRequired", "Explicitly accept importing only the reviewed supported data.")
        }
        guard project == savedProject || request.discardChanges == true else {
            throw failure("unsavedChanges", "Save or explicitly discard your changes before importing another project.")
        }
        let requested = try requiredURL(request.path)
        guard requested.pathExtension.lowercased() == "rebaseproj" else {
            throw failure("destination", "Choose a new .rebaseproj folder.")
        }
        let destination = try ProjectFileIO.canonicalRoot(requested.deletingLastPathComponent())
            .appendingPathComponent(requested.lastPathComponent)
        // Core binds its actual source read to the reviewed digest and publishes
        // only a new, fully validated directory. No path-only approval is used.
        let imported = try CPRProject.importProject(from: source, to: destination,
            allowPartial: true, expectedSHA256: cached.snapshot.report.sourceSHA256)
        reviewedCPR = nil
        do {
            let snapshot = try PortablePackageSnapshot.capture(in: destination)
            let loaded = try importedSnapshotLoader(destination)
            guard imported.report == cached.snapshot.report, loaded.project == imported.project,
                  loaded.manifest == (try ProjectStore.encodedManifest(imported.project)),
                  try ProjectFileIO.readManifest(in: destination) == loaded.manifest,
                  try CPRProject.compatibilityReport(from: destination) == imported.report,
                  try PortablePackageSnapshot.capture(in: destination) == snapshot else {
                throw failure("importIntegrity", "The published project did not match its reviewed import.")
            }
            project = loaded.project; savedProject = loaded.project; root = destination
            manifestDigest = PortableSHA256.hexDigest(loaded.manifest); isScratch = false
            history.reset(); selection = ProjectSelection().reconciled(in: loaded.project); revision += 1
        } catch {
            throw failure("importPublished", "The import was published, but its final readback failed. The destination may already exist. Reopen it to inspect the result; do not overwrite it or retry the import blindly.")
        }
    }

    private func ruler(_ request: PortableSessionRequest) throws -> PortableSessionReply.Ruler {
        guard let project, let root else { throw failure("noProject", "Open a project first.") }
        guard let scale = request.value, scale.isFinite, MusicalRuler.pixelsPerSecondRange.contains(scale) else {
            throw failure("value", "Ruler scale must be finite and between 4 and 420 pixels per second.")
        }
        let duration = request.duration ?? MusicalRuler.defaultDuration(for: project)
        guard duration.isFinite, (0...MusicalRuler.maximumDuration).contains(duration) else {
            throw failure("duration", "Ruler duration must be finite and between 0 and 86,400 seconds.")
        }
        try checkSourceUnchanged(root)
        return .init(revision: revision, duration: duration, pixelsPerSecond: scale,
            ticks: try MusicalRuler.ticks(project: project, duration: duration, pixelsPerSecond: scale))
    }

    private func waveform(_ request: PortableSessionRequest) throws -> PortableSessionReply.Waveform {
        guard let project, let root else { throw failure("noProject", "Open a project first.") }
        guard let id = request.clipID, let clip = project.tracks.flatMap(\.clips).first(where: { $0.id == id }) else {
            throw failure("selection", "Select an editable audio clip.")
        }
        try checkSourceUnchanged(root)
        let source = try WAVPCMSource(url: ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root))
        let envelope = try WaveformPeaks.read(source: source, offset: clip.sourceOffset, duration: clip.duration)
        return .init(revision: revision, clipID: id, sampleRate: envelope.sampleRate,
            sourceStartFrame: envelope.sourceStartFrame, sourceFrames: envelope.sourceFrames,
            mediaSHA256: source.snapshotSHA256, peaks: envelope.peaks)
    }

    private func execute(_ request: PortableSessionRequest) throws -> PortableSessionReply.Render? {
        if request.command == "state" { return nil }
        if request.command == "importCPR" { try importReviewedCPR(request); return nil }
        if request.command == "newProject" {
            guard project == savedProject || request.discardChanges == true else {
                throw failure("unsavedChanges", "Save or explicitly discard your changes before creating another project.")
            }
            let requested = try requiredURL(request.path)
            let destination = try ProjectFileIO.canonicalRoot(requested.deletingLastPathComponent())
                .appendingPathComponent(requested.lastPathComponent)
            if let root {
                try checkSourceUnchanged(root)
                guard !ProjectFileIO.samePath(destination, root), !ProjectFileIO.contains(destination, in: root) else {
                    throw failure("destination", "Choose a new scratch folder outside the current project.")
                }
            }
            let created = try ProjectStore.createExclusiveSnapshot(at: destination)
            // No fallible I/O remains after publication. The session immediately
            // adopts ownership of this verified scratch package.
            ownedScratch.append(destination)
            project = created.project; savedProject = created.project; self.root = destination; isScratch = true
            manifestDigest = PortableSHA256.hexDigest(created.manifest)
            selection = ProjectSelection(); history.reset(); reviewedCPR = nil; revision += 1
            return nil
        }
        if request.command == "open" {
            guard project == savedProject || request.discardChanges == true else {
                throw failure("unsavedChanges", "Save or explicitly discard your changes before opening another project.")
            }
            let source = try ProjectFileIO.canonicalRoot(projectURL(request.path))
            let originalManifest = try ProjectFileIO.readManifest(in: source)
            let snapshot = request.asCopy == true ? try PortablePackageSnapshot.capture(in: source) : nil
            let loadedSnapshot = try ProjectStore.loadSnapshot(from: source)
            let loaded = loadedSnapshot.project
            guard try ProjectFileIO.readManifest(in: source) == originalManifest,
                  loadedSnapshot.manifest == originalManifest else {
                throw failure("externalChange", "The project changed while it was opening. Reopen it and try again.")
            }
            let destination: URL
            let acceptedProject: Project
            var scratch: URL?
            var accepted = false
            defer { if !accepted, let scratch { try? FileManager.default.removeItem(at: scratch) } }
            if let snapshot {
                let temp = try scratchProjectURL()
                destination = try copyPackage(source, to: temp, snapshot: snapshot)
                scratch = destination
                let copied = try ProjectStore.loadSnapshot(from: destination)
                guard copied.manifest == originalManifest,
                      try ProjectFileIO.readManifest(in: destination) == originalManifest,
                      try PortablePackageSnapshot.capture(in: destination) == snapshot else {
                    throw failure("externalChange", "The copied project changed before it could be opened.")
                }
                acceptedProject = copied.project
            } else { destination = source; acceptedProject = loaded }
            project = acceptedProject; savedProject = acceptedProject; root = destination
            manifestDigest = PortableSHA256.hexDigest(originalManifest); isScratch = request.asCopy == true
            selection = ProjectSelection().reconciled(in: acceptedProject); history.reset(); revision += 1
            reviewedCPR = nil
            if let scratch { ownedScratch.append(scratch) }
            accepted = true
            return nil
        }
        guard let current = project, let root else { throw failure("noProject", "Open a project first.") }
        switch request.command {
        case "importAudio":
            guard let paths = request.paths, (1...ProjectStore.maximumAudioImportFiles).contains(paths.count) else {
                throw failure("audioPaths", "Choose 1–32 audio files to import.")
            }
            guard let position = request.value, position.isFinite, (0...86_400).contains(position) else {
                throw failure("value", "Import audio at a finite position within 24 hours.")
            }
            let grid = try snapGrid(request.snap)
            let sources = try paths.map { try requiredURL($0) }
            try checkSourceUnchanged(root)
            let imported = try ProjectStore.importAudioTracks(from: sources, into: root,
                project: current, position: position, grid: grid, expectedManifestSHA256: manifestDigest)
            history.record(current)
            project = imported.project; selection = imported.selection; revision += 1
        case "selectClip":
            guard let id = request.clipID, current.tracks.contains(where: { $0.clips.contains { $0.id == id } || $0.unresolvedAudioEvents.contains { $0.id == id } }) else {
                throw failure("selection", "The clip does not exist.")
            }
            selection = selection.selectingClip(id, in: current)
        case "selectTrack":
            guard let id = request.trackID, current.tracks.contains(where: { $0.id == id }) else { throw failure("selection", "The track does not exist.") }
            selection = selection.selectingTrack(id, in: current)
        case "undo", "redo":
            let next = request.command == "undo" ? history.undo(current: current) : history.redo(current: current)
            if let next { project = next; selection = selection.reconciled(in: next); revision += 1 }
        case "save":
            guard !isScratch else { throw failure("saveAsRequired", "Choose Save As for this unsaved project.") }
            try checkSourceUnchanged(root)
            _ = try ProjectStore.load(from: root)
            let expectedDigest = PortableSHA256.hexDigest(try ProjectStore.encodedManifest(current))
            try ProjectStore.save(current, to: root)
            // The completed write is a state transition even if a subsequent
            // read fails or another process replaces the manifest immediately.
            manifestDigest = expectedDigest; savedProject = current
            try checkSourceUnchanged(root)
        case "saveAs":
            let requestedDestination = try projectURL(request.path)
            let destination = try ProjectFileIO.canonicalRoot(requestedDestination.deletingLastPathComponent())
                .appendingPathComponent(requestedDestination.lastPathComponent)
            guard destination.pathExtension.lowercased() == "rebaseproj" else { throw failure("destination", "Choose a new .rebaseproj folder.") }
            try checkSourceUnchanged(root)
            let snapshot = try PortablePackageSnapshot.capture(in: root)
            let sourceSnapshot = try ProjectStore.loadSnapshot(from: root)
            guard PortableSHA256.hexDigest(sourceSnapshot.manifest) == manifestDigest else {
                throw failure("externalChange", "The saved project changed while it was being read.")
            }
            try checkSourceUnchanged(root)
            let stage = destination.deletingLastPathComponent().appendingPathComponent(".rebase-save-" + UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: stage) }
            let copiedRoot = try copyPackage(root, to: stage, snapshot: snapshot)
            try ProjectFileIO.requireRealDirectory(copiedRoot)
            guard try ProjectStore.loadSnapshot(from: copiedRoot).manifest == sourceSnapshot.manifest,
                  try PortablePackageSnapshot.capture(in: copiedRoot) == snapshot else {
                throw failure("externalChange", "The copied project changed before it could be saved.")
            }
            let encoded = try ProjectStore.encodedManifest(current)
            let savedSnapshot = try snapshot.replacingManifest(with: encoded)
            try ProjectStore.save(current, to: stage)
            guard try ProjectStore.load(from: stage) == current,
                  try PortablePackageSnapshot.capture(in: stage) == savedSnapshot else {
                throw failure("externalChange", "The saved project changed before publication.")
            }
            let digest = PortableSHA256.hexDigest(encoded)
            try ProjectFileIO.publishNewDirectory(stage, to: destination)
            self.root = destination; manifestDigest = digest; isScratch = false
            savedProject = current; revision += 1
        case "render":
            try checkSourceUnchanged(root)
            _ = try ProjectStore.load(from: root)
            return try render(current, root: root, destination: requiredURL(request.path))
        case "attachSourceMedia":
            try checkSourceUnchanged(root)
            guard let eventID = request.clipID,
                  current.unresolvedAudioEvents.contains(where: { $0.id == eventID }) else {
                throw failure("selection", "Select a preserved source event.")
            }
            let updated = try ProjectStore.attachCPRAudioMedia(from: requiredURL(request.path),
                to: eventID, in: current, at: root)
            history.record(current)
            project = updated; selection = selection.selectingClip(eventID, in: updated); revision += 1
        case "renderSourceEvent":
            try checkSourceUnchanged(root)
            guard let eventID = request.clipID,
                  current.unresolvedAudioEvents.contains(where: { $0.id == eventID }) else {
                throw failure("selection", "Select a preserved source event.")
            }
            guard let mode = CPRSourceEventPlaybackMode(rawValue: request.mode ?? "sourceRate") else {
                throw failure("sourceMode", "Choose a supported source audition mode.")
            }
            return try renderSourceEvent(eventID: eventID, mode: mode, project: current, root: root,
                destination: requiredURL(request.path), startSeconds: request.startSeconds ?? 0,
                rewindAtEnd: request.rewindAtEnd == true)
        default:
            if let edit = try makeEdit(request, project: current, root: root),
               let result = try history.apply(edit, to: current, selection: selection) {
                project = result.project; selection = result.selection; revision += 1
            }
        }
        return nil
    }

    private func snapGrid(_ snap: String?) throws -> GridSnap? {
        switch snap ?? "off" {
        case "off": return nil
        case "quarter": return .quantize(1)
        case "eighth": return .quantize(0.5)
        case "sixteenth": return .quantize(0.25)
        case "bar": return .bar
        default: throw failure("snap", "Unsupported snap grid.")
        }
    }

    private func makeEdit(_ request: PortableSessionRequest, project: Project, root: URL) throws -> ProjectEdit? {
        func value() throws -> Double {
            guard let number = request.value, number.isFinite else { throw failure("value", "A finite edit value is required.") }
            return number
        }
        func clipID() throws -> UUID {
            guard let id = request.clipID, project.tracks.contains(where: { $0.clips.contains { $0.id == id } }) else {
                throw failure("selection", "Select an editable clip.")
            }
            return id
        }
        func trackID() throws -> UUID {
            guard let id = request.trackID, project.tracks.contains(where: { $0.id == id }) else { throw failure("selection", "Select a track.") }
            return id
        }
        func snapped() throws -> Double {
            let grid = try snapGrid(request.snap)
            return try ProjectEditing.snappedTime(max(0, value()), in: project, grid: grid)
        }
        switch request.command {
        case "moveClip": return try .moveClip(clipID(), position: snapped())
        case "trimClip":
            let id = try clipID(), clip = project.tracks.flatMap(\.clips).first { $0.id == id }!
            let source = try WAVPCMSource(url: ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root))
            return try .trimClip(id, end: snapped(), availableSourceDuration: Double(source.frameCount) / source.sampleRate - clip.sourceOffset)
        case "splitClip": return try .splitClip(clipID(), at: snapped(), newClipID: UUID())
        case "deleteEvent":
            guard let id = request.clipID, project.tracks.contains(where: { $0.clips.contains { $0.id == id } || $0.unresolvedAudioEvents.contains { $0.id == id } }) else {
                throw failure("selection", "Select an event.")
            }
            return .deleteEvent(id)
        case "setGain": return try .setGain(trackID(), value())
        case "setPan": return try .setPan(trackID(), value())
        case "toggleMute": return try .toggleMute(trackID())
        case "toggleSolo": return try .toggleSolo(trackID())
        case "upsertAutomationPoint", "removeAutomationPoint", "setAutomationRead":
            let id = try trackID()
            guard let rawParameter = request.parameter,
                  let parameter = AutomationParameter(rawValue: rawParameter) else {
                throw failure("automationParameter", "Choose gainDB or pan automation.")
            }
            let track = project.tracks.first { $0.id == id }!
            let original = track.automation.first { $0.parameter == parameter }
            var lane = original ?? AutomationLane(parameter: parameter)
            switch request.command {
            case "upsertAutomationPoint":
                guard let time = request.time, time.isFinite, (0...86_400).contains(time) else {
                    throw failure("automationTime", "Automation time must be finite and within 0…86,400 seconds.")
                }
                let number = try value()
                guard parameter.valueRange.contains(number) else {
                    throw failure("automationValue", "The automation value is outside this parameter's range.")
                }
                guard let interpolation = AutomationInterpolation(rawValue: request.interpolation ?? "linear") else {
                    throw failure("automationInterpolation", "Choose linear or step interpolation.")
                }
                if let pointID = request.pointID, !lane.points.contains(where: { $0.id == pointID }) {
                    throw failure("selection", "The automation point does not exist in this lane.")
                }
                let previousCount = lane.points.count
                try lane.upsert(AutomationPoint(id: request.pointID ?? UUID(), time: time,
                    value: number, interpolation: interpolation))
                guard lane.points.count <= Self.maximumEditableAutomationPoints || lane.points.count <= previousCount else {
                    throw failure("automationLimit", "This lane cannot grow beyond 4,096 points through session edits. Existing points remain editable.")
                }
            case "removeAutomationPoint":
                guard let pointID = request.pointID, lane.points.contains(where: { $0.id == pointID }) else {
                    throw failure("selection", "The automation point does not exist in this lane.")
                }
                lane.removePoint(id: pointID)
            default:
                guard let enabled = request.enabled else {
                    throw failure("automationRead", "An automation Read state is required.")
                }
                lane.isReadEnabled = enabled
            }
            // Do not replace the other lanes, recreate lane identity, or clear
            // redo history merely because a field was committed unchanged.
            guard lane != original else { return nil }
            return .setAutomation(id, lane)
        case "setTempo":
            guard project.tempoMap.nativeClock == nil else { throw failure("nativeTiming", "This timing map requires an explicit conversion in the Mac application.") }
            var map = project.tempoMap
            map.events[0].bpm = try value()
            return .replaceTempoMap(map)
        default: throw failure("command", "Unknown session command.")
        }
    }

    private func inspectSourceEvent(_ request: PortableSessionRequest) throws -> PortableSessionReply.SourceInspection {
        guard let current = project, let root else { throw failure("noProject", "Open a project first.") }
        try checkSourceUnchanged(root)
        guard let eventID = request.clipID else { throw failure("selection", "Select a preserved source event.") }
        let verified = try ProjectStore.verifiedCPRSourceEvent(eventID, in: current, at: root)
        var modes: [PortableSessionReply.SourceMode] = []
        for mode in CPRSourceEventPlaybackMode.allCases {
            do {
                // Preparation validates the supported source interpretation and
                // media. It does not drain a converter or promise device playback.
                let prepared = try CPRSourceAudition.prepare(eventID: eventID, in: current, at: root, mode: mode)
                let info = prepared.info
                guard info.sourceSHA256 == verified.container.sha256 else {
                    throw failure("externalChange", "The preserved source changed during inspection.")
                }
                let available = info.frameCount > 0
                let liveAvailable = available && info.sampleRate.isFinite && info.sampleRate.rounded() == info.sampleRate
                    && (8_000...192_000).contains(info.sampleRate)
                    && info.frameCount <= Int64(info.sampleRate) * 86_400
                    && (info.sourceTrack?.events.count ?? 1) <= 4096
                    && (info.sourceTrack?.fragments.count ?? 0) <= 16_384
                let snapshotAvailable = available && info.frameCount <= Self.maximumSourceAuditionFrames
                modes.append(.init(mode: mode.rawValue, available: available,
                    reason: available ? nil : "The source contains no playback frames.",
                    liveAvailable: liveAvailable, snapshotExportAvailable: snapshotAvailable,
                    liveReason: liveAvailable ? nil : "The source exceeds the validated live stream admission bounds.",
                    snapshotExportReason: snapshotAvailable ? nil : "This preview exceeds the 32 million frame snapshot export limit.",
                    sampleRate: info.sampleRate, frames: info.frameCount, sourceSampleRate: info.sourceSampleRate,
                    mediaSHA256: info.mediaSHA256, timelineRange: info.timelineRange.map(PortableSourceAuditionManifest.Range.init),
                    savedProjectAudioSetup: info.savedProjectAudioSetup, contributorCount: info.sourceTrack?.events.count ?? 1,
                    fragmentCount: info.sourceTrack?.fragments.count ?? (info.timelineRange == nil ? 0 : 1)))
            } catch {
                modes.append(.init(mode: mode.rawValue, available: false, reason: error.localizedDescription,
                    liveAvailable: false, snapshotExportAvailable: false,
                    liveReason: error.localizedDescription, snapshotExportReason: error.localizedDescription,
                    sampleRate: nil, frames: nil, sourceSampleRate: nil, mediaSHA256: nil, timelineRange: nil,
                    savedProjectAudioSetup: nil, contributorCount: nil, fragmentCount: nil))
            }
        }
        try checkSourceUnchanged(root)
        let after = try ProjectStore.verifiedCPRSourceEvent(eventID, in: current, at: root)
        guard after.container.sha256 == verified.container.sha256 else {
            throw failure("externalChange", "The preserved source changed during inspection.")
        }
        let result = PortableSessionReply.SourceInspection(revision: revision, eventID: eventID,
            sourceSHA256: verified.container.sha256, modes: modes)
        guard try JSONEncoder().encode(result).count <= 131_072 else {
            throw failure("sourceInspectionLimit", "The complete source inspection exceeds the reply limit.")
        }
        return result
    }

    private func sourceOutputURL(_ requested: URL, outside root: URL) throws -> URL {
        let output = requested.standardizedFileURL
        let parent = output.deletingLastPathComponent()
        try ProjectFileIO.requireRealDirectory(parent)
        guard ProjectFileIO.samePath(output, try ProjectFileIO.canonicalRoot(output)),
              !ProjectFileIO.samePath(output, root), !ProjectFileIO.contains(output, in: root),
              (try? FileManager.default.attributesOfItem(atPath: output.path)) == nil else {
            throw failure("destination", "Choose new output files outside the source project; existing files and links are never replaced.")
        }
        return output
    }

    private func readSourceManifestFile(_ url: URL) throws -> Data {
        guard ProjectFileIO.samePath(url, try ProjectFileIO.canonicalRoot(url)),
              try !ProjectFileIO.isLinkOrReparsePoint(url) else {
            throw failure("externalChange", "The source report must remain a regular file.")
        }
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        guard attributes[.type] as? FileAttributeType == .typeRegular,
              let size = (attributes[.size] as? NSNumber)?.intValue,
              (1...Self.maximumSourceAuditionManifestBytes).contains(size) else {
            throw failure("sourceManifestLimit", "The source report exceeds the bounded file contract.")
        }
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        let bytes = try file.read(upToCount: size + 1) ?? Data()
        guard bytes.count == size else { throw failure("externalChange", "The source report changed while being read.") }
        return bytes
    }

    private func revalidateAudition(_ info: CPRSourceEventPlaybackInfo, project: Project, root: URL,
                                    reportBytes: Data) throws {
        try checkSourceUnchanged(root)
        let verified = try ProjectStore.verifiedCPRSourceEvent(info.eventID, in: project, at: root)
        guard verified.container.sha256 == info.sourceSHA256,
              try readSourceManifestFile(root.appendingPathComponent(CPRProject.reportRelativePath)) == reportBytes else {
            throw failure("externalChange", "The source or import report changed during audition preparation.")
        }
        let identities = info.sourceTrack?.events.map { ($0.eventID, $0.mediaSHA256) } ?? [(info.eventID, info.mediaSHA256)]
        for (id, digest) in identities {
            guard let event = project.unresolvedAudioEvents.first(where: { $0.id == id }),
                  let attachment = project.attachedMedia(for: event), attachment.mediaSHA256 == digest else {
                throw failure("externalChange", "An audition contributor no longer has its verified media association.")
            }
            let url = try CPRAudioMediaValidation.attachedURL(attachment.mediaPath, root: root)
            guard PortableSHA256.hexDigest(try CPRAudioMediaValidation.snapshot(url)) == digest else {
                throw failure("externalChange", "An audition contributor's media changed before publication.")
            }
        }
    }

    private func renderSourceEvent(eventID: UUID, mode: CPRSourceEventPlaybackMode, project: Project,
                                   root: URL, destination: URL, startSeconds: Double,
                                   rewindAtEnd: Bool) throws -> PortableSessionReply.Render {
        guard startSeconds.isFinite, startSeconds >= 0 else {
            throw failure("sourceSeek", "Source audition time must be finite and nonnegative.")
        }
        guard ["wav", "wave"].contains(destination.pathExtension.lowercased()) else {
            throw failure("destination", "Choose a new WAV outside the project folder.")
        }
        let output = try sourceOutputURL(destination, outside: root)
        let sidecar = try sourceOutputURL(output.appendingPathExtension("source-audition.json"), outside: root)
        // Resolve returned paths before publishing either output.
        let outputPath = try nativePath(output), sidecarPath = try nativePath(sidecar)
        let reportURL = root.appendingPathComponent(CPRProject.reportRelativePath)
        let reportBytes = try readSourceManifestFile(reportURL)
        guard let report = try CPRProject.compatibilityReport(from: root),
              try readSourceManifestFile(reportURL) == reportBytes else {
            throw failure("externalChange", "The verified import report changed before source preparation.")
        }
        let prepared = try CPRSourceAudition.prepare(eventID: eventID, in: project, at: root, mode: mode)
        let info = prepared.info
        guard info.frameCount > 0, info.frameCount <= Self.maximumSourceAuditionFrames else {
            throw failure("sourceFrameLimit", "This preview exceeds the 32 million frame snapshot limit; streaming is required.")
        }
        guard info.sampleRate.isFinite, let rate = UInt32(exactly: info.sampleRate), rate > 0, rate <= UInt32.max / 8,
              info.mode == mode, info.eventID == eventID,
              prepared.frameCount == info.frameCount, prepared.sampleRate == info.sampleRate else {
            throw failure("sourceRender", "Source audition metadata is inconsistent.")
        }
        let roundedFrame = try prepared.startFrame(at: startSeconds)
        let startFrame: Int64 = rewindAtEnd && roundedFrame == info.frameCount ? 0 : roundedFrame
        let remainingFrames = info.frameCount - startFrame
        // The 58-byte IEEE-float/fact header is the existing authored writer
        // contract. Blocks are already in the shared playback output domain;
        // do not rerun gain, conversion, ring transfer or callback processing.
        func le<T: FixedWidthInteger>(_ value: T) -> Data {
            var little = value.littleEndian; return withUnsafeBytes(of: &little) { Data($0) }
        }
        let pcmBytes = Int(remainingFrames) * 8
        var wave = Data("RIFF".utf8) + le(UInt32(50 + pcmBytes)) + Data("WAVEfmt ".utf8)
        wave += le(UInt32(18)) + le(UInt16(3)) + le(UInt16(2)) + le(rate)
        wave += le(rate * 8) + le(UInt16(8)) + le(UInt16(32)) + le(UInt16(0))
        wave += Data("fact".utf8) + le(UInt32(4)) + le(UInt32(remainingFrames))
        wave += Data("data".utf8) + le(UInt32(pcmBytes))
        wave.reserveCapacity(58 + pcmBytes)
        let cursor = try prepared.cursor(from: startFrame)
        var frames: Int64 = 0
        while let block = try cursor.nextPlaybackBlock() {
            guard block.frameCount > 0, Int64(block.frameCount) <= remainingFrames - frames,
                  block.left.count == block.frameCount, block.right.count == block.frameCount else {
                throw failure("sourceRender", "The source cursor returned an invalid or excessive block.")
            }
            let samples = block.interleaved
            guard samples.count == block.frameCount * 2, samples.allSatisfy(\.isFinite) else {
                throw failure("sourceRender", "The source cursor returned non-finite or incomplete samples.")
            }
            #if _endian(little)
            samples.withUnsafeBytes { wave.append(contentsOf: $0) }
            #else
            for sample in samples { wave += le(sample.bitPattern) }
            #endif
            frames += Int64(block.frameCount)
        }
        guard frames == remainingFrames, wave.count == 58 + pcmBytes else {
            throw failure("sourceRender", "The source cursor ended before its declared output frame count.")
        }
        let outputDigest = PortableSHA256.hexDigest(wave)
        let clockRole: String
        switch mode {
        case .sourceRate: clockRole = "source-rate"
        case .nativeTimelineSourceRate: clockRole = "source-clock-unconverted"
        case .nativeTimelineProjectClock: clockRole = "current-project-clock-unconverted"
        case .nativeTimelineSavedProjectClock, .nativeTrackSavedProjectClock: clockRole = "saved-project-clock-unconverted"
        case .nativeMode0ProjectRate, .nativeMode1ProjectRate, .nativeMode2ProjectRate: clockRole = "current-project-rate-converted"
        }
        let manifest = PortableSourceAuditionManifest(revision: revision, eventID: eventID, name: info.name,
            mode: mode.rawValue, sourceKind: info.sourceTrack == nil ? "event" : "track", clockRole: clockRole,
            projectSampleRate: project.sampleRate, currentNativeClock: project.tempoMap.nativeClock,
            preservedNativeClock: report.nativeClock, projectManifestSHA256: try digestManifest(root),
            currentProjectSHA256: PortableSHA256.hexDigest(try ProjectStore.encodedManifest(project)),
            importReportSHA256: PortableSHA256.hexDigest(reportBytes), sourceSHA256: info.sourceSHA256,
            mediaSHA256: info.mediaSHA256, sampleRate: info.sampleRate, sourceSampleRate: info.sourceSampleRate,
            frames: frames, startFrame: startFrame, totalFrames: info.frameCount,
            timelineRange: info.timelineRange.map(PortableSourceAuditionManifest.Range.init),
            savedProjectAudioSetup: info.savedProjectAudioSetup, sourceTrack: info.sourceTrack.map(PortableSourceAuditionManifest.Track.init),
            wavFileName: output.lastPathComponent, wavBytes: wave.count, wavSHA256: outputDigest)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let proof = try encoder.encode(manifest)
        guard proof.count <= Self.maximumSourceAuditionManifestBytes else {
            throw failure("sourceManifestLimit", "The complete audition provenance exceeds 8 MiB; no contributors were omitted.")
        }
        let parent = output.deletingLastPathComponent()
        let stage = parent.appendingPathComponent(".rebase-source-wave-" + UUID().uuidString)
        let proofStage = parent.appendingPathComponent(".rebase-source-proof-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: stage); try? FileManager.default.removeItem(at: proofStage) }
        try wave.write(to: stage, options: .withoutOverwriting)
        try proof.write(to: proofStage, options: .withoutOverwriting)
        // Re-read exact staged bytes and all contributor media before exposing
        // either file. The output limit is checked before the WAV allocation.
        let stagedAttributes = try FileManager.default.attributesOfItem(atPath: stage.path)
        guard stagedAttributes[.type] as? FileAttributeType == .typeRegular,
              (stagedAttributes[.size] as? NSNumber)?.intValue == wave.count,
              try !ProjectFileIO.isLinkOrReparsePoint(stage) else {
            throw failure("sourceRender", "The staged audition is no longer the completed regular file.")
        }
        let stagedFile = try FileHandle(forReadingFrom: stage)
        let stagedBytes: Data
        do { defer { try? stagedFile.close() }; stagedBytes = try stagedFile.read(upToCount: wave.count + 1) ?? Data() }
        guard stagedBytes == wave, try readSourceManifestFile(proofStage) == proof else {
            throw failure("sourceRender", "The staged audition changed before publication.")
        }
        try revalidateAudition(info, project: project, root: root, reportBytes: reportBytes)
        _ = try sourceOutputURL(output, outside: root)
        _ = try sourceOutputURL(sidecar, outside: root)
        try ProjectFileIO.publishNewFile(proofStage, to: sidecar)
        do {
            try ProjectFileIO.publishNewFile(stage, to: output)
        } catch {
            // Delete only the exact hard link we published. If ownership cannot
            // be proved, preserve the file and report possible publication.
            let staged = try? FileManager.default.attributesOfItem(atPath: proofStage.path)
            let published = try? FileManager.default.attributesOfItem(atPath: sidecar.path)
            if let inode = staged?[.systemFileNumber] as? NSNumber,
               published?[.type] as? FileAttributeType == .typeRegular,
               published?[.systemFileNumber] as? NSNumber == inode,
               (try? ProjectFileIO.isLinkOrReparsePoint(sidecar)) == false {
                try? FileManager.default.removeItem(at: sidecar)
            }
            throw failure("sourcePublicationIncomplete", "The audition could not be published completely. Its provenance file may exist; existing outputs are never replaced.")
        }
        return .init(path: outputPath, revision: revision, sampleRate: info.sampleRate, frames: frames,
            channels: 2, wavBytes: wave.count, sha256: outputDigest, kind: "sourceEvent", eventID: eventID,
            sourceSHA256: info.sourceSHA256, mediaSHA256: info.mediaSHA256, mode: mode.rawValue,
            manifestPath: sidecarPath, manifestSHA256: PortableSHA256.hexDigest(proof), manifestBytes: proof.count,
            startFrame: startFrame, totalFrames: info.frameCount)
    }

    private func requiredURL(_ path: String?) throws -> URL {
        guard let path, !path.isEmpty, !path.contains("\0") else { throw failure("path", "Choose a filesystem path.") }
        return URL(fileURLWithPath: path).standardizedFileURL
    }
    private func nativePath(_ url: URL) throws -> String {
        try url.withUnsafeFileSystemRepresentation { path in
            guard let path else { throw failure("path", "The path cannot be represented on this host.") }
            return String(cString: path)
        }
    }
    private func projectURL(_ path: String?) throws -> URL {
        let url = try requiredURL(path)
        return url.lastPathComponent == ProjectStore.manifestName ? url.deletingLastPathComponent() : url
    }
    private func digestManifest(_ root: URL) throws -> String {
        PortableSHA256.hexDigest(try ProjectFileIO.readManifest(in: root))
    }
    private func checkSourceUnchanged(_ root: URL) throws {
        guard try digestManifest(root) == manifestDigest else { throw failure("externalChange", "The saved project changed outside this session. Reopen it before saving or rendering.") }
    }
    private func copyPackage(_ source: URL, to destination: URL, snapshot: PortablePackageSnapshot) throws -> URL {
        try snapshot.copy(from: source, to: destination)
    }

    private func scratchProjectURL() throws -> URL {
        var parent = FileManager.default.temporaryDirectory
        #if canImport(Darwin)
        // Foundation canonicalization retains the /var system alias in its
        // temporary directory. Use an application-managed runtime cache for
        // internal copies, leaving all user/worker path admission unchanged.
        // These packages remain ownedScratch and are removed on session exit.
        parent = try FileManager.default.url(for: .cachesDirectory, in: .userDomainMask,
            appropriateFor: nil, create: false).appendingPathComponent("Rebase").appendingPathComponent("SessionCopies")
        try Self.prepareScratchDirectories(parent)
        #endif
        return parent.appendingPathComponent("RebaseSession-" + UUID().uuidString + ".rebaseproj")
    }

    static func prepareScratchDirectories(_ parent: URL) throws {
        var directories: [URL] = [], current = parent.standardizedFileURL
        while true {
            directories.append(current)
            guard let next = try PortableSourceStream.parentDirectory(of: current) else { break }
            current = next
        }
        for directory in directories.reversed() {
            if !FileManager.default.fileExists(atPath: directory.path) {
                do { try ProjectFileIO.createNewDirectory(directory) }
                catch {
                    // Another session may create the shared cache directory.
                    // Accept only a freshly rechecked real directory.
                    try ProjectFileIO.requireRealDirectory(directory)
                }
            }
            try ProjectFileIO.requireRealDirectory(directory)
        }
    }

    private func render(_ project: Project, root: URL, destination: URL) throws -> PortableSessionReply.Render {
        guard project.tempoMap.nativeClock == nil, project.unresolvedAudioEvents.isEmpty, project.cprMediaAttachments.isEmpty else {
            throw failure("nativePlayback", "Native CPR playback is not integrated in the Windows session yet.")
        }
        let output = destination.standardizedFileURL
        guard ["wav", "wave"].contains(output.pathExtension.lowercased()),
              !ProjectFileIO.contains(output.resolvingSymlinksInPath(), in: root.resolvingSymlinksInPath()),
              !FileManager.default.fileExists(atPath: output.path) else { throw failure("destination", "Render to a new WAV outside the project folder.") }
        var readers: [String: WAVPCMSource] = [:]
        var totalBytes = 0
        for clip in project.tracks.flatMap(\.clips) {
            if readers[clip.mediaPath] == nil {
                let url = try ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root)
                let bytes = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
                guard bytes > 0, bytes <= WAVPCMSource.maximumBytes - totalBytes else { throw RebaseCoreError.mediaTooLarge }
                totalBytes += bytes
                let reader = try WAVPCMSource(url: url)
                var frame: Int64 = 0
                while frame < reader.frameCount {
                    let count = Int(min(8192, reader.frameCount - frame))
                    _ = try reader.read(from: frame, count: count); frame += Int64(count)
                }
                readers[clip.mediaPath] = reader
            }
            let reader = readers[clip.mediaPath]!
            try PCMRenderer.validateInterval(clip, sampleRate: reader.sampleRate, frameCount: reader.frameCount)
        }
        let prepared = try PCMRenderer.prepare(project) { readers[$0.mediaPath]! }
        guard prepared.frameCount > 0, prepared.frameCount <= PCMRenderer.maximumClipFrames else { throw RebaseCoreError.mediaTooLarge }
        let pcm = try PCMRenderer.mix(prepared.clips, sampleRate: prepared.sampleRate, from: 0, count: Int(prepared.frameCount))
        let bytes = try WAVPCMSource.encode(pcm)
        let stage = output.deletingLastPathComponent().appendingPathComponent(".rebase-session-render-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: stage) }
        try bytes.write(to: stage, options: .withoutOverwriting)
        try ProjectFileIO.publishNewFile(stage, to: output)
        return .init(path: try nativePath(output), revision: revision, sampleRate: pcm.sampleRate,
            frames: prepared.frameCount, channels: pcm.channels.count, wavBytes: bytes.count,
            sha256: PortableSHA256.hexDigest(bytes), kind: "project", eventID: nil,
            sourceSHA256: nil, mediaSHA256: nil)
    }
}
#endif
