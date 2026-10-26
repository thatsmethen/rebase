#if !REBASE_PORTABLE
import Foundation
import AVFoundation

extension ProjectStore {
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
    static func inspectImport(url: URL, name: String) throws -> (sampleRate: Double, frameCount: Int64, channelCount: Int) {
        let file = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
        let format = file.processingFormat
        guard (1...2).contains(format.channelCount), format.sampleRate.isFinite,
              (8_000...192_000).contains(format.sampleRate),
              file.length > 0, file.length <= PCMRenderer.maximumClipFrames else {
            throw RebaseCoreError.unsupportedAudio("Import supports mono/stereo audio at 8–192 kHz with 1–16 million frames per file.")
        }
        let facts = try AudioSampleValidation.scan(url: url, name: name)
        guard facts.sampleRate == format.sampleRate, facts.frameCount == file.length else {
            throw RebaseCoreError.unsupportedAudio("The decoded audio changed while importing.")
        }
        return (facts.sampleRate, facts.frameCount, Int(format.channelCount))
    }
    static func scan(url: URL, name: String) throws -> (sampleRate: Double, frameCount: Int64) {
        try AudioSampleValidation.scan(url: url, name: name)
    }
}
#endif
