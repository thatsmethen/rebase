import Foundation

/// Owned planar Float32 stereo output. Allocation and device scheduling are
/// application policy; sample operations belong to the shared audition cursor.
public struct StereoPCMBlock {
    public private(set) var left: [Float]
    public private(set) var right: [Float]
    public var frameCount: Int { left.count }

    public init(left: [Float], right: [Float]) throws {
        guard left.count == right.count, left.count <= 16_000_000 else {
            throw RebaseCoreError.mediaTooLarge
        }
        self.left = left; self.right = right
    }

    init(frameCount: Int) throws {
        guard (0...16_000_000).contains(frameCount) else { throw RebaseCoreError.mediaTooLarge }
        left = [Float](repeating: 0, count: frameCount)
        right = [Float](repeating: 0, count: frameCount)
    }

    init(interleaved samples: ArraySlice<Float>) throws {
        guard samples.count % 2 == 0, samples.count <= 32_000_000 else {
            throw RebaseCoreError.mediaTooLarge
        }
        try self.init(frameCount: samples.count / 2)
        let first = samples.startIndex
        for frame in 0..<frameCount {
            left[frame] = samples[first + frame * 2]
            right[frame] = samples[first + frame * 2 + 1]
        }
    }

    public var interleaved: [Float] {
        var samples = [Float](repeating: 0, count: frameCount * 2)
        for frame in 0..<frameCount {
            samples[frame * 2] = left[frame]
            samples[frame * 2 + 1] = right[frame]
        }
        return samples
    }

    mutating func withUnsafeMutableChannels<T>(
        _ body: (UnsafeMutablePointer<Float>, UnsafeMutablePointer<Float>) throws -> T
    ) rethrows -> T {
        try left.withUnsafeMutableBufferPointer { left in
            try right.withUnsafeMutableBufferPointer { right in
                // Callers admit a nonempty block before accessing its planes.
                try body(left.baseAddress!, right.baseAddress!)
            }
        }
    }
}
