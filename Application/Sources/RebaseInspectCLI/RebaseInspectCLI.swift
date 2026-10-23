import Foundation
import RebasePortable
#if os(Windows)
import WinSDK
#elseif canImport(Darwin)
import Darwin
#else
import Glibc
#endif

/// Bounded inspection and application-mix conformance. This executable does not
/// implement project persistence, native CPR playback, or device transport.
@main
struct RebaseInspectCLI {
    static func main() {
        do { try run() }
        catch {
            FileHandle.standardError.write(Data(("rebase-inspect: " + error.localizedDescription + "\n").utf8))
            #if os(Windows)
            ExitProcess(1)
            #else
            exit(1)
            #endif
        }
    }

    private static func run() throws {
        let arguments = Array(CommandLine.arguments.dropFirst())
        guard (arguments.count == 2 && ["project", "cpr"].contains(arguments[0])) ||
                (arguments.count == 3 && arguments[0] == "render") else {
            throw InspectionError.usage
        }
        let source = URL(fileURLWithPath: arguments[1])
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let output: Data
        if arguments[0] == "cpr" {
            output = try encoder.encode(CPRProject.inspect(from: source))
        } else {
            let root = (source.lastPathComponent == "Project.json" ? source.deletingLastPathComponent() : source)
                .standardizedFileURL.resolvingSymlinksInPath()
            let manifest = root.appendingPathComponent("Project.json")
            let file = try FileHandle(forReadingFrom: manifest)
            defer { try? file.close() }
            let limit = 8_388_608
            let data = try file.read(upToCount: limit + 1) ?? Data()
            guard data.count <= limit else { throw InspectionError.oversized }
            let project = try JSONDecoder().decode(Project.self, from: data)
            try project.validate()
            if arguments[0] == "render" {
                output = try render(project, root: root, destination: URL(fileURLWithPath: arguments[2]), encoder: encoder)
            } else {
                output = try encoder.encode(ProjectSummary(name: project.name, tracks: project.tracks.count,
                    clips: project.tracks.reduce(0) { $0 + $1.clips.count }, sampleRate: project.sampleRate,
                    duration: project.duration, unresolvedEvents: project.unresolvedAudioEvents.count,
                    validation: "Project model only; media files and preserved CPR provenance were not validated."))
            }
        }
        FileHandle.standardOutput.write(output + Data([10]))
    }

