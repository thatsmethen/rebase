import Foundation
import Testing
@testable import RebaseCore

/// Analytical interval controls, not backend reads or Reference playback tests.
struct CPRSegmentReadPlanTests {
    private let workspace = PrivateResearchFixtures.root
    private func segment(start: UInt64 = 100, offset: UInt64 = 7, length: UInt64 = 123) -> CPRAudioSegmentReference {
        let object = CPRObjectRecord(className: "AClusterSegment", version: 0, declarationOffset: 0,
            objectOffset: 0, identityOffset: 0, payloadOffset: 4, payloadByteCount: 28,
            payloadSHA256: String(repeating: "0", count: 64))
        return CPRAudioSegmentReference(object: object, streamIdentity: 1,
            storedOffset: offset, storedLength: length, storedStart: start)
    }
    private func plan(_ segment: CPRAudioSegmentReference, at position: Int64 = 140,
                      count: Int = 100, frames: Int64 = 130, size: Int = 6) throws -> CPRSegmentReadPlan {
        try CPRSegmentReadPlan.project(segment: segment, clusterPosition: position,
            requestedFrames: count, sourceFrameCount: frames, frameSize: size)
    }
    private struct Vectors: Decodable {
        struct Interval: Decodable {
            let start: UInt64, offset: UInt64, length: UInt64
            let position: Int64, requested: Int, source_seek: Int64, source_count: Int, remainder: Int
            let source_half_open: [Int64]
        }
        let intervals: [Interval]
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func allSixPinnedAnalyticalIntervalsMatchIncludingNonzeroStartAndOffset() throws {
        let path = workspace.appendingPathComponent("evidence/cpr-static/cpr-audio-events-001/segment-consumer/interval-and-rate-vectors.json")
        let bytes = try Data(contentsOf: path)
        #expect(cprSHA256(bytes) == "83fd06bd41ee507e3d4735c69b52988dbf89687c41e46e94850b73b445117bcb")
        let vectors = try JSONDecoder().decode(Vectors.self, from: bytes).intervals
        #expect(vectors.count == 6)
        for vector in vectors {
            let raw = segment(start: vector.start, offset: vector.offset, length: vector.length)
            let result = try plan(raw, at: vector.position, count: vector.requested,
                                  frames: Int64(vector.offset + vector.length))
            #expect(result.sourceStart == vector.source_seek)
            #expect(result.sourceFrameCount == vector.source_count)
            #expect(result.silenceFrameCount == vector.remainder)
            #expect([result.sourceStart, result.sourceStart + Int64(result.sourceFrameCount)] == vector.source_half_open)
            #expect(result.nextClusterPosition == vector.position + Int64(vector.requested))
            #expect(result.sourceFrameCount + result.silenceFrameCount == vector.requested)
            #expect(raw.storedStart == vector.start && raw.storedOffset == vector.offset && raw.storedLength == vector.length)
        }
        let discriminator = try plan(segment())
        #expect(discriminator.sourceStart == 47 && discriminator.sourceFrameCount == 83)
        #expect(discriminator.silenceFrameCount == 17 && discriminator.nextClusterPosition == 240)
    }

    @Test func halfOpenPositionBoundariesAreStrictAndDoNotInventPrefixSilence() throws {
        let raw = segment()
        let first = try plan(raw, at: 100, count: 1)
        #expect(first.sourceStart == 7 && first.sourceFrameCount == 1 && first.silenceFrameCount == 0)
        let last = try plan(raw, at: 222, count: 2)
        #expect(last.sourceStart == 129 && last.sourceFrameCount == 1 && last.silenceFrameCount == 1)
        #expect(last.nextClusterPosition == 224)
        for position: Int64 in [-1, 0, 99, 223, 224, .max] {
            #expect(throws: CPRSegmentReadPlanError.positionOutsideSegment) { try plan(raw, at: position) }
        }
    }

