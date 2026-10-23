import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Independent integer/Fraction IEEE controls for explicit callback values.
/// These do not supply a Cubase scheduler, transport state or block partition.
@Suite(.serialized)
struct NativeCallbackAdapterTests {
    private let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private struct Window: Decodable {
        let position: Int64
        let offset_bits, rate_bits: String
        let frames: Int32
        let valid: Bool
        // Out-of-range analytical values are not decoded into signed64.
        let start, end: Decimal
        let fma_discriminator: Bool
    }
    private struct Offset: Decodable {
        let frames: Int32
        let rate_bits, expected_bits: String
    }
    private struct Prefix: Decodable {
        let start, end, boundary: Int64
        let transport, expected: Int32
        let whole: UInt8
    }
    private struct Planes: Decodable {
        let name: String
        let frames, capacity, offset, prefix: Int32
        let input_bits: [[String]]
        let output_bits: [[String]]?
        let action: Int32
        let valid: Bool
    }
    private struct Oracle: Decodable {
        let generator_sha256: String
        let windows: [Window]
        let offsets: [Offset]
        let prefixes: [Prefix]
        let postprocess: [Planes]
    }
    private func oracle() throws -> Oracle {
        let folder = root.appendingPathComponent("research/evidence/application/APP013")
        let data = try Data(contentsOf: folder.appendingPathComponent("callback-adapter-oracle.json"))
        #expect(cprSHA256(data) == "47fbe487b5665fbf211b0b097f744f9c70f17bf5ebf37b41ccadf617b9aeb923")
        let result = try JSONDecoder().decode(Oracle.self, from: data)
        #expect(result.generator_sha256 == "8d96b89ea9494e0a0d31faf64e7118d5b1949ef2e88f8787c81005f4cd50f483")
        #expect(cprSHA256(try Data(contentsOf: folder.appendingPathComponent("callback-adapter-oracle.py"))) == result.generator_sha256)
        return result
    }
    private func value(_ bits: String) -> Double {
        Double(bitPattern: UInt64(bits, radix: 16)!)
    }
    private func withPlanes<T>(_ words: [[UInt32]], _ body: ([UnsafeMutablePointer<Float>?]) throws -> T) rethrows -> T {
        let pointers = words.map { channel -> UnsafeMutablePointer<Float>? in
            let pointer = UnsafeMutablePointer<Float>.allocate(capacity: channel.count)
            for index in channel.indices { pointer.advanced(by: index).initialize(to: Float(bitPattern: channel[index])) }
            return pointer
        }
        defer {
            for (index, pointer) in pointers.enumerated() {
                pointer!.deinitialize(count: words[index].count); pointer!.deallocate()
            }
        }
        return try body(pointers)
    }
    private func words(_ pointers: [UnsafeMutablePointer<Float>?], capacity: Int) -> [[UInt32]] {
        pointers.map { pointer in (0..<capacity).map { pointer![$0].bitPattern } }
    }

    @Test func FusedWindowAndSeparateReciprocalOffsetMatchIndependentIEEEValues() throws {
        let expected = try oracle()
        // Twelve deliberately searched controls plus four independently
        // discriminating near-half/integer boundary cases in the base grid.
        #expect(expected.windows.filter(\.fma_discriminator).count == 16)
        for row in expected.windows {
            var result = RBCallbackWindow(startFrame: 111, endFrame: 222)
            let status = rb_native_callback_window(row.position, value(row.offset_bits), value(row.rate_bits), row.frames, &result)
            if row.valid {
                #expect(status == RB_NATIVE_CALLBACK_OK)
                #expect(Decimal(result.startFrame) == row.start && Decimal(result.endFrame) == row.end)
            } else {
                #expect(status == RB_NATIVE_CALLBACK_RANGE)
                #expect(result.startFrame == 111 && result.endFrame == 222)
            }
        }
        for row in expected.offsets {
            var result = Double.nan
            #expect(rb_native_callback_offset_from_frames(row.frames, value(row.rate_bits), &result) == RB_NATIVE_CALLBACK_OK)
            #expect(result.bitPattern == UInt64(row.expected_bits, radix: 16))
        }
    }

