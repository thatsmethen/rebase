import Foundation

/// A batch is published as one new media directory. Document/history owners
/// install the returned value only after this transaction has completed.
extension ProjectStore {
    public static let maximumAudioImportFiles = 32
    public static let maximumAudioImportBytes = WAVPCMSource.maximumBytes

    /// Creates a complete new package; even an existing empty destination is
    /// never reused. The existing create API remains available for legacy hosts.
    public static func createExclusive(at requested: URL, name: String = "Untitled") throws -> Project {
        try createExclusiveSnapshot(at: requested, name: name).project
    }

    static func createExclusiveSnapshot(at requested: URL, name: String = "Untitled") throws -> (project: Project, manifest: Data) {
        guard requested.isFileURL, !requested.path.contains("\0"), !requested.absoluteString.lowercased().contains("%00") else {
            throw RebaseCoreError.invalidProject("Choose a local new project folder without NUL characters.")
        }
        let parent = try ProjectFileIO.canonicalRoot(requested.deletingLastPathComponent())
        try ProjectFileIO.requireRealDirectory(parent)
        guard requested.pathExtension.lowercased() == "rebaseproj" else {
            throw RebaseCoreError.invalidProject("Choose a new .rebaseproj folder.")
        }
        let destination = parent.appendingPathComponent(requested.lastPathComponent)
        let stage = parent.appendingPathComponent(".rebase-new-" + UUID().uuidString)
        try ProjectFileIO.createNewDirectory(stage)
        do {
            try ProjectFileIO.createNewDirectory(stage.appendingPathComponent("Media"))
            let project = Project(name: name)
            try save(project, to: stage)
            let snapshot = try loadSnapshot(from: stage)
            guard snapshot.project == project, snapshot.manifest == (try encodedManifest(project)) else { throw importChanged() }
            try ProjectFileIO.publishNewDirectory(stage, to: destination)
            return snapshot
        } catch {
            try cleanImportStage(stage, originalError: error)
            throw error
        }
    }

    public static func importAudioTracks(from sources: [URL], into root: URL,
                                         project: Project, position: Double,
                                         grid: GridSnap? = nil, expectedManifestSHA256: String? = nil) throws -> ProjectEditResult {
        try importAudioTracks(from: sources, into: root, project: project,
                              position: position, grid: grid, expectedManifestSHA256: expectedManifestSHA256, beforePublication: {})
    }

