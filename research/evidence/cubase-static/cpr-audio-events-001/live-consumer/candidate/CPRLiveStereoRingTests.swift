import Foundation
import RebaseTimingDSP
import Testing

/// Application value-operation checks against an independently maintained
/// FIFO of raw sample words. No Cubase code, audio hardware or scheduling.
struct CPRLiveStereoRingTests {
    private final class Ring {
        let left = UnsafeMutablePointer<Float>.allocate(capacity: 32768)
        let right = UnsafeMutablePointer<Float>.allocate(capacity: 32768)
        var state = rb_cpr_live_stereo_ring()
        init() {
            left.initialize(repeating: Float(bitPattern: 0x3e123456), count: 32768)
            right.initialize(repeating: Float(bitPattern: 0xbe654321), count: 32768)
            precondition(rb_cpr_live_ring_init(&state, left, right) == RB_CPR_LIVE_RING_OK)
        }
        deinit {
            left.deinitialize(count: 32768); left.deallocate()
            right.deinitialize(count: 32768); right.deallocate()
        }
        func write(_ words: [UInt32]) -> Int32 {
            precondition(words.count.isMultiple(of: 2))
            let samples = words.map(Float.init(bitPattern:))
            return samples.withUnsafeBufferPointer {
                rb_cpr_live_ring_write(&state, $0.baseAddress, Int32(words.count / 2))
            }
        }
        func read(_ count: Int, start: Int64 = 0, stopped: UInt8 = 0, drain: UInt8 = 0)
            -> (Int32, [UInt32], [UInt32], rb_cpr_live_ring_result) {
            var l = [Float](repeating: 7, count: count)
            var r = [Float](repeating: -7, count: count)
            var result = rb_cpr_live_ring_result(copied_frames: -9, silent_frames: -9, timeline_frames: -9)
            let status = l.withUnsafeMutableBufferPointer { lp in
                r.withUnsafeMutableBufferPointer { rp in
                    rb_cpr_live_ring_consume(&state, lp.baseAddress, rp.baseAddress,
                        start, start + Int64(count), stopped, drain, &result)
                }
            }
            return (status, l.map(\.bitPattern), r.map(\.bitPattern), result)
        }
        var snapshot: [Int64] {
            [Int64(state.write_index), Int64(state.read_index),
             state.submitted_frames, state.timeline_frames]
        }
    }
    private func words(first: Int, count: Int) -> [UInt32] {
        var result: [UInt32] = []
        result.reserveCapacity(count * 2)
        for i in first..<(first + count) {
            // Distinct channels, signs and negative-zero positions.
            let left: UInt32 = i % 11 == 0 ? 0x80000000 : (0x3f000000 | UInt32(i & 0x7fffff))
            let right: UInt32 = i % 17 == 0 ? 0 : (0xbf000000 | UInt32((i * 3) & 0x7fffff))
            result.append(left)
            result.append(right)
        }
        return result
    }

    @Test func stereoBitOrderAndWrappingMatchIndependentFIFO() {
        let ring = Ring()
        var expectedLeft: [UInt32] = [], expectedRight: [UInt32] = []
        var submitted = 0, consumed = 0
        for n in [8192, 8192, 8192, 8192, 1, 8191, 5000, 7000, 12, 8192, 8192] {
            let input = words(first: submitted, count: n)
            #expect(ring.write(input) == RB_CPR_LIVE_RING_OK)
            expectedLeft += stride(from: 0, to: input.count, by: 2).map { input[$0] }
            expectedRight += stride(from: 1, to: input.count, by: 2).map { input[$0] }
            submitted += n
            // Absolute callback positions do not reposition the ring.
            let value = ring.read(n, start: consumed.isMultiple(of: 2) ? -1234 : 900000)
            #expect(value.0 == RB_CPR_LIVE_RING_OK)
            #expect(value.1 == Array(expectedLeft.prefix(n)))
            #expect(value.2 == Array(expectedRight.prefix(n)))
            expectedLeft.removeFirst(n); expectedRight.removeFirst(n); consumed += n
            #expect(value.3.copied_frames == n && value.3.silent_frames == 0)
            #expect(value.3.timeline_frames == consumed)
            #expect(ring.state.submitted_frames == submitted)
            #expect(ring.state.write_index == submitted % 32768)
            #expect(ring.state.read_index == consumed % 32768)
        }
        #expect(submitted > 65536)
    }

    @Test func nativeHalfCapacityGuardIsInclusiveAndAtomic() {
        let ring = Ring()
        let rejected = words(first: 0, count: 16386)
        let before = ring.snapshot
        #expect(ring.write(rejected) == RB_CPR_LIVE_RING_WOULD_BLOCK)
        #expect(ring.snapshot == before)
        #expect(ring.left[0].bitPattern == 0x3e123456)
        #expect(ring.right[0].bitPattern == 0xbe654321)
        let accepted = Array(rejected.prefix(16385 * 2))
        #expect(ring.write(accepted) == RB_CPR_LIVE_RING_OK)
        let full = ring.snapshot
        #expect(ring.write([1, 2]) == RB_CPR_LIVE_RING_WOULD_BLOCK)
        #expect(ring.snapshot == full)
        #expect(ring.read(1).0 == RB_CPR_LIVE_RING_OK)
        #expect(ring.write([0x3f000001, 0xbf000002]) == RB_CPR_LIVE_RING_OK)
        let sampleBeforeReset = ring.left[0].bitPattern
        #expect(rb_cpr_live_ring_reset(&ring.state) == RB_CPR_LIVE_RING_OK)
        #expect(ring.snapshot == [0, 0, 0, 0])
        #expect(ring.left[0].bitPattern == sampleBeforeReset)
    }

