import Foundation

#if REBASE_PORTABLE
/// SHA-256 for byte identities in the framework-independent inspection target.
/// This is not an encryption or authentication API. Known-answer tests cover
/// empty, short, multi-block, padding-boundary and million-byte messages.
enum PortableSHA256 {
    private static let constants: [UInt32] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
    ]

    private static func rotate(_ value: UInt32, by count: UInt32) -> UInt32 {
        (value >> count) | (value << (32 - count))
    }

    /// Incremental state retains only a partial 64-byte block and fixed words.
    /// Finalization is non-destructive, so callers can inspect a prefix digest.
    struct Hasher {
        private var state: [UInt32] = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                       0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
        private var words = [UInt32](repeating: 0, count: 64)
        private var pending: [UInt8] = []
        private(set) var byteCount: UInt64 = 0
        var bufferedByteCount: Int { pending.count }

        mutating func update(_ data: Data) {
            precondition(UInt64(data.count) <= UInt64.max / 8 - byteCount)
            byteCount += UInt64(data.count)
            data.withUnsafeBytes { (bytes: UnsafeRawBufferPointer) in
                var offset = 0
                if !pending.isEmpty {
                    let take = min(64 - pending.count, bytes.count)
                    pending.append(contentsOf: bytes.prefix(take)); offset += take
                    if pending.count == 64 {
                        let block = pending
                        block.withUnsafeBytes { compress($0) }
                        pending.removeAll(keepingCapacity: true)
                    }
                }
                while bytes.count - offset >= 64 {
                    compress(UnsafeRawBufferPointer(rebasing: bytes[offset..<(offset + 64)]))
                    offset += 64
                }
                pending.append(contentsOf: bytes.dropFirst(offset))
            }
        }

        func hexDigest() -> String {
            var finalized = self
            var tail = pending
            tail.append(0x80)
            while tail.count % 64 != 56 { tail.append(0) }
            let bitCount = byteCount * 8
            for shift in stride(from: 56, through: 0, by: -8) {
                tail.append(UInt8(truncatingIfNeeded: bitCount >> UInt64(shift)))
            }
            tail.withUnsafeBytes { (bytes: UnsafeRawBufferPointer) in
                for offset in stride(from: 0, to: bytes.count, by: 64) {
                    finalized.compress(UnsafeRawBufferPointer(rebasing: bytes[offset..<(offset + 64)]))
                }
            }
            let digits = Array("0123456789abcdef".utf8)
            var result = [UInt8](); result.reserveCapacity(64)
            for word in finalized.state {
                for shift in stride(from: 28, through: 0, by: -4) {
                    result.append(digits[Int((word >> UInt32(shift)) & 15)])
                }
            }
            return String(decoding: result, as: UTF8.self)
        }

        private mutating func compress(_ block: UnsafeRawBufferPointer) {
            for i in 0..<16 {
                let j = i * 4
                words[i] = UInt32(block[j]) << 24 | UInt32(block[j + 1]) << 16 |
                    UInt32(block[j + 2]) << 8 | UInt32(block[j + 3])
            }
            for i in 16..<64 {
                let x = words[i - 15], y = words[i - 2]
                let low = rotate(x, by: 7) ^ rotate(x, by: 18) ^ (x >> 3)
                let high = rotate(y, by: 17) ^ rotate(y, by: 19) ^ (y >> 10)
                words[i] = words[i - 16] &+ low &+ words[i - 7] &+ high
            }
            var a = state[0], b = state[1], c = state[2], d = state[3]
            var e = state[4], f = state[5], g = state[6], h = state[7]
            for i in 0..<64 {
                let sigma1 = rotate(e, by: 6) ^ rotate(e, by: 11) ^ rotate(e, by: 25)
                let choose = (e & f) ^ (~e & g)
                let first = h &+ sigma1 &+ choose &+ constants[i] &+ words[i]
                let sigma0 = rotate(a, by: 2) ^ rotate(a, by: 13) ^ rotate(a, by: 22)
                let majority = (a & b) ^ (a & c) ^ (b & c)
                let second = sigma0 &+ majority
                h = g; g = f; f = e; e = d &+ first
                d = c; c = b; b = a; a = first &+ second
            }
            for (i, value) in [a, b, c, d, e, f, g, h].enumerated() { state[i] &+= value }
        }
    }

    static func hexDigest(_ data: Data) -> String {
        var hasher = Hasher(); hasher.update(data); return hasher.hexDigest()
    }
}
#endif
