import Darwin
import Foundation
import RebaseTimingDSP
import RebaseSoXR
import Testing
@testable import RebaseCore

/// Independent expectations come from original instruction operations, rounded
/// using Fraction/IEEE arithmetic. Spy output is deliberately not a resampler.
struct NativeRateMode2Tests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private let evidence = "research/evidence/application/APP012/"

    fileprivate struct BackendCall: Decodable, Equatable {
        let input_frames: Int
        let null_input: Bool
        let input_sha256: String
        let first_bits, last_bits: [String]
        let requested, used, produced: Int
        let output_sha256: String
    }
    private struct Snapshot: Decodable, Equatable {
        let ratio_bits, cumulative_ideal_bits: String
        let cumulative_input, cumulative_visible, total_returned: UInt64
        let backend_calls, backend_input_used, backend_output_produced: UInt64
        let channels, delay, discard, input_capacity, output_capacity: UInt32
        let input_end, input_consumed, pending_input, output_read, output_end: UInt32
        let finished, failed: UInt32
        init(_ s: RBMode2Snapshot) {
            ratio_bits = String(format: "%016llx", s.ratio.bitPattern)
            cumulative_ideal_bits = String(format: "%016llx", s.cumulative_ideal.bitPattern)
            cumulative_input = s.cumulative_input; cumulative_visible = s.cumulative_visible
            total_returned = s.total_returned; backend_calls = s.backend_calls
            backend_input_used = s.backend_input_used; backend_output_produced = s.backend_output_produced
            channels = s.channels; delay = s.delay; discard = s.discard
            input_capacity = s.input_capacity; output_capacity = s.output_capacity
            input_end = s.input_end; input_consumed = s.input_consumed; pending_input = s.pending_input
            output_read = s.output_read; output_end = s.output_end
            finished = s.finished; failed = s.failed
        }
    }
    private struct Step: Decodable {
        let input_frames, returned: Int
        let final: Bool
        let output_sha256: String
        let snapshot: Snapshot
        let backend_calls: [BackendCall]
    }
    private struct Case: Decodable {
        let name, policy, pattern: String
        let source, output: Double
        let channels: Int
        let initial: Snapshot
        let steps: [Step]
    }
    private struct CountCase: Decodable {
        let source, output: Double
        let input_frames, block_frames, returned_frames: Int
    }
    private struct Oracle: Decodable {
        let generator_sha256: String
        let cases: [Case]
        let full_source_counts: [CountCase]
    }
    private func oracle() throws -> Oracle {
        let data = try Data(contentsOf: workspace.appendingPathComponent(evidence + "mode2-wrapper-oracle.json"))
        #expect(cprSHA256(data) == "bae42e6878db26177403ebd9cb622afc926794a06431dc88ba79d772af205225")
        let result = try JSONDecoder().decode(Oracle.self, from: data)
        let generator = try Data(contentsOf: workspace.appendingPathComponent(evidence + "mode2-wrapper-oracle.py"))
        #expect(cprSHA256(generator) == result.generator_sha256)
        return result
    }
    fileprivate static func pcmBytes(_ samples: [Float]) -> Data {
        var data = Data(capacity: samples.count * 4)
        for sample in samples {
            var little = sample.bitPattern.littleEndian
            withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
        }
        return data
    }
    private func samples(start: Int, frames: Int, channels: Int, pattern: String = "ramp") -> [Float] {
        var result: [Float] = []
        result.reserveCapacity(frames * channels)
        for index in start..<(start + frames) {
            var left: Float, right: Float
            if pattern == "impulse" {
                left = index == 0 ? 0.5 : 0
                right = index == 1 ? -0.25 : 0
            } else if pattern == "alternating" {
                left = index % 2 == 0 ? 0.5 : -0.5
                right = index % 2 == 0 ? -0.25 : 0.25
            } else if pattern == "nonzero-last" {
                left = index == 8192 ? 0.375 : 0
                right = index == 8192 ? -0.375 : 0
            } else {
                let i = index % 16637
                left = Float(i - 63) / 128
                right = Float((i * 17) % 131 - 65) / 256
            }
            result.append(left)
            if channels == 2 { result.append(right) }
        }
        return result
    }
    fileprivate final class Spy {
        let channels: Int
        let policy: String
        var calls: [BackendCall] = []
        var sequence = 0
        var creates = 0
        var destroys = 0
        var failure: String?
        var createFailure = false
        init(channels: Int = 2, policy: String = "full") {
            self.channels = channels; self.policy = policy
        }
        var backend: RBMode2Backend {
            RBMode2Backend(context: Unmanaged.passUnretained(self).toOpaque(),
                create: { context, _, _, _, result in
                    guard let context, let result else { return -1 }
                    let spy = Unmanaged<Spy>.fromOpaque(context).takeUnretainedValue()
                    spy.creates += 1
                    if spy.createFailure { return -1 }
                    result.pointee = context
                    return 0
                }, process: { context, input, frames, used, output, capacity, produced in
                    guard let context, let used, let produced else { return -1 }
                    let spy = Unmanaged<Spy>.fromOpaque(context).takeUnretainedValue()
                    let values = input.map { Array(UnsafeBufferPointer(start: $0, count: frames * spy.channels)) } ?? []
                    var consumed = frames
                    var count = capacity
                    if spy.policy == "lag" {
                        consumed = input == nil ? 0 : max(0, frames - min(7, frames))
                        count = max(0, capacity - 3)
                    }
                    if spy.policy == "zero" { count = 0 }
                    var result: [Float] = []
                    result.reserveCapacity(count * spy.channels)
                    for frame in 0..<count {
                        for channel in 0..<spy.channels {
                            let word = UInt32(0x3e000000 + ((spy.sequence + frame) % 65521) * 2 + channel)
                            result.append(Float(bitPattern: word))
                        }
                    }
                    spy.sequence += count
                    spy.calls.append(BackendCall(input_frames: frames, null_input: input == nil,
                        input_sha256: cprSHA256(NativeRateMode2Tests.pcmBytes(values)),
                        first_bits: values.prefix(spy.channels).map { String(format: "%08x", $0.bitPattern) },
                        last_bits: values.suffix(spy.channels).map { String(format: "%08x", $0.bitPattern) },
                        requested: capacity, used: consumed, produced: count,
                        output_sha256: cprSHA256(NativeRateMode2Tests.pcmBytes(result))))
                    if let output {
                        for i in result.indices { output[i] = result[i] }
                    }
                    used.pointee = consumed; produced.pointee = count
                    switch spy.failure {
                    case "error": return -1
                    case "used": used.pointee = frames + 1
                    case "produced": produced.pointee = capacity + 1
                    case "nan": if capacity > 0 { output?[0] = .nan }
                    default: break
                    }
                    return 0
                }, destroy: { context in
                    if let context {
                        Unmanaged<Spy>.fromOpaque(context).takeUnretainedValue().destroys += 1
                    }
                })
        }
    }
    private func make(_ spy: Spy, source: Double = 44100, output: Double = 48000) throws -> OpaquePointer {
        var state: OpaquePointer?
        try #require(rb_native_mode2_create(source, output, UInt32(spy.channels), spy.backend, &state) == RB_MODE2_OK)
        return try #require(state)
    }
    private func snapshot(_ state: OpaquePointer) throws -> Snapshot {
        var result = RBMode2Snapshot()
        try #require(rb_native_mode2_snapshot(state, &result) == RB_MODE2_OK)
        return Snapshot(result)
    }
    private func process(_ state: OpaquePointer, input: [Float], channels: Int, final: Bool,
                         capacity: Int? = nil) throws -> [Float] {
        var expected = 0
        try #require(rb_native_mode2_count(state, input.count / channels, final ? 1 : 0, &expected) == RB_MODE2_OK)
        var output = [Float](repeating: Float(bitPattern: 0x3f123456), count: max(1, capacity ?? expected) * channels)
        var produced = 987654
        let status = input.withUnsafeBufferPointer { i in
            output.withUnsafeMutableBufferPointer { o in
                rb_native_mode2_process(state, input.isEmpty ? nil : i.baseAddress, input.count / channels,
                    o.baseAddress, capacity ?? expected, final ? 1 : 0, &produced)
            }
        }
        try #require(status == RB_MODE2_OK)
        #expect(produced == expected)
        return Array(output.prefix(produced * channels))
    }

    @Test func originalInstructionSpyVectorsMatchCountsCallsStorageAndEverySnapshot() throws {
        let cases = try oracle().cases
        #expect(cases.count == 47)
        for vector in cases {
            let spy = Spy(channels: vector.channels, policy: vector.policy)
            let state = try make(spy, source: vector.source, output: vector.output)
            #expect(try snapshot(state) == vector.initial, "\(vector.name)")
            var offset = 0
            for step in vector.steps {
                let before = try snapshot(state)
                var predicted = 12345
                #expect(rb_native_mode2_count(state, step.input_frames, step.final ? 1 : 0, &predicted) == RB_MODE2_OK)
                #expect(predicted == step.returned, "\(vector.name)")
                #expect(try snapshot(state) == before)
                let callStart = spy.calls.count
                let input = samples(start: offset, frames: step.input_frames,
                                    channels: vector.channels, pattern: vector.pattern)
                let output = try process(state, input: input, channels: vector.channels, final: step.final)
                #expect(cprSHA256(Self.pcmBytes(output)) == step.output_sha256, "\(vector.name)")
                #expect(Array(spy.calls[callStart...]) == step.backend_calls, "\(vector.name)")
                #expect(try snapshot(state) == step.snapshot, "\(vector.name)")
                offset += step.input_frames
            }
            rb_native_mode2_destroy(state)
            #expect(spy.creates == 1 && spy.destroys == 1)
        }
    }

    @Test func fullSourceCountsAreBackendIndependentAndKeepQueryStateUnchanged() throws {
        for vector in try oracle().full_source_counts {
            let spy = Spy()
            let state = try make(spy, source: vector.source, output: vector.output)
            defer { rb_native_mode2_destroy(state) }
            let before = try snapshot(state)
            var result = 123
            #expect(rb_native_mode2_count_blocks(state, vector.input_frames, vector.block_frames, &result) == RB_MODE2_OK)
            #expect(result == vector.returned_frames)
            #expect(try snapshot(state) == before)
            #expect(spy.calls.isEmpty)
        }
    }

    @Test func invalidArgumentsCapacityAndSamplesDoNotConsumeBackendOrState() throws {
        let spy = Spy()
        let state = try make(spy)
        defer { rb_native_mode2_destroy(state) }
        let before = try snapshot(state)
        var result = 731
        #expect(rb_native_mode2_count(state, 65409, 1, &result) == RB_MODE2_INVALID)
        #expect(result == 731)
        #expect(rb_native_mode2_count(state, 0, 0, &result) == RB_MODE2_INVALID)
        #expect(rb_native_mode2_count_blocks(state, 1, 0, &result) == RB_MODE2_INVALID)
        #expect(rb_native_mode2_count_blocks(state, 16_000_001, 8192, &result) != RB_MODE2_OK)
        let input = samples(start: 0, frames: 8192, channels: 2)
        var count = 0
        try #require(rb_native_mode2_count(state, 8192, 1, &count) == RB_MODE2_OK)
        var output = [Float](repeating: 0.375, count: (count + 1) * 2)
        let untouched = Self.pcmBytes(output)
        let status = input.withUnsafeBufferPointer { i in
            output.withUnsafeMutableBufferPointer { o in
                rb_native_mode2_process(state, i.baseAddress, 8192, o.baseAddress, count - 1, 1, &result)
            }
        }
        #expect(status == RB_MODE2_CAPACITY)
        #expect(result == 731 && Self.pcmBytes(output) == untouched)
        for bad in [Float.nan, Float.infinity, -Float.infinity, Float.leastNonzeroMagnitude] {
            let invalid: [Float] = [bad, 0]
            let status = invalid.withUnsafeBufferPointer { i in
                output.withUnsafeMutableBufferPointer { o in
                    rb_native_mode2_process(state, i.baseAddress, 1, o.baseAddress, count, 1, &result)
                }
            }
            #expect(status == RB_MODE2_SAMPLE_DOMAIN)
            #expect(result == 731 && Self.pcmBytes(output) == untouched)
        }
        #expect(try snapshot(state) == before)
        #expect(spy.calls.isEmpty)
    }

    @Test func backendFailurePoisonsStateButNeverPublishesPartialSamplesOrCounts() throws {
        for failure in ["error", "used", "produced", "nan"] {
            let spy = Spy()
            spy.failure = failure
            let state = try make(spy)
            defer { rb_native_mode2_destroy(state) }
            let input = samples(start: 0, frames: 8192, channels: 2)
            var capacity = 0
            try #require(rb_native_mode2_count(state, 8192, 1, &capacity) == RB_MODE2_OK)
            var output = [Float](repeating: 0.375, count: capacity * 2)
            let untouched = Self.pcmBytes(output)
            var result = 731
            let status = input.withUnsafeBufferPointer { i in
                output.withUnsafeMutableBufferPointer { o in
                    rb_native_mode2_process(state, i.baseAddress, 8192, o.baseAddress, capacity, 1, &result)
                }
            }
            #expect(status != RB_MODE2_OK)
            #expect(result == 731 && Self.pcmBytes(output) == untouched)
            #expect(try snapshot(state).failed == 1)
            #expect(rb_native_mode2_count(state, 1, 1, &result) == RB_MODE2_STATE)
            #expect(spy.calls.count == 1)
        }
    }

    @Test func oneTerminalCallIsEnforcedAndEqualRatesDoNotBypassBackend() throws {
        for frames in [0, 1, 2048, 8192] {
            let spy = Spy()
            let state = try make(spy, source: 48000, output: 48000)
            defer { rb_native_mode2_destroy(state) }
            _ = try process(state, input: samples(start: 0, frames: frames, channels: 2), channels: 2, final: true)
            #expect(!spy.calls.isEmpty)
            let before = try snapshot(state)
            var result = 731
            #expect(rb_native_mode2_count(state, 0, 1, &result) == RB_MODE2_STATE)
            #expect(rb_native_mode2_count(state, 1, 0, &result) == RB_MODE2_STATE)
            #expect(result == 731)
            #expect(try snapshot(state) == before)
        }
    }

    @Test func publicSoXRSamplesMatchSeparateInstructionWrapperWithPositiveAndNullEOF() throws {
        let data = try Data(contentsOf: workspace.appendingPathComponent(evidence + "mode2-public-oracle.json"))
        #expect(cprSHA256(data) == "12333d54cf1608abf0d4cbc0a18790c0309c22982ac3ad0619e48eb2956389ca")
        let model = try JSONDecoder().decode(Oracle.self, from: publicOracleCompatibleJSON(data))
        #expect(model.cases.count == 27)
        for vector in model.cases {
            var state: OpaquePointer?
            try #require(rb_native_mode2_create(vector.source, vector.output, 2, rb_public_soxr_backend(), &state) == RB_MODE2_OK)
            let actual = try #require(state)
            defer { rb_native_mode2_destroy(actual) }
            #expect(try snapshot(actual) == vector.initial)
            var offset = 0
            for step in vector.steps {
                let input = samples(start: offset, frames: step.input_frames, channels: 2, pattern: vector.pattern)
                let output = try process(actual, input: input, channels: 2, final: step.final)
                #expect(cprSHA256(Self.pcmBytes(output)) == step.output_sha256, "\(vector.name)")
                #expect(try snapshot(actual) == step.snapshot, "\(vector.name)")
                offset += step.input_frames
            }
        }
    }
    private func publicOracleCompatibleJSON(_ data: Data) throws -> Data {
        var object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        object["full_source_counts"] = []
        return try JSONSerialization.data(withJSONObject: object)
    }

    @Test func aliasesFactoriesAndRoundingFailuresAreRejectedBeforeCallbacks() throws {
        let spy = Spy()
        let state = try make(spy)
        defer { rb_native_mode2_destroy(state) }
        let before = try snapshot(state)
        var arena = [Float](repeating: 0.25, count: 40000)
        let unchanged = Self.pcmBytes(arena)
        var returned = 731
        let overlapStatus = arena.withUnsafeMutableBufferPointer { p in
            rb_native_mode2_process(state, p.baseAddress, 8192, p.baseAddress, 16000, 1, &returned)
        }
        #expect(overlapStatus == RB_MODE2_INVALID)
        let countAliasStatus = arena.withUnsafeMutableBufferPointer { p in
            let countPointer = UnsafeMutableRawPointer(p.baseAddress!).assumingMemoryBound(to: Int.self)
            return rb_native_mode2_process(state, p.baseAddress, 8192, p.baseAddress!.advanced(by: 18000),
                                           10000, 1, countPointer)
        }
        #expect(countAliasStatus == RB_MODE2_INVALID)
        #expect(Self.pcmBytes(arena) == unchanged && returned == 731)
        #expect(try snapshot(state) == before && spy.calls.isEmpty)
        for rates in [(Double.nan, 48000.0), (44100.5, 48000), (7999, 48000), (44100, 192001)] {
            var untouched: OpaquePointer?
            #expect(rb_native_mode2_create(rates.0, rates.1, 2, spy.backend, &untouched) == RB_MODE2_INVALID)
            #expect(untouched == nil)
        }
        let badFactory = Spy()
        badFactory.createFailure = true
        var untouched: OpaquePointer?
        #expect(rb_native_mode2_create(44100, 48000, 2, badFactory.backend, &untouched) == RB_MODE2_BACKEND)
        #expect(untouched == nil && badFactory.creates == 1 && badFactory.destroys == 0)
        let saved = fegetround()
        defer { _ = fesetround(saved) }
        for mode in [FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO] {
            try #require(fesetround(mode) == 0)
            #expect(rb_native_mode2_count(state, 1, 1, &returned) == RB_MODE2_INVALID)
            #expect(returned == 731)
            #expect(fegetround() == mode)
        }
        try #require(fesetround(saved) == 0)
        #expect(try snapshot(state) == before && spy.calls.isEmpty)
    }
}
