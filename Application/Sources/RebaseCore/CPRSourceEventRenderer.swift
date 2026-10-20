import Foundation
import RebaseTimingDSP

public struct CPRSourceEventRenderResult: Equatable {
    public let frameCount: Int
    public let sampleRate: UInt32
    public let channelCount: Int
    public let sourceSHA256: String
    public let mediaSHA256: String
    public let outputSHA256: String
}

/// A verified, immutable source snapshot shared by export and event audition.
/// Samples are interleaved at the saved source rate; no mixer policy is applied.
struct CPRPreparedSourceEvent {
    let plan: CPRSourceEventRenderPlan
    let samples: [Float]
    let sourceSHA256: String
    let mediaSHA256: String
}

/// Research reconstruction of a single saved event, from explicitly attached
/// media. No track effects, mixer, automation, runtime pitch context or project
/// transport is restored. This never promotes an unresolved event to a Clip.
public enum CPRSourceEventRenderer {
    public static func render(eventID: UUID, in project: Project, at root: URL, to destination: URL) throws
        -> CPRSourceEventRenderResult {
        let output = destination.standardizedFileURL.resolvingSymlinksInPath()
        let package = root.standardizedFileURL.resolvingSymlinksInPath()
        guard output != package, !output.path.hasPrefix(package.path + "/") else {
            throw RebaseCoreError.invalidProject("Save the rendered event outside its source project package.")
        }
        let prepared = try prepare(eventID: eventID, in: project, at: root)
        let plan = prepared.plan
        let wave = encodeWave(prepared.samples, plan: plan)
        // Entire input, output and all checks complete before atomic publication.
        try wave.write(to: output, options: .atomic)
        return CPRSourceEventRenderResult(frameCount: plan.frames, sampleRate: plan.rate, channelCount: plan.channels,
            sourceSHA256: prepared.sourceSHA256, mediaSHA256: prepared.mediaSHA256, outputSHA256: cprSHA256(wave))
    }

