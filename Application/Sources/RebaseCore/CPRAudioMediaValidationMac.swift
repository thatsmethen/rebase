#if !REBASE_PORTABLE
import Foundation
import AVFoundation
import CryptoKit

enum CPRAudioMediaDecoder {
    static func read(_ url: URL, reference: CPRAudioFileReference) throws -> CPRAudioMediaFacts {
        let before = try CPRAudioMediaValidation.regularAttributes(url)
        let file = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
        let format = file.fileFormat.streamDescription.pointee
        guard format.mFormatID == kAudioFormatLinearPCM else {
            throw RebaseCoreError.unsupportedAudio("The selected file must store linear PCM audio.")
        }
        try CPRAudioMediaValidation.validateFormat(frames: file.length, rate: format.mSampleRate,
            channels: Int(format.mChannelsPerFrame), bits: Int(format.mBitsPerChannel),
            frameSize: Int(format.mBytesPerFrame), reference: reference)
        let decoded = try AudioSampleValidation.scan(url: url, name: url.lastPathComponent)
        guard decoded.frameCount == file.length, decoded.sampleRate == format.mSampleRate else {
            throw RebaseCoreError.unsupportedAudio("The decoded media format differs from its stored PCM format.")
        }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let size = (before[.size] as! NSNumber).intValue
        var hash = SHA256(), count = 0
        while let bytes = try handle.read(upToCount: 1_048_576), !bytes.isEmpty {
            count += bytes.count
            guard count <= CPRAudioMediaValidation.maximumBytes else { throw RebaseCoreError.mediaTooLarge }
            hash.update(data: bytes)
        }
        let after = try CPRAudioMediaValidation.regularAttributes(url)
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
#endif
