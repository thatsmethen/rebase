import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Hand-computed interval and boundary controls; these execute authored code.
@Suite(.serialized)
struct CPRTrackOverlapNormalizerTests {
    typealias R = CPRTrackOverlapNormalizer.Range
    private let epsilon = Double(bitPattern: 0x3f1a36e2eb1c432d)
    private func r(_ source: Int, _ start: Double, _ end: Double, _ priority: Int32 = 1,
                   ordinal: Int? = nil) -> R {
        R(sourceIndex: source, ordinal: ordinal ?? source, priority: priority, start: start, end: end)
    }
    private func normalize(_ input: [R]) throws -> [R] { try CPRTrackOverlapNormalizer.normalize(input) }
    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }

    @Test func crossingAndNestedEqualPriorityKeepOriginalContributorOrdinals() throws {
        #expect(try normalize([r(0, 0, 4), r(1, 2, 6)]) == [r(0, 0, 2), r(1, 2, 6)])
        #expect(try normalize([r(0, 0, 10), r(1, 2, 8), r(2, 4, 6)]) == [
            r(0, 0, 2), r(1, 2, 4), r(2, 4, 6), r(1, 6, 8), r(0, 8, 10)])
        #expect(try normalize([r(0, 0, 8), r(1, 0, 4)]) == [r(1, 0, 4), r(0, 4, 8)])
        #expect(try normalize([r(0, 0, 4), r(1, 0, 4)]) == [r(1, 0, 4)])
    }

    @Test func prioritiesUseSignedInt32AndOriginalOrdinalRatherThanCurrentQueuePosition() throws {
        #expect(try normalize([r(0, 0, 4, .min), r(1, 2, 6, .max)]) == [r(0, 0, 2, .min), r(1, 2, 6, .max)])
        #expect(try normalize([r(0, 0, 4, .max), r(1, 2, 6, .min)]) == [r(0, 0, 4, .max), r(1, 4, 6, .min)])
        #expect(try normalize([r(0, 0, 4, 1, ordinal: 9), r(1, 2, 6, 1, ordinal: 3)]) == [
            r(0, 0, 4, 1, ordinal: 9), r(1, 4, 6, 1, ordinal: 3)])
        #expect(try normalize([r(0, 0, 4, 3), r(1, 2, 10, 1), r(2, 4, 8, 2)]) == [
            r(0, 0, 4, 3), r(2, 4, 8, 2), r(1, 8, 10, 1)])
    }

    @Test func savedSuccessorSurvivesRemovalAndTailReinsertion() throws {
        #expect(try normalize([r(0, 0, 10, 4), r(1, 2, 4, 2), r(2, 6, 12, 1)]) == [
            r(0, 0, 10, 4), r(2, 10, 12, 1)])
        #expect(try normalize([r(0, 0, 6, 1), r(1, 2, 8, 3), r(2, 4, 10, 2), r(3, 6, 12, 4)]) == [
            r(0, 0, 2, 1), r(1, 2, 6, 3), r(3, 6, 12, 4)])
    }

    @Test func touchingAndSubEpsilonOverlapBypassPriorityThenClampPublishedStarts() throws {
        #expect(try normalize([r(0, 0, 2, .min), r(1, 2, 4, .max)]) == [r(0, 0, 2, .min), r(1, 2, 4, .max)])
        #expect(try normalize([r(0, 0, epsilon.nextDown, .min), r(1, 0, 1, .max)]) == [
            r(0, 0, epsilon.nextDown, .min), r(1, epsilon.nextDown, 1, .max)])
        for width in [epsilon, epsilon.nextUp] {
            #expect(try normalize([r(0, 0, width, .min), r(1, 0, 1, .max)]) == [r(1, 0, 1, .max)])
        }
    }

    @Test func epsilonPrefixAndTailThresholdsUseActualRoundedSubtraction() throws {
        for width in [epsilon.nextDown, epsilon, epsilon.nextUp] {
            let result = try normalize([r(0, 0, 1), r(1, width, 1, 2)])
            let expected = width < epsilon ? [r(1, width, 1, 2)] : [r(0, 0, width), r(1, width, 1, 2)]
            #expect(result == expected)
        }
        for mode in 0..<3 {
            let firstEnd = mode == 1 ? epsilon : epsilon.nextUp
            let secondEnd = mode == 2 ? (2 * epsilon).nextUp : 2 * epsilon
            let distance = secondEnd - firstEnd
            #expect(distance.bitPattern == [epsilon.nextDown, epsilon, epsilon.nextUp][mode].bitPattern)
            let currentWins = try normalize([r(0, 0, firstEnd, 2), r(1, 0, secondEnd)])
            #expect(currentWins == (distance < epsilon ? [r(0, 0, firstEnd, 2)] :
                [r(0, 0, firstEnd, 2), r(1, firstEnd, secondEnd)]))
            let followingWins = try normalize([r(0, 0, secondEnd), r(1, 0, firstEnd, 2)])
            #expect(followingWins == (distance < epsilon ? [r(1, 0, firstEnd, 2)] :
                [r(1, 0, firstEnd, 2), r(0, firstEnd, secondEnd)]))
        }
    }

    @Test func fullContributorLimitSupports8191NestedFragmentsAndQuadraticTailVisits() throws {
        let nested = (0..<4096).map { r($0, Double($0), Double(8192 - $0)) }
        let fragments = try normalize(nested)
        #expect(fragments.count == 8191)
        #expect(Array(fragments.prefix(4095)) == (0..<4095).map { r($0, Double($0), Double($0 + 1)) })
        #expect(fragments[4095] == r(4095, 4095, 4097))
        #expect(fragments.last == r(0, 8191, 8192))
        let quadratic = (0..<4096).map { r($0, Double($0), Double(4096 + $0), Int32(4096 - $0)) }
        let resolved = try normalize(quadratic)
        #expect(resolved.count == 4096 && resolved[0] == quadratic[0])
        var expectedTails: [R] = []
        for index: Int in 1..<4096 {
            let firstInteger: Int = 4095 + index
            let lastInteger: Int = 4096 + index
            let priorityInteger: Int = 4096 - index
            let first: Double = Double(firstInteger)
            let last: Double = Double(lastInteger)
            let priority: Int32 = Int32(priorityInteger)
            expectedTails.append(R(sourceIndex: index, ordinal: index,
                priority: priority, start: first, end: last))
        }
        #expect(Array(resolved.dropFirst()) == expectedTails)
    }

    @Test func invalidInputsRejectWithoutSortingOrRepair() {
        for input in [[R](), [r(0, 1, 2), r(1, 0, 1)], [r(0, 0, 1), r(1, 1, 2, ordinal: 0)],
                      [r(0, 0, 0)], [r(0, -1, 1)], [r(0, 0, .infinity)], [r(0, .nan, 1)],
                      [r(0, Double.leastNonzeroMagnitude, 1)], [r(0, 0, 86401)], [r(1, 0, 1)],
                      (0..<4097).map { r($0, Double($0), Double($0 + 1)) }] {
            #expect(rejects { _ = try normalize(input) })
        }
    }

    @Test func insufficientOutputAndWrongFloatingPointModeAreTransactional() {
        let input = [RBTrackOverlapRange(sourceIndex: 0, ordinal: 0, priority: 1, start: 0, end: 8),
                     RBTrackOverlapRange(sourceIndex: 1, ordinal: 1, priority: 1, start: 2, end: 4)]
        var result = RBTrackOverlapRange(sourceIndex: 77, ordinal: 88, priority: -99, start: 123, end: 456)
        var count: Int32 = 98
        #expect(input.withUnsafeBufferPointer {
            rb_cpr_track_overlap_normalize($0.baseAddress, 2, &result, 1, &count)
        } == RB_TRACK_OVERLAP_LIMIT)
        #expect(result.sourceIndex == 77 && result.ordinal == 88 && result.priority == -99 && result.start == 123 && result.end == 456 && count == 98)
        let saved = fegetround(); defer { _ = fesetround(saved) }
        for mode in [FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO] {
            #expect(fesetround(mode) == 0)
            #expect(input.withUnsafeBufferPointer {
                rb_cpr_track_overlap_normalize($0.baseAddress, 2, &result, 1, &count)
            } == RB_TRACK_OVERLAP_FP_ENVIRONMENT)
            #expect(result.sourceIndex == 77 && result.start == 123 && result.end == 456 && count == 98)
        }
    }
}
