import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Independent Fraction/IEEE controls, not captured target output. These test
/// only the explicitly selected, bounded mode0 upsampling reconstruction.
struct NativeRateMode0Tests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private let evidence = "research/evidence/application/APP010/"

    private struct Oracle: Decodable {
        struct Difference: Decodable { let index: Int; let correct: String, wrong: String }
        struct Vector: Decodable {
            let name, source_rate_f32_bits, output_rate_f32_bits: String
            let channels, output_frames: Int
            let input_f32_bits, output_f32_bits: [String]
            let step_f64_bits, final_phase_f64_bits: String
            let final_previous_f64_bits: [String]
            let first_unfused_differences, first_distributed_differences: [Difference]
            var input: [Float] { input_f32_bits.map { Float(bitPattern: UInt32($0, radix: 16)!) } }
            var expected: [UInt32] { output_f32_bits.map { UInt32($0, radix: 16)! } }
        }
        let generator_sha256: String
        let vectors: [Vector]
    }

    private func oracle() throws -> Oracle {
        let data = try Data(contentsOf: workspace.appendingPathComponent(evidence + "native-rate-mode0-oracle.json"))
        #expect(cprSHA256(data) == "d2c91862a7a93b744f6da5793d92ec00b58aab56f0c15772121835b2843c9aa5")
        let result = try JSONDecoder().decode(Oracle.self, from: data)
        let generator = try Data(contentsOf: workspace.appendingPathComponent(evidence + "native-rate-mode0-oracle.py"))
        #expect(cprSHA256(generator) == result.generator_sha256)
        #expect(result.generator_sha256 == "6b5357c1bf923034673e9bcb240136b6dc31e8fde0276132036232811f2623a4")
        return result
    }

    private func makeState(source: Float = 44100, output: Float = 48000, channels: UInt32 = 2) throws -> RBMode0State {
        var state = RBMode0State()
        try #require(rb_native_mode0_init(source, output, channels, &state) == RB_MODE0_OK)
        return state
    }

    private func state(for vector: Oracle.Vector) throws -> RBMode0State {
        try makeState(source: Float(bitPattern: UInt32(vector.source_rate_f32_bits, radix: 16)!),
            output: Float(bitPattern: UInt32(vector.output_rate_f32_bits, radix: 16)!),
            channels: UInt32(vector.channels))
    }

    private func bytes(_ value: RBMode0State) -> Data {
        var copy = value
        return withUnsafeBytes(of: &copy) { Data($0) }
    }

    private func process(_ input: [Float], state: inout RBMode0State) throws -> [Float] {
        let frames = input.count / Int(state.channels)
        let before = bytes(state)
        var count = -1
        try #require(rb_native_mode0_count(&state, frames, &count) == RB_MODE0_OK)
        #expect(bytes(state) == before)
        var output = [Float](repeating: 99, count: count * Int(state.channels))
        var produced = -1
        let status = input.withUnsafeBufferPointer { source in
            output.withUnsafeMutableBufferPointer { destination in
                rb_native_mode0_process(&state, source.baseAddress, frames, destination.baseAddress, count, &produced)
            }
        }
        try #require(status == RB_MODE0_OK)
        #expect(produced == count)
        return output
    }

    private func partitioned(_ vector: Oracle.Vector, sizes: [Int]) throws -> ([Float], RBMode0State) {
        var state = try state(for: vector)
        let input = vector.input
        var result: [Float] = []
        var frame = 0, block = 0
        while frame < input.count / vector.channels {
            let count = min(sizes[block % sizes.count], input.count / vector.channels - frame)
            let start = frame * vector.channels, end = (frame + count) * vector.channels
            result += try process(Array(input[start..<end]), state: &state)
            frame += count; block += 1
        }
        return (result, state)
    }

    @Test func allIndependentOracleSamplesAndStateBitsMatch() throws {
        let vectors = try oracle().vectors
        #expect(vectors.count == 9)
        #expect(vectors.reduce(0) { $0 + $1.output_f32_bits.count } == 19_592)
        for vector in vectors {
            var state = try state(for: vector)
            let result = try process(vector.input, state: &state)
            #expect(result.map(\.bitPattern) == vector.expected, Comment(rawValue: vector.name))
            #expect(result.count == vector.output_frames * vector.channels)
            #expect(state.step.bitPattern == UInt64(vector.step_f64_bits, radix: 16))
            #expect(state.phase.bitPattern == UInt64(vector.final_phase_f64_bits, radix: 16))
            #expect(state.previous.0.bitPattern == UInt64(vector.final_previous_f64_bits[0], radix: 16))
            if vector.channels == 2 {
                #expect(state.previous.1.bitPattern == UInt64(vector.final_previous_f64_bits[1], radix: 16))
            }
        }
    }

    @Test func fusedMultiplyAndSeparatelyRoundedTermsAreDiscriminated() throws {
        let vector = try #require(try oracle().vectors.first { $0.name == "two-frame-stereo-fma-cancellation" })
        var state = try state(for: vector)
        let output = try process(vector.input, state: &state).map(\.bitPattern)
        #expect(vector.first_unfused_differences.count == 2)
        #expect(vector.first_distributed_differences.count == 2)
        for difference in vector.first_unfused_differences + vector.first_distributed_differences {
            #expect(output[difference.index] == UInt32(difference.correct, radix: 16))
            #expect(output[difference.index] != UInt32(difference.wrong, radix: 16))
        }
        #expect(output == [0xbf130000, 0x3e930000, 0xa3f80000, 0x23780000])
    }

    @Test func partitionsPreserveSamplesPhaseAndHistoryAcross8192Boundary() throws {
        for vector in try oracle().vectors {
            var initial = try state(for: vector)
            _ = try process(vector.input, state: &initial)
            for sizes in [[1], [7, 1, 64, 2, 257], [8192], [8191, 2, 1]] {
                let (result, state) = try partitioned(vector, sizes: sizes)
                #expect(result.map(\.bitPattern) == vector.expected, Comment(rawValue: vector.name))
                #expect(bytes(state) == bytes(initial))
            }
        }
    }

    @Test func liveCursorAndPrerollSuffixesMatchIndependentSampleBits() throws {
        let vectors = try oracle().vectors.filter {
            $0.channels == 2 && $0.output_frames > 0 && $0.name != "adjacent-f32-rate-mantissa"
        }
        for vector in vectors {
            let source = Float(bitPattern: UInt32(vector.source_rate_f32_bits, radix: 16)!)
            let output = Float(bitPattern: UInt32(vector.output_rate_f32_bits, radix: 16)!)
            let stream = try CPRRateConvertedStream(source: vector.input,
                sourceRate: Double(source), outputRate: Double(output), gain: 1)
            #expect(stream.frameCount == Int64(vector.output_frames))
            let candidates = [0, 1, 2, 7, 8915, 8916, 8917,
                              vector.output_frames - 1, vector.output_frames]
            for first in Set(candidates).sorted() where first >= 0 && first <= vector.output_frames {
                let cursor = try stream.cursor(from: Int64(first))
                var actual: [UInt32] = []
                var calls = 0
                while let block = try cursor.nextInterleaved() {
                    #expect(!block.isEmpty && block.count % 2 == 0)
                    actual += block.map(\.bitPattern)
                    calls += 1
                    try #require(calls <= vector.input.count / 2 + 1)
                }
                #expect(actual == Array(vector.expected.dropFirst(first * 2)), Comment(rawValue: vector.name))
                #expect(cursor.isAtEnd && cursor.deliveredFrames == Int64(vector.output_frames))
                #expect(try cursor.nextInterleaved() == nil)
            }
            #expect(throws: (any Error).self) { try stream.cursor(from: -1) }
            #expect(throws: (any Error).self) { try stream.cursor(from: stream.frameCount + 1) }
        }
    }

    @Test func resetFirstFrameAndZeroInputNeverInventTailPadding() throws {
        var state = try makeState()
        #expect(state.phase.bitPattern == Double(1).bitPattern)
        #expect(try process([0.5, -0.25], state: &state).isEmpty)
        #expect(state.phase.bitPattern == 0)
        #expect(state.previous.0 == 0.5 && state.previous.1 == -0.25)
        let before = bytes(state)
        for _ in 0..<3 {
            var produced = 123
            #expect(rb_native_mode0_process(&state, nil, 0, nil, 0, &produced) == RB_MODE0_OK)
            #expect(produced == 0 && bytes(state) == before)
        }
        #expect(try process([-0.5, 0.25], state: &state).count == 4)
        #expect(rb_native_mode0_reset(&state) == RB_MODE0_OK)
        #expect(bytes(state) == bytes(try makeState()))
        let maximum = try #require(try oracle().vectors.first { $0.name == "maximum-allowed-upsampling" })
        #expect(maximum.output_frames == 241) // Rounded recurrence, not an exact-ratio count of 240.
    }

    @Test func capacityAndLateSampleFailuresAreTransactional() throws {
        let cases: [([Float], Int, Int32)] = [
            ([0.5, -0.25, -0.5, 0.25], 1, Int32(RB_MODE0_CAPACITY)),
            ([0.5, -0.25, -0.5, 0.25, .nan, 0], 8, Int32(RB_MODE0_SAMPLE_DOMAIN)),
            ([0.5, -0.25, .infinity, 0], 8, Int32(RB_MODE0_SAMPLE_DOMAIN)),
            ([0.5, -0.25, Float(bitPattern: 1), 0], 8, Int32(RB_MODE0_SAMPLE_DOMAIN)),
            // All inputs are permitted, but interpolation creates a subnormal output.
            ([0, 0, .leastNormalMagnitude, .leastNormalMagnitude], 8, Int32(RB_MODE0_SAMPLE_DOMAIN))
        ]
        for (input, capacity, expected) in cases {
            var state = try makeState()
            let before = bytes(state)
            var output = [Float](repeating: -77, count: capacity * 2), produced = 123
            let status = input.withUnsafeBufferPointer { source in
                output.withUnsafeMutableBufferPointer { destination in
                    rb_native_mode0_process(&state, source.baseAddress, input.count / 2,
                        destination.baseAddress, capacity, &produced)
                }
            }
            #expect(status == expected)
            #expect(bytes(state) == before && produced == 123)
            #expect(output.allSatisfy { $0 == -77 })
        }
    }

    @Test func invalidStateRateBoundsAndAliasingRejectWithoutWrites() throws {
        var sentinel = try makeState()
        let before = bytes(sentinel)
        for (source, output, channels): (Float, Float, UInt32) in [
            (44100, 44100, 2), (48000, 44100, 2), (7999, 48000, 2), (44100, 192001, 2),
            (.nan, 48000, 2), (44100, .infinity, 2), (0, 48000, 2), (44100, 48000, 3)
        ] {
            #expect(rb_native_mode0_init(source, output, channels, &sentinel) == RB_MODE0_INVALID)
            #expect(bytes(sentinel) == before)
        }
        var invalid = [RBMode0State]()
        var s = sentinel; s.phase = -0.01; invalid.append(s)
        s = sentinel; s.phase = .nan; invalid.append(s)
        s = sentinel; s.step = s.step.nextUp; invalid.append(s)
        s = sentinel; s.reserved = 1; invalid.append(s)
        s = sentinel; s.previous.0 = Double(1).nextUp; invalid.append(s)
        for var state in invalid {
            let original = bytes(state)
            var count = 123
            #expect(rb_native_mode0_count(&state, 2, &count) == RB_MODE0_INVALID)
            #expect(rb_native_mode0_reset(&state) == RB_MODE0_INVALID)
            #expect(bytes(state) == original && count == 123)
        }
        var count = 123
        #expect(rb_native_mode0_count(&sentinel, 16_000_001, &count) == RB_MODE0_INVALID)
        #expect(count == 123 && bytes(sentinel) == before)
        var maximum = try makeState(source: 8000, output: 192000)
        let maximumBefore = bytes(maximum)
        #expect(rb_native_mode0_count(&maximum, 666_668, &count) == RB_MODE0_CAPACITY)
        #expect(count == 123 && bytes(maximum) == maximumBefore)
        var samples: [Float] = [0.5, -0.25, -0.5, 0.25]
        let sampleBits = samples.map(\.bitPattern)
        let status = samples.withUnsafeMutableBufferPointer { pointer in
            rb_native_mode0_process(&sentinel, pointer.baseAddress, 2, pointer.baseAddress, 2, &count)
        }
        #expect(status == RB_MODE0_INVALID && count == 123 && bytes(sentinel) == before)
        #expect(samples.map(\.bitPattern) == sampleBits)
        #expect(rb_native_mode0_init(44100, 48000, 2, nil) == RB_MODE0_INVALID)
        #expect(rb_native_mode0_count(&sentinel, 1, nil) == RB_MODE0_INVALID)
        #expect(rb_native_mode0_process(&sentinel, nil, 0, nil, 0, nil) == RB_MODE0_INVALID)
    }

    @Test func nonNearestModesRejectAndPreserveEnvironmentAndOutputs() throws {
        var state = try makeState()
        let before = bytes(state), saved = fegetround()
        defer { _ = fesetround(saved) }
        for mode in [FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO] {
            try #require(fesetround(mode) == 0)
            var count = 123
            #expect(rb_native_mode0_init(44100, 48000, 2, &state) == RB_MODE0_INVALID)
            #expect(rb_native_mode0_reset(&state) == RB_MODE0_INVALID)
            #expect(rb_native_mode0_count(&state, 0, &count) == RB_MODE0_INVALID)
            #expect(rb_native_mode0_process(&state, nil, 0, nil, 0, &count) == RB_MODE0_INVALID)
            #expect(bytes(state) == before && count == 123)
            #expect(fegetround() == mode)
        }
    }
}
