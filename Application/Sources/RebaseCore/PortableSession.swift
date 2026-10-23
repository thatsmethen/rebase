import Foundation
#if REBASE_PORTABLE

/// Versioned local-process protocol. This is not a network service.
public struct PortableSessionRequest: Codable {
    public var protocolVersion: Int
    public var id: UInt64
    public var command: String
    public var expectedRevision: UInt64?
    public var path: String?
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
    enum CodingKeys: String, CodingKey {
        case protocolVersion = "protocol"
        case id, command, expectedRevision, path, clipID, trackID, value, duration, snap, discardChanges, asCopy
        case reviewID, sourceSHA256, allowPartial, reviewOffset
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
    public let error: Failure?
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
    }
    public struct Failure: Encodable { public let code: String; public let message: String }
    enum CodingKeys: String, CodingKey { case protocolVersion = "protocol"; case id, ok, state, render, waveform, ruler, cprReview, error }
}

/// Serialized document owner for a native host. The host sends intents; all
/// edits, validation, undo, timing and mixing use the same application sources.
public final class PortableSession {
    public static let maximumRequestBytes = 65_536
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
    private let importedSnapshotLoader: (URL) throws -> (project: Project, manifest: Data)
    public init() { importedSnapshotLoader = { try ProjectStore.loadSnapshot(from: $0) } }
    // A readback dependency permits deterministic verification of the
    // publication-success/readback-failure boundary without filesystem races.
    init(importedSnapshotLoader: @escaping (URL) throws -> (project: Project, manifest: Data)) {
        self.importedSnapshotLoader = importedSnapshotLoader
    }
    deinit { for url in ownedScratch { try? FileManager.default.removeItem(at: url) } }

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
            if request.command == "waveform" {
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
                error: .init(code: (error as? SessionError)?.code ?? (error as? PortableCPRReviewError)?.code ?? "operationFailed", message: error.localizedDescription))
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
                let temp = FileManager.default.temporaryDirectory.appendingPathComponent("RebaseSession-" + UUID().uuidString + ".rebaseproj")
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
            guard !isScratch else { throw failure("saveAsRequired", "Choose Save As for this example copy.") }
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
            let destination = try requiredURL(request.path)
            let rendered = try CPRSourceEventRenderer.renderAudition(eventID: eventID, in: current,
                at: root, to: destination)
            let size = try destination.resourceValues(forKeys: [.fileSizeKey]).fileSize
            guard let size, size > 0 else { throw failure("render", "The source preview has no file data.") }
            return .init(path: try nativePath(destination), revision: revision,
                sampleRate: Double(rendered.sampleRate), frames: Int64(rendered.frameCount),
                channels: rendered.channelCount, wavBytes: size, sha256: rendered.outputSHA256,
                kind: "sourceEvent", eventID: eventID, sourceSHA256: rendered.sourceSHA256,
                mediaSHA256: rendered.mediaSHA256)
        default:
            let edit = try makeEdit(request, project: current, root: root)
            if let result = try history.apply(edit, to: current, selection: selection) {
                project = result.project; selection = result.selection; revision += 1
            }
        }
        return nil
    }

    private func makeEdit(_ request: PortableSessionRequest, project: Project, root: URL) throws -> ProjectEdit {
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
            let grid: GridSnap?
            switch request.snap ?? "off" {
            case "off": grid = nil
            case "quarter": grid = .quantize(1)
            case "eighth": grid = .quantize(0.5)
            case "sixteenth": grid = .quantize(0.25)
            case "bar": grid = .bar
            default: throw failure("snap", "Unsupported snap grid.")
            }
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
        case "setTempo":
            guard project.tempoMap.nativeClock == nil else { throw failure("nativeTiming", "This timing map requires an explicit conversion in the Mac application.") }
            var map = project.tempoMap
            map.events[0].bpm = try value()
            return .replaceTempoMap(map)
        default: throw failure("command", "Unknown session command.")
        }
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