    @Test func rawSignedRangeAndBothEndpointOverflowsAreRejected() throws {
        for raw in [segment(length: 0), segment(start: UInt64.max), segment(offset: UInt64.max),
                    segment(length: UInt64.max), segment(start: UInt64(Int64.max) + 1),
                    segment(offset: UInt64(Int64.max) + 1), segment(length: UInt64(Int64.max) + 1)] {
            #expect(throws: CPRSegmentReadPlanError.invalidSegment) { try plan(raw) }
        }
        let clusterOverflow = segment(start: UInt64(Int64.max), offset: 0, length: 1)
        #expect(throws: CPRSegmentReadPlanError.arithmeticOverflow) {
            try plan(clusterOverflow, at: .max, count: 1, frames: 1, size: 1)
        }
        let sourceOverflow = segment(start: 0, offset: UInt64(Int64.max), length: 1)
        #expect(throws: CPRSegmentReadPlanError.arithmeticOverflow) {
            try plan(sourceOverflow, at: 0, count: 1, frames: .max, size: 1)
        }
        let nextOverflow = segment(start: UInt64(Int64.max - 2), offset: 0, length: 2)
        #expect(throws: CPRSegmentReadPlanError.arithmeticOverflow) {
            try plan(nextOverflow, at: Int64.max - 1, count: 2, frames: 2, size: 1)
        }
    }

    @Test func completeSegmentMustFitValidatedActualSourceEvenForShortRequest() throws {
        #expect(throws: CPRSegmentReadPlanError.invalidSourceFrameCount) { try plan(segment(), frames: -1) }
        for actualFrames: Int64 in [0, 7, 129] {
            // Even the first frame would fit some of these files; the entire
            // saved interval is an explicit attachment-capacity precondition.
            #expect(throws: CPRSegmentReadPlanError.sourceRangeExceeded) {
                try plan(segment(), at: 100, count: 1, frames: actualFrames)
            }
        }
        #expect(try plan(segment(), at: 100, count: 123, frames: 130).sourceFrameCount == 123)
        #expect(try plan(segment(), at: 100, count: 124, frames: 130).silenceFrameCount == 1)
        #expect(try plan(segment(), at: 100, count: 123, frames: 131).silenceFrameCount == 0)
    }

    @Test func requestAndByteCountBoundsIncludePaddingAndNeverAllocate() throws {
        for count in [-1, 0, Int(Int32.max) + 1, Int.max] {
            #expect(throws: CPRSegmentReadPlanError.invalidRequest) { try plan(segment(), count: count) }
        }
        for size in [-1, 0, Int(Int32.max) + 1, Int.max] {
            #expect(throws: CPRSegmentReadPlanError.invalidRequest) { try plan(segment(), size: size) }
        }
        let limit = Int(Int32.max), short = segment(start: 0, offset: 0, length: 1)
        #expect(throws: CPRSegmentReadPlanError.byteCountExceeded) {
            try plan(short, at: 0, count: limit / 6 + 1, frames: 1, size: 6)
        }
        #expect(throws: CPRSegmentReadPlanError.byteCountExceeded) {
            try plan(short, at: 0, count: limit, frames: 1, size: limit)
        }
        let exact = try plan(short, at: 0, count: limit, frames: 1, size: 1)
        #expect(exact.sourceFrameCount == 1 && exact.silenceFrameCount == limit - 1)
        #expect(exact.nextClusterPosition == Int64(Int32.max))
        let below = try plan(short, at: 0, count: limit / 6, frames: 1, size: 6)
        #expect(below.sourceFrameCount + below.silenceFrameCount == limit / 6)
        #expect(try plan(short, at: 0, count: 1, frames: 1, size: limit).sourceFrameCount == 1)
    }

    @Test func signed64EndpointsAndIntegersBeyondDoublePrecisionRemainExact() throws {
        let raw = segment(start: UInt64(Int64.max - 1), offset: UInt64(Int64.max - 1), length: 1)
        let boundary = try plan(raw, at: Int64.max - 1, count: 1, frames: .max, size: 1)
        #expect(boundary.sourceStart == Int64.max - 1 && boundary.nextClusterPosition == Int64.max)
        #expect(boundary.sourceFrameCount == 1 && boundary.silenceFrameCount == 0)
        let start: Int64 = 9_007_199_254_740_993
        let large = segment(start: UInt64(start), offset: 7, length: 123)
        let exact = try plan(large, at: start + 40, count: 100)
        #expect(exact.sourceStart == 47 && exact.sourceFrameCount == 83)
        #expect(exact.nextClusterPosition == start + 140 && exact.silenceFrameCount == 17)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func pinnedFactorySegmentsProjectOnlyTheirSourceFramesWithoutChangingEvents() throws {
        let folder = workspace.appendingPathComponent("templates")
        for (name, expectedSHA, frames) in [
            ("LoFi Hip Hop", "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495", Int64(1_058_400)),
            ("Classic House", "28db9a9e6aca3357e0758c4b985c4bbdfb4e1d9268502d53238f0ceb2733e892", Int64(677_376))
        ] {
            let bytes = try Data(contentsOf: folder.appendingPathComponent(name + ".cpr"))
            #expect(cprSHA256(bytes) == expectedSHA)
            let result = try CPRRecoveryV4(container: CPRProject.readContainer(bytes)).decode(sourceName: name + ".cpr")
            let project = try #require(result.recovery.project), event = try #require(project.unresolvedAudioEvents.first)
            let raw = try #require(event.segments.first), file = try #require(event.files.first)
            #expect(raw.streamIdentity == file.object.identityOffset)
            let full = try plan(raw, at: 0, count: Int(frames), frames: frames, size: Int(file.frameSize))
            #expect(full.sourceStart == 0 && full.sourceFrameCount == Int(frames) && full.silenceFrameCount == 0)
            #expect(full.nextClusterPosition == frames)
            let tail = try plan(raw, at: frames - 1, count: 4, frames: frames, size: Int(file.frameSize))
            #expect(tail.sourceStart == frames - 1 && tail.sourceFrameCount == 1 && tail.silenceFrameCount == 3)
            #expect(tail.nextClusterPosition == frames + 3)
            #expect(project.tracks.flatMap(\.clips).isEmpty && project.unresolvedAudioEvents == [event])
            #expect(event.placement?.duration == (name == "LoFi Hip Hop" ? 24 : nil))
        }
    }
}
