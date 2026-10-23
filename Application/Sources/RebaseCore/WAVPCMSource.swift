import Foundation

/// Bounded little-endian RIFF/WAVE adapter for portable conformance and PCM import.
/// Compressed, RF64, extensible, and big-endian files are rejected explicitly.
/// This adapter does not authorize or alter preserved CPR media associations.
public final class WAVPCMSource: PCMSourceReader {
    public static let maximumBytes = 268_435_456
    public let sampleRate: Double
    public let channelCount: Int
    public let frameCount: Int64
    private let bytes: Data
    private let dataOffset: Int
    private let blockAlign: Int
    private let bits: Int
    private let format: Int

    // Stored metadata is distinct from the Float32 decoder output.
    var storedBitsPerSample: Int { bits }
    var storedBytesPerFrame: Int { blockAlign }
    var snapshotSHA256: String { cprSHA256(bytes) }

    public convenience init(url: URL) throws {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        guard attributes[.type] as? FileAttributeType == .typeRegular,
              let size = (attributes[.size] as? NSNumber)?.intValue,
              size >= 12, size <= Self.maximumBytes else {
            throw RebaseCoreError.unsupportedAudio("Choose a regular WAV file of at most 256 MiB.")
        }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        // A bounded snapshot: even a changing file cannot cause an unbounded read.
        var data = Data()
        while data.count <= size {
            guard let chunk = try handle.read(upToCount: min(1_048_576, size + 1 - data.count)), !chunk.isEmpty else { break }
            data.append(chunk)
            if data.count > size { break }
        }
        guard data.count == size else {
            throw RebaseCoreError.unsupportedAudio("The WAV size changed while reading.")
        }
        try self.init(data: data)
    }

    public init(data: Data) throws {
        let data = Data(data)
        guard data.count >= 12, data.count <= Self.maximumBytes,
              Self.tag(data, at: 0) == "RIFF", Self.tag(data, at: 8) == "WAVE",
              Int(Self.u32(data, at: 4)) + 8 == data.count else {
            throw Self.invalid("Only a complete, bounded RIFF/WAVE file is supported.")
        }
        var cursor = 12
        var formatRange: Range<Int>?
        var audioRange: Range<Int>?
        while cursor < data.count {
            guard data.count - cursor >= 8 else { throw Self.invalid("Truncated WAV chunk header.") }
            let tag = Self.tag(data, at: cursor)
            let length = Int(Self.u32(data, at: cursor + 4))
            let start = cursor + 8
            guard length <= data.count - start else { throw Self.invalid("Truncated WAV chunk.") }
            let range = start..<(start + length)
            if tag == "fmt " {
                guard formatRange == nil else { throw Self.invalid("Duplicate WAV format chunk.") }
                formatRange = range
            } else if tag == "data" {
                guard audioRange == nil else { throw Self.invalid("Multiple WAV data chunks are unsupported.") }
                audioRange = range
            }
            cursor = range.upperBound + (length & 1)
            guard cursor <= data.count else { throw Self.invalid("Missing WAV chunk padding.") }
        }
        guard let fmt = formatRange, let audio = audioRange, fmt.count >= 16 else {
            throw Self.invalid("WAV format or audio data is missing.")
        }
        let base = fmt.lowerBound
        let format = Int(Self.u16(data, at: base))
        let channels = Int(Self.u16(data, at: base + 2))
        let rate = Int(Self.u32(data, at: base + 4))
        let byteRate = Int(Self.u32(data, at: base + 8))
        let align = Int(Self.u16(data, at: base + 12))
        let bits = Int(Self.u16(data, at: base + 14))
        guard (1...2).contains(channels), (8_000...192_000).contains(rate),
              (format == 1 && [16, 24, 32].contains(bits)) || (format == 3 && [32, 64].contains(bits)),
              align == channels * (bits / 8), byteRate == rate * align,
              audio.count > 0, audio.count % align == 0,
              audio.count / align <= PCMRenderer.maximumClipFrames else {
            throw Self.invalid("WAV requires mono/stereo PCM16/24/32 or float32/64, 8–192 kHz, and at most 16 million frames.")
        }
        if fmt.count != 16 {
            guard fmt.count >= 18, Int(Self.u16(data, at: base + 16)) == fmt.count - 18 else {
                throw Self.invalid("Invalid WAV format extension length.")
            }
        }
        bytes = Data(data) // normalized zero-based storage, independent of caller slices
        dataOffset = audio.lowerBound; blockAlign = align
        self.format = format; self.bits = bits
        sampleRate = Double(rate); channelCount = channels; frameCount = Int64(audio.count / align)
    }