    static func prepare(eventID: UUID, in project: Project, at root: URL) throws -> CPRPreparedSourceEvent {
        let verified = try ProjectStore.verifiedCPRSourceEvent(eventID, in: project, at: root)
        let fades = try CPRAutoFadeArchive.read(container: verified.container)
        let plan = try CPRSourceEventRenderPlan.make(source: verified.source, retained: verified.retained, fades: fades)
        guard let attachment = project.attachedMedia(for: verified.retained) else {
            throw RebaseCoreError.unsupportedAudio("Attach matching PCM24 WAV media before using this source event.")
        }
        try attachment.validate(reference: plan.file)
        let sourceURL = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: root)
        let before = try FileManager.default.attributesOfItem(atPath: sourceURL.path)
        guard let size = (before[.size] as? NSNumber)?.intValue, size <= CPRAudioMediaValidation.maximumBytes else {
            throw RebaseCoreError.mediaTooLarge
        }
        let handle = try FileHandle(forReadingFrom: sourceURL)
        defer { try? handle.close() }
        let data = try handle.read(upToCount: CPRAudioMediaValidation.maximumBytes + 1) ?? Data()
        let after = try FileManager.default.attributesOfItem(atPath: sourceURL.path)
        guard data.count == size, cprSHA256(data) == attachment.mediaSHA256,
              before[.systemFileNumber] as? NSNumber == after[.systemFileNumber] as? NSNumber,
              before[.modificationDate] as? Date == after[.modificationDate] as? Date else {
            throw RebaseCoreError.invalidProject("The attached media changed. Attach the intended file again before using this source event.")
        }
        return CPRPreparedSourceEvent(plan: plan, samples: try decodePCM24(data, plan: plan),
            sourceSHA256: verified.container.sha256, mediaSHA256: attachment.mediaSHA256)
    }

    static func renderPCM24Wave(_ data: Data, plan: CPRSourceEventRenderPlan) throws -> Data {
        encodeWave(try decodePCM24(data, plan: plan), plan: plan)
    }

    private static func decodePCM24(_ data: Data, plan: CPRSourceEventRenderPlan) throws -> [Float] {
        func invalid() -> RebaseCoreError { .unsupportedAudio("Source rendering supports bounded little-endian PCM24 WAV files matching the saved rate, channels and exact frame count.") }
        func u16(_ offset: Int) -> UInt16 { UInt16(data[offset]) | UInt16(data[offset+1]) << 8 }
        func u32(_ offset: Int) -> UInt32 { UInt32(data[offset]) | UInt32(data[offset+1]) << 8 | UInt32(data[offset+2]) << 16 | UInt32(data[offset+3]) << 24 }
        guard data.count >= 12, data.count <= CPRAudioMediaValidation.maximumBytes,
              data.prefix(4) == Data("RIFF".utf8), u32(4) == data.count - 8,
              data.subdata(in: 8..<12) == Data("WAVE".utf8),
              plan.frames > 0, plan.frames <= 16_000_000, (1...2).contains(plan.channels) else { throw invalid() }
        var position = 12, format: Range<Int>?, samples: Range<Int>?, chunkCount = 0
        while position < data.count {
            guard data.count-position >= 8, chunkCount < 10_000 else { throw invalid() }
            let tag = data.subdata(in: position..<(position+4)), count = Int(u32(position+4)), start = position+8
            guard count <= data.count-start, (count & 1) <= data.count-start-count else { throw invalid() }
            let range = start..<(start+count)
            if tag == Data("fmt ".utf8) {
                guard format == nil else { throw invalid() }; format = range
            } else if tag == Data("data".utf8) {
                guard samples == nil else { throw invalid() }; samples = range
            }
            position = range.upperBound + (count & 1); chunkCount += 1
        }
        guard let format, [16,18].contains(format.count), let samples else { throw invalid() }
        let f = format.lowerBound
        guard u16(f) == 1, u16(f+2) == plan.channels, u32(f+4) == plan.rate,
              u32(f+8) == plan.rate * UInt32(plan.channels * 3), u16(f+12) == plan.channels * 3,
              u16(f+14) == 24, format.count == 16 || u16(f+16) == 0,
              samples.count == plan.frames * plan.channels * 3 else { throw invalid() }
        let count = plan.frames * plan.channels
        var values = [Float](repeating: 0, count: count)
        let status = data.withUnsafeBytes { input in
            values.withUnsafeMutableBufferPointer { output in
                rb_cpr_event_pcm24_f32(input.baseAddress!.advanced(by: samples.lowerBound).assumingMemoryBound(to: UInt8.self),
                    output.baseAddress!, count, plan.gain.bitPattern)
            }
        }
        guard status == 0 else {
            throw RebaseCoreError.unsupportedAudio("Source rendering requires round-to-nearest mode and a gain that keeps PCM24 samples in the normal Float32 range.")
        }
        return values
    }

    private static func encodeWave(_ values: [Float], plan: CPRSourceEventRenderPlan) -> Data {
        func le<T: FixedWidthInteger>(_ value: T) -> Data {
            var little = value.littleEndian
            return withUnsafeBytes(of: &little) { Data($0) }
        }
        let byteCount = values.count * 4
        // IEEE-float WAVEFORMATEX with fact sample count. File structure is our
        // explicit writer contract, not a reconstruction of Reference metadata.
        var wave = Data("RIFF".utf8) + le(UInt32(50 + byteCount)) + Data("WAVEfmt ".utf8)
        wave += le(UInt32(18)) + le(UInt16(3)) + le(UInt16(plan.channels)) + le(plan.rate)
        wave += le(plan.rate * UInt32(plan.channels * 4)) + le(UInt16(plan.channels * 4)) + le(UInt16(32)) + le(UInt16(0))
        wave += Data("fact".utf8) + le(UInt32(4)) + le(UInt32(plan.frames))
        wave += Data("data".utf8) + le(UInt32(byteCount))
        #if _endian(little)
        values.withUnsafeBytes { wave.append(contentsOf: $0) }
        #else
        for value in values { wave += le(value.bitPattern) }
        #endif
        return wave
    }
}
