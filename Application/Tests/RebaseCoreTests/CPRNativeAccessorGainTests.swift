import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Independent raw-bit gain stages and native-derived retained accessor calls.
/// These controls do not establish an actual selected Reference backend.
@Suite(.serialized)
struct CPRNativeAccessorGainTests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private struct Equal: Decodable {
        let integer: Int
        let gain_bits, decoded_bits, scalar_bits, vector_bits, separate_bits: String
    }
    private struct Stage: Decodable {
        let filter_output_bits, gain_bits, q24_then_gain_bits, gain_then_q24_bits, gain_without_q24_bits: String
    }
    private struct Stages: Decodable {
        let equal_rate_vectors, below_bound_discriminators: [Equal]
        let downsample_stage_vectors: [Stage]
    }
    private struct Step: Decodable {
        let operation, gain_bits: String
        let source_position: Int64
        let first: Bool
        let requested, returned, budget, actual: Int?
        let first_call, terminal: Bool?
        let output_f32_bits: [String]?
    }
    private struct Scenario: Decodable {
        let name, source_format, converter, initial_gain_bits: String
        let source_rate, output_rate: Double
        let mode2_budget_available: Bool
        let input_f32_bits: [String]
        let steps: [Step]
    }
    private struct Streams: Decodable { let scenarios: [Scenario] }
    private func stages() throws -> Stages {
        let data = try Data(contentsOf: workspace.appendingPathComponent(
            "research/evidence/application/APP017/gain-order-stage-oracle.json"))
        try #require(cprSHA256(data) == "e28870caa88a1eda66d8cc77eaf804ea513695e3fc3694ee77d719f2d1799cc1")
        return try JSONDecoder().decode(Stages.self, from: data)
    }
    private func streams() throws -> Streams {
        let data = try Data(contentsOf: workspace.appendingPathComponent(
            "research/evidence/application/APP017/accessor-gain-oracle.json"))
        try #require(cprSHA256(data) == "2a78917ad3318b904f66bda1a8205305d420d4c7d088ffb2ac8d6562e2d6aaaa")
        return try JSONDecoder().decode(Streams.self, from: data)
    }
    private func bits(_ hex: String) -> UInt32 { UInt32(hex, radix: 16)! }
    private func value(_ hex: String) -> Float { Float(bitPattern: bits(hex)) }
    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }
    private func source(_ frames: Int = 1024) -> [Float] {
        (0..<frames * 2).map { Float(($0 * 37) % 4093 - 2046) / 8192 }
    }
    private func accessor(gain: Float = 1, output: Double = 48000,
                          format: CPRNativeAudioAccessor.SourceFormat = .float32,
                          samples: [Float]? = nil) throws -> CPRNativeAudioAccessor {
        try CPRNativeAudioAccessor(source: samples ?? source(), sourceRate: 44100,
            outputRate: output, sourceFormat: format, converter: .mode1,
            mode2BudgetAvailable: false, gain: gain)
    }

    @Test func EqualRatePCM24ScalarSIMDAndFloat32ProjectionAgreeWithinBound() throws {
        let rows = try stages().equal_rate_vectors
        #expect(rows.count == 3168)
        for (gainHex, group) in Dictionary(grouping: rows, by: \.gain_bits) {
            let gain = value(gainHex)
            let input = group.flatMap { [value($0.decoded_bits), value($0.decoded_bits)] }
            let expected = group.flatMap { [bits($0.separate_bits), bits($0.separate_bits)] }
            #expect(group.allSatisfy { $0.scalar_bits == $0.vector_bits && $0.vector_bits == $0.separate_bits })
            var c = input
            try #require(rb_cpr_accessor_gain_f32(&c, c.count, gain.bitPattern) == 0)
            #expect(c.map(\.bitPattern) == expected)
            for format in [CPRNativeAudioAccessor.SourceFormat.float32, .pcm24] {
                let read = try accessor(gain: gain, output: 44100, format: format, samples: input)
                let result = try read.read(requestedFrames: group.count)
                #expect(result.samples.map(\.bitPattern) == expected)
                #expect(read.firstConvertedRead == (format == .float32 && gain == 1))
                #expect(!read.terminalSeen && !read.failed)
            }
        }
        for gain in Set(try stages().below_bound_discriminators.map(\.gain_bits)) {
            #expect(rejects { _ = try accessor(gain: value(gain), output: 44100, format: .pcm24) })
        }
        // Below the PCM24 fast-path bound, direct Float32 gain remains a
        // separately admitted path. The output is normal for this source.
        let lower = value("0fffffff")
        let direct = try accessor(gain: lower, output: 44100, samples: [-1, 1])
        #expect(try direct.read(requestedFrames: 1).samples.map(\.bitPattern) ==
            [lower.bitPattern | 0x80000000, lower.bitPattern])
    }

    @Test func DownsamplePackedRoundtripPrecedesDestinationGainAndDoesNotClipGain() throws {
        var wrongOrder = 0, missingRoundtrip = 0
        for row in try stages().downsample_stage_vectors {
            var sample = [value(row.filter_output_bits)]
            try #require(rb_cpr_accessor_pcm24_roundtrip(&sample, 1) == 0)
            try #require(rb_cpr_accessor_gain_f32(&sample, 1, bits(row.gain_bits)) == 0)
            #expect(sample[0].bitPattern == bits(row.q24_then_gain_bits))
            wrongOrder += row.q24_then_gain_bits != row.gain_then_q24_bits ? 1 : 0
            missingRoundtrip += row.q24_then_gain_bits != row.gain_without_q24_bits ? 1 : 0
        }
        #expect(wrongOrder == 67 && missingRoundtrip == 66)
        var over = [Float(0.75), -0.75]
        try #require(rb_cpr_accessor_gain_f32(&over, 2, Float(2).bitPattern) == 0)
        #expect(over == [1.5, -1.5])
    }

    @Test func MutableGainReadsMatchIndependentFilterHistoryAndFormatOrder() throws {
        var checked = 0, upwardZeroHasTail = 0
        for row in try streams().scenarios {
            let input = row.input_f32_bits.map(value)
            let current = try CPRNativeAudioAccessor(source: input, sourceRate: row.source_rate,
                outputRate: row.output_rate, sourceFormat: row.source_format == "pcm24" ? .pcm24 : .float32,
                converter: row.converter == "mode1" ? .mode1 : .mode2,
                mode2BudgetAvailable: row.mode2_budget_available, gain: value(row.initial_gain_bits))
            for step in row.steps {
                if step.operation == "gain" {
                    try current.setGain(value(step.gain_bits))
                } else if step.operation == "seek" {
                    #expect(try current.seek(to: Int64(step.requested!)) == Int64(step.returned!))
                } else {
                    let read = try current.read(requestedFrames: step.requested!)
                    let expected = step.output_f32_bits!.map(bits)
                    checked += expected.count
                    #expect(read.samples.map(\.bitPattern) == expected, "\(row.name)")
                    #expect(read.returnedOutputFrames == step.returned)
                    #expect(read.budgetSourceFrames == step.budget && read.actualSourceFrames == step.actual)
                    #expect(read.firstCall == step.first_call && read.terminal == step.terminal)
                    if value(step.gain_bits) == 0 {
                        if row.source_rate < row.output_rate {
                            if read.samples.contains(where: { $0 != 0 }) { upwardZeroHasTail += 1 }
                        } else { #expect(read.samples.allSatisfy { $0 == 0 }) }
                    }
                }
                #expect(current.gain.bitPattern == bits(step.gain_bits))
                #expect(current.sourcePosition == step.source_position && current.firstConvertedRead == step.first)
                #expect(!current.failed)
            }
        }
        #expect(checked == 16540)
        #expect(upwardZeroHasTail > 0)
    }

    @Test func SignedZerosUnityAndEqualRateFirstFlagHaveExplicitBehavior() throws {
        let input = [Float(0), Float(bitPattern: 0x80000000), Float(1), Float(-1)]
        for (gain, expected) in [
            (Float(0), [UInt32(0), 0x80000000, 0, 0x80000000]),
            (Float(bitPattern: 0x80000000), [UInt32(0x80000000), 0, 0x80000000, 0]),
            (Float(1), input.map(\.bitPattern)),
            (Float(-1), [UInt32(0x80000000), 0, 0xbf800000, 0x3f800000])
        ] {
            let current = try accessor(gain: gain, output: 44100, samples: input)
            #expect(try current.read(requestedFrames: 2).samples.map(\.bitPattern) == expected)
            #expect(current.firstConvertedRead == (gain == 1))
        }
        let current = try accessor(output: 44100, samples: source(16))
        _ = try current.read(requestedFrames: 1)
        #expect(current.firstConvertedRead)
        try current.setGain(-1)
        #expect(current.firstConvertedRead && current.sourcePosition == 1)
        _ = try current.read(requestedFrames: 1)
        #expect(!current.firstConvertedRead)
        try current.setGain(1)
        #expect(!current.firstConvertedRead && current.sourcePosition == 2)
    }

    @Test func GainErrorsPreserveBuffersAndUnsupportedSetterDoesNotResetHistory() throws {
        let original = [Float(0.25), -0.125, 0.5, 0.75]
        for bad in [Float.nan, .infinity, -.infinity, .leastNonzeroMagnitude] {
            var buffer = original
            #expect(rb_cpr_accessor_gain_f32(&buffer, buffer.count, bad.bitPattern) != 0)
            #expect(buffer.map(\.bitPattern) == original.map(\.bitPattern))
            #expect(rejects { _ = try accessor(gain: bad) })
        }
        for bad in [Float.nan, .infinity, .leastNonzeroMagnitude, .greatestFiniteMagnitude] {
            for index in original.indices {
                var input = original; input[index] = bad
                let before = input.map(\.bitPattern)
                #expect(rb_cpr_accessor_gain_f32(&input, input.count, Float(2).bitPattern) != 0)
                #expect(input.map(\.bitPattern) == before)
            }
        }
        var tiny = [Float(1), Float.leastNormalMagnitude]
        let before = tiny.map(\.bitPattern)
        #expect(rb_cpr_accessor_gain_f32(&tiny, tiny.count, Float(0.5).bitPattern) != 0)
        #expect(tiny.map(\.bitPattern) == before)
        #expect(rb_cpr_accessor_gain_f32(nil, 1, Float(1).bitPattern) != 0)
        for count in [0, 32_000_001] {
            var buffer = original
            #expect(rb_cpr_accessor_gain_f32(&buffer, count, Float(1).bitPattern) != 0)
            #expect(buffer == original)
        }
        let current = try accessor(gain: value("3e99999a"))
        let control = try accessor(gain: value("3e99999a"))
        _ = try current.read(requestedFrames: 129); _ = try control.read(requestedFrames: 129)
        for bad in [Float.nan, .infinity, .leastNonzeroMagnitude] {
            #expect(rejects { try current.setGain(bad) })
            #expect(current.gain.bitPattern == 0x3e99999a && !current.firstConvertedRead)
        }
        let a = try current.read(requestedFrames: 73), b = try control.read(requestedFrames: 73)
        #expect(a.samples.map(\.bitPattern) == b.samples.map(\.bitPattern))
        let bounded = try accessor(output: 44100, format: .pcm24)
        #expect(rejects { try bounded.setGain(value("0fffffff")) })
        #expect(bounded.gain == 1 && bounded.firstConvertedRead && bounded.sourcePosition == 0)
        let failed = try accessor(gain: 2, output: 44100, samples: [.greatestFiniteMagnitude, 0])
        #expect(rejects { _ = try failed.read(requestedFrames: 1) })
        #expect(failed.failed && failed.sourcePosition == 0 && !failed.firstConvertedRead)
        #expect(rejects { try failed.setGain(1) })
        #expect(failed.gain == 2)
        // The API excludes post-terminal continuation even though the native
        // setter itself only writes the field. Do not reset a child to admit it.
        let finished = try accessor(gain: 0.75, samples: source(129))
        let terminal = try finished.read(requestedFrames: 512)
        #expect(terminal.terminal && finished.terminalSeen)
        #expect(rejects { try finished.setGain(-1) })
        #expect(finished.gain == 0.75 && finished.sourcePosition == 129)
    }

    @Test func NonNearestGainEnvironmentRejectsTransactionally() throws {
        let prior = fegetround()
        defer { _ = fesetround(prior) }
        for mode in [FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO] {
            var data: [Float] = [0.25, -0.125, 0, Float(bitPattern: 0x80000000)]
            let before = data.map(\.bitPattern)
            try #require(fesetround(mode) == 0)
            #expect(rb_cpr_accessor_gain_f32(&data, data.count, Float(-0.75).bitPattern) == 2)
            #expect(data.map(\.bitPattern) == before)
            try #require(fesetround(prior) == 0)
        }
    }
}
