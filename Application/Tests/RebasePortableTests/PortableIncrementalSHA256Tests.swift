import Foundation
import Testing
@testable import RebasePortable

struct PortableIncrementalSHA256Tests {
    @Test func knownAnswersAcrossEveryPaddingAndPartitionBoundary() {
        let vectors: [(Data, String)] = [
            (Data(), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
            (Data("abc".utf8), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
            (Data("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq".utf8), "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
            (Data(repeating: 97, count: 1_000_000), "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0")]
        for (data, expected) in vectors {
            for size in [1, 55, 56, 63, 64, 65, 257, 8192] {
                var hash = PortableSHA256.Hasher()
                var peak = 0
                for first in stride(from: 0, to: data.count, by: size) {
                    hash.update(data.subdata(in: first..<min(data.count, first + size)))
                    peak = max(peak, hash.bufferedByteCount)
                }
                #expect(hash.hexDigest() == expected && hash.byteCount == UInt64(data.count) && peak < 64)
            }
        }
    }
    @Test func PrefixFinalizationDoesNotChangeFutureInputOrCopiedState() {
        var hash = PortableSHA256.Hasher(); hash.update(Data("a".utf8))
        let prefix = hash.hexDigest(), repeated = hash.hexDigest()
        #expect(prefix == repeated && prefix == "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb")
        var other = hash; other.update(Data("bc".utf8)); hash.update(Data(" different suffix".utf8))
        #expect(other.hexDigest() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        #expect(hash.hexDigest() == PortableSHA256.hexDigest(Data("a different suffix".utf8)))
        #expect(hash.hexDigest() != other.hexDigest())
    }
}
