import Foundation
import AVFoundation
import RebaseAmbiDSP

public enum AmbisonicDirection: Sendable {
    case fumaToAmbix
    case ambixToFuma
    fileprivate var parameter: Double { self == .fumaToAmbix ? 0 : 1 }
}

public struct AmbisonicFileInfo: Sendable {
    public let channels: Int
    public let precision: Int
    public let sampleRate: Double
    public let frames: Int64
}

public enum AmbisonicConversionError: LocalizedError {
    case message(String)
    public var errorDescription: String? {
        switch self { case .message(let text): return text }
    }
}

/// Standalone file conversion. Track buses and live insert routing are separate.
public enum AmbisonicFileConverter {
    public static func inspect(source: URL) throws -> AmbisonicFileInfo {
        let file = try AVAudioFile(forReading: source)
        let stored = file.fileFormat.streamDescription.pointee
        let precision = stored.mFormatID == kAudioFormatLinearPCM &&
            stored.mFormatFlags & kAudioFormatFlagIsFloat != 0 && stored.mBitsPerChannel == 64 ? 64 : 32
        let channels = Int(file.processingFormat.channelCount)
        guard [4, 9, 16].contains(channels), file.length > 0 else {
            throw AmbisonicConversionError.message("Choose a nonempty audio file with 4, 9, or 16 stored channels.")
        }
        let rate = file.processingFormat.sampleRate
        guard rate.isFinite, rate > 0, rate.rounded(.towardZero) == rate,
              rate <= Double(UInt32.max) / Double(channels * (precision / 8)) else {
            throw AmbisonicConversionError.message("The source sample rate cannot be represented exactly in this WAV format.")
        }
        try validateOutputSize(frames: file.length, channels: channels, precision: precision)
        return AmbisonicFileInfo(channels: channels, precision: precision,
                                 sampleRate: file.processingFormat.sampleRate, frames: file.length)
    }

    // Conservative RIFF budget reserves 4096 bytes for headers (currently 56).
    // Division avoids overflowing when inspecting a very long source file.
    static func validateOutputSize(frames: Int64, channels: Int, precision: Int) throws {
        guard frames > 0, [4, 9, 16].contains(channels), [32, 64].contains(precision),
              frames <= (Int64(UInt32.max) - 4097) / Int64(channels * (precision / 8)) else {
            throw AmbisonicConversionError.message("This conversion exceeds the supported WAV file size. Choose a shorter source.")
        }
    }

    @discardableResult
    public static func convert(source: URL, destination: URL, direction: AmbisonicDirection) throws -> AmbisonicFileInfo {
        let fm = FileManager.default
        let sourcePath = source.standardizedFileURL.resolvingSymlinksInPath()
        let outputPath = destination.standardizedFileURL.resolvingSymlinksInPath()
        var isDirectory: ObjCBool = false
        let exists = fm.fileExists(atPath: destination.path, isDirectory: &isDirectory)
        let aliasesSource = try exists && sameFile(sourcePath, outputPath)
        guard sourcePath != outputPath, !aliasesSource else {
            throw AmbisonicConversionError.message("Choose an output file different from the source, including its links.")
        }
        guard !isDirectory.boolValue else {
            throw AmbisonicConversionError.message("The output path is a folder. Choose a WAV file.")
        }
        let info = try inspect(source: source)
        let temporary = destination.deletingLastPathComponent().appendingPathComponent(".rebase-\(UUID().uuidString).wav")
        defer { try? fm.removeItem(at: temporary) }
        // This helper returns only after its output file has closed.
        try writeConverted(source: source, temporary: temporary, direction: direction, info: info)
        if exists { _ = try fm.replaceItemAt(destination, withItemAt: temporary) }
        else { try fm.moveItem(at: temporary, to: destination) }
        return info
    }

    private static func sameFile(_ lhs: URL, _ rhs: URL) throws -> Bool {
        let a = try FileManager.default.attributesOfItem(atPath: lhs.path)
        let b = try FileManager.default.attributesOfItem(atPath: rhs.path)
        return (a[.systemNumber] as? NSNumber) == (b[.systemNumber] as? NSNumber) &&
            (a[.systemFileNumber] as? NSNumber) == (b[.systemFileNumber] as? NSNumber)
    }