    private static func render(_ project: Project, root: URL, destination: URL, encoder: JSONEncoder) throws -> Data {
        guard project.tempoMap.nativeClock == nil, project.cprMediaAttachments.isEmpty,
              project.unresolvedAudioEvents.isEmpty else { throw InspectionError.nativeProject }
        let output = destination.standardizedFileURL.resolvingSymlinksInPath()
        guard ["wav", "wave"].contains(output.pathExtension.lowercased()),
              !isWithin(output, root: root), !FileManager.default.fileExists(atPath: output.path) else {
            throw InspectionError.destination
        }
        // Every declared clip is checked, including muted clips. This remains
        // an authored WAV-only path, without a substitute provenance store.
        var sources: [String: WAVPCMSource] = [:]
        var totalBytes = 0
        for clip in project.tracks.flatMap(\.clips) {
            if sources[clip.mediaPath] == nil {
                let parts = clip.mediaPath.split(separator: "/", omittingEmptySubsequences: false)
                guard parts.count >= 2, parts.first == "Media", !parts.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }),
                      !clip.mediaPath.contains("\\"), !clip.mediaPath.contains(":"), !clip.mediaPath.contains("\0") else {
                    throw RebaseCoreError.invalidMediaPath(clip.mediaPath)
                }
                let url = root.appendingPathComponent(clip.mediaPath).standardizedFileURL
                guard url.resolvingSymlinksInPath() == url, isWithin(url, root: root.appendingPathComponent("Media")) else {
                    throw RebaseCoreError.invalidMediaPath(clip.mediaPath)
                }
                let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
                guard size > 0, size <= WAVPCMSource.maximumBytes - totalBytes else { throw RebaseCoreError.mediaTooLarge }
                totalBytes += size
                let reader = try WAVPCMSource(url: url)
                // Scan all samples in bounded chunks so hidden nonfinite values
                // cannot become accepted media merely because a clip omits them.
                var position: Int64 = 0
                while position < reader.frameCount {
                    let count = Int(min(8192, reader.frameCount - position))
                    _ = try reader.read(from: position, count: count)
                    position += Int64(count)
                }
                sources[clip.mediaPath] = reader
            }
            let reader = sources[clip.mediaPath]!
            try PCMRenderer.validateInterval(clip, sampleRate: reader.sampleRate, frameCount: reader.frameCount)
        }
        let prepared = try PCMRenderer.prepare(project) { clip in
            guard let reader = sources[clip.mediaPath] else { throw RebaseCoreError.invalidMediaPath(clip.mediaPath) }
            return reader
        }
        guard prepared.frameCount > 0, prepared.frameCount <= PCMRenderer.maximumClipFrames else {
            throw RebaseCoreError.mediaTooLarge
        }
        let pcm = try PCMRenderer.mix(prepared.clips, sampleRate: prepared.sampleRate, from: 0, count: Int(prepared.frameCount))
        let bytes = try WAVPCMSource.encode(pcm)
        let manager = FileManager.default
        let staging = output.deletingLastPathComponent().appendingPathComponent(".rebase-render-" + UUID().uuidString + ".tmp")
        defer { try? manager.removeItem(at: staging) }
        try bytes.write(to: staging, options: .withoutOverwriting)
        // The completed file is published in one no-overwrite operation. A
        // concurrent creator wins safely, and write failures expose no WAV.
        // Filesystems without hard-link support fail instead of weakening this.
        #if os(Windows)
        // Foundation 6.4.1 linkItem creates a symbolic link on Windows. Calling
        // the native hard-link API keeps output valid after staging is removed.
        let sourcePath = try windowsPath(staging)
        let destinationPath = try windowsPath(output)
        let error: DWORD = destinationPath.withUnsafeBufferPointer { destination in
            sourcePath.withUnsafeBufferPointer { source in
                CreateHardLinkW(destination.baseAddress, source.baseAddress, nil) ? 0 : GetLastError()
            }
        }
        guard error == 0 else { throw InspectionError.publication(error) }
        #else
        try manager.linkItem(at: staging, to: output)
        #endif
        do {
            let values = try output.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard values.isRegularFile == true, values.isSymbolicLink == false, values.fileSize == bytes.count else {
                throw InspectionError.publicationVerification
            }
            let file = try FileHandle(forReadingFrom: output)
            defer { try? file.close() }
            guard try file.seekToEnd() == UInt64(bytes.count) else { throw InspectionError.publicationVerification }
        } catch {
            // Publication succeeded above, so this link belongs to this run.
            // A failed no-overwrite call never enters this cleanup path.
            try? manager.removeItem(at: output)
            throw error
        }
        return try encoder.encode(RenderSummary(name: project.name, frames: pcm.frameCount, channels: pcm.channels.count,
            sampleRate: pcm.sampleRate, wavBytes: bytes.count,
            sampleWordFingerprint: fingerprint(pcm), peak: pcm.channels.flatMap { $0 }.reduce(Float(0)) { max($0, abs($1)) },
            validation: "Shared application mixer over checked WAV sources. No device playback or native CPR compatibility is claimed."))
    }

    #if os(Windows)
    private static func windowsPath(_ url: URL) throws -> [WCHAR] {
        // Foundation's public filesystem conversion handles RFC8089 drive
        // prefixes and UNC separators before encoding the Win32 UTF-16 path.
        try url.withUnsafeFileSystemRepresentation { representation in
            guard let representation else { throw InspectionError.destination }
            var path = String(cString: representation)
            if !path.hasPrefix("\\\\?\\") {
                if path.hasPrefix("\\\\") { path = "\\\\?\\UNC\\" + path.dropFirst(2) }
                else { path = "\\\\?\\" + path }
            }
            return Array(path.utf16) + [0]
        }
    }
    #endif

    private static func isWithin(_ url: URL, root: URL) -> Bool {
        #if os(Windows)
        let candidate = url.pathComponents.map { $0.lowercased() }, base = root.pathComponents.map { $0.lowercased() }
        #else
        let candidate = url.pathComponents, base = root.pathComponents
        #endif
        return candidate.starts(with: base)
    }

    /// FNV-1a over interleaved little-endian Float32 words is a conformance
    /// fingerprint only. Release integrity still uses external SHA-256.
    private static func fingerprint(_ pcm: PCMBuffer) -> String {
        var hash: UInt64 = 0xcbf29ce484222325
        for frame in 0..<pcm.frameCount {
            for channel in pcm.channels {
                let word = channel[frame].bitPattern
                for shift: UInt32 in [0, 8, 16, 24] {
                    hash = (hash ^ UInt64(UInt8(truncatingIfNeeded: word >> shift))) &* 0x100000001b3
                }
            }
        }
        return String(hash, radix: 16)
    }

    private struct RenderSummary: Encodable {
        let name: String
        let frames: Int
        let channels: Int
        let sampleRate: Double
        let wavBytes: Int
        let sampleWordFingerprint: String
        let peak: Float
        let validation: String
    }

    private struct ProjectSummary: Encodable {
        let name: String
        let tracks: Int
        let clips: Int
        let sampleRate: Double
        let duration: Double
        let unresolvedEvents: Int
        let validation: String
    }

    private enum InspectionError: Error, LocalizedError {
        case usage, oversized, nativeProject, destination
        case publication(UInt32)
        case publicationVerification
        var errorDescription: String? {
            switch self {
            case .usage: "Usage: rebase-inspect project PROJECT.rebaseproj | cpr SOURCE.cpr | render PROJECT.rebaseproj OUTPUT.wav"
            case .oversized: "Project inspection accepts manifests up to 8 MiB."
            case .nativeProject: "Portable rendering accepts authored projects only; native clocks, CPR events and media associations require the original provenance store."
            case .destination: "Choose a new .wav file outside the source project package. Existing files are never replaced."
            case .publication(let code): "The completed WAV could not be published (Windows error \(code))."
            case .publicationVerification: "The published WAV did not pass its file and size checks."
            }
        }
    }
}
