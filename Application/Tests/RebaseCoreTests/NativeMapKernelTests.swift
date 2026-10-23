import Testing
import Foundation
import CryptoKit
import RebaseTimingDSP

private let mapKernelRoot = PrivateResearchFixtures.root
private let mapKernelGoldens = mapKernelRoot.appendingPathComponent(
    "evidence/cpr-static/cpr-map-clock-001/oracle-iterator/map-clock-goldens.json")

final class NativeMapKernelTests {
    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func detachedMapArithmeticMatchesIndependentBits() throws {
        let bytes = try Data(contentsOf: mapKernelGoldens)
        #expect(SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
                == "98b3922f598f57e51e961252a61a6503c67cead5b8d17605024e2bedc202795c")
        let object = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let maps = try #require(object["maps"] as? [String: [[String: Any]]])
        let vectors = try #require(object["vectors"] as? [[String: Any]])
        #expect(vectors.count == 105)
        func bits(_ value: Any?) throws -> UInt64 {
            let value = try #require(value as? String)
            return try #require(UInt64(value.dropFirst(2), radix: 16))
        }
        for vector in vectors {
            let name = try #require(vector["map"] as? String)
            let rows = try #require(maps[name])
            let points = try rows.map {
                rb_native_jump_point(period_bits: UInt32(try bits($0["period_f32_bits"])),
                                     seconds: Double(bitPattern: try bits($0["seconds_f64_bits"])),
                                     ticks: Double(bitPattern: try bits($0["ticks_f64_bits"])))
            }
            let input = Double(bitPattern: try bits(vector["input_f64_bits"]))
            var output = -12345.25
            let forward = try #require(vector["direction"] as? String) == "seconds_to_ticks"
            let status = points.withUnsafeBufferPointer {
                forward ? rb_native_map_ticks($0.baseAddress, UInt32($0.count), input, &output)
                        : rb_native_map_seconds($0.baseAddress, UInt32($0.count), input, &output)
            }
            #expect(status == 0)
            #expect(output.bitPattern == (try bits(vector["result_f64_bits"])))
        }
    }

    @Test func canonicalValidationRejectsOneULPWithoutRewritingDetachedAnchors() {
        let origin = rb_native_jump_point(period_bits: 0x3f400000, seconds: 0, ticks: 0)
        let valid = [origin, rb_native_jump_point(period_bits: 0x3f000000, seconds: 600, ticks: 384000)]
        #expect(valid.withUnsafeBufferPointer { rb_native_map_validate($0.baseAddress, 2) } == 0)
        for seconds in [Double(600).nextDown, Double(600).nextUp] {
            let points = [origin, rb_native_jump_point(period_bits: 0x3f000000, seconds: seconds, ticks: 384000)]
            #expect(points.withUnsafeBufferPointer { rb_native_map_validate($0.baseAddress, 2) } != 0)
            var result = 0.0
            #expect(points.withUnsafeBufferPointer { rb_native_map_seconds($0.baseAddress, 2, 384000, &result) } == 0)
            #expect(result.bitPattern == seconds.bitPattern) // Detached primitive preserves supplied A.
        }
    }

    @Test func malformedMapInputsFailBeforeWriteAndZeroRetainsNativeSigns() {
        let points = [rb_native_jump_point(period_bits: 0x3f000000, seconds: 0, ticks: 0)]
        for input in [Double.nan, .infinity, -1, .leastNonzeroMagnitude] {
            var forward = -12345.25, inverse = -12345.25
            #expect(points.withUnsafeBufferPointer { rb_native_map_ticks($0.baseAddress, 1, input, &forward) } != 0)
            #expect(points.withUnsafeBufferPointer { rb_native_map_seconds($0.baseAddress, 1, input, &inverse) } != 0)
            #expect(forward == -12345.25 && inverse == -12345.25)
        }
        for count: UInt32 in [0, 3, .max] {
            var output = -12345.25
            #expect(points.withUnsafeBufferPointer { rb_native_map_ticks($0.baseAddress, count, 1, &output) } != 0)
            #expect(output == -12345.25)
        }
        var forward = 1.0, inverse = 1.0
        #expect(points.withUnsafeBufferPointer { rb_native_map_ticks($0.baseAddress, 1, -0.0, &forward) } == 0)
        #expect(points.withUnsafeBufferPointer { rb_native_map_seconds($0.baseAddress, 1, -0.0, &inverse) } == 0)
        #expect(forward.bitPattern == 0x8000000000000000)
        #expect(inverse.bitPattern == 0)
    }
}
