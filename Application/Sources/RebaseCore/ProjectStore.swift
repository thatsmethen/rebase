import Foundation

public struct ImportedAudio: Equatable {
    public let mediaPath: String
    public let name: String
    public let duration: TimeInterval
    public let sampleRate: Double
    public let channelCount: Int
}

public enum ProjectStore {
    public static let manifestName = "Project.json"

    public static func create(at root: URL, name: String = "Untitled") throws -> Project {
        let manager = FileManager.default
        let root = try ProjectFileIO.canonicalRoot(root)
        let manifest = try ProjectFileIO.manifestURL(in: root)
        guard !manager.fileExists(atPath: manifest.path) else {
            throw RebaseCoreError.invalidProject("A project already exists in this folder.")
        }
        try manager.createDirectory(at: root.appendingPathComponent("Media"), withIntermediateDirectories: true)
        let project = Project(name: name)
        try save(project, to: root)
        return project
    }

    public static func load(from root: URL) throws -> Project {
        try loadSnapshot(from: root).project
    }

    /// Binds the validated model to the exact manifest bytes that produced it.
    /// Legacy decoding may assign fresh identities to omitted default maps.
    static func loadSnapshot(from root: URL) throws -> (project: Project, manifest: Data) {
        let root = try ProjectFileIO.canonicalRoot(root)
        let data = try ProjectFileIO.readManifest(in: root)
        let project = try JSONDecoder().decode(Project.self, from: data)
        try project.validate()
        try validateNativeClockProvenance(project, at: root)
        try validateCPRAudioMedia(project, at: root)
        var checkedMedia: [URL: (sampleRate: Double, frameCount: Int64)] = [:]
        for clip in project.tracks.flatMap(\.clips) {
            let url = try resolveMediaURL(clip.mediaPath, projectRoot: root)
            if checkedMedia[url] == nil {
                checkedMedia[url] = try ProjectStoreMedia.scan(url: url, name: clip.name)
            }
            let bounds = checkedMedia[url]!
            // Cache media decoding, never clip validity: several clips can use
            // the same asset with different source intervals.
            try PCMRenderer.validateInterval(clip, sampleRate: bounds.sampleRate,
                                              frameCount: bounds.frameCount)
        }
        return (project, data)
    }

    public static func save(_ project: Project, to root: URL) throws {
        let root = try ProjectFileIO.canonicalRoot(root)
        try project.validate()
        try validateNativeClockProvenance(project, at: root)
        try validateCPRAudioMedia(project, at: root)
        for clip in project.tracks.flatMap(\.clips) {
            _ = try resolveMediaURL(clip.mediaPath, projectRoot: root)
        }
        let data = try encodedManifest(project)
        _ = try ProjectFileIO.manifestURL(in: root)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try ProjectFileIO.writeManifest(data, in: root)
    }

    /// The exact saved representation; validation and filesystem publication
    /// remain the responsibility of save(_:to:).
    static func encodedManifest(_ project: Project) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(project)
        guard data.count <= ProjectFileIO.maximumManifestBytes else {
            throw RebaseCoreError.invalidProject("Project manifests must be at most 8 MiB.")
        }
        return data
    }

    static func validateNativeClockProvenance(_ project: Project, at root: URL) throws {
        guard project.tempoMap.nativeClock != nil || !project.unresolvedAudioEvents.isEmpty else { return }
        guard let report = try CPRProject.compatibilityReport(from: root) else {
            throw RebaseCoreError.invalidProject("Native timing and audio events require their verified preserved CPR source and import report.")
        }
        if let clock = project.tempoMap.nativeClock, report.nativeClock != clock {
            throw RebaseCoreError.invalidProject("The active native clock does not match a verified preserved CPR import. Use an explicitly converted application timing map or restore the original import evidence.")
        }
        // Deletion is an explicit edit; retained source events must remain exact
        // and on their original imported track. A saved report alone is not proof:
        // compatibilityReport has already replayed the frozen source profile.
        for track in project.tracks where !track.unresolvedAudioEvents.isEmpty {
            guard let baseline = report.recoveredProject?.tracks.first(where: { $0.id == track.id }),
                  track.unresolvedAudioEvents.allSatisfy({ baseline.unresolvedAudioEvents.contains($0) }) else {
                throw RebaseCoreError.invalidProject("A preserved CPR audio event no longer matches its source interpretation or original track.")
            }
        }
    }

    /// Replays the frozen import before interpreting additional saved fields.
    /// New source inspection never changes a historical report or playable Clip.
    static func verifiedCPRSourceEvent(_ eventID: UUID, in project: Project, at root: URL) throws
        -> (container: CPRContainer, retained: UnresolvedCPRAudioEvent, source: CPRSourceAudioEvent) {
        try project.validate()
        try validateNativeClockProvenance(project, at: root)
        guard let retained = project.unresolvedAudioEvents.first(where: { $0.id == eventID }) else {
            throw RebaseCoreError.invalidProject("Select a retained CPR audio event.")
        }
        let container = try CPRProject.readSource(root.appendingPathComponent(CPRProject.originalRelativePath))
        guard container.sha256 == retained.sourceSHA256,
              let source = try CPRAudioEventArchive.read(container: container).first(where: { $0.event == retained.event }),
              source.clip == retained.clip, source.cluster.object == retained.cluster else {
            throw RebaseCoreError.invalidProject("The source event no longer matches its preserved CPR identity.")
        }
        return (container, retained, source)
    }

    public static func resolveMediaURL(_ path: String, projectRoot: URL) throws -> URL {
        let parts = path.split(separator: "/", omittingEmptySubsequences: false)
        guard parts.count >= 2, parts.first == "Media",
              !parts.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }),
              !path.contains("\\"), !path.contains(":"), !path.contains("\0") else {
            throw RebaseCoreError.invalidMediaPath(path)
        }
        let root = try ProjectFileIO.canonicalRoot(projectRoot)
        let media = root.appendingPathComponent("Media").standardizedFileURL
        // A project Media directory must itself remain within the project.
        guard ProjectFileIO.samePath(media.resolvingSymlinksInPath(), media) else {
            throw RebaseCoreError.invalidMediaPath(path)
        }
        let result = root.appendingPathComponent(path).standardizedFileURL.resolvingSymlinksInPath()
        guard ProjectFileIO.contains(result, in: media),
              (try? result.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else {
            throw RebaseCoreError.invalidMediaPath(path)
        }
        return result
    }
}
