import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

struct CPRSourceFragmentProjectionTests {
    private func canonical(start: Double, end: Double, offset: Double, rate: Double = 32000,
                           frames: Int = 44100) -> CPRPlacedSourceEventPlan.Canonical {
        let object = CPRObjectRecord(className: "AudioFile", version: 0, declarationOffset: 0,
            objectOffset: 0, identityOffset: 0, payloadOffset: 0, payloadByteCount: 0,
            payloadSHA256: String(repeating: "0", count: 64))
        let file = CPRAudioFileReference(object: object, filename: "Authored.wav", directory: "",
            frameCount: UInt64(frames), sampleSize: 24, frameSize: 6, channels: 2,
            sampleRateBits: Float(44100).bitPattern)
        let media = CPRSourceEventRenderPlan(frames: frames, rate: 44100, channels: 2, gain: 1, file: file)
        return .init(media: media, timelineRate: rate, canonicalStart: start, canonicalEnd: end,
            canonicalSourceOffset: offset, contract: "authored-fragment-control")
    }
    private func seek(_ range: CPRSourceEventTimelineRange, rate: Double) throws -> Int64 {
        var output: Int64 = 0
        #expect(rb_cpr_timeline_quantize(1 / rate, range.offset, &output) == 0)
        return output
    }
    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }

    @Test func everyFragmentProjectsFromOriginalUnsnappedOriginAndOffset() throws {
        for (rate, cut, expected, naiveExpected) in [(32000.0, 2 / 960.0, Int64(34), Int64(35)),
                                                    (44100.0, 9 / 960.0, 369, 368)] {
            let original = canonical(start: 1 / 960, end: 0.5, offset: 1 / 44100, rate: rate)
            let full = try original.completeEvent()
            let fragment = try #require(try original.project(windowStart: cut, windowEnd: 0.4))
            #expect(try seek(fragment.range, rate: rate) == expected)
            #expect(fragment.canonicalStart.bitPattern == original.canonicalStart.bitPattern)
            #expect(fragment.canonicalSourceOffset.bitPattern == original.canonicalSourceOffset.bitPattern)
            var wrong = RBTimelineBuilderProjection()
            #expect(rb_cpr_timeline_builder_project(full.range.position,
                full.range.position + full.range.duration, full.range.offset,
                fragment.range.position, fragment.range.position + fragment.range.duration,
                rate, &wrong) == RB_TIMELINE_BUILDER_OK)
            #expect(wrong.offsetFrame == naiveExpected && wrong.offsetFrame != expected)
        }
    }

    @Test func validSnappedEmptyFragmentsAreDistinctFromInvalidOrIncompleteReads() throws {
        let original = canonical(start: 0, end: 1, offset: 0, rate: 8192)
        #expect(try original.project(windowStart: 0, windowEnd: 0.25 / 8192) == nil)
        #expect(rejects { _ = try original.project(windowStart: -1, windowEnd: 0.5) })
        #expect(rejects { _ = try original.project(windowStart: 0.5, windowEnd: 2) })
        let beyond = canonical(start: 0, end: 1, offset: 0, rate: 48000, frames: 44100)
        #expect(rejects { _ = try beyond.completeEvent() })
        #expect(try beyond.project(windowStart: 0, windowEnd: 1, requireCompleteRead: false) != nil)
        let fragment = try #require(try beyond.project(windowStart: 0, windowEnd: 0.5))
        #expect(fragment.range.duration == 0.5)
    }

    @Test func repeatedFragmentsPreserveOriginalSignedZeroContextWithoutMutation() throws {
        let original = canonical(start: 0, end: 1, offset: -0.0)
        let windows = [(0.0, 0.1), (0.3, 0.5), (0.7, 1.0)]
        let first = try windows.map { try #require(try original.project(windowStart: $0.0, windowEnd: $0.1)) }
        let second = try windows.map { try #require(try original.project(windowStart: $0.0, windowEnd: $0.1)) }
        #expect(first.map(\.range) == second.map(\.range))
        #expect(first.allSatisfy { $0.canonicalSourceOffset.bitPattern == (-0.0).bitPattern })
        #expect(original.canonicalSourceOffset.bitPattern == (-0.0).bitPattern)
    }

    @Test func normalizedFragmentsShareImmutableSourceStorageWithinTheInputBudget() throws {
        let source = CPRNativeTimelineStream.Source(samples: [Float](repeating: 0.25, count: 16384), sourceRate: 8192)
        let segments = (0..<8191).map { index in
            CPRNativeTimelineStream.Segment(start: Double(index) / 8192, length: 1 / 8192,
                offset: 0, source: source, gain: 1)
        }
        #expect(rejects { _ = try CPRNativeTimelineStream(sampleRate: 8192, segments: segments) })
        let stream = try CPRNativeTimelineStream(sampleRate: 8192, segments: segments, policy: .normalizedTrack)
        #expect(stream.frameCount == 8191)
        let cursor = try stream.cursor(from: 4094)
        let buffer = try #require(try cursor.nextBuffer(maximumFrames: 4))
        #expect(buffer.frameLength == 4)
        for channel in 0..<2 {
            #expect((0..<4).allSatisfy { buffer.floatChannelData![channel][$0].bitPattern == Float(0.25).bitPattern })
        }
    }

    @Test func distinctSourcesCannotSpoofSharedStorageIdentityToEvadeTheSampleBudget() {
        // Copy-on-write may share these Swift array bytes, but two independently
        // owned source snapshots still count separately. There is no public key
        // with which a different buffer can pretend to be a validated source.
        let samples = [Float](repeating: 0, count: 16_000_002)
        let first = CPRNativeTimelineStream.Source(samples: samples, sourceRate: 8192)
        let second = CPRNativeTimelineStream.Source(samples: samples, sourceRate: 8192)
        let segments = [CPRNativeTimelineStream.Segment(start: 0, length: 1 / 8192, offset: 0, source: first, gain: 1),
                        CPRNativeTimelineStream.Segment(start: 1 / 8192, length: 1 / 8192, offset: 0, source: second, gain: 1)]
        #expect(rejects { _ = try CPRNativeTimelineStream(sampleRate: 8192, segments: segments, policy: .normalizedTrack) })
    }
}
