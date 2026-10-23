import Foundation

extension ProjectStore {
    /// Copies an explicitly selected matching asset. It remains separate from
    /// the frozen source event and does not authorize native playback.
    public static func attachCPRAudioMedia(from source: URL, to eventID: UUID,
                                           in project: Project, at root: URL) throws -> Project {
        let root = try ProjectFileIO.canonicalRoot(root)
        try ProjectFileIO.requireRealDirectory(root)
        try project.validate()
        try validateNativeClockProvenance(project, at: root)
        guard let event = project.unresolvedAudioEvents.first(where: { $0.id == eventID }),
              event.files.count == 1, event.segments.count == 1,
              let reference = event.files.first, let segment = event.segments.first,
              segment.streamIdentity == reference.object.identityOffset,
              let start = Int64(exactly: segment.storedStart), let length = Int(exactly: segment.storedLength) else {
            throw RebaseCoreError.unsupportedAudio("Media attachment currently requires one source file and one segment on a recovered audio event.")
        }
        let source = try ProjectFileIO.canonicalRoot(source)
        let facts = try CPRAudioMediaValidation.read(source, reference: reference)
        // Bounds use the recovered interval arithmetic only. Format comparison
        // here is an attachment policy, not proof of native accessor selection.
        _ = try CPRSegmentReadPlan.project(segment: segment, clusterPosition: start,
            requestedFrames: length, sourceFrameCount: facts.frameCount, frameSize: facts.bytesPerFrame)
        let media = root.standardizedFileURL.resolvingSymlinksInPath().appendingPathComponent("Media")
        if !FileManager.default.fileExists(atPath: media.path) { try ProjectFileIO.createNewDirectory(media) }
        try ProjectFileIO.requireRealDirectory(root)
        try ProjectFileIO.requireRealDirectory(media)
        let suffix = source.pathExtension.lowercased().filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
        let filename = UUID().uuidString + (suffix.isEmpty ? "" : "." + String(suffix.prefix(12)))
        let destination = media.appendingPathComponent(filename)
        var accepted = false
        defer { if !accepted { try? FileManager.default.removeItem(at: destination) } }
        try FileManager.default.copyItem(at: source, to: destination)
        try ProjectFileIO.requireRealDirectory(media)
        let copied = try CPRAudioMediaValidation.read(destination, reference: reference)
        guard copied.sha256 == facts.sha256 else {
            throw RebaseCoreError.invalidProject("The selected media changed while it was being copied.")
        }
        let attachment = CPRAudioMediaAttachment(id: UUID(), association: "user-selected",
            sourceSHA256: event.sourceSHA256, sourceFileIdentity: reference.object.identityOffset,
            mediaPath: "Media/" + filename, mediaSHA256: copied.sha256, selectedFilename: source.lastPathComponent,
            frameCount: copied.frameCount, sampleRate: copied.sampleRate, channels: copied.channels,
            bitsPerSample: copied.bitsPerSample, bytesPerFrame: copied.bytesPerFrame)
        var result = project
        result.cprMediaAttachments.removeAll { $0.matches(reference, sourceSHA256: event.sourceSHA256) }
        result.cprMediaAttachments.append(attachment)
        try result.validate()
        try validateNativeClockProvenance(result, at: root)
        try validateCPRAudioMedia(result, at: root)
        accepted = true
        return result
    }

    static func validateCPRAudioMedia(_ project: Project, at root: URL) throws {
        for attachment in project.cprMediaAttachments {
            guard let event = project.unresolvedAudioEvents.first(where: { event in
                event.files.contains { attachment.matches($0, sourceSHA256: event.sourceSHA256) }
            }), let reference = event.files.first(where: { $0.object.identityOffset == attachment.sourceFileIdentity }) else {
                throw RebaseCoreError.invalidProject("The attached media has no preserved CPR reference.")
            }
            let url = try CPRAudioMediaValidation.attachedURL(attachment.mediaPath, root: root)
            let actual = try CPRAudioMediaValidation.read(url, reference: reference)
            guard actual.sha256 == attachment.mediaSHA256 else {
                throw RebaseCoreError.invalidProject("The attached CPR media changed. Attach the intended file again to establish a new association.")
            }
            for linked in project.unresolvedAudioEvents where linked.files.contains(where: {
                attachment.matches($0, sourceSHA256: linked.sourceSHA256)
            }) {
                guard linked.files.count == 1, linked.segments.count == 1, let segment = linked.segments.first,
                      segment.streamIdentity == reference.object.identityOffset,
                      let start = Int64(exactly: segment.storedStart), let length = Int(exactly: segment.storedLength) else {
                    throw RebaseCoreError.unsupportedAudio("Attached CPR media requires a supported single-segment source relationship.")
                }
                _ = try CPRSegmentReadPlan.project(segment: segment, clusterPosition: start,
                    requestedFrames: length, sourceFrameCount: actual.frameCount, frameSize: actual.bytesPerFrame)
            }
        }
    }

}
