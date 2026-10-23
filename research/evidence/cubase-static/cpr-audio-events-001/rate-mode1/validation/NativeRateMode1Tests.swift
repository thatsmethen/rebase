import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Independent original-instruction expectations, with exact Fraction tap
/// arithmetic and explicitly shared host libm primitives for the table.
@Suite(.serialized)
struct NativeRateMode1Tests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private let evidence = "research/evidence/application/APP013/"
    private struct Snapshot: Decodable, Equatable {
        let ratio_bits, step_bits, phase_bits: String
        let cumulative_input, cumulative_generated, total_returned: UInt64
        let input_capacity, fresh: UInt32
        init(_ s: RBMode1Snapshot) {
            ratio_bits = String(format: "%016llx", s.ratio.bitPattern)
            step_bits = String(format: "%016llx", s.step.bitPattern)
            phase_bits = String(format: "%016llx", s.phase.bitPattern)
            cumulative_input = s.cumulative_input
            cumulative_generated = s.cumulative_generated
            total_returned = s.total_returned
            input_capacity = s.input_capacity
            fresh = s.fresh
        }
    }
    private struct Call: Decodable {
        let reset: Bool?
        let input_frames, generated_frames, returned_frames: Int?
        let final: Bool?
        let input_f32_bits, output_f32_bits: [String]?
        let storage_prefix_f64_bits: [[String]]?
        let snapshot: Snapshot
    }
    private struct Vector: Decodable {
        let name: String
        let source_rate, output_rate: Double
        let channels: UInt32
        let calls: [Call]
    }
    private struct Table: Decodable {
        let source_rate, output_rate: Double
        let coefficient_sha256_le, difference_sha256_le: String
        let indices: [Int]
        let coefficient_bits, difference_bits: [String]
    }
    private struct CountVector: Decodable {
        let source_rate, output_rate: Double
        let source_frames, block_frames, total_returned: Int
        let calls: [Call]
    }
    private struct Oracle: Decodable {
        let generator_sha256: String
        let vectors: [Vector]
        let tables: [Table]
        let full_source_counts: [CountVector]
    }
    private func oracle() throws -> Oracle {
        let data = try Data(contentsOf: workspace.appendingPathComponent(evidence + "mode1-oracle.json"))
        #expect(cprSHA256(data) == "d985ab0b74146b093ccae9ca98edd5e8a7d78e904a35f6966ec841f98340d8a9")
        let result = try JSONDecoder().decode(Oracle.self, from: data)
        #expect(result.generator_sha256 == "f031f38172356ca244c683c35c17c2413333f52a58a1d43048f457258d8e9238")
        #expect(cprSHA256(try Data(contentsOf: workspace.appendingPathComponent(evidence + "mode1-oracle.py"))) == result.generator_sha256)
        return result
    }
    private func make(_ source: Double = 44100, _ output: Double = 48000,
                      channels: UInt32 = 2) throws -> OpaquePointer {
        var state: OpaquePointer?
        try #require(rb_native_mode1_create(source, output, channels, &state) == RB_MODE1_OK)
        return try #require(state)
    }
    private func snapshot(_ state: OpaquePointer) throws -> Snapshot {
        var value = RBMode1Snapshot()
        try #require(rb_native_mode1_snapshot(state, &value) == RB_MODE1_OK)
        return Snapshot(value)
    }
    private func storage(_ state: OpaquePointer, channel: UInt32 = 0, count: Int = 256) throws -> [UInt64] {
        var values = [Double](repeating: 0, count: count)
        try #require(rb_native_mode1_copy_storage(state, channel, 0, count, &values) == RB_MODE1_OK)
        return values.map(\.bitPattern)
    }
    private func bytes(_ values: [Double]) -> Data {
        var result = Data(capacity: values.count * 8)
        for value in values {
            var word = value.bitPattern.littleEndian
            withUnsafeBytes(of: &word) { result.append(contentsOf: $0) }
        }
        return result
    }

    @Test func CompleteCoefficientTablesMatchIndependentInstructionGenerator() throws {
        for table in try oracle().tables {
            let state = try make(table.source_rate, table.output_rate, channels: 1)
            defer { rb_native_mode1_destroy(state) }
            for kind in UInt32(0)...1 {
                var values = [Double](repeating: .nan, count: 32769)
                try #require(rb_native_mode1_copy_table(state, kind, 0, values.count, &values) == RB_MODE1_OK)
                #expect(cprSHA256(bytes(values)) == (kind == 0 ? table.coefficient_sha256_le : table.difference_sha256_le))
                let expected = kind == 0 ? table.coefficient_bits : table.difference_bits
                #expect(table.indices.enumerated().allSatisfy { pair in
                    values[pair.element].bitPattern == UInt64(expected[pair.offset], radix: 16)
                })
            }
        }
    }

    @Test func EveryReturnedSampleAndHistoryMatchesIndependentFractionOracle() throws {
        for vector in try oracle().vectors {
            let state = try make(vector.source_rate, vector.output_rate, channels: vector.channels)
            defer { rb_native_mode1_destroy(state) }
            for call in vector.calls {
                if call.reset == true {
                    let before = try storage(state, count: 512)
                    try #require(rb_native_mode1_reset(state) == RB_MODE1_OK)
                    #expect(try storage(state, count: 512) == before)
                } else {
                    let input = call.input_f32_bits!.map { Float(bitPattern: UInt32($0, radix: 16)!) }
                    let before = try snapshot(state)
                    var count = -1
                    try #require(rb_native_mode1_count(state, call.input_frames!, call.final! ? 1 : 0, &count) == RB_MODE1_OK)
                    #expect(count == call.returned_frames)
                    #expect(try snapshot(state) == before)
                    let sentinel = Float(bitPattern: 0x3e314159)
                    var output = [Float](repeating: sentinel, count: max(1, count * Int(vector.channels) + 8))
                    var returned = -7
                    let status = input.withUnsafeBufferPointer { source in
                        rb_native_mode1_process(state, input.isEmpty ? nil : source.baseAddress,
                            call.input_frames!, &output, count, call.final! ? 1 : 0, &returned)
                    }
                    try #require(status == RB_MODE1_OK, "\(vector.name): status \(status)")
                    #expect(returned == count)
                    let expected = call.output_f32_bits!.map { UInt32($0, radix: 16)! }
                    #expect(Array(output.prefix(expected.count)).map(\.bitPattern) == expected, "\(vector.name)")
                    #expect(output.dropFirst(expected.count).allSatisfy { $0.bitPattern == sentinel.bitPattern })
                    for channel in 0..<vector.channels {
                        #expect(try storage(state, channel: channel) ==
                            call.storage_prefix_f64_bits![Int(channel)].map { UInt64($0, radix: 16)! }, "\(vector.name)")
                    }
                }
                #expect(try snapshot(state) == call.snapshot, "\(vector.name)")
            }
        }
    }

    @Test func FullSourceCountQueriesMatchIndependentLedgerWithoutMutatingState() throws {
        for vector in try oracle().full_source_counts {
            let state = try make(vector.source_rate, vector.output_rate)
            defer { rb_native_mode1_destroy(state) }
            let before = try snapshot(state)
            let memory = try storage(state)
            var count = -1
            try #require(rb_native_mode1_count_blocks(state, vector.source_frames, vector.block_frames, &count) == RB_MODE1_OK)
            #expect(count == vector.total_returned)
            #expect(try snapshot(state) == before)
            #expect(try storage(state) == memory)
            #expect(vector.calls.reduce(0) { $0 + ($1.returned_frames ?? 0) } == count)
        }
    }

    @Test func PreflightFailuresLeaveStateOutputAndCountUnchanged() throws {
        let state = try make()
        defer { rb_native_mode1_destroy(state) }
        let before = try snapshot(state), memory = try storage(state)
        var samples = [Float](repeating: 0.25, count: 258)
        var output = [Float](repeating: -0.375, count: 512)
        let outputBefore = output.map(\.bitPattern)
        var returned = 12345, needed = 0
        try #require(rb_native_mode1_count(state, 129, 1, &needed) == RB_MODE1_OK && needed > 0)
        #expect(rb_native_mode1_process(state, &samples, 129, &output, needed - 1, 1, &returned) == RB_MODE1_CAPACITY)
        for bad in [Float.nan, Float.infinity, Float.leastNonzeroMagnitude] {
            samples[5] = bad
            #expect(rb_native_mode1_process(state, &samples, 129, &output, 256, 1, &returned) == RB_MODE1_SAMPLE_DOMAIN)
        }
        samples[5] = 0.25
        #expect(rb_native_mode1_process(state, &samples, 0, &output, 256, 0, &returned) == RB_MODE1_INVALID)
        #expect(rb_native_mode1_process(state, nil, 129, &output, 256, 1, &returned) == RB_MODE1_INVALID)
        #expect(rb_native_mode1_process(state, &samples, 129, &output, 256, 2, &returned) == RB_MODE1_INVALID)
        #expect(try snapshot(state) == before)
        #expect(try storage(state) == memory)
        #expect(returned == 12345 && output.map(\.bitPattern) == outputBefore)
    }

    @Test func NativeAllocationBoundaryAndRepeatedEOFRejectTransactionally() throws {
        let state = try make()
        defer { rb_native_mode1_destroy(state) }
        var input: [Float] = [0.25, -0.25]
        var output = [Float](repeating: 0.5, count: 1024)
        var returned = 99
        try #require(rb_native_mode1_process(state, &input, 1, &output, 512, 0, &returned) == RB_MODE1_OK)
        #expect(returned == 0)
        let before = try snapshot(state), memory = try storage(state)
        for n in [65474, 65535, 65536] {
            returned = 123
            #expect(rb_native_mode1_count(state, n, 1, &returned) == RB_MODE1_NATIVE_BOUNDS)
            #expect(returned == 123)
        }
        var safe = 0
        #expect(rb_native_mode1_count(state, 65473, 1, &safe) == RB_MODE1_OK)
        #expect(rb_native_mode1_count(state, 65537, 1, &safe) == RB_MODE1_OK)
        #expect(try snapshot(state) == before && (try storage(state)) == memory)
        try #require(rb_native_mode1_process(state, nil, 0, &output, 512, 1, &returned) == RB_MODE1_OK)
        let final = try snapshot(state)
        returned = 123
        #expect(rb_native_mode1_process(state, nil, 0, &output, 512, 1, &returned) == RB_MODE1_STATE)
        #expect(rb_native_mode1_process(state, &input, 1, &output, 512, 0, &returned) == RB_MODE1_STATE)
        #expect(returned == 123)
        #expect(try snapshot(state) == final)
    }

    @Test func AliasesBadRatesAndRoundingModesCannotSilentlyChangeTheAlgorithm() throws {
        for rate in [7999.0, 192001, 44100.5, Double.nan, Double.infinity] {
            var state: OpaquePointer?
            #expect(rb_native_mode1_create(44100, rate, 2, &state) == RB_MODE1_INVALID && state == nil)
        }
        let state = try make()
        defer { rb_native_mode1_destroy(state) }
        let before = try snapshot(state)
        var arena = [Float](repeating: 0.25, count: 1024)
        let original = arena.map(\.bitPattern)
        var returned = 123
        arena.withUnsafeMutableBufferPointer { values in
            #expect(rb_native_mode1_process(state, values.baseAddress, 129, values.baseAddress,
                512, 1, &returned) == RB_MODE1_INVALID)
            let aliasedCount = UnsafeMutableRawPointer(values.baseAddress!).assumingMemoryBound(to: Int.self)
            #expect(rb_native_mode1_process(state, values.baseAddress, 129, values.baseAddress! + 300,
                300, 1, aliasedCount) == RB_MODE1_INVALID)
        }
        #expect(arena.map(\.bitPattern) == original && returned == 123)
        let saved = fegetround()
        defer { _ = fesetround(saved) }
        for mode in [FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO] {
            try #require(fesetround(mode) == 0)
            #expect(rb_native_mode1_count(state, 129, 1, &returned) == RB_MODE1_INVALID)
            #expect(returned == 123)
        }
        try #require(fesetround(saved) == 0)
        #expect(try snapshot(state) == before)
    }
}
