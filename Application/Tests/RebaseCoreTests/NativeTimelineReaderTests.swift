import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Exact independent Fraction/IEEE controls for already-bound reader values.
/// No provider, source coordinate interpretation or Reference execution is supplied.
@Suite(.serialized)
struct NativeTimelineReaderTests {
    private struct Quantizer: Decodable {
        let period_bits, coordinate_bits: String
        let expected: Decimal
        let signed64_representable, fma_discriminator, narrowing_discriminator: Bool
    }
    private struct Partition: Decodable {
        let start_bits, end_bits: String
        let remaining: Int32
        let flags: UInt32
        let start, end, frames: Int64
        let silence, separate_endpoint_difference: Bool
    }
    private struct Window: Decodable {
        let request_start, request_end, cursor: Int64
        let descriptor_bits: [String]?
        let expected: [String: Int64]
    }
    private struct Read: Decodable {
        let request, returned, action, native: Int32
        let begin, segment: Int64
        let retried: UInt32
    }
    private struct Oracle: Decodable {
        let generator_sha256: String
        let quantizers: [Quantizer]
        let partitions: [Partition]
        let windows: [Window]
        let reads: [Read]
    }
    private func oracle() throws -> Oracle {
        let folder = PrivateResearchFixtures.root
            .appendingPathComponent("evidence/application/APP014")
        let data = try Data(contentsOf: folder.appendingPathComponent("timeline-reader-oracle.json"))
        #expect(cprSHA256(data) == "0df450ef24e5124574b720c7eeb020cd9136f3267f037ad8808426faa34641cf")
        let decoded = try JSONDecoder().decode(Oracle.self, from: data)
        #expect(decoded.generator_sha256 == "b67e58e68583f34422915bc0a1b2a42c6226b3d71bdc4a8684c2b347964272e2")
        #expect(cprSHA256(try Data(contentsOf: folder.appendingPathComponent("timeline-reader-oracle.py"))) == decoded.generator_sha256)
        return decoded
    }
    private func value(_ bits: String) -> Double { Double(bitPattern: UInt64(bits, radix: 16)!) }
    private func words<T>(_ object: T) -> Data {
        var copy = object
        return withUnsafeBytes(of: &copy) { Data($0) }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func NarrowedReciprocalFusedQuantizationMatchesIndependentRounding() throws {
        let data = try oracle()
        #expect(data.quantizers.count == 254)
        #expect(data.quantizers.filter(\.fma_discriminator).count == 19)
        #expect(data.quantizers.filter(\.narrowing_discriminator).count == 15)
        for row in data.quantizers {
            var result: Int64 = 0x12345678
            let status = rb_cpr_timeline_quantize(value(row.period_bits), value(row.coordinate_bits), &result)
            if row.signed64_representable {
                #expect(status == RB_TIMELINE_OK)
                #expect(Decimal(result) == row.expected, "\(row.period_bits):\(row.coordinate_bits)")
            } else {
                #expect(status == RB_TIMELINE_RANGE && result == 0x12345678)
            }
        }
        // Unlike signed nearest rounding, descriptor quantization always adds +.5.
        var minusOne: Int64 = 99
        #expect(rb_cpr_timeline_quantize(1, -1, &minusOne) == RB_TIMELINE_OK && minusOne == 0)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func MappedPartitionsRoundLengthSeparatelyAndRespectSilenceBit() throws {
        let data = try oracle()
        #expect(data.partitions.count == 560)
        #expect(data.partitions.filter(\.separate_endpoint_difference).count == 176)
        for row in data.partitions {
            var result = RBTimelinePartition()
            #expect(rb_cpr_timeline_partition(value(row.start_bits), value(row.end_bits),
                row.remaining, row.flags, &result) == RB_TIMELINE_OK)
            #expect(result.frames == row.frames && (result.silence != 0) == row.silence)
            if !row.silence {
                #expect(result.startFrame == row.start && result.endFrame == row.end)
            }
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func IntegerWindowsCoverGapsInclusiveSelectionAndHalfOpenReads() throws {
        let data = try oracle()
        #expect(data.windows.count == 110)
        for (index, row) in data.windows.enumerated() {
            var result = RBTimelinePlan()
            let status: Int32
            if let bits = row.descriptor_bits {
                var descriptor = RBTimelineSegment(start: value(bits[0]), end: value(bits[1]), sourceOffset: value(bits[2]))
                status = rb_cpr_timeline_plan(row.request_start, row.request_end, row.cursor, 1, &descriptor, &result)
            } else {
                status = rb_cpr_timeline_plan(row.request_start, row.request_end, row.cursor, 1, nil, &result)
            }
            #expect(status == RB_TIMELINE_OK)
            let actual: [String: Int64] = [
                "action": Int64(result.action), "fields": Int64(result.quantizedFields),
                "stop": Int64(result.stopAfter), "next": result.nextCursor,
                "silence_frames": result.silenceFrames, "read_frames": result.readFrames,
                "segment_start": result.segmentStart, "segment_end": result.segmentEnd,
                "segment_offset": result.segmentOffset, "silence_offset": result.silenceOffset,
                "skip": Int64(result.skipReason), "read_offset": result.readOffset,
                "read_begin": result.readBegin, "source_seek": result.sourceSeek,
                "retry": Int64(result.retryAtSegmentStart)]
            for (key, expected) in row.expected {
                #expect(actual[key] == expected, "window \(index), \(key)")
            }
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func RetryRequiresExactStartAndOccursOnlyOnceWithoutReinterpretingErrors() throws {
        let data = try oracle()
        #expect(data.reads.count == 126)
        for row in data.reads {
            var result = RBTimelineReadDecision()
            #expect(rb_cpr_timeline_read_result(row.request, row.begin, row.segment,
                row.retried, row.returned, &result) == RB_TIMELINE_OK)
            #expect(result.action == row.action && result.nativeResult == row.native)
        }
        var result = RBTimelineReadDecision(action: 71, nativeResult: 72)
        for (request, retried) in [(Int32(0), UInt32(0)), (-1, 0), (16_000_001, 0), (1, 2)] {
            #expect(rb_cpr_timeline_read_result(request, 0, 0, retried, 0, &result) == RB_TIMELINE_INVALID)
            #expect(result.action == 71 && result.nativeResult == 72)
        }
    }

    @Test func UnsupportedArithmeticBoundsAndAliasesPreserveCallerOutput() throws {
        var quantized: Int64 = 73
        for (period, coordinate) in [(0.0, 1.0), (-1, 1), (.infinity, 1),
                                    (.nan, 1), (1, .nan), (1, .infinity),
                                    (Double.leastNonzeroMagnitude, 1), (1, Double.leastNonzeroMagnitude)] {
            #expect(rb_cpr_timeline_quantize(period, coordinate, &quantized) == RB_TIMELINE_INVALID)
            #expect(quantized == 73)
        }
        for period in [Double.leastNormalMagnitude, Double.greatestFiniteMagnitude] {
            #expect(rb_cpr_timeline_quantize(period, 1, &quantized) == RB_TIMELINE_RANGE)
            #expect(quantized == 73)
        }
        var plan = RBTimelinePlan()
        plan.action = 71; plan.sourceSeek = 72
        let initial = words(plan)
        for (start, end, cursor) in [(Int64(2), Int64(1), Int64(2)), (0, 1, -1),
                                     (0, 1, 2), (0, 16_000_001, 0), (.min, .max, 0)] {
            #expect(rb_cpr_timeline_plan(start, end, cursor, 1, nil, &plan) != 0)
            #expect(words(plan) == initial)
        }
        // Source seek must be checked even when request bounds themselves fit.
        var excessive = RBTimelineSegment(start: -0x1p63, end: 16, sourceOffset: 0)
        #expect(rb_cpr_timeline_plan(0, 16, 1, 1, &excessive, &plan) == RB_TIMELINE_RANGE)
        #expect(words(plan) == initial)
        let allocation = UnsafeMutableRawPointer.allocate(byteCount: MemoryLayout<RBTimelinePlan>.stride, alignment: 8)
        defer { allocation.deallocate() }
        allocation.initializeMemory(as: UInt8.self, repeating: 0xa5, count: MemoryLayout<RBTimelinePlan>.stride)
        let alias = allocation.assumingMemoryBound(to: RBTimelineSegment.self)
        alias.pointee = RBTimelineSegment(start: 0, end: 2, sourceOffset: 0)
        let before = Data(bytes: allocation, count: MemoryLayout<RBTimelinePlan>.stride)
        #expect(rb_cpr_timeline_plan(0, 2, 0, 1, alias,
            allocation.assumingMemoryBound(to: RBTimelinePlan.self)) == RB_TIMELINE_INVALID)
        #expect(Data(bytes: allocation, count: MemoryLayout<RBTimelinePlan>.stride) == before)
        let saved = fegetround()
        defer { _ = fesetround(saved) }
        for mode in [FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO] {
            #expect(fesetround(mode) == 0)
            #expect(rb_cpr_timeline_quantize(1, 1, &quantized) == RB_TIMELINE_FP_ENVIRONMENT)
            #expect(rb_cpr_timeline_plan(0, 1, 0, 1, nil, &plan) == RB_TIMELINE_FP_ENVIRONMENT)
            #expect(quantized == 73 && words(plan) == initial)
        }
    }
}
