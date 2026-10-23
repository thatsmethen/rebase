import AVFoundation
import Foundation
import RebaseTimingDSP

/// Absolute-frame, direct stereo reader. The recovered native window and seek
/// operations are separate from Rebase's worker scheduling and device output.
/// Descriptors here are already-constructed PAudioSegment values, not raw CPR
/// fields. The separately verified placed-source plan constructs them from a preserved
/// CPR. Synthetic descriptors additionally exercise multiple-segment behavior.
struct CPRNativeTimelineStream {
    /// Immutable identity owned by this allocation, never a caller-provided key.
    /// Fragments may share one verified snapshot without multiplying its budget.
    final class Source {
        let samples: [Float]
        let sourceRate: Double
        init(samples: [Float], sourceRate: Double) {
            self.samples = samples; self.sourceRate = sourceRate
        }
    }

    struct Segment {
        let start: Double
        let length: Double
        let offset: Double
        let source: Source
        let gain: Float
        var samples: [Float] { source.samples }
        var sourceRate: Double { source.sourceRate }

        init(start: Double, length: Double, offset: Double, samples: [Float], gain: Float, sourceRate: Double) {
            self.init(start: start, length: length, offset: offset,
                source: Source(samples: samples, sourceRate: sourceRate), gain: gain)
        }
        init(start: Double, length: Double, offset: Double, source: Source, gain: Float) {
            self.start = start; self.length = length; self.offset = offset
            self.source = source; self.gain = gain
        }
    }

    enum SegmentPolicy { case ordinary, normalizedTrack }
    private struct SourceGainKey: Hashable {
        let identity: ObjectIdentifier
        let gainBits: UInt32
    }

    private struct BoundSegment {
        let descriptor: RBTimelineSegment
        let source: Segment
        let startFrame: Int64
        let endFrame: Int64
    }

    let format: AVAudioFormat
    let frameCount: Int64
    private let period: Double
    private let segments: [BoundSegment]

