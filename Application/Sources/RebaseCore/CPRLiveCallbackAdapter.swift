import RebaseTimingDSP

/// The recovered audition Float32 adapter's output stage. Rebase supplies its
/// own converted-buffer partitions and no transport prefix. Native callback
/// window/latency/transport state are not inferred from the local cursor.
enum CPRLiveCallbackAdapter {
    static func process(_ buffer: inout StereoPCMBlock) throws {
        guard buffer.frameCount > 0, buffer.frameCount <= Int32.max else {
            throw RebaseCoreError.unsupportedAudio("The source callback requires a nonempty planar stereo buffer.")
        }
        let frames = buffer.frameCount
        try buffer.withUnsafeMutableChannels { left, right in
            try process(left: left, right: right, frames: frames, capacity: frames)
        }
    }

    private static func process(left: UnsafeMutablePointer<Float>, right: UnsafeMutablePointer<Float>,
                                frames: Int, capacity: Int) throws {
        let planes: [UnsafeMutablePointer<Float>?] = [left, right]
        var result = RBCallbackPostResult()
        let status = planes.withUnsafeBufferPointer {
            rb_native_callback_postprocess_f32($0.baseAddress, 2,
                Int32(frames), Int32(capacity), 0, 0, &result)
        }
        guard status == 0 else {
            throw RebaseCoreError.unsupportedAudio("The source callback could not preserve its supported sample and rounding contract. Playback stopped.")
        }
    }
}

#if canImport(AVFoundation) && !REBASE_PORTABLE
import AVFoundation

extension CPRLiveCallbackAdapter {
    static func process(_ buffer: AVAudioPCMBuffer) throws {
        guard buffer.format.commonFormat == .pcmFormatFloat32,
              buffer.format.channelCount == 2, !buffer.format.isInterleaved,
              buffer.frameLength > 0, buffer.frameCapacity <= Int32.max,
              let channels = buffer.floatChannelData else {
            throw RebaseCoreError.unsupportedAudio("The source callback requires a nonempty planar stereo buffer.")
        }
        try process(left: channels[0], right: channels[1], frames: Int(buffer.frameLength),
                    capacity: Int(buffer.frameCapacity))
    }
}
#endif
