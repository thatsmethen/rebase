#if REBASE_PORTABLE
import Foundation

extension ProjectStore {
    static func validateCPRAudioMedia(_ project: Project, at root: URL) throws {
        guard project.cprMediaAttachments.isEmpty else {
            throw RebaseCoreError.unsupportedAudio("Portable project storage cannot yet validate CPR media attachments. Open this project in the macOS application; its source and associations have not been changed.")
        }
    }
}

enum ProjectStoreMedia {
    static func scan(url: URL, name: String) throws -> (sampleRate: Double, frameCount: Int64) {
        let reader = try WAVPCMSource(url: url)
        var position: Int64 = 0
        while position < reader.frameCount {
            let count = Int(min(8192, reader.frameCount - position))
            _ = try reader.read(from: position, count: count)
            position += Int64(count)
        }
        return (reader.sampleRate, reader.frameCount)
    }
}
#endif