    private static func writeConverted(source: URL, temporary: URL, direction: AmbisonicDirection,
                                       info: AmbisonicFileInfo) throws {
        let common: AVAudioCommonFormat = info.precision == 64 ? .pcmFormatFloat64 : .pcmFormatFloat32
        let input = try AVAudioFile(forReading: source, commonFormat: common, interleaved: false)
        guard input.length == info.frames, Int(input.processingFormat.channelCount) == info.channels,
              input.processingFormat.sampleRate == info.sampleRate else {
            throw AmbisonicConversionError.message("The source format changed while opening it.")
        }
        let capacity: AVAudioFrameCount = 8192
        guard let inBuffer = AVAudioPCMBuffer(pcmFormat: input.processingFormat, frameCapacity: capacity),
              let outBuffer = AVAudioPCMBuffer(pcmFormat: input.processingFormat, frameCapacity: capacity) else {
            throw AmbisonicConversionError.message("Unable to allocate conversion buffers.")
        }
        let processor = try AmbisonicProcessor(channels: info.channels, precision: info.precision, maximumFrames: Int(capacity))
        guard FileManager.default.createFile(atPath: temporary.path, contents: nil) else {
            throw AmbisonicConversionError.message("Unable to create the converted file.")
        }
        let output = try FileHandle(forWritingTo: temporary)
        defer { try? output.close() }
        // AVAudioFile's WAV encoder narrowed tested binary64 output to binary32.
        // Emit IEEE-float RIFF explicitly so both sample precision and channel
        // order are retained, without assigning speaker labels to the channels.
        let header = waveHeader(info)
        try output.write(contentsOf: header)
        var written: Int64 = 0
        while written < info.frames {
            let wanted = AVAudioFrameCount(min(Int64(capacity), info.frames - written))
            try input.read(into: inBuffer, frameCount: wanted)
            guard inBuffer.frameLength > 0, inBuffer.frameLength <= wanted else {
                throw AmbisonicConversionError.message("The source ended before all declared frames could be read.")
            }
            // File decoding supplies actual samples, with no host silence flags.
            _ = try processor.process(input: inBuffer, output: outBuffer, direction: direction)
            try output.write(contentsOf: interleavedBytes(outBuffer, precision: info.precision))
            written += Int64(inBuffer.frameLength)
        }
        let expectedBytes = UInt64(header.count) + UInt64(info.frames) * UInt64(info.channels * (info.precision / 8))
        guard written == info.frames, try output.offset() == expectedBytes else {
            throw AmbisonicConversionError.message("The converted file has an unexpected frame count.")
        }
        try output.synchronize()
        try output.close()
    }

    private static func waveHeader(_ info: AmbisonicFileInfo) -> Data {
        let frameBytes = info.channels * (info.precision / 8)
        let payloadBytes = UInt32(info.frames * Int64(frameBytes))
        var data = Data("RIFF".utf8)
        func append<T: FixedWidthInteger>(_ value: T) {
            var little = value.littleEndian
            withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
        }
        append(payloadBytes + 48)
        data.append(Data("WAVEfmt ".utf8))
        append(UInt32(16)); append(UInt16(3)); append(UInt16(info.channels))
        append(UInt32(info.sampleRate)); append(UInt32(info.sampleRate) * UInt32(frameBytes))
        append(UInt16(frameBytes)); append(UInt16(info.precision))
        data.append(Data("fact".utf8)); append(UInt32(4)); append(UInt32(info.frames))
        data.append(Data("data".utf8)); append(payloadBytes)
        return data
    }

    private static func interleavedBytes(_ buffer: AVAudioPCMBuffer, precision: Int) -> Data {
        let planes = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: buffer.audioBufferList))
        let frames = Int(buffer.frameLength), width = precision / 8
        var data = Data(count: frames * planes.count * width)
        data.withUnsafeMutableBytes { output in
            for channel in planes.indices {
                let input = UnsafeRawPointer(planes[channel].mData!)
                for frame in 0..<frames {
                    let offset = (frame * planes.count + channel) * width
                    if precision == 64 {
                        let bits = input.load(fromByteOffset: frame * width, as: UInt64.self).littleEndian
                        output.storeBytes(of: bits, toByteOffset: offset, as: UInt64.self)
                    } else {
                        let bits = input.load(fromByteOffset: frame * width, as: UInt32.self).littleEndian
                        output.storeBytes(of: bits, toByteOffset: offset, as: UInt32.self)
                    }
                }
            }
        }
        return data
    }
}

