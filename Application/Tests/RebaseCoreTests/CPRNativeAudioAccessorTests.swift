import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Independent arithmetic and retained-history sequences. Public SoXR sample
/// controls share the pinned public backend, not the candidate wrapper.
@Suite(.serialized)
struct CPRNativeAudioAccessorTests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    private struct Seek: Decodable {
        let source_rate, output_rate: Double
        let requested_frame, source_frame, returned_frame: Int64
        let ratio_bits, source_product_bits, quotient_bits: String
    }
    private struct Step: Decodable {
        let operation: String
        let requested, returned: Int
        let source_position: Int64
        let first: Bool
        let budget, actual: Int?
        let first_call, terminal: Bool?
        let output_f32_bits: [String]?
    }
    private struct Scenario: Decodable {
        let name: String
        let source_rate, output_rate: Double
        let converter, source_format: String
        let mode2_budget_available: Bool
        let input_f32_bits: [String]
        let steps: [Step]
    }
    private struct Oracle: Decodable {
        let seek_vectors: [Seek]
        let scenarios: [Scenario]
    }
    private func oracle() throws -> Oracle {
        let data = try Data(contentsOf: workspace.appendingPathComponent(
            "research/evidence/application/APP016/accessor-state-oracle.json"))
        try #require(cprSHA256(data) == "5742689c7f78313468e9c682aa49735b245ff86493aefafa79508e8e9caa347a")
        return try JSONDecoder().decode(Oracle.self, from: data)
    }
    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }
    private func samples(_ frames: Int) -> [Float] {
        (0..<frames * 2).map { Float(($0 * 37) % 4093 - 2046) / 8192 }
    }
    private func make(_ source: Double = 44100, _ output: Double = 48000,
                      frames: Int = 1024, format: CPRNativeAudioAccessor.SourceFormat = .float32,
                      converter: CPRNativeAudioAccessor.Converter = .mode1,
                      available: Bool = false) throws -> CPRNativeAudioAccessor {
        try CPRNativeAudioAccessor(source: samples(frames), sourceRate: source, outputRate: output,
            sourceFormat: format, converter: converter, mode2BudgetAvailable: available)
    }

    @Test func ExactFloat32SeekMappingMatchesFractionVectorsAndRejectsBeforeWrites() throws {
        for row in try oracle().seek_vectors {
            var output = RBAccessorSeek()
            try #require(rb_cpr_accessor_seek(Float(row.source_rate).bitPattern,
                Float(row.output_rate).bitPattern, row.requested_frame, &output) == 0)
            #expect(output.sourceFrame == row.source_frame)
            #expect(output.returnedOutputFrame == row.returned_frame)
            #expect(output.sourcePerOutputBits == UInt32(row.ratio_bits, radix: 16))
            #expect(output.sourceProductBits == UInt64(row.source_product_bits, radix: 16))
            #expect(output.outputQuotientBits == UInt64(row.quotient_bits, radix: 16))
        }
        // Inspect stable allocated storage, including padding. Swift value
        // copies need not preserve a C struct's unspecified padding bytes.
        let result = UnsafeMutablePointer<RBAccessorSeek>.allocate(capacity: 1)
        defer { result.deallocate() }
        UnsafeMutableRawPointer(result).initializeMemory(as: UInt8.self, repeating: 0xa5,
                                                        count: MemoryLayout<RBAccessorSeek>.stride)
        let before = Data(bytes: result, count: MemoryLayout<RBAccessorSeek>.stride)
        for bad in [Float.nan, .infinity, 0, -1, 7999, 44100.5, 192001] {
            #expect(rb_cpr_accessor_seek(bad.bitPattern, Float(48000).bitPattern, 1, result) != 0)
            #expect(Data(bytes: result, count: before.count) == before)
        }
        for position in [Int64(-1), 9_007_199_254_740_993] {
            #expect(rb_cpr_accessor_seek(Float(44100).bitPattern, Float(48000).bitPattern,
                position, result) != 0)
            #expect(Data(bytes: result, count: before.count) == before)
        }
        #expect(rb_cpr_accessor_seek(Float(44100).bitPattern, Float(48000).bitPattern, 1, nil) != 0)
        let prior = fegetround()
        defer { _ = fesetround(prior) }
        for rounding in [FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO] {
            try #require(fesetround(rounding) == 0)
            #expect(rb_cpr_accessor_seek(Float(44100).bitPattern, Float(48000).bitPattern, 1, result) == 2)
            #expect(Data(bytes: result, count: before.count) == before)
        }
    }

    @Test func EveryReadCountPositionAndSampleMatchesIndependentRetainedSequences() throws {
        for row in try oracle().scenarios {
            let input = row.input_f32_bits.map { Float(bitPattern: UInt32($0, radix: 16)!) }
            let accessor = try CPRNativeAudioAccessor(source: input,
                sourceRate: row.source_rate, outputRate: row.output_rate,
                sourceFormat: row.source_format == "pcm24" ? .pcm24 : .float32,
                converter: row.converter == "mode1" ? .mode1 : .mode2,
                mode2BudgetAvailable: row.mode2_budget_available)
            for step in row.steps {
                if step.operation == "seek" {
                    let returned = try accessor.seek(to: Int64(step.requested))
                    #expect(returned == Int64(step.returned), "\(row.name)")
                } else {
                    let read = try accessor.read(requestedFrames: step.requested)
                    #expect(read.requestedOutputFrames == step.requested)
                    #expect(read.budgetSourceFrames == step.budget, "\(row.name)")
                    #expect(read.actualSourceFrames == step.actual, "\(row.name)")
                    #expect(read.firstCall == step.first_call)
                    #expect(read.terminal == step.terminal)
                    #expect(read.returnedOutputFrames == step.returned, "\(row.name)")
                    let expected = step.output_f32_bits!.map { UInt32($0, radix: 16)! }
                    #expect(read.samples.map(\.bitPattern) == expected, "\(row.name)")
                }
                #expect(accessor.sourcePosition == step.source_position, "\(row.name)")
                #expect(accessor.firstConvertedRead == step.first, "\(row.name)")
                #expect(!accessor.failed)
            }
        }
    }

    @Test func NonsequentialSeeksRetainFilterHistoryRatherThanResetOrPreroll() throws {
        let kept = try make(), fresh = try make()
        _ = try kept.read(requestedFrames: 129)
        let first = kept.firstConvertedRead
        _ = try kept.seek(to: 200)
        #expect(kept.firstConvertedRead == first)
        _ = try fresh.seek(to: 200)
        let retained = try kept.read(requestedFrames: 73)
        let reset = try fresh.read(requestedFrames: 73)
        #expect(retained.samples.map(\.bitPattern) != reset.samples.map(\.bitPattern))
        #expect(!retained.firstCall && reset.firstCall)
        // The independent sequence test supplies the correct retained samples;
        // this negative alternative ensures a fresh state is discriminated.
    }

    @Test func FirstBudgetAvailabilityIsSeparateFromChosenFallbackAndZeroCount() throws {
        let fallback = try make(frames: 6000, converter: .mode1, available: true)
        let ordinary = try make(frames: 6000, converter: .mode1, available: false)
        let padded = try fallback.read(requestedFrames: 129)
        let unpadded = try ordinary.read(requestedFrames: 129)
        // Independently: ceil(44100/48000*(129+4096)), corrected by reverse test.
        #expect(padded.budgetSourceFrames == 3882)
        #expect(unpadded.budgetSourceFrames == 119)
        #expect(padded.actualSourceFrames == 3882 && unpadded.actualSourceFrames == 119)
        _ = try fallback.seek(to: 0)
        #expect(!fallback.firstConvertedRead)
        #expect(try fallback.read(requestedFrames: 129).budgetSourceFrames == 119)
        let zero = try make(8000, 192000, frames: 16)
        let empty = try zero.read(requestedFrames: 1)
        #expect(empty.budgetSourceFrames == 0 && empty.returnedOutputFrames == 0)
        #expect(zero.sourcePosition == 0 && !zero.firstConvertedRead && !zero.terminalSeen)
        _ = try zero.seek(to: 0)
        #expect(!zero.firstConvertedRead)
        let noAllowance = try make(frames: 6000, converter: .mode2, available: false)
        let discarding = try noAllowance.read(requestedFrames: 129)
        #expect(discarding.budgetSourceFrames == 119 && discarding.returnedOutputFrames == 0)
        #expect(noAllowance.sourcePosition == 119 && !noAllowance.firstConvertedRead)
    }

    @Test func EOFUsesFirstShortPredicateAndDefensiveTerminalStateRemainsExplicit() throws {
        for mode: CPRNativeAudioAccessor.Converter in [.mode1, .mode2] {
            let accessor = try make(frames: 129, converter: mode, available: mode == .mode2)
            let output = try accessor.read(requestedFrames: 512)
            #expect(output.terminal && accessor.terminalSeen)
            #expect(accessor.sourcePosition == 129 && output.actualSourceFrames == 129)
            #expect(rejects { _ = try accessor.seek(to: 0) })
            #expect(rejects { _ = try accessor.read(requestedFrames: 1) })
            #expect(accessor.sourcePosition == 129 && !accessor.failed)
        }
        let full = try make(8000, 16000, frames: 129)
        let output = try full.read(requestedFrames: 258)
        #expect(output.actualSourceFrames == output.budgetSourceFrames)
        #expect(!output.terminal && !full.terminalSeen)
        let end = try full.read(requestedFrames: 2)
        #expect(end.actualSourceFrames == 0 && !end.terminal)
        _ = try full.seek(to: 0)
        #expect(!full.firstConvertedRead)
        // Existing public mode2 wrapper deliberately excludes zero nonterminal
        // input. The accessor stops; it must not invent final=true or reset.
        let unsupported = try make(8000, 16000, frames: 129, converter: .mode2)
        _ = try unsupported.read(requestedFrames: 258)
        #expect(rejects { _ = try unsupported.read(requestedFrames: 2) })
        #expect(unsupported.failed && !unsupported.terminalSeen)
        #expect(unsupported.sourcePosition == 129)
        #expect(rejects { _ = try unsupported.seek(to: 0) })
    }

    @Test func InvalidDomainsAndFailedPreflightDoNotPublishProgress() throws {
        for source in [[], [Float(0)], [Float.nan, 0], [Float.infinity, 0], [Float.leastNonzeroMagnitude, 0]] {
            #expect(rejects { _ = try CPRNativeAudioAccessor(source: source, sourceRate: 44100, outputRate: 48000) })
        }
        for source in [[Float(1), 0], [Float(bitPattern: 0x33800000), 0],
                       [Float(bitPattern: 0x80000000), 0], [-1.0001, 0]] {
            #expect(rejects { _ = try CPRNativeAudioAccessor(source: source,
                sourceRate: 44100, outputRate: 48000, sourceFormat: .pcm24) })
        }
        for rate in [Double.nan, .infinity, -1, 7999, 44100.1, 192001] {
            #expect(rejects { _ = try make(rate, 48000) })
            #expect(rejects { _ = try make(44100, rate) })
        }
        let accessor = try make()
        for frame in [Int64(-1), 1_000_000] {
            #expect(rejects { _ = try accessor.seek(to: frame) })
            #expect(accessor.sourcePosition == 0 && accessor.firstConvertedRead)
        }
        for count in [-1, 0, 65537] {
            #expect(rejects { _ = try accessor.read(requestedFrames: count) })
            #expect(accessor.sourcePosition == 0 && accessor.firstConvertedRead && !accessor.failed)
        }
        let tooLarge = try make(192000, 8000, frames: 16)
        #expect(rejects { _ = try tooLarge.read(requestedFrames: 65536) })
        #expect(tooLarge.sourcePosition == 0 && tooLarge.firstConvertedRead && !tooLarge.failed)
        let prior = fegetround()
        defer { _ = fesetround(prior) }
        try #require(fesetround(FE_DOWNWARD) == 0)
        #expect(rejects { _ = try accessor.read(requestedFrames: 128) })
        #expect(accessor.sourcePosition == 0 && accessor.firstConvertedRead && !accessor.failed)
        try #require(fesetround(prior) == 0)
        #expect(try accessor.read(requestedFrames: 128).actualSourceFrames > 0)
    }

    @Test func EqualRateDirectReadsPreserveSnapshotAndReturnActualShortCount() throws {
        var original = samples(16)
        let expected = original.map(\.bitPattern)
        let accessor = try CPRNativeAudioAccessor(source: original, sourceRate: 44100,
            outputRate: 44100, sourceFormat: .float32)
        original[0] = 999
        let read = try accessor.read(requestedFrames: 7)
        #expect(read.samples.map(\.bitPattern) == Array(expected.prefix(14)))
        #expect(accessor.firstConvertedRead)
        var detachedOutput = read.samples
        detachedOutput[0] = 777
        #expect(read.samples[0].bitPattern == expected[0])
        _ = try accessor.seek(to: 0)
        #expect(try accessor.read(requestedFrames: 32).samples.map(\.bitPattern) == expected)
        #expect(accessor.sourcePosition == 16 && !accessor.terminalSeen)
        #expect(try accessor.read(requestedFrames: 1).returnedOutputFrames == 0)
        let pcm = try make(44100, 44100, frames: 16, format: .pcm24)
        _ = try pcm.read(requestedFrames: 1)
        #expect(!pcm.firstConvertedRead && !pcm.terminalSeen)
    }
}
