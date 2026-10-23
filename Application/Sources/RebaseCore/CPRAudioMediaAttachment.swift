import Foundation
import AVFoundation
import CryptoKit

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
        let manager = FileManager.default
        let before = try manager.attributesOfItem(atPath: url.path)
        guard before[.type] as? FileAttributeType == .typeRegular,
              let size = (before[.size] as? NSNumber)?.intValue,
              size > 0, size <= maximumBytes else {
            throw RebaseCoreError.unsupportedAudio("Attach a regular PCM audio file of at most 256 MiB.")
        }
        let file = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
        let format = file.fileFormat.streamDescription.pointee
        guard format.mFormatID == kAudioFormatLinearPCM,
              file.length > 0, file.length <= maximumFrames,
              UInt64(file.length) == reference.frameCount,
              format.mSampleRate.isFinite, (8_000...192_000).contains(format.mSampleRate),
              format.mSampleRate == reference.sampleRate,
              (1...2).contains(format.mChannelsPerFrame), Int(format.mChannelsPerFrame) == Int(reference.channels),
              Int(format.mBitsPerChannel) == Int(reference.sampleSize),
              Int(format.mBytesPerFrame) == Int(reference.frameSize) else {
            throw RebaseCoreError.unsupportedAudio("The selected file must match the CPR reference: \(reference.frameCount) frames, \(reference.sampleRate) Hz, \(reference.channels) channels, \(reference.sampleSize)-bit PCM and \(reference.frameSize) bytes per frame. Attachment currently supports up to 16 million frames.")
        }
        let decoded = try AudioSampleValidation.scan(url: url, name: url.lastPathComponent)
        guard decoded.frameCount == file.length, decoded.sampleRate == format.mSampleRate else {
            throw RebaseCoreError.unsupportedAudio("The decoded media format differs from its stored PCM format.")
        }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hash = SHA256(), count = 0
        while let bytes = try handle.read(upToCount: 1_048_576), !bytes.isEmpty {
            count += bytes.count
            guard count <= maximumBytes else { throw RebaseCoreError.mediaTooLarge }
            hash.update(data: bytes)
        }
        let after = try manager.attributesOfItem(atPath: url.path)
        guard count == size, (after[.size] as? NSNumber)?.intValue == size,
              before[.systemFileNumber] as? NSNumber == after[.systemFileNumber] as? NSNumber,
              before[.modificationDate] as? Date == after[.modificationDate] as? Date else {
            throw RebaseCoreError.invalidProject("The attached media changed during validation.")
        }
        return CPRAudioMediaFacts(sha256: hash.finalize().map { String(format: "%02x", $0) }.joined(),
            frameCount: file.length, sampleRate: format.mSampleRate, channels: Int(format.mChannelsPerFrame),
            bitsPerSample: Int(format.mBitsPerChannel), bytesPerFrame: Int(format.mBytesPerFrame))
    }
}