/// Owns prepared scratch storage. A processor instance is used serially.
/// Internal so tests exercise the exact buffer bridge used by file conversion.
final class AmbisonicProcessor {
    private var state = ambip_state()
    private let scratch: UnsafeMutableRawPointer
    private let channels: Int
    private let precision: Int
    private let maximumFrames: Int

    init(channels: Int, precision: Int, maximumFrames: Int) throws {
        guard [4, 9, 16].contains(channels), [32, 64].contains(precision),
              maximumFrames > 0, maximumFrames <= Int(Int32.max) else {
            throw AmbisonicConversionError.message("Unsupported converter configuration.")
        }
        self.channels = channels
        self.precision = precision
        self.maximumFrames = maximumFrames
        let bytes = channels * maximumFrames * (precision / 8)
        scratch = .allocate(byteCount: bytes, alignment: 8)
        let status = ambip_init(&state, UInt32(channels), UInt32(precision), maximumFrames, scratch, bytes)
        guard status == 0 else {
            scratch.deallocate()
            throw AmbisonicConversionError.message("Unable to prepare the converter (status \(status)).")
        }
    }

    deinit { scratch.deallocate() }

    @discardableResult
    func process(input: AVAudioPCMBuffer, output: AVAudioPCMBuffer, direction: AmbisonicDirection,
                 bypass: Bool = false, silenceFlags: UInt64 = 0) throws -> ambip_report {
        let common: AVAudioCommonFormat = precision == 64 ? .pcmFormatFloat64 : .pcmFormatFloat32
        guard input.format.commonFormat == common, output.format.commonFormat == common,
              !input.format.isInterleaved, !output.format.isInterleaved,
              Int(input.format.channelCount) == channels, Int(output.format.channelCount) == channels,
              Int(input.frameLength) <= maximumFrames, output.frameCapacity >= input.frameLength else {
            throw AmbisonicConversionError.message("Unsupported converter buffer layout or capacity.")
        }
        let inputList = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input.audioBufferList))
        let outputList = UnsafeMutableAudioBufferListPointer(output.mutableAudioBufferList)
        guard inputList.count == channels, outputList.count == channels,
              inputList.allSatisfy({ $0.mNumberChannels == 1 && $0.mData != nil }),
              outputList.allSatisfy({ $0.mNumberChannels == 1 && $0.mData != nil }) else {
            throw AmbisonicConversionError.message("The converter could not access the sample planes.")
        }
        let ins: [UnsafeRawPointer?] = inputList.map { UnsafeRawPointer($0.mData!) }
        let outs: [UnsafeMutableRawPointer?] = outputList.map { $0.mData }
        var points = [ambip_point(sample_offset: 0, value: direction.parameter),
                      ambip_point(sample_offset: 0, value: bypass ? 1 : 0)]
        var report = ambip_report()
        let code = ins.withUnsafeBufferPointer { sourcePlanes in
            outs.withUnsafeBufferPointer { destinationPlanes in
                points.withUnsafeMutableBufferPointer { pointStorage in
                    let queues = [ambip_queue(parameter_id: 2, point_count: 1, last_point_result: 0, points: pointStorage.baseAddress),
                                  ambip_queue(parameter_id: 1, point_count: 1, last_point_result: 0, points: pointStorage.baseAddress! + 1)]
                    return queues.withUnsafeBufferPointer { queueStorage in
                        var source = ambip_input(channels: UInt32(channels), frame_capacity: Int(input.frameCapacity),
                                                 planes: sourcePlanes.baseAddress, silence_flags: silenceFlags)
                        var destination = ambip_output(channels: UInt32(channels), frame_capacity: Int(output.frameCapacity),
                                                       planes: destinationPlanes.baseAddress, silence_flags: 0)
                        if precision == 64 {
                            return ambip_process_f64(&state, &source, &destination, Int(input.frameLength),
                                                     queueStorage.baseAddress, queueStorage.count, &report)
                        }
                        return ambip_process_f32(&state, &source, &destination, Int(input.frameLength),
                                                 queueStorage.baseAddress, queueStorage.count, &report)
                    }
                }
            }
        }
        guard code == 0 else {
            let detail = code == Int32(AMBIP_FP_ENVIRONMENT.rawValue) ? "Unsupported floating-point controls." :
                "Unsupported samples, channel storage, or processing state."
            throw AmbisonicConversionError.message("\(detail) Conversion stopped (status \(code)). No converted file was saved.")
        }
        output.frameLength = input.frameLength
        return report
    }
}
