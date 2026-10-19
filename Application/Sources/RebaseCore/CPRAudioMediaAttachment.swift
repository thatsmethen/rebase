import Foundation
import AVFoundation
import CryptoKit

/// An explicit user-selected association, separate from the frozen CPR import
/// baseline. Matching format and a checksum identify the selected local asset;
/// they do not prove it is the missing original or establish native processing.
public struct CPRAudioMediaAttachment: Codable, Equatable, Identifiable {
    public let id: UUID
    public let association: String
    public let sourceSHA256: String
    public let sourceFileIdentity: Int
    public let mediaPath: String
    public let mediaSHA256: String
    public let selectedFilename: String
    public let frameCount: Int64
    public let sampleRate: Double
    public let channels: Int
    public let bitsPerSample: Int
    public let bytesPerFrame: Int

    func matches(_ file: CPRAudioFileReference, sourceSHA256: String) -> Bool {
        self.sourceSHA256 == sourceSHA256 && sourceFileIdentity == file.object.identityOffset
    }

    func validate(reference: CPRAudioFileReference) throws {
        guard association == "user-selected", sourceFileIdentity == reference.object.identityOffset,
              mediaSHA256.count == 64, mediaSHA256.allSatisfy({ $0.isHexDigit && !$0.isUppercase }),
              frameCount > 0, UInt64(frameCount) == reference.frameCount,
              sampleRate.isFinite, sampleRate == reference.sampleRate,
              channels == Int(reference.channels), bitsPerSample == Int(reference.sampleSize),
              bytesPerFrame == Int(reference.frameSize) else {
            throw RebaseCoreError.invalidProject("The attached audio metadata does not match its preserved CPR media reference.")
        }
    }
}

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
