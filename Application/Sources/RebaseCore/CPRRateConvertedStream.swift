import AVFoundation
import Foundation
import RebaseTimingDSP

/// Explicit mode-0 stereo conversion of an immutable, verified source snapshot.
/// Source PCM remains resident; only the converted queue is bounded. Neither the
/// backend choice, queue size, downsample memory layout/partitions nor
/// reset-and-preroll seeking is a native host claim.
struct CPRRateConvertedStream {
    static let inputBlockFrames = 8192
    let source: [Float]
    let format: AVAudioFormat
    let frameCount: Int64
    let gain: Float
    enum ConverterState {
        case up(RBMode0State)
        case down(RBMode0DownState)
    }
    let initialState: ConverterState

    static func unavailableReason(sourceRate: Double, outputRate: Double) -> String? {
        guard sourceRate.isFinite, outputRate.isFinite,
              sourceRate.rounded() == sourceRate, outputRate.rounded() == outputRate,
              (8000...192000).contains(sourceRate), (8000...192000).contains(outputRate),
              sourceRate != outputRate else {
            return "Native mode 0 requires different integral source and project rates between 8 and 192 kHz. Use original-rate audition when the rates match."
        }
        return nil
    }

    init(source: [Float], sourceRate: Double, outputRate: Double, gain: Float) throws {
        if let reason = Self.unavailableReason(sourceRate: sourceRate, outputRate: outputRate) {
            throw RebaseCoreError.unsupportedAudio(reason)
        }
        guard !source.isEmpty, source.count % 2 == 0, source.count <= 32_000_000,
              gain.isFinite, gain > 0 else { throw RebaseCoreError.mediaTooLarge }
        let state: ConverterState
        var count = 0
        if sourceRate < outputRate {
            var up = RBMode0State()
            guard rb_native_mode0_init(Float(sourceRate), Float(outputRate), 2, &up) == 0,
                  rb_native_mode0_count(&up, source.count / 2, &count) == 0 else {
                throw Self.preparationError
            }
            state = .up(up)
        } else {
            var down = RBMode0DownState()
            guard rb_native_mode0_down_init(Float(sourceRate), Float(outputRate), 2, &down) == 0,
                  rb_native_mode0_down_count_blocks(&down, source.count / 2, Self.inputBlockFrames,
                    UInt32(RB_MODE0_DOWN_OUTPUT_ABOVE), &count) == 0 else {
                throw Self.preparationError
            }
            state = .down(down)
        }
        guard count > 0, count <= 16_000_000 else {
            throw RebaseCoreError.unsupportedAudio("The converted event exceeds the supported rate, frame count or floating-point environment.")
        }
        self.source = source; self.gain = gain; initialState = state
        frameCount = Int64(count)
        format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: outputRate,
                              channels: 2, interleaved: false)!
    }

    private static var preparationError: RebaseCoreError {
        .unsupportedAudio("Native mode 0 could not prepare this event within its supported rate, block and floating-point domain.")
    }

    func cursor(from outputFrame: Int64) throws -> Cursor {
        guard outputFrame >= 0, outputFrame <= frameCount else {
            throw RebaseCoreError.invalidProject("Converted playback position is outside the source event.")
        }
        return try Cursor(stream: self, from: outputFrame)
    }

    final class Cursor {
        private let stream: CPRRateConvertedStream
        private var state: ConverterState
        private var inputPosition = 0
        private var generatedFrames: Int64 = 0
        private var pending: [Float]?
        private let transfer: CPRLiveStereoTransfer
        private(set) var deliveredFrames: Int64
        var isAtEnd: Bool { deliveredFrames == stream.frameCount }

        fileprivate init(stream: CPRRateConvertedStream, from first: Int64) throws {
            self.stream = stream; state = stream.initialState; deliveredFrames = first
            transfer = try CPRLiveStereoTransfer()
            // The end has no samples and does not need expensive preroll.
            if first == stream.frameCount { inputPosition = stream.source.count / 2; return }
            while generatedFrames < first {
                guard let block = try convertNextInputBlock() else {
                    throw RebaseCoreError.invalidProject("The converter ended before the requested frame.")
                }
                if generatedFrames > first {
                    let keep = Int(generatedFrames - first) * 2
                    pending = Array(block.suffix(keep))
                }
            }
        }

        /// Used by both the live queue and deterministic sample tests. A zero
        /// output block advances source state; it is never confused with EOF.
        func nextInterleaved() throws -> [Float]? {
            guard !isAtEnd else { return nil }
            let result: [Float]
            if let ready = pending { result = ready; pending = nil }
            else {
                guard let block = try convertNextInputBlock() else {
                    throw RebaseCoreError.invalidProject("Converted playback ended at an unexpected frame.")
                }
                result = block
            }
            deliveredFrames += Int64(result.count / 2)
            guard deliveredFrames <= stream.frameCount else {
                throw RebaseCoreError.invalidProject("The converter exceeded its verified frame count.")
            }
            return result
        }

        func nextBuffer() throws -> AVAudioPCMBuffer? {
            guard let values = try nextInterleaved() else { return nil }
            let frames = values.count / 2
            let buffer = try AudioPreparation.buffer(format: stream.format, frames: frames)
            try transfer.copy(values, to: buffer)
            return buffer
        }

        private func convertNextInputBlock() throws -> [Float]? {
            let total = stream.source.count / 2
            while inputPosition < total {
                let frames: Int
                var values: [Float]
                switch state {
                case .up(var up):
                    frames = min(CPRRateConvertedStream.inputBlockFrames, total - inputPosition)
                    var count = 0, produced = 0
                    guard rb_native_mode0_count(&up, frames, &count) == 0 else { throw conversionError }
                    values = [Float](repeating: 0, count: max(2, count * 2))
                    let status = stream.source.withUnsafeBufferPointer { source in
                        values.withUnsafeMutableBufferPointer { output in
                            rb_native_mode0_process(&up, source.baseAddress!.advanced(by: inputPosition * 2),
                                frames, output.baseAddress, count, &produced)
                        }
                    }
                    guard status == 0, produced == count else { throw conversionError }
                    values.removeLast(values.count - count * 2)
                    state = .up(up)
                case .down(var down):
                    // The small-ratio native branch can read beyond a final
                    // singleton with pending state. Rebalance that pair of
                    // blocks, using the identical policy as count_blocks.
                    frames = rb_native_mode0_down_next_block(total - inputPosition,
                        CPRRateConvertedStream.inputBlockFrames)
                    var count = 0, produced = 0
                    let layout = UInt32(RB_MODE0_DOWN_OUTPUT_ABOVE)
                    guard frames > 0,
                          rb_native_mode0_down_count(&down, frames, layout, 0, &count) == 0 else {
                        throw conversionError
                    }
                    // One arena establishes actual pointer order, independently
                    // of the allocator. Output follows the entire input block.
                    // Do not replace this with two unrelated Swift arrays.
                    let inputSamples = frames * 2
                    var arena = [Float](repeating: 0, count: inputSamples + max(2, count * 2))
                    values = try arena.withUnsafeMutableBufferPointer { storage in
                        let input = storage.baseAddress!
                        let output = input.advanced(by: inputSamples)
                        stream.source.withUnsafeBufferPointer {
                            input.update(from: $0.baseAddress!.advanced(by: inputPosition * 2), count: inputSamples)
                        }
                        guard rb_native_mode0_down_process(&down, input, frames, output, count,
                            layout, 0, &produced) == 0, produced == count else { throw conversionError }
                        return Array(UnsafeBufferPointer(start: output, count: count * 2))
                    }
                    state = .down(down)
                }
                inputPosition += frames
                // A zero-output block still advances the native source state.
                if values.isEmpty { continue }
                // Native segment gain is a separate Float32 operation after the
                // accessor's rate conversion. Do not move it to the source side.
                let gainStatus = values.withUnsafeMutableBufferPointer {
                    rb_cpr_event_gain_f32($0.baseAddress, $0.count, stream.gain.bitPattern)
                }
                guard gainStatus == 0 else { throw conversionError }
                generatedFrames += Int64(values.count / 2)
                return values
            }
            return nil
        }

        private var conversionError: RebaseCoreError {
            .unsupportedAudio("Native mode 0 could not produce this block within its supported finite sample and rounding domain. Playback stopped.")
        }
    }
}
