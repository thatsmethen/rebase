import Darwin
import Foundation
import RebaseTimingDSP
import Testing

/// Hand-computable arithmetic/safety controls; independent IEEE/origin-source
/// expectations are owned by CPRPlacedSourceEventTests and its external oracle.
@Suite(.serialized)
struct NativeTimelineBuilderTests {
    private func bytes(_ value: RBTimelineBuilderProjection) -> Data {
        var copy = value
        return withUnsafeBytes(of: &copy) { Data($0) }
    }

    @Test func ClipsBothEndsAndAddsLeftTrimBeforeSourceQuantization() {
        var r = RBTimelineBuilderProjection()
        #expect(rb_cpr_timeline_builder_project(2, 6, 0.5, 3, 5, 48_000, &r) == RB_TIMELINE_BUILDER_OK)
        #expect(r.disposition == RB_TIMELINE_BUILDER_SEGMENT)
        #expect(r.clippedStart == 3 && r.clippedEnd == 5 && r.clippedSourceOffset == 1.5)
        #expect(r.startFrame == 144_000 && r.endFrame == 240_000 && r.offsetFrame == 72_000)
        #expect(r.start == 3 && r.reconstructedEnd == 5 && r.length == 2)
        #expect(r.sourceOffset == 1.5 && r.getterEnd == 5)
    }

    @Test func SignedHalfFramesUseBuilderBiasAndPreserveClippingEqualityOperand() {
        let half = 0.5 / 8192.0
        var r = RBTimelineBuilderProjection()
        #expect(rb_cpr_timeline_builder_project(-half, half, -half, -1, 1, 8192, &r) == RB_TIMELINE_BUILDER_OK)
        #expect(r.startFrame == -1 && r.endFrame == 1 && r.offsetFrame == -1)
        #expect(r.start == -1 / 8192.0 && r.length == 2 / 8192.0)
        #expect(r.sourceOffset == -1 / 8192.0 && r.getterEnd == 1 / 8192.0)
        #expect(rb_cpr_timeline_builder_project(-0.0, 1, 0, 0, 1, 8192, &r) == RB_TIMELINE_BUILDER_OK)
        #expect(r.clippedStart.bitPattern == (-0.0).bitPattern)
        #expect(r.start.bitPattern == 0 && r.startFrame == 0)
    }

    @Test func NoPositiveIntersectionAndSnappedEmptyRemainDistinct() {
        var r = RBTimelineBuilderProjection()
        for (a, b, w0, w1) in [(0.0, 1.0, 1.0, 2.0), (1, 2, 0, 1),
                               (1, 1, 0, 2), (0, 2, 1, 1)] {
            #expect(rb_cpr_timeline_builder_project(a, b, 0, w0, w1, 8192, &r) == RB_TIMELINE_BUILDER_OK)
            #expect(r.disposition == RB_TIMELINE_BUILDER_EMPTY && r.emptyReason == RB_TIMELINE_BUILDER_NO_OVERLAP)
            #expect(r.period == 0 && r.startFrame == 0 && r.getterEnd == 0)
        }
        #expect(rb_cpr_timeline_builder_project(0, 0.25 / 8192, 0, 0, 1, 8192, &r) == RB_TIMELINE_BUILDER_OK)
        #expect(r.disposition == RB_TIMELINE_BUILDER_EMPTY && r.emptyReason == RB_TIMELINE_BUILDER_SNAPPED_EMPTY)
        #expect(r.period == 1 / 8192.0 && r.startFrame == 0 && r.endFrame == 0)
    }

    @Test func InvalidDomainsAndIntermediateSubnormalLeaveOutputUnchanged() {
        var r = RBTimelineBuilderProjection()
        r.startFrame = 77; r.sourceOffset = 88
        let original = bytes(r)
        for invalid in [Double.nan, .infinity, -.infinity, .leastNonzeroMagnitude, 86_401] {
            #expect(rb_cpr_timeline_builder_project(invalid, 1, 0, 0, 1, 48_000, &r) == RB_TIMELINE_BUILDER_INVALID)
            #expect(bytes(r) == original)
        }
        for rate in [0.0, 7_999, 192_001, 44_100.5, .nan, .infinity] {
            #expect(rb_cpr_timeline_builder_project(0, 1, 0, 0, 1, rate, &r) == RB_TIMELINE_BUILDER_INVALID)
            #expect(bytes(r) == original)
        }
        #expect(rb_cpr_timeline_builder_project(1, 0, 0, 0, 1, 48_000, &r) == RB_TIMELINE_BUILDER_INVALID)
        #expect(rb_cpr_timeline_builder_project(0, 1, 0, 1, 0, 48_000, &r) == RB_TIMELINE_BUILDER_INVALID)
        #expect(rb_cpr_timeline_builder_project(0, 1, 0, 0, 1, 48_000, nil) == RB_TIMELINE_BUILDER_INVALID)
        #expect(bytes(r) == original)
        let tiny = Double.leastNormalMagnitude
        #expect(rb_cpr_timeline_builder_project(tiny, tiny * 2, 0,
            tiny.nextUp, tiny * 2, 48_000, &r) == RB_TIMELINE_BUILDER_RANGE)
        #expect(bytes(r) == original)
    }

    @Test func NonNearestFloatingPointEnvironmentIsRejectedTransactionally() {
        var r = RBTimelineBuilderProjection()
        r.startFrame = 77; r.sourceOffset = 88
        let original = bytes(r), saved = fegetround()
        defer { _ = fesetround(saved) }
        for mode in [FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO] {
            #expect(fesetround(mode) == 0)
            #expect(rb_cpr_timeline_builder_project(0, 1, 0, 0, 1, 48_000, &r) == RB_TIMELINE_BUILDER_FP_ENVIRONMENT)
            #expect(bytes(r) == original)
        }
    }
}
