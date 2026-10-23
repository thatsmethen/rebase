import Foundation
import RebaseTimingDSP

/// Value normalization only. Original contributors remain independently owned
/// and validated; a returned sourceIndex never becomes a new source identity.
enum CPRTrackOverlapNormalizer {
    struct Range: Equatable {
        let sourceIndex: Int
        let ordinal: Int
        let priority: Int32
        let start: Double
        let end: Double
    }

    static func normalize(_ ranges: [Range]) throws -> [Range] {
        guard !ranges.isEmpty, ranges.count <= Int(RB_TRACK_OVERLAP_MAX_INPUTS),
              ranges.allSatisfy({ Int32(exactly: $0.sourceIndex) != nil && Int32(exactly: $0.ordinal) != nil }) else {
            throw RebaseCoreError.unsupportedAudio("The source track exceeds the supported contributor bounds.")
        }
        let input = ranges.map { RBTrackOverlapRange(sourceIndex: Int32($0.sourceIndex),
            ordinal: Int32($0.ordinal), priority: $0.priority, start: $0.start, end: $0.end) }
        var output = [RBTrackOverlapRange](repeating: RBTrackOverlapRange(), count: Int(RB_TRACK_OVERLAP_MAX_OUTPUTS))
        var count: Int32 = 0
        let status = input.withUnsafeBufferPointer { source in
            output.withUnsafeMutableBufferPointer { destination in
                rb_cpr_track_overlap_normalize(source.baseAddress, Int32(source.count),
                    destination.baseAddress, Int32(destination.count), &count)
            }
        }
        guard status == RB_TRACK_OVERLAP_OK else {
            throw RebaseCoreError.unsupportedAudio(status == RB_TRACK_OVERLAP_LIMIT
                ? "Track overlap normalization exceeds the supported work or fragment bounds."
                : "Track overlap normalization requires chronological finite source ranges and the supported floating-point environment.")
        }
        return output.prefix(Int(count)).map { Range(sourceIndex: Int($0.sourceIndex),
            ordinal: Int($0.ordinal), priority: $0.priority, start: $0.start, end: $0.end) }
    }
}
