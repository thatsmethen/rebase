import Testing
import RebaseDSP

// These are application integration tests of the bounded recovered kernel.
// They are not comparisons against an executing Reference plug-in.
final class RecoveredDSPTests {
    private func run<T>(_ planes: [[T]], sentinel: T, direction: Double = 0,
                        present: UInt32 = 1, bypass: UInt32 = 0, silence: UInt64 = 0,
                        overlap: Bool = false,
                        kernel: (UnsafePointer<ambi_input>?, Int, UnsafePointer<ambi_output>?, Int,
                                 UnsafePointer<ambi_options>?) -> Int32) -> (Int32, [[T]]) {
        let frames = planes[0].count
        let inputs = planes.map { plane -> UnsafeMutablePointer<T> in
            let pointer = UnsafeMutablePointer<T>.allocate(capacity: frames)
            for n in plane.indices { pointer.advanced(by: n).initialize(to: plane[n]) }
            return pointer
        }
        let outputs = planes.map { _ -> UnsafeMutablePointer<T> in
            let pointer = UnsafeMutablePointer<T>.allocate(capacity: frames)
            pointer.initialize(repeating: sentinel, count: frames)
            return pointer
        }
        defer {
            for pointer in inputs + outputs { pointer.deinitialize(count: frames); pointer.deallocate() }
        }
        let inputDescriptors = inputs.map { ambi_input(samples: UnsafeRawPointer($0), frames: frames) }
        var outputDescriptors = outputs.map { ambi_output(samples: UnsafeMutableRawPointer($0), frames: frames) }
        if overlap { outputDescriptors[0].samples = UnsafeMutableRawPointer(inputs[0]) }
        var options = ambi_options(direction: direction, direction_present: present, bypass: bypass, input_silence_flags: silence)
        let result = inputDescriptors.withUnsafeBufferPointer { input in
            outputDescriptors.withUnsafeBufferPointer { output in
                kernel(input.baseAddress, input.count, output.baseAddress, output.count, &options)
            }
        }
        return (result, outputs.map { Array(UnsafeBufferPointer(start: $0, count: frames)) })
    }

    @Test func testFloat32ExactCoefficientsAndThresholdPermutation() {
        let input: [[Float]] = [[1], [0.25], [0.5], [0.75]]
        let low = run(input, sentinel: -1, direction: 0.5.nextDown, kernel: ambi_first_order_f32)
        let high = run(input, sentinel: -1, direction: 0.5, kernel: ambi_first_order_f32)
        expectEqual(low.0, Int32(AMBI_OK.rawValue))
        expectEqual(high.0, Int32(AMBI_OK.rawValue))
        expectEqual(low.1.map { $0[0].bitPattern }, [0x3fb504f3, 0x3f000000, 0x3f400000, 0x3e800000])
        expectEqual(high.1.map { $0[0].bitPattern }, [0x3f3504f3, 0x3f400000, 0x3e800000, 0x3f000000])
    }

    @Test func testFloat64RetainsObservedOneULPInverseDifference() {
        let input: [[Double]] = [[1], [0.25], [0.5], [0.75]]
        let low = run(input, sentinel: -1, direction: 0, kernel: ambi_first_order_f64)
        let high = run(input, sentinel: -1, direction: 1, kernel: ambi_first_order_f64)
        expectEqual(low.0, Int32(AMBI_OK.rawValue))
        expectEqual(high.0, Int32(AMBI_OK.rawValue))
        expectEqual(low.1.map { $0[0].bitPattern }, [0x3ff6a09e667f3bcd, 0x3fe0000000000000, 0x3fe8000000000000, 0x3fd0000000000000])
        expectEqual(high.1.map { $0[0].bitPattern }, [0x3fe6a09e667f3bcc, 0x3fe8000000000000, 0x3fd0000000000000, 0x3fe0000000000000])
        expectNotEqual(high.1[0][0].bitPattern, Double(0.5).squareRoot().bitPattern)
    }

    @Test func testFourFrameBasisIsScatteredWithSignedZeroPreserved() {
        let input: [[Float]] = [[0.125, -0.0, 0, 0], [0, 0.25, 0, 0], [0, 0, 0.5, 0], [0, 0, 0, 0.75]]
        let result = run(input, sentinel: -1, direction: 0, kernel: ambi_first_order_f32)
        expectEqual(result.0, Int32(AMBI_OK.rawValue))
        expectEqual(result.1[0].map(\.bitPattern), [0x3e3504f3, 0x80000000, 0, 0])
        expectEqual(result.1[1], [0, 0, 0.5, 0])
        expectEqual(result.1[2], [0, 0, 0, 0.75])
        expectEqual(result.1[3], [0, 0.25, 0, 0])
    }

    @Test func testRejectedStateDomainAndAliasingDoNotWriteOutputs() {
        let input = Array(repeating: [Float(0.25), 0.5], count: 4)
        let expected = Array(repeating: [Float(-0.75), -0.75], count: 4)
        let cases = [run(input, sentinel: -0.75, direction: .nan, kernel: ambi_first_order_f32),
                     run(input, sentinel: -0.75, present: 0, kernel: ambi_first_order_f32),
                     run(input, sentinel: -0.75, bypass: 1, kernel: ambi_first_order_f32),
                     run(input, sentinel: -0.75, silence: 1, kernel: ambi_first_order_f32)]
        for result in cases {
            expectEqual(result.0, Int32(AMBI_UNSUPPORTED_STATE.rawValue))
            expectEqual(result.1, expected)
        }
        var invalid = input
        invalid[3][1] = .infinity
        let domain = run(invalid, sentinel: -0.75, kernel: ambi_first_order_f32)
        expectEqual(domain.0, Int32(AMBI_SAMPLE_DOMAIN.rawValue))
        expectEqual(domain.1, expected)
        let alias = run(input, sentinel: -0.75, overlap: true, kernel: ambi_first_order_f32)
        expectEqual(alias.0, Int32(AMBI_OVERLAP.rawValue))
        expectEqual(alias.1, expected)
    }
}