    @Test func underrunHoldDrainAndStopRemainDistinct() {
        let ring = Ring(), input = words(first: 7, count: 3)
        #expect(ring.write(input) == RB_CPR_LIVE_RING_OK)
        let before = ring.snapshot
        let hold = ring.read(4)
        #expect(hold.0 == RB_CPR_LIVE_RING_OK && hold.1 == [0, 0, 0, 0] && hold.2 == hold.1)
        #expect(hold.3.copied_frames == 0 && hold.3.silent_frames == 4)
        #expect(ring.snapshot == before)
        let stop = ring.read(2, stopped: 1)
        #expect(stop.1 == [0, 0] && stop.2 == [0, 0])
        #expect(ring.state.read_index == 0 && ring.state.timeline_frames == 2)
        let drain = ring.read(4, drain: 1)
        #expect(drain.1 == [input[0], input[2], input[4], 0])
        #expect(drain.2 == [input[1], input[3], input[5], 0])
        #expect(drain.3.copied_frames == 3 && drain.3.silent_frames == 1)
        #expect(ring.snapshot == [3, 3, 3, 6])
        let emptyDrain = ring.read(2, drain: 1)
        #expect(emptyDrain.1 == [0, 0] && emptyDrain.3.timeline_frames == 8)
        let emptyHold = ring.read(2)
        #expect(emptyHold.3.timeline_frames == 8)
    }

    @Test func rejectedCountsAliasingAndOverflowPreserveAllDestinations() {
        let ring = Ring()
        #expect(ring.write(words(first: 1, count: 3)) == RB_CPR_LIVE_RING_OK)
        let before = ring.snapshot, oldSample = ring.left[0].bitPattern
        var output = [Float](repeating: 9, count: 8)
        var result = rb_cpr_live_ring_result(copied_frames: -1, silent_frames: -2, timeline_frames: -3)
        #expect(rb_cpr_live_ring_write(&ring.state, ring.left, 1) == RB_CPR_LIVE_RING_ALIAS)
        #expect(rb_cpr_live_ring_write(&ring.state, nil, -1) == RB_CPR_LIVE_RING_RANGE)
        output.withUnsafeMutableBufferPointer { p in
            #expect(rb_cpr_live_ring_consume(&ring.state, p.baseAddress, p.baseAddress,
                0, 2, 0, 0, &result) == RB_CPR_LIVE_RING_ALIAS)
            #expect(rb_cpr_live_ring_consume(&ring.state, ring.left, p.baseAddress,
                0, 2, 0, 0, &result) == RB_CPR_LIVE_RING_ALIAS)
            for (start, end) in [(Int64.min, Int64.max), (3, 2), (0, 32769)] {
                #expect(rb_cpr_live_ring_consume(&ring.state, p.baseAddress, p.baseAddress! + 4,
                    start, end, 0, 0, &result) == RB_CPR_LIVE_RING_RANGE)
            }
            #expect(rb_cpr_live_ring_consume(&ring.state, p.baseAddress, p.baseAddress! + 4,
                0, 2, 2, 0, &result) == RB_CPR_LIVE_RING_RANGE)
            ring.state.timeline_frames = Int64.max
            #expect(rb_cpr_live_ring_consume(&ring.state, p.baseAddress, p.baseAddress! + 4,
                0, 2, 0, 0, &result) == RB_CPR_LIVE_RING_RANGE)
            ring.state.timeline_frames = before[3]
        }
        ring.state.submitted_frames = Int64.max
        #expect(ring.write([1, 2]) == RB_CPR_LIVE_RING_RANGE)
        ring.state.submitted_frames = before[2]
        #expect(output == Array(repeating: 9, count: 8))
        #expect(result.copied_frames == -1 && result.silent_frames == -2 && result.timeline_frames == -3)
        #expect(ring.snapshot == before && ring.left[0].bitPattern == oldSample)
    }

    @Test func zeroLengthAndInvalidInitializationAreExplicit() {
        let ring = Ring()
        var result = rb_cpr_live_ring_result()
        #expect(rb_cpr_live_ring_write(&ring.state, nil, 0) == RB_CPR_LIVE_RING_OK)
        #expect(rb_cpr_live_ring_consume(&ring.state, nil, nil, Int64.min, Int64.min,
            0, 0, &result) == RB_CPR_LIVE_RING_OK)
        #expect(result.copied_frames == 0 && result.silent_frames == 0 && result.timeline_frames == 0)
        let oldLeft = ring.state.left
        #expect(rb_cpr_live_ring_init(&ring.state, ring.left, ring.left) == RB_CPR_LIVE_RING_ALIAS)
        #expect(ring.state.left == oldLeft)
        ring.state.read_index = -1
        #expect(rb_cpr_live_ring_write(&ring.state, nil, 0) == RB_CPR_LIVE_RING_RANGE)
        #expect(rb_cpr_live_ring_reset(&ring.state) == RB_CPR_LIVE_RING_OK)
        #expect(ring.snapshot == [0, 0, 0, 0])
    }
}
