import Foundation
import RebaseTimingDSP

/// Value-level reconstruction of the native track's segment selector. Native
/// lock/refcount callbacks are outside this immutable, finite-coordinate model.
/// A selection at an inclusive endpoint is not an extra playable sample.
enum CPRTimelineSelection {
    struct Segment: Equatable {
        let start: Double
        let length: Double
        let successor: Int64
    }
    struct Cursor: Equatable {
        var current: Int64 = -1
        var generation: UInt32

        mutating func reset(generation: UInt32) {
            current = -1
            self.generation = generation
        }
    }

    static func select(_ segments: [Segment], at query: Double, generation: UInt32,
                       cursor: inout Cursor) throws -> Int? {
        let starts = segments.map(\.start), lengths = segments.map(\.length), successors = segments.map(\.successor)
        var selected: Int64 = -1, updated = cursor.generation
        let status = starts.withUnsafeBufferPointer { start in
            lengths.withUnsafeBufferPointer { length in
                successors.withUnsafeBufferPointer { next in
                    rb_cpr_timeline_select(start.baseAddress, length.baseAddress, next.baseAddress, segments.count,
                        generation, query, cursor.current, cursor.generation, &selected, &updated)
                }
            }
        }
        guard status == 0 else {
            throw RebaseCoreError.unsupportedAudio("Native segment selection requires finite nonnegative normal-or-zero coordinates, valid links and round-to-nearest arithmetic.")
        }
        cursor.generation = updated
        return selected < 0 ? nil : Int(selected)
    }
}
