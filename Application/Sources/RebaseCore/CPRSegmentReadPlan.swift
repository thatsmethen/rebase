import Foundation

public enum CPRSegmentReadPlanError: LocalizedError, Equatable {
    case invalidSegment
    case invalidSourceFrameCount
    case invalidRequest
    case positionOutsideSegment
    case arithmeticOverflow
    case byteCountExceeded
    case sourceRangeExceeded

    public var errorDescription: String? {
        switch self {
        case .invalidSegment: return "The saved segment requires nonnegative signed-64-bit Start and Offset, and a positive Length."
        case .invalidSourceFrameCount: return "The validated source frame count must be nonnegative."
        case .invalidRequest: return "The requested frames and frame size must be positive signed-32-bit values."
        case .positionOutsideSegment: return "The requested cluster position must be inside the saved segment."
        case .arithmeticOverflow: return "The saved segment or requested interval exceeds signed-64-bit positions."
        case .byteCountExceeded: return "The requested buffer exceeds the supported signed-32-bit byte count."
        case .sourceRangeExceeded: return "The saved segment exceeds the validated source frame count."
        }
    }
}

/// A pure frame-interval projection of the bounded direct-read contract in
/// CPR-AUDIO-SEGMENT-CONSUMER-001. It neither reads audio nor authorizes playback.
///
/// The caller must separately establish one unchanged segment linked to the
/// intended source/accessor, matching current format and rate, gain exactly one,
/// sufficient destination storage, and a successful complete backend read.
/// Differing formats/rates, short reads, errors and other segments are outside
/// this contract. Source identity and these runtime conditions are not inferred
/// from the saved segment or the returned plan.
public struct CPRSegmentReadPlan: Equatable, Sendable {
    public let sourceStart: Int64
    public let sourceFrameCount: Int
    /// Trailing frames counted as silence only after the complete bounded read.
    /// This is a frame count, not a promise that every format uses zero bytes.
    public let silenceFrameCount: Int
    public let nextClusterPosition: Int64

    private init(sourceStart: Int64, sourceFrameCount: Int, silenceFrameCount: Int,
                 nextClusterPosition: Int64) {
        self.sourceStart = sourceStart
        self.sourceFrameCount = sourceFrameCount
        self.silenceFrameCount = silenceFrameCount
        self.nextClusterPosition = nextClusterPosition
    }

    /// Preserves the stored Offset/Length/Start meanings without sorting,
    /// resampling, clamping, or floating-point conversion. Requiring the entire
    /// source interval to fit the validated file is an application acceptance
    /// policy; the native read method does not establish that capacity itself.
    public static func project(segment: CPRAudioSegmentReference, clusterPosition: Int64,
                               requestedFrames: Int, sourceFrameCount: Int64,
                               frameSize: Int) throws -> CPRSegmentReadPlan {
        guard let start = Int64(exactly: segment.storedStart),
              let offset = Int64(exactly: segment.storedOffset),
              let length = Int64(exactly: segment.storedLength), length > 0 else {
            throw CPRSegmentReadPlanError.invalidSegment
        }
        guard sourceFrameCount >= 0 else { throw CPRSegmentReadPlanError.invalidSourceFrameCount }
        guard requestedFrames > 0, requestedFrames <= Int(Int32.max),
              frameSize > 0, frameSize <= Int(Int32.max) else {
            throw CPRSegmentReadPlanError.invalidRequest
        }
        let (byteCount, byteOverflow) = requestedFrames.multipliedReportingOverflow(by: frameSize)
        guard !byteOverflow, byteCount <= Int(Int32.max) else {
            throw CPRSegmentReadPlanError.byteCountExceeded
        }
        let clusterEnd = try add(start, length)
        let sourceEnd = try add(offset, length)
        guard sourceEnd <= sourceFrameCount else { throw CPRSegmentReadPlanError.sourceRangeExceeded }
        guard clusterPosition >= start, clusterPosition < clusterEnd else {
            throw CPRSegmentReadPlanError.positionOutsideSegment
        }
        // Both subtractions are safe after the nonnegative, ordered bounds.
        let relativePosition = clusterPosition - start
        let availableFrames = clusterEnd - clusterPosition
        let boundedCount = min(Int64(requestedFrames), availableFrames)
        let sourceStart = try add(relativePosition, offset)
        let nextPosition = try add(clusterPosition, Int64(requestedFrames))
        return CPRSegmentReadPlan(sourceStart: sourceStart, sourceFrameCount: Int(boundedCount),
            silenceFrameCount: requestedFrames - Int(boundedCount), nextClusterPosition: nextPosition)
    }

    private static func add(_ lhs: Int64, _ rhs: Int64) throws -> Int64 {
        let (result, overflow) = lhs.addingReportingOverflow(rhs)
        guard !overflow else { throw CPRSegmentReadPlanError.arithmeticOverflow }
        return result
    }
}