    // The hook is internal and supplies deterministic change/failure controls;
    // production callers use the public transaction above.
    static func importAudioTracks(from sources: [URL], into requestedRoot: URL,
                                  project: Project, position: Double, grid: GridSnap?,
                                  expectedManifestSHA256: String? = nil,
                                  publish: (URL, URL) throws -> Void = { try ProjectFileIO.publishNewDirectory($0, to: $1) },
                                  beforePublication: () throws -> Void) throws -> ProjectEditResult {
        guard (1...maximumAudioImportFiles).contains(sources.count),
              position.isFinite, (0...86_400).contains(position) else {
            throw RebaseCoreError.invalidProject("Import 1–32 audio files at a finite position within 24 hours.")
        }
        let position = try ProjectEditing.snappedTime(position, in: project, grid: grid)
        try project.validate()
        let root = try ProjectFileIO.canonicalRoot(requestedRoot)
        try ProjectFileIO.requireRealDirectory(root)
        let baseline = try PortablePackageSnapshot.capture(in: root)
        // Validate both the saved model and any unsaved media/provenance before
        // extending the document. No manifest is written by an audio import.
        let saved = try loadSnapshot(from: root)
        if let expectedManifestSHA256, cprSHA256(saved.manifest) != expectedManifestSHA256 { throw importChanged() }
        try validateNativeClockProvenance(project, at: root)
        try validateCPRAudioMedia(project, at: root)
        for clip in project.tracks.flatMap(\.clips) {
            let facts = try ProjectStoreMedia.scan(url: resolveMediaURL(clip.mediaPath, projectRoot: root), name: clip.name)
            try PCMRenderer.validateInterval(clip, sampleRate: facts.sampleRate, frameCount: facts.frameCount)
        }
        let media = root.appendingPathComponent("Media")
        let createdMedia = !FileManager.default.fileExists(atPath: media.path)
        let baselineBytes = baseline.entries.reduce(0) { $0 + $1.size }
        guard baseline.entries.count + sources.count + 1 + (createdMedia ? 1 : 0) <= PortablePackageSnapshot.maximumEntries else {
            throw RebaseCoreError.invalidProject("The imported project would exceed the 10,000-entry package bound.")
        }
        if createdMedia { try ProjectFileIO.createNewDirectory(media) }
        let batch = "Import-" + UUID().uuidString
        let stageName = ".rebase-import-" + UUID().uuidString
        let stage = media.appendingPathComponent(stageName)
        var ownsStage = false
        do {
            try ProjectFileIO.requireRealDirectory(media)
            try ProjectFileIO.createNewDirectory(stage); ownsStage = true
            var candidate = project
            var imported: [(source: URL, digest: String, file: String)] = []
            var totalBytes = 0
            var waveformIDs: [UUID] = []
            var selected = ProjectSelection()
            for source in sources {
                // A complete bounded snapshot, not a path-only promise. The
                // original is never opened for writing or moved into a project.
                let bytes = try CPRAudioMediaValidation.snapshot(source)
                guard bytes.count <= maximumAudioImportBytes - totalBytes else { throw RebaseCoreError.mediaTooLarge }
                totalBytes += bytes.count
                guard totalBytes <= PortablePackageSnapshot.maximumBytes - baselineBytes else { throw RebaseCoreError.mediaTooLarge }
                let suffix = source.pathExtension.lowercased().filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
                let filename = UUID().uuidString + (suffix.isEmpty ? "" : "." + String(suffix.prefix(12)))
                let copy = stage.appendingPathComponent(filename)
                try bytes.write(to: copy, options: .withoutOverwriting)
                let digest = cprSHA256(bytes)
                let facts = try ProjectStoreMedia.inspectImport(url: copy, name: source.lastPathComponent)
                guard try cprSHA256(CPRAudioMediaValidation.snapshot(copy)) == digest else { throw importChanged() }
                let name = source.deletingPathExtension().lastPathComponent
                let clip = Clip(mediaPath: "Media/" + batch + "/" + filename, name: name,
                                position: position, sourceOffset: 0, duration: Double(facts.frameCount) / facts.sampleRate)
                let track = Track(name: name, clips: [clip])
                candidate.tracks.append(track)
                selected = ProjectSelection(trackID: track.id, clipID: clip.id)
                waveformIDs.append(clip.id)
                imported.append((source, digest, filename))
            }
            try candidate.validate()
            _ = try encodedManifest(candidate)
            try beforePublication()
            for item in imported {
                guard try cprSHA256(CPRAudioMediaValidation.snapshot(item.source)) == item.digest,
                      try cprSHA256(CPRAudioMediaValidation.snapshot(stage.appendingPathComponent(item.file))) == item.digest else {
                    throw importChanged()
                }
            }
            let staged = try PortablePackageSnapshot.capture(in: stage)
            guard staged.entries.count == imported.count,
                  Set(staged.entries.map { $0.components }) == Set(imported.map { [$0.file] }),
                  staged.entries.allSatisfy({ !$0.isDirectory }) else { throw importChanged() }
            let after = try PortablePackageSnapshot.capture(in: root)
            let priorEntries = after.entries.filter {
                !$0.components.starts(with: ["Media", stageName]) && !(createdMedia && $0.components == ["Media"])
            }
            guard priorEntries == baseline.entries else { throw importChanged() }
            try ProjectFileIO.requireRealDirectory(media)
            // One exclusive rename publishes all files together. Every throwing
            // validation precedes it; installing the returned model is in-memory.
            try publish(stage, media.appendingPathComponent(batch))
            return ProjectEditResult(project: candidate, selection: selected, waveformClipIDs: waveformIDs)
        } catch {
            if ownsStage { try cleanImportStage(stage, originalError: error) }
            if createdMedia {
                // Remove only the empty directory we created. Never recursively
                // remove another actor's newly added content during rollback.
                do {
                    try ProjectFileIO.requireRealDirectory(media)
                    guard try FileManager.default.contentsOfDirectory(atPath: media.path).isEmpty else { throw importChanged() }
                    try FileManager.default.removeItem(at: media)
                } catch let cleanup {
                    throw RebaseCoreError.invalidProject("Audio import failed: \(error.localizedDescription) Cleanup also failed: \(cleanup.localizedDescription)")
                }
            }
            throw error
        }
    }

    private static func cleanImportStage(_ stage: URL, originalError: Error) throws {
        do {
            try ProjectFileIO.requireRealDirectory(stage)
            try FileManager.default.removeItem(at: stage)
        } catch {
            throw RebaseCoreError.invalidProject("Audio transaction failed: \(originalError.localizedDescription) Staging cleanup also failed: \(error.localizedDescription)")
        }
    }
    private static func importChanged() -> RebaseCoreError {
        .invalidProject("The project or selected audio changed during import. No document edit was applied.")
    }
}
