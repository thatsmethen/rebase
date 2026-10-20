import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Discriminators for the recovered selector, distinct from host PCM scheduling.
struct CPRTimelineSelectionTests {
    typealias Segment = CPRTimelineSelection.Segment
    typealias Cursor = CPRTimelineSelection.Cursor
    private let segments = [Segment(start: 10, length: 2, successor: 1),
                            Segment(start: 20, length: 3, successor: -1)]

    @Test func FreshScanUsesInclusiveEndAndDoesNotTestTheStart() throws {
        for (query, expected) in [(0.0, 0), (10, 0), (12, 0), (Double(12).nextUp, 1), (19, 1), (23, 1)] {
            var cursor = Cursor(generation: 7)
            #expect(try CPRTimelineSelection.select(segments, at: query, generation: 7, cursor: &cursor) == expected)
            #expect(cursor == Cursor(generation: 7))
        }
        var cursor = Cursor(generation: 1)
        #expect(try CPRTimelineSelection.select(segments, at: Double(23).nextUp, generation: 9, cursor: &cursor) == nil)
        #expect(cursor == Cursor(generation: 9))
    }

    @Test func FreshTraversalFollowsLinksAndRejectsANonterminatingCycle() throws {
        let linked = [Segment(start: 0, length: 1, successor: 2),
                      Segment(start: 0, length: 100, successor: -1),
                      Segment(start: 3, length: 1, successor: -1)]
        var cursor = Cursor(generation: 0)
        #expect(try CPRTimelineSelection.select(linked, at: 2, generation: 1, cursor: &cursor) == 2)
        #expect(cursor == Cursor(generation: 1))
        #expect(try CPRTimelineSelection.select(linked, at: 5, generation: 1, cursor: &cursor) == nil)
        let cycle = [Segment(start: 0, length: 1, successor: 1), Segment(start: 0, length: 1, successor: 0)]
        #expect(throws: RebaseCoreError.self) { try CPRTimelineSelection.select(cycle, at: 2, generation: 2, cursor: &cursor) }
        #expect(cursor == Cursor(generation: 1))
    }

    @Test func MatchingCursorReturnsSuccessorRegardlessOfQueryWithoutAdvancingCurrent() throws {
        for query in [0.0, 1, 12, 1000] {
            var cursor = Cursor(current: 0, generation: 7)
            #expect(try CPRTimelineSelection.select(segments, at: query, generation: 7, cursor: &cursor) == 1)
            #expect(cursor == Cursor(current: 0, generation: 7))
            cursor.current = 1 // Assignment belongs to the caller.
            #expect(try CPRTimelineSelection.select(segments, at: 0, generation: 7, cursor: &cursor) == nil)
            #expect(cursor == Cursor(current: 1, generation: 7))
        }
    }

    @Test func GenerationMismatchIgnoresOldCurrentAndResetClearsIt() throws {
        var cursor = Cursor(current: 123456, generation: UInt32.max)
        #expect(try CPRTimelineSelection.select(segments, at: 0, generation: 0, cursor: &cursor) == 0)
        #expect(cursor == Cursor(current: 123456, generation: 0))
        // A caller must install the returned node before using the cached path.
        #expect(throws: RebaseCoreError.self) { try CPRTimelineSelection.select(segments, at: 0, generation: 0, cursor: &cursor) }
        cursor.reset(generation: 3)
        #expect(cursor == Cursor(generation: 3))
        #expect(try CPRTimelineSelection.select([], at: 0, generation: 4, cursor: &cursor) == nil)
        #expect(cursor == Cursor(generation: 4))
    }

    @Test func EndIsOneRoundedBinary64Addition() throws {
        let tie = Segment(start: 1, length: 0x1p-53, successor: -1)
        var cursor = Cursor(generation: 0)
        #expect(try CPRTimelineSelection.select([tie], at: 1, generation: 0, cursor: &cursor) == 0)
        #expect(try CPRTimelineSelection.select([tie], at: Double(1).nextUp, generation: 0, cursor: &cursor) == nil)
        let odd = Segment(start: Double(1).nextUp, length: 0x1p-53, successor: -1)
        #expect(try CPRTimelineSelection.select([odd], at: Double(1).nextUp.nextUp, generation: 0, cursor: &cursor) == 0)
    }

    @Test func NativeEndSelectionAndHostFrameEndRemainSeparate() throws {
        var cursor = Cursor(generation: 0)
        #expect(try CPRTimelineSelection.select([Segment(start: 0, length: 24, successor: -1)],
            at: 24, generation: 0, cursor: &cursor) == 0)
        // Source frame index1058400 is the exclusive PCM end; audition tests
        // independently assert that its host schedule contains no buffer.
        #expect(try CPRTimelineSelection.select([Segment(start: 0, length: 24, successor: -1)],
            at: Double(24).nextUp, generation: 0, cursor: &cursor) == nil)
    }

    @Test func InvalidDomainLeavesCursorAndKernelOutputsUntouched() throws {
        let invalid = [Segment(start: -.infinity, length: 1, successor: -1),
                       Segment(start: 0, length: .nan, successor: -1),
                       Segment(start: 0, length: -.leastNormalMagnitude, successor: -1),
                       Segment(start: 0, length: .leastNonzeroMagnitude, successor: -1),
                       Segment(start: .greatestFiniteMagnitude, length: .greatestFiniteMagnitude, successor: -1),
                       Segment(start: 0, length: 1, successor: 1)]
        for segment in invalid {
            var cursor = Cursor(generation: 7)
            #expect(throws: RebaseCoreError.self) { try CPRTimelineSelection.select([segment], at: 0, generation: 8, cursor: &cursor) }
            #expect(cursor == Cursor(generation: 7))
        }
        for query in [Double.nan, .infinity, -1, .leastNonzeroMagnitude] {
            var cursor = Cursor(generation: 7)
            #expect(throws: RebaseCoreError.self) { try CPRTimelineSelection.select(segments, at: query, generation: 8, cursor: &cursor) }
            #expect(cursor == Cursor(generation: 7))
        }
        let previous = fegetround(); defer { fesetround(previous) }
        for mode in [FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO] {
            fesetround(mode)
            var selected: Int64 = 123, generation: UInt32 = 456
            #expect(rb_cpr_timeline_select(nil, nil, nil, 0, 7, 0, -1, 8, &selected, &generation) != 0)
            #expect(selected == 123 && generation == 456)
        }
    }
}
