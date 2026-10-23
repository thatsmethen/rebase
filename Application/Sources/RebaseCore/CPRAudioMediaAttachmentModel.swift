import Foundation

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