    init(sampleRate: Double, segments: [Segment], policy: SegmentPolicy = .ordinary) throws {
        let segmentLimit = policy == .normalizedTrack ? 8192 : 4096
        guard sampleRate.rounded() == sampleRate, (8_000...192_000).contains(sampleRate),
              !segments.isEmpty, segments.count <= segmentLimit else { throw Self.invalid }
        let period = 1 / sampleRate
        var bound: [BoundSegment] = []
        var previousEnd: Int64 = 0
        var totalSamples = 0
        var countedSources = Set<ObjectIdentifier>()
        var checkedGains = Set<SourceGainKey>()
        for source in segments {
            guard source.start >= 0, source.length > 0, source.offset >= 0,
                  source.sourceRate.rounded() == source.sourceRate,
                  (8_000...192_000).contains(source.sourceRate),
                  source.gain.isNormal, source.gain > 0,
                  !source.samples.isEmpty, source.samples.count % 2 == 0 else { throw Self.invalid }
            let identity = ObjectIdentifier(source.source)
            if countedSources.insert(identity).inserted {
                guard source.samples.count <= 32_000_000 - totalSamples else { throw Self.invalid }
                totalSamples += source.samples.count
            }
            // The concrete native end getter performs this addition separately
            // before the reader's FMA and signed integer conversion.
            let end = source.start + source.length
            let descriptor = RBTimelineSegment(start: source.start, end: end, sourceOffset: source.offset)
            var first: Int64 = 0, last: Int64 = 0, offset: Int64 = 0
            guard rb_cpr_timeline_quantize(period, source.start, &first) == 0,
                  rb_cpr_timeline_quantize(period, end, &last) == 0,
                  rb_cpr_timeline_quantize(period, source.offset, &offset) == 0,
                  first >= previousEnd, last > first, last <= Int64(sampleRate) * 86_400,
                  offset >= 0, offset <= Int64(source.samples.count / 2),
                  last - first <= Int64(source.samples.count / 2) - offset else { throw Self.invalid }
            // Reject unsupported arithmetic before live scheduling. The actual
            // multiply still follows each direct read, exactly once.
            if checkedGains.insert(SourceGainKey(identity: identity, gainBits: source.gain.bitPattern)).inserted {
                for value in source.samples {
                    let result = value * source.gain
                    guard value.isFinite, value == 0 || value.isNormal,
                          result.isFinite, result == 0 ? value == 0 : result.isNormal else { throw Self.invalid }
                }
            }
            bound.append(BoundSegment(descriptor: descriptor, source: source,
                                      startFrame: first, endFrame: last))
            previousEnd = last
        }
        self.period = period
        self.segments = bound
        frameCount = previousEnd
        format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate,
                              channels: 2, interleaved: false)!
    }

    func cursor(from frame: Int64) throws -> Cursor {
        guard (0...frameCount).contains(frame) else { throw Self.invalid }
        return Cursor(stream: self, position: frame)
    }

    private static var invalid: RebaseCoreError {
        .unsupportedAudio("The native timeline reader requires ordered, nonoverlapping stereo source segments, complete source reads and finite supported frame bounds.")
    }

    final class Cursor {
        private let stream: CPRNativeTimelineStream
        private var segmentIndex = 0
        private var activeAccessor: (segment: Int, accessor: CPRNativeAudioAccessor)?
        private(set) var deliveredFrames: Int64
        var isAtEnd: Bool { deliveredFrames == stream.frameCount }

        fileprivate init(stream: CPRNativeTimelineStream, position: Int64) {
            self.stream = stream
            deliveredFrames = position
            // End equality remains selected for the native planner to skip.
            while segmentIndex < stream.segments.count,
                  stream.segments[segmentIndex].endFrame < position {
                segmentIndex += 1
            }
        }

        /// The block size is application policy. Equal-rate direct source reads
        /// have no converter history. No audition FIFO or resampler is used.
        func nextBuffer(maximumFrames: Int = 4096) throws -> AVAudioPCMBuffer? {
            guard (1...65_536).contains(maximumFrames) else { throw CPRNativeTimelineStream.invalid }
            guard !isAtEnd else { return nil }
            let first = deliveredFrames
            let end = min(stream.frameCount, first + Int64(maximumFrames))
            let frames = Int(end - first)
            let buffer = try AudioPreparation.buffer(format: stream.format, frames: frames)
            let channels = buffer.floatChannelData!
            for channel in 0..<2 { channels[channel].update(repeating: 0, count: frames) }
            var position = first
            var index = segmentIndex
            while position < end {
                // The native lease survives another block selecting the same
                // descriptor, and ends when selection changes (including nil).
                // A dictionary of every visited segment would retain history
                // beyond the native last-descriptor cache's lifetime.
                if activeAccessor?.segment != index || index >= stream.segments.count {
                    activeAccessor = nil
                }
                var plan = RBTimelinePlan()
                let status: Int32
                if index < stream.segments.count {
                    var descriptor = stream.segments[index].descriptor
                    status = rb_cpr_timeline_plan(first, end, position, stream.period, &descriptor, &plan)
                } else {
                    status = rb_cpr_timeline_plan(first, end, position, stream.period, nil, &plan)
                }
                guard status == 0 else { throw CPRNativeTimelineStream.invalid }
                if plan.action == RB_TIMELINE_SKIP {
                    guard index < stream.segments.count else { throw CPRNativeTimelineStream.invalid }
                    index += 1
                    continue
                }
                if plan.action == RB_TIMELINE_READ {
                    guard index < stream.segments.count, plan.readFrames > 0,
                          plan.sourceSeek >= 0, plan.readOffset >= 0,
                          plan.readOffset + plan.readFrames <= Int64(frames) else {
                        throw CPRNativeTimelineStream.invalid
                    }
                    let source = stream.segments[index].source
                    guard plan.sourceSeek + plan.readFrames <= Int64(source.samples.count / 2) else {
                        throw CPRNativeTimelineStream.invalid
                    }
                    let count = Int(plan.readFrames)
                    // The ordinary native reader does not set accessor rate.
                    // Its source-owned rate therefore stays unchanged even
                    // when the timeline consumes these raw frames at a different
                    // clock rate. No rate conversion is inserted here.
                    let accessor: CPRNativeAudioAccessor
                    if let cached = activeAccessor { accessor = cached.accessor }
                    else {
                        accessor = try CPRNativeAudioAccessor(source: source.samples,
                            sourceRate: source.sourceRate,
                            outputRate: source.sourceRate)
                        activeAccessor = (index, accessor)
                    }
                    _ = try accessor.seek(to: plan.sourceSeek)
                    let read = try accessor.read(requestedFrames: count)
                    var decision = RBTimelineReadDecision()
                    guard rb_cpr_timeline_read_result(Int32(count), plan.readBegin, plan.segmentStart,
                        0, Int32(read.returnedOutputFrames), &decision) == 0,
                        decision.action == RB_TIMELINE_READ_COMPLETE else { throw CPRNativeTimelineStream.invalid }
                    for channel in 0..<2 {
                        let output = channels[channel].advanced(by: Int(plan.readOffset))
                        for frame in 0..<count {
                            output[frame] = read.samples[frame * 2 + channel]
                        }
                        guard rb_cpr_event_gain_f32(output, count, source.gain.bitPattern) == 0 else {
                            throw CPRNativeTimelineStream.invalid
                        }
                    }
                }
                guard plan.nextCursor > position || plan.stopAfter != 0 else { throw CPRNativeTimelineStream.invalid }
                position = plan.nextCursor
                if plan.stopAfter != 0 { break }
                // The native selector advances its current node after each
                // segment. Our admitted sorted list has no concurrent mutation.
                index += 1
            }
            // Publish cursor progress only after the complete block succeeds.
            deliveredFrames = end
            segmentIndex = index
            return buffer
        }
    }
}
