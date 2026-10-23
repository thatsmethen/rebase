import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Expectations are generated independently from original ARM64 instructions
/// using Fraction arithmetic, never from this candidate or Cubase execution.
struct NativeRateMode0DownTests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private let evidence = "research/evidence/application/APP011/"
    private struct State: Decodable {
        let step_f64_bits, phase_f64_bits: String
        let history_f64_bits: [String]
        let pending: Bool
    }
    private struct Call: Decodable {
        let input_frames: Int
        let output_frames: Int?
        let rejected_source_bounds: String?
        let state_after: State?
    }
    private struct Vector: Decodable {
        let name, source_rate_f32_bits, output_rate_f32_bits, layout: String
        let channels: Int
        let initial_state, final_state: State
        let calls: [Call]
        let input_f32_bits, output_f32_bits: [String]?
        let input_frames, output_frames: Int?
        let input_f32le_sha256, output_f32le_sha256: String?
        let suffix_f32le_sha256: [String: String]?
        var sourceRate: Float { Float(bitPattern: UInt32(source_rate_f32_bits, radix: 16)!) }
        var outputRate: Float { Float(bitPattern: UInt32(output_rate_f32_bits, radix: 16)!) }
        var ordering: UInt32 { layout == "above" ? 1 : 0 }
        var input: [Float] {
            if let input_f32_bits { return input_f32_bits.map { Float(bitPattern: UInt32($0, radix: 16)!) } }
            var samples: [Float] = []
            for i in 0..<input_frames! {
                let left = Float(i % 127 - 63) / Float(128)
                let right = Float((i * 17) % 131 - 65) / Float(256)
                samples.append(left)
                samples.append(right)
            }
            return samples
        }
    }
    private struct Oracle: Decodable {
        struct Difference: Decodable {
            let vector, variant, correct, wrong: String
            let index: Int
        }
        let generator_sha256: String
        let vectors, large_partition_vectors: [Vector]
        let arithmetic_discriminators: [Difference]
    }
    private func oracle() throws -> Oracle {
        let data = try Data(contentsOf: workspace.appendingPathComponent(evidence + "native-rate-down-oracle.json"))
        #expect(cprSHA256(data) == "3938e9ce6332f9ce4155377f9f5c6d3a9c45afe173b61d11b08ef2c7923c204a")
        let result = try JSONDecoder().decode(Oracle.self, from: data)
        let generator = try Data(contentsOf: workspace.appendingPathComponent(evidence + "native-rate-down-oracle.py"))
        #expect(cprSHA256(generator) == result.generator_sha256)
        #expect(result.generator_sha256 == "cc071510f036d4a8005ac8da52b1a496b7d20a1fcdc4dd0729bb03a230276468")
        return result
    }
    private func bytes(_ state: RBMode0DownState) -> Data {
        var copy = state
        return withUnsafeBytes(of: &copy) { Data($0) }
    }
    private func pcmBytes(_ samples: [Float]) -> Data {
        var result = Data()
        for sample in samples {
            var little = sample.bitPattern.littleEndian
            withUnsafeBytes(of: &little) { result.append(contentsOf: $0) }
        }
        return result
    }
    private func makeState(source: Float = 48000, output: Float = 44100,
                           channels: UInt32 = 2) throws -> RBMode0DownState {
        var state = RBMode0DownState()
        try #require(rb_native_mode0_down_init(source, output, channels, &state) == RB_MODE0_DOWN_OK)
        return state
    }
    private func state(for vector: Vector) throws -> RBMode0DownState {
        var state = try makeState(source: vector.sourceRate, output: vector.outputRate,
                                  channels: UInt32(vector.channels))
        state.phase = Double(bitPattern: UInt64(vector.initial_state.phase_f64_bits, radix: 16)!)
        state.history.0 = Double(bitPattern: UInt64(vector.initial_state.history_f64_bits[0], radix: 16)!)
        if vector.channels == 2 {
            state.history.1 = Double(bitPattern: UInt64(vector.initial_state.history_f64_bits[1], radix: 16)!)
        }
        state.pending = vector.initial_state.pending ? 1 : 0
        return state
    }
    private func check(_ actual: RBMode0DownState, _ expected: State) {
        #expect(actual.step.bitPattern == UInt64(expected.step_f64_bits, radix: 16))
        #expect(actual.phase.bitPattern == UInt64(expected.phase_f64_bits, radix: 16))
        #expect(actual.pending == (expected.pending ? 1 : 0))
        #expect(actual.history.0.bitPattern == UInt64(expected.history_f64_bits[0], radix: 16))
        if actual.channels == 2 {
            #expect(actual.history.1.bitPattern == UInt64(expected.history_f64_bits[1], radix: 16))
        }
    }
    private func call(_ input: [Float], state: inout RBMode0DownState, layout: UInt32,
                      flush: UInt32, expected: Call) throws -> [Float] {
        let before = bytes(state)
        var predicted = 123
        let wanted = expected.rejected_source_bounds == nil ? Int32(RB_MODE0_DOWN_OK) : Int32(RB_MODE0_DOWN_LOOKAHEAD)
        #expect(rb_native_mode0_down_count(&state, expected.input_frames, layout, flush, &predicted) == wanted)
        #expect(bytes(state) == before)
        let capacity = max(expected.input_frames + 2, 2)
        let channels = Int(state.channels), outputSamples = capacity * channels
        // One allocation makes both disjoint address orderings deterministic.
        var arena = [Float](repeating: -77, count: input.count + outputSamples + 8)
        let sourceOffset = layout == 1 ? 0 : outputSamples + 4
        let outputOffset = layout == 1 ? input.count + 4 : 0
        arena.replaceSubrange(sourceOffset..<(sourceOffset + input.count), with: input)
        let untouched = arena.map(\.bitPattern)
        var produced = 123
        let status = arena.withUnsafeMutableBufferPointer { buffer in
            rb_native_mode0_down_process(&state, buffer.baseAddress! + sourceOffset,
                expected.input_frames, buffer.baseAddress! + outputOffset, capacity, layout, flush, &produced)
        }
        try #require(status == wanted)
        if wanted != RB_MODE0_DOWN_OK {
            #expect(predicted == 123 && produced == 123 && bytes(state) == before)
            #expect(arena.map(\.bitPattern) == untouched)
            return []
        }
        #expect(predicted == expected.output_frames && produced == predicted)
        check(state, try #require(expected.state_after))
        #expect(Array(arena[sourceOffset..<(sourceOffset + input.count)]).map(\.bitPattern) == input.map(\.bitPattern))
        #expect(arena[(outputOffset + produced * channels)..<(outputOffset + outputSamples)].allSatisfy { $0 == -77 })
        return Array(arena[outputOffset..<(outputOffset + produced * channels)])
    }
    private func execute(_ vector: Vector, flush: UInt32 = 0) throws -> [Float] {
        var state = try state(for: vector)
        let input = vector.input
        var at = 0, output: [Float] = []
        for expected in vector.calls {
            let end = at + expected.input_frames * vector.channels
            output += try call(Array(input[at..<end]), state: &state, layout: vector.ordering,
                               flush: flush, expected: expected)
            if expected.rejected_source_bounds != nil { break }
            at = end
        }
        check(state, vector.final_state)
        return output
    }

    @Test func originalInstructionVectorsMatchEverySampleStateAndIgnoredFlush() throws {
        let controls = try oracle()
        #expect(controls.vectors.count == 105)
        for vector in controls.vectors {
            let expected = try #require(vector.output_f32_bits).map { UInt32($0, radix: 16)! }
            for flush: UInt32 in [0, 1] {
                #expect(try execute(vector, flush: flush).map(\.bitPattern) == expected,
                        Comment(rawValue: vector.name))
            }
        }
    }

    @Test func fusedOperationAndDifferentMonoStereoCarryAreDiscriminated() throws {
        let controls = try oracle()
        #expect(controls.arithmetic_discriminators.count == 6)
        for difference in controls.arithmetic_discriminators {
            let vector = try #require(controls.vectors.first { $0.name == difference.vector })
            let actual = try execute(vector).map(\.bitPattern)
            #expect(actual[difference.index] == UInt32(difference.correct, radix: 16))
            #expect(actual[difference.index] != UInt32(difference.wrong, radix: 16))
        }
        let mono = try #require(controls.vectors.first { $0.name == "mono-stereo-carry-rounding-c1" })
        let stereo = try #require(controls.vectors.first { $0.name == "mono-stereo-carry-rounding-c2" })
        #expect(try execute(mono).first?.bitPattern == Float(sign: .plus, exponent: -54, significand: 1).bitPattern)
        #expect(try execute(stereo).map(\.bitPattern) == [0, 0])
    }

    @Test func partitionPolicyAndReachableSingletonFailureMatchIndependentDigests() throws {
        let controls = try oracle().large_partition_vectors
        #expect(controls.count == 18)
        for vector in controls {
            #expect(cprSHA256(pcmBytes(vector.input)) == vector.input_f32le_sha256)
            let output = try execute(vector)
            #expect(output.count / 2 == vector.output_frames)
            #expect(cprSHA256(pcmBytes(output)) == vector.output_f32le_sha256, Comment(rawValue: vector.name))
            if vector.name.hasSuffix("avoid-singleton") {
                var state = try state(for: vector), count = -1
                let before = bytes(state)
                #expect(rb_native_mode0_down_count_blocks(&state, vector.input_frames!, 8192, 1, &count) == RB_MODE0_DOWN_OK)
                #expect(count == vector.output_frames && bytes(state) == before)
                var remaining = vector.input_frames!
                for call in vector.calls {
                    let block = rb_native_mode0_down_next_block(remaining, 8192)
                    #expect(block == call.input_frames && block >= 2)
                    remaining -= block
                }
                #expect(remaining == 0)
            }
        }
        let hazard = try #require(controls.first { $0.name == "48000-32000-16385-fixed8192" })
        #expect(hazard.calls.last?.rejected_source_bounds != nil)
        let fixed = try #require(controls.first { $0.name == "48000-44100-16385-fixed8192" })
        let safe = try #require(controls.first { $0.name == "48000-44100-16385-avoid-singleton" })
        #expect(fixed.output_frames == 15_051 && safe.output_frames == 15_052)
    }

    @Test func liveCursorPlanarBuffersAndPrerollMatchIndependentPartitionOracle() throws {
        for vector in try oracle().large_partition_vectors where vector.name.hasSuffix("avoid-singleton") {
            let stream = try CPRRateConvertedStream(source: vector.input,
                sourceRate: Double(vector.sourceRate), outputRate: Double(vector.outputRate), gain: 1)
            #expect(stream.frameCount == Int64(vector.output_frames!))
            for (start, expectedDigest) in try #require(vector.suffix_f32le_sha256) {
                let cursor = try stream.cursor(from: Int64(start)!)
                var output: [Float] = []
                while let buffer = try cursor.nextBuffer() {
                    let channels = try #require(buffer.floatChannelData)
                    for frame in 0..<Int(buffer.frameLength) {
                        output.append(channels[0][frame]); output.append(channels[1][frame])
                    }
                }
                #expect(cprSHA256(pcmBytes(output)) == expectedDigest, Comment(rawValue: vector.name + "/" + start))
                #expect(cursor.isAtEnd && cursor.deliveredFrames == stream.frameCount)
            }
        }
    }

    @Test func equalRateIsNotCopyAndZeroInputNeverFlushes() throws {
        let vector = try #require(try oracle().vectors.first { $0.name == "48000-48000-c2-above-35" })
        let result = try execute(vector)
        #expect(result.count == 33 * 2)
        #expect(result.map(\.bitPattern) != vector.input.map(\.bitPattern))
        var state = try makeState()
        state.phase = 0.25; state.pending = 1; state.history.0 = 0.5
        let before = bytes(state)
        for flush: UInt32 in [0, 1] {
            var produced = 123
            #expect(rb_native_mode0_down_process(&state, nil, 0, nil, 0, 1, flush, &produced) == RB_MODE0_DOWN_OK)
            #expect(produced == 0 && bytes(state) == before)
        }
        #expect(rb_native_mode0_down_reset(&state) == RB_MODE0_DOWN_OK)
        #expect(bytes(state) == bytes(try makeState()))
    }

    @Test func lateSamplesOutputDomainAndCapacityFailuresPreserveAllCallerBytes() throws {
        let cases: [([Float], Int, Int32, Bool)] = [
            ([0.5, -0.25, 0.25, -0.5, 0.75, 0.5], 0, Int32(RB_MODE0_DOWN_CAPACITY), false),
            ([0.5, -0.25, 0.25, -0.5, .nan, 0], 8, Int32(RB_MODE0_DOWN_SAMPLE_DOMAIN), false),
            ([0.5, -0.25, .infinity, 0], 8, Int32(RB_MODE0_DOWN_SAMPLE_DOMAIN), false),
            ([0, 0, Float(bitPattern: 1), 0], 8, Int32(RB_MODE0_DOWN_SAMPLE_DOMAIN), false),
            ([.leastNormalMagnitude, .leastNormalMagnitude, 0, 0], 8, Int32(RB_MODE0_DOWN_SAMPLE_DOMAIN), true)
        ]
        for (input, capacity, expected, pending) in cases {
            var state = try makeState()
            if pending { state.phase = 0.5; state.pending = 1 }
            let before = bytes(state)
            var arena = input + [Float](repeating: -77, count: 32)
            let untouched = arena.map(\.bitPattern)
            var count = 123
            let status = arena.withUnsafeMutableBufferPointer {
                rb_native_mode0_down_process(&state, $0.baseAddress, input.count / 2,
                    $0.baseAddress! + input.count + 4, capacity, 1, 0, &count)
            }
            #expect(status == expected && count == 123 && bytes(state) == before)
            #expect(arena.map(\.bitPattern) == untouched)
        }
    }

    @Test func invalidStateBoundsPointerOrderAndAliasingAreTransactional() throws {
        var state = try makeState(), count = 123
        let before = bytes(state)
        for (source, output, channels): (Float, Float, UInt32) in [
            (44100, 48000, 2), (48000, 7999, 2), (192001, 48000, 2),
            (.nan, 44100, 2), (48000, .infinity, 2), (48000, 44100, 3)
        ] {
            #expect(rb_native_mode0_down_init(source, output, channels, &state) == RB_MODE0_DOWN_INVALID)
            #expect(bytes(state) == before)
        }
        var invalid: [RBMode0DownState] = []
        var s = state; s.phase = -0.01; invalid.append(s)
        s = state; s.step = s.step.nextUp; invalid.append(s)
        s = state; s.pending = 2; invalid.append(s)
        s = state; s.history.0 = .infinity; invalid.append(s)
        s = try makeState(source: 96000, output: 44100); s.phase = -0.5; s.pending = 0; invalid.append(s)
        for var bad in invalid {
            let original = bytes(bad)
            #expect(rb_native_mode0_down_count(&bad, 8, 1, 0, &count) == RB_MODE0_DOWN_INVALID)
            #expect(rb_native_mode0_down_reset(&bad) == RB_MODE0_DOWN_INVALID)
            #expect(bytes(bad) == original && count == 123)
        }
        #expect(rb_native_mode0_down_count(&state, 16_000_001, 1, 0, &count) == RB_MODE0_DOWN_INVALID)
        #expect(rb_native_mode0_down_count(&state, 8, 2, 0, &count) == RB_MODE0_DOWN_INVALID)
        #expect(rb_native_mode0_down_count(&state, 8, 1, 2, &count) == RB_MODE0_DOWN_INVALID)
        #expect(rb_native_mode0_down_count_blocks(&state, 8, 2, 1, &count) == RB_MODE0_DOWN_INVALID)
        var arena = [Float](repeating: 0.5, count: 32)
        let original = arena.map(\.bitPattern)
        for (offset, layout): (Int, UInt32) in [(0, 1), (1, 1), (16, 0)] {
            let result = arena.withUnsafeMutableBufferPointer {
                rb_native_mode0_down_process(&state, $0.baseAddress, 4, $0.baseAddress! + offset, 4, layout, 0, &count)
            }
            #expect(result == RB_MODE0_DOWN_INVALID)
            #expect(bytes(state) == before && count == 123 && arena.map(\.bitPattern) == original)
        }
        #expect(rb_native_mode0_down_init(48000, 44100, 2, nil) == RB_MODE0_DOWN_INVALID)
        #expect(rb_native_mode0_down_count(&state, 0, 1, 0, nil) == RB_MODE0_DOWN_INVALID)
    }

    @Test func nonNearestRoundingRejectsWithoutChangingStateOrEnvironment() throws {
        let original = fegetround()
        defer { _ = fesetround(original) }
        var state = try makeState(), count = 123
        let before = bytes(state)
        for mode in [FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO] {
            try #require(fesetround(mode) == 0)
            #expect(rb_native_mode0_down_count(&state, 8, 1, 0, &count) == RB_MODE0_DOWN_INVALID)
            #expect(rb_native_mode0_down_reset(&state) == RB_MODE0_DOWN_INVALID)
            #expect(bytes(state) == before && count == 123 && fegetround() == mode)
        }
    }
}
