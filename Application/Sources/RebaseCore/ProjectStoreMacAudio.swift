#if !REBASE_PORTABLE
import Foundation
import AVFoundation

extension ProjectStore {
    /// Copies an explicitly selected matching asset. It remains separate from
    /// the frozen source event and does not authorize native playback.
    public static func attachCPRAudioMedia(from source: URL, to eventID: UUID,
                                           in project: Project, at root: URL) throws -> Project {
        try project.validate()
        try validateNativeClockProvenance(project, at: root)
        guard let event = project.unresolvedAudioEvents.first(where: { $0.id == eventID }),
              event.files.count == 1, event.segments.count == 1,
              let reference = event.files.first, let segment = event.segments.first,
              segment.streamIdentity == reference.object.identityOffset,
              let start = Int64(exactly: segment.storedStart), let length = Int(exactly: segment.storedLength) else {
            throw RebaseCoreError.unsupportedAudio("Media attachment currently requires one source file and one segment on a recovered audio event.")
        }
        let source = source.resolvingSymlinksInPath()
        let facts = try CPRAudioMediaValidation.read(source, reference: reference)
        // Bounds use the recovered interval arithmetic only. Format comparison
        // here is an attachment policy, not proof of native accessor selection.
        _ = try CPRSegmentReadPlan.project(segment: segment, clusterPosition: start,
            requestedFrames: length, sourceFrameCount: facts.frameCount, frameSize: facts.bytesPerFrame)
        let media = root.standardizedFileURL.resolvingSymlinksInPath().appendingPathComponent("Media")
        try FileManager.default.createDirectory(at: media, withIntermediateDirectories: true)
        guard media.resolvingSymlinksInPath() == media else { throw RebaseCoreError.invalidMediaPath("Media") }
        let suffix = source.pathExtension.lowercased().filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
        let filename = UUID().uuidString + (suffix.isEmpty ? "" : "." + String(suffix.prefix(12)))
        let destination = media.appendingPathComponent(filename)
        var accepted = false
        defer { if !accepted { try? FileManager.default.removeItem(at: destination) } }
        try FileManager.default.copyItem(at: source, to: destination)
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
            let url = try resolveMediaURL(attachment.mediaPath, projectRoot: root)
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

    public static func importAudio(from source: URL, into root: URL) throws -> ImportedAudio {
        let source = source.resolvingSymlinksInPath()
        guard (try? source.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else {
            throw RebaseCoreError.unsupportedAudio("Choose a regular audio file.")
        }
        let audio = try AVAudioFile(forReading: source, commonFormat: .pcmFormatFloat32, interleaved: false)
        let format = audio.processingFormat
        guard (1...2).contains(format.channelCount), format.sampleRate > 0, audio.length > 0 else {
            throw RebaseCoreError.unsupportedAudio("Import supports nonempty mono or stereo audio files.")
        }
        let media = root.standardizedFileURL.resolvingSymlinksInPath().appendingPathComponent("Media")
        try FileManager.default.createDirectory(at: media, withIntermediateDirectories: true)
        guard media.resolvingSymlinksInPath().path == media.path else {
            throw RebaseCoreError.invalidMediaPath("Media")
        }
        let suffix = source.pathExtension.lowercased().filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
        let filename = UUID().uuidString + (suffix.isEmpty ? "" : "." + String(suffix.prefix(12)))
        let destination = media.appendingPathComponent(filename)
        try FileManager.default.copyItem(at: source, to: destination)
        do {
            try AudioSampleValidation.scan(url: destination, name: source.lastPathComponent)
        } catch {
            try? FileManager.default.removeItem(at: destination)
            throw error
        }
        return ImportedAudio(mediaPath: "Media/" + filename, name: source.deletingPathExtension().lastPathComponent,
                             duration: Double(audio.length) / format.sampleRate,
                             sampleRate: format.sampleRate, channelCount: Int(format.channelCount))
    }
}

enum ProjectStoreMedia {
    static func scan(url: URL, name: String) throws -> (sampleRate: Double, frameCount: Int64) {
        try AudioSampleValidation.scan(url: url, name: name)
    }
}
#endif