    public func read(from start: Int64, count: Int) throws -> PCMBuffer {
        guard start >= 0, count >= 0, start <= frameCount,
              Int64(count) <= frameCount - start else {
            throw Self.invalid("WAV read lies outside the audio data.")
        }
        var output = Array(repeating: [Float](repeating: 0, count: count), count: channelCount)
        let width = bits / 8
        for frame in 0..<count {
            let offset = dataOffset + (Int(start) + frame) * blockAlign
            for channel in 0..<channelCount {
                let p = offset + channel * width
                let sample: Float
                switch (format, bits) {
                case (1, 16): sample = Float(Int16(bitPattern: Self.u16(bytes, at: p))) / 32_768
                case (1, 24):
                    let packed = UInt32(bytes[p]) | UInt32(bytes[p + 1]) << 8 | UInt32(bytes[p + 2]) << 16
                    sample = Float(Int32(bitPattern: packed << 8) >> 8) / 8_388_608
                case (1, 32): sample = Float(Double(Int32(bitPattern: Self.u32(bytes, at: p))) / 2_147_483_648)
                case (3, 32): sample = Float(bitPattern: Self.u32(bytes, at: p))
                case (3, 64):
                    let bits = UInt64(Self.u32(bytes, at: p)) | UInt64(Self.u32(bytes, at: p + 4)) << 32
                    sample = Float(Double(bitPattern: bits))
                default: throw Self.invalid("Unsupported WAV format.")
                }
                guard sample.isFinite else { throw RebaseCoreError.nonFiniteAudio("WAV contains a sample outside the finite Float32 range.") }
                output[channel][frame] = sample
            }
        }
        return try PCMBuffer(sampleRate: sampleRate, channels: output)
    }

    /// Deterministic float32 WAV encoding, including WAVEFORMATEX and fact chunks.
    /// Callers own destination containment, atomic publication, and overwrite policy.
    public static func encode(_ pcm: PCMBuffer) throws -> Data {
        guard pcm.frameCount > 0, let rate = UInt32(exactly: pcm.sampleRate),
              (8_000...192_000).contains(rate) else { throw invalid("WAV export requires a whole-number 8–192 kHz rate and audio frames.") }
        let channels = UInt16(pcm.channels.count)
        let payload = pcm.frameCount * Int(channels) * 4
        var data = Data()
        data.reserveCapacity(58 + payload)
        func tag(_ value: String) { data.append(contentsOf: value.utf8) }
        func u16(_ value: UInt16) { data.append(UInt8(truncatingIfNeeded: value)); data.append(UInt8(truncatingIfNeeded: value >> 8)) }
        func u32(_ value: UInt32) { for shift in stride(from: 0, to: 32, by: 8) { data.append(UInt8(truncatingIfNeeded: value >> shift)) } }
        tag("RIFF"); u32(UInt32(50 + payload)); tag("WAVE")
        tag("fmt "); u32(18); u16(3); u16(channels); u32(rate)
        u32(rate * UInt32(channels) * 4); u16(channels * 4); u16(32); u16(0)
        tag("fact"); u32(4); u32(UInt32(pcm.frameCount))
        tag("data"); u32(UInt32(payload))
        for frame in 0..<pcm.frameCount {
            for channel in 0..<Int(channels) { u32(pcm.channels[channel][frame].bitPattern) }
        }
        return data
    }

    private static func invalid(_ message: String) -> RebaseCoreError { .unsupportedAudio(message) }
    private static func tag(_ data: Data, at offset: Int) -> String { String(decoding: data[offset..<(offset + 4)], as: UTF8.self) }
    private static func u16(_ data: Data, at offset: Int) -> UInt16 { UInt16(data[offset]) | UInt16(data[offset + 1]) << 8 }
    private static func u32(_ data: Data, at offset: Int) -> UInt32 {
        UInt32(data[offset]) | UInt32(data[offset + 1]) << 8 | UInt32(data[offset + 2]) << 16 | UInt32(data[offset + 3]) << 24
    }
}