    @Test func AdmissionUsesBitZeroButPrefixUsesWholeNonzeroTransportResult() throws {
        for present: Int32 in [0, 1, -1] {
            for transport: Int32 in [0, 1, 2, 3, -1, -2, .min] {
                for forced: Int32 in [0, 1, -1] {
                    let expected = present != 0 && (transport & 1 != 0 || forced != 0)
                    #expect((rb_native_callback_enabled(present, transport, forced) != 0) == expected)
                }
            }
        }
        for row in try oracle().prefixes {
            var window = RBCallbackWindow(startFrame: row.start, endFrame: row.end)
            var result: Int32 = -99
            #expect(rb_native_callback_prefix(&window, row.transport, row.whole, row.boundary, &result) == RB_NATIVE_CALLBACK_OK)
            #expect(result == row.expected)
        }
        var overflow = RBCallbackWindow(startFrame: .min, endFrame: .min + 16)
        var untouched: Int32 = 19
        #expect(rb_native_callback_prefix(&overflow, 2, 0, .max, &untouched) == RB_NATIVE_CALLBACK_RANGE)
        #expect(untouched == 19)
        #expect(rb_native_callback_prefix(&overflow, 0, 0, .max, &untouched) == RB_NATIVE_CALLBACK_OK && untouched == 0)
    }

    @Test func SentinelSelectionAlternatingRoundingAndPrefixOrderingMatchExactBits() throws {
        for row in try oracle().postprocess {
            let input = row.input_bits.map { $0.map { UInt32($0, radix: 16)! } }
            withPlanes(input) { pointers in
                var result = RBCallbackPostResult(action: 91, prefixFrames: 92)
                let status = pointers.withUnsafeBufferPointer {
                    rb_native_callback_postprocess_f32($0.baseAddress, Int32(pointers.count),
                        row.frames, row.capacity, row.offset, row.prefix, &result)
                }
                if row.valid {
                    #expect(status == RB_NATIVE_CALLBACK_OK, "\(row.name)")
                    #expect(result.action == row.action && result.prefixFrames == row.prefix)
                    #expect(words(pointers, capacity: Int(row.capacity)) ==
                        row.output_bits!.map { $0.map { UInt32($0, radix: 16)! } }, "\(row.name)")
                } else {
                    #expect(status == RB_NATIVE_CALLBACK_UNSUPPORTED_SAMPLES)
                    #expect(result.action == 91 && result.prefixFrames == 92)
                    #expect(words(pointers, capacity: Int(row.capacity)) == input)
                }
            }
        }
    }

    @Test func AliasesBadRangesAndRoundingRejectBeforeAnyPublication() throws {
        let original: [[UInt32]] = [[0x3e800000, 1, 0x3f123456, 0x80000000],
                                   [0xbe800000, 0, 0x3f654321, 0]]
        withPlanes(original) { pointers in
            var result = RBCallbackPostResult(action: 91, prefixFrames: 92)
            let invalid: [(Int32, Int32, Int32, Int32)] =
                [(0, 4, 0, 0), (5, 4, 0, 0), (2, 4, -1, 0), (2, 4, 0, -1), (2, 4, 0, 3), (2, 4, 4, 1)]
            for (frames, capacity, offset, prefix) in invalid {
                pointers.withUnsafeBufferPointer {
                    #expect(rb_native_callback_postprocess_f32($0.baseAddress, 2, frames, capacity,
                        offset, prefix, &result) == RB_NATIVE_CALLBACK_INVALID)
                }
            }
            let aliases = [pointers[0], pointers[0]]
            aliases.withUnsafeBufferPointer {
                #expect(rb_native_callback_postprocess_f32($0.baseAddress, 2, 2, 4, 0, 0, &result) == RB_NATIVE_CALLBACK_ALIAS)
            }
            pointers.withUnsafeBufferPointer {
                let aliasedResult = UnsafeMutableRawPointer(pointers[0]!).assumingMemoryBound(to: RBCallbackPostResult.self)
                #expect(rb_native_callback_postprocess_f32($0.baseAddress, 2, 2, 4, 0, 0, aliasedResult) == RB_NATIVE_CALLBACK_ALIAS)
            }
            let saved = fegetround()
            defer { _ = fesetround(saved) }
            for mode in [FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO] {
                #expect(fesetround(mode) == 0)
                pointers.withUnsafeBufferPointer {
                    #expect(rb_native_callback_postprocess_f32($0.baseAddress, 2, 2, 4, 0, 0, &result) == RB_NATIVE_CALLBACK_FP_ENVIRONMENT)
                }
            }
            #expect(fesetround(saved) == 0)
            #expect(result.action == 91 && result.prefixFrames == 92)
            #expect(words(pointers, capacity: 4) == original)
        }
        for rate in [0.0, 0.5, Double.infinity, Double.nan] {
            var result = RBCallbackWindow(startFrame: 91, endFrame: 92)
            #expect(rb_native_callback_window(0, 0, rate, 1, &result) == RB_NATIVE_CALLBACK_INVALID)
            #expect(result.startFrame == 91 && result.endFrame == 92)
        }
    }
}
