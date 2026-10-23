#if REBASE_PORTABLE
import Foundation

/// Portable file decoding is an application adapter. It establishes matching
/// stored PCM metadata and finite samples, not original-source media identity.
enum CPRAudioMediaDecoder {
    static func read(_ url: URL, reference: CPRAudioFileReference) throws -> CPRAudioMediaFacts {
        let data = try CPRAudioMediaValidation.snapshot(url)
        let file = try WAVPCMSource(data: data)
        try CPRAudioMediaValidation.validateFormat(frames: file.frameCount, rate: file.sampleRate,
            channels: file.channelCount, bits: file.storedBitsPerSample,
            frameSize: file.storedBytesPerFrame, reference: reference)
        var position: Int64 = 0
        while position < file.frameCount {
            let count = Int(min(8192, file.frameCount - position))
            _ = try file.read(from: position, count: count)
            position += Int64(count)
        }
        return CPRAudioMediaFacts(sha256: cprSHA256(data), frameCount: file.frameCount,
            sampleRate: file.sampleRate, channels: file.channelCount,
            bitsPerSample: file.storedBitsPerSample, bytesPerFrame: file.storedBytesPerFrame)
    }
}
#endif
