import Foundation
import RebaseTimingDSP

/// The recovered stereo producer/consumer value operations, serialized by the
/// owning cursor. Rebase fills and drains each chunk before a host
/// schedules it; this is not the proprietary callback graph or polling policy.
final class CPRLiveStereoTransfer {
    private let left: UnsafeMutablePointer<Float>
    private let right: UnsafeMutablePointer<Float>
    private var state = rb_cpr_live_stereo_ring()

    init() throws {
        let capacity = Int(RB_CPR_LIVE_RING_CAPACITY)
        left = .allocate(capacity: capacity); right = .allocate(capacity: capacity)
        left.initialize(repeating: 0, count: capacity)
        right.initialize(repeating: 0, count: capacity)
        guard rb_cpr_live_ring_init(&state, left, right) == 0 else {
            throw RebaseCoreError.invalidProject("The stereo transfer buffer could not be initialized.")
        }
    }

    deinit { left.deallocate(); right.deallocate() }

    func copy(_ interleaved: [Float], to output: inout StereoPCMBlock) throws {
        guard interleaved.count % 2 == 0,
              output.frameCount == interleaved.count / 2 else {
            throw RebaseCoreError.invalidProject("The stereo transfer requires matching planar output storage.")
        }
        if interleaved.isEmpty { return }
        try output.withUnsafeMutableChannels { leftOutput, rightOutput in
            try interleaved.withUnsafeBufferPointer { input in
                var position = 0
                while position < interleaved.count / 2 {
                    let frames = min(8192, interleaved.count / 2 - position)
                    var result = rb_cpr_live_ring_result()
                    guard rb_cpr_live_ring_write(&state, input.baseAddress!.advanced(by: position * 2), Int32(frames)) == 0,
                          rb_cpr_live_ring_consume(&state, leftOutput.advanced(by: position),
                            rightOutput.advanced(by: position), 0, Int64(frames), 0, 0, &result) == 0,
                          result.copied_frames == frames, result.silent_frames == 0 else {
                        throw RebaseCoreError.invalidProject("The stereo transfer could not deliver the converted block.")
                    }
                    position += frames
                }
            }
        }
    }
}
