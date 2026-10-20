import AVFoundation
import RebaseTimingDSP

/// The recovered audition Float32 adapter's output stage. Rebase supplies its
/// own converted-buffer partitions and no transport prefix. Native callback
/// window/latency/transport state are not inferred from the local cursor.
enum CPRLiveCallbackAdapter {
    static func process(_ buffer: AVAudioPCMBuffer) throws {
        guard buffer.format.commonFormat == .pcmFormatFloat32,
              buffer.format.channelCount == 2, !buffer.format.isInterleaved,
              buffer.frameLength > 0, buffer.frameCapacity <= Int32.max,
              let channels = buffer.floatChannelData else {
            throw RebaseCoreError.unsupportedAudio("The source callback requires a nonempty planar stereo buffer.")
        }
        let planes: [UnsafeMutablePointer<Float>?] = [channels[0], channels[1]]
        var result = RBCallbackPostResult()
        let status = planes.withUnsafeBufferPointer {
            rb_native_callback_postprocess_f32($0.baseAddress, 2,
                Int32(buffer.frameLength), Int32(buffer.frameCapacity), 0, 0, &result)
        }
        guard status == 0 else {
            throw RebaseCoreError.unsupportedAudio("The source callback could not preserve its supported sample and rounding contract. Playback stopped.")
        }
    }
}
