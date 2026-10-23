import Foundation

struct CPRAudioMediaFacts {
    let sha256: String
    let frameCount: Int64
    let sampleRate: Double
    let channels: Int
    let bitsPerSample: Int
    let bytesPerFrame: Int
}

enum CPRAudioMediaValidation {
    static let maximumBytes = 268_435_456
    static let maximumFrames: Int64 = 16_000_000

    static func read(_ url: URL, reference: CPRAudioFileReference) throws -> CPRAudioMediaFacts {
        try CPRAudioMediaDecoder.read(url, reference: reference)
    }

    static func validateFormat(frames: Int64, rate: Double, channels: Int, bits: Int,
                               frameSize: Int, reference: CPRAudioFileReference) throws {
        guard frames > 0, frames <= maximumFrames, UInt64(frames) == reference.frameCount,
              rate.isFinite, (8_000...192_000).contains(rate), rate == reference.sampleRate,
              (1...2).contains(channels), channels == Int(reference.channels),
              bits == Int(reference.sampleSize), frameSize == Int(reference.frameSize) else {
            throw RebaseCoreError.unsupportedAudio("The selected file must match the CPR reference: \(reference.frameCount) frames, \(reference.sampleRate) Hz, \(reference.channels) channels, \(reference.sampleSize)-bit PCM and \(reference.frameSize) bytes per frame. Attachment currently supports up to 16 million frames.")
        }
    }

    static func regularAttributes(_ url: URL) throws -> [FileAttributeKey: Any] {
        guard ProjectFileIO.samePath(url.standardizedFileURL, try ProjectFileIO.canonicalRoot(url)),
              try !ProjectFileIO.isLinkOrReparsePoint(url) else {
            throw RebaseCoreError.invalidProject("The attached media path was redirected during validation.")
        }
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        guard attributes[.type] as? FileAttributeType == .typeRegular,
              let size = (attributes[.size] as? NSNumber)?.intValue,
              size > 0, size <= maximumBytes else {
            throw RebaseCoreError.unsupportedAudio("Attach a regular PCM audio file of at most 256 MiB.")
        }
        return attributes
    }

    /// Bounded bytes and before/after path and identity checks shared by
    /// attachment validation and the exact PCM24 renderer.
    static func snapshot(_ url: URL) throws -> Data {
        let before = try regularAttributes(url)
        let size = (before[.size] as! NSNumber).intValue
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var data = Data()
        while data.count <= size {
            guard let chunk = try handle.read(upToCount: min(1_048_576, size + 1 - data.count)),
                  !chunk.isEmpty else { break }
            data.append(chunk)
        }
        let after = try regularAttributes(url)
        guard data.count == size, (after[.size] as? NSNumber)?.intValue == size,
              before[.systemFileNumber] as? NSNumber == after[.systemFileNumber] as? NSNumber,
              before[.modificationDate] as? Date == after[.modificationDate] as? Date else {
            throw RebaseCoreError.invalidProject("The attached media changed during validation.")
        }
        return data
    }

    static func attachedURL(_ path: String, root: URL) throws -> URL {
        let root = try ProjectFileIO.canonicalRoot(root)
        let resolved = try ProjectStore.resolveMediaURL(path, projectRoot: root)
        let expected = root.appendingPathComponent(path).standardizedFileURL
        guard ProjectFileIO.samePath(expected, resolved) else { throw RebaseCoreError.invalidMediaPath(path) }
        var current = root
        for part in path.split(separator: "/") {
            current.appendPathComponent(String(part))
            guard try !ProjectFileIO.isLinkOrReparsePoint(current) else { throw RebaseCoreError.invalidMediaPath(path) }
        }
        return resolved
    }
}
