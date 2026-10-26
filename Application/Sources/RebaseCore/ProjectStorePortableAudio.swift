#if REBASE_PORTABLE
import Foundation

enum ProjectStoreMedia {
    static func inspectImport(url: URL, name: String) throws -> (sampleRate: Double, frameCount: Int64, channelCount: Int) {
        let reader = try WAVPCMSource(url: url)
        var position: Int64 = 0
        while position < reader.frameCount {
            let count = Int(min(8192, reader.frameCount - position))
            _ = try reader.read(from: position, count: count)
            position += Int64(count)
        }
        return (reader.sampleRate, reader.frameCount, reader.channelCount)
    }
    static func scan(url: URL, name: String) throws -> (sampleRate: Double, frameCount: Int64) {
        let facts = try inspectImport(url: url, name: name)
        return (facts.sampleRate, facts.frameCount)
    }
}
#endif
