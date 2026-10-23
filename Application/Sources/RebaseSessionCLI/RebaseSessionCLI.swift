import Foundation
import RebasePortable
#if os(Windows)
import WinSDK
#elseif canImport(Darwin)
import Darwin
#else
import Glibc
#endif

@main struct RebaseSessionCLI {
    static func main() {
        guard Array(CommandLine.arguments.dropFirst()) == ["--stdio"] else {
            FileHandle.standardError.write(Data("Usage: rebase-session --stdio\n".utf8))
            finish(2)
        }
        let session = PortableSession()
        var pending = Data()
        do {
            // read(upToCount:) may fill the requested length on a pipe. The
            // interactive host needs each available frame before closing stdin.
            while true {
                let chunk = FileHandle.standardInput.availableData
                if chunk.isEmpty { break }
                pending.append(chunk)
                while let end = pending.firstIndex(of: 10) {
                    let line = Data(pending[..<end])
                    guard line.count <= PortableSession.maximumRequestBytes else { finish(2) }
                    let response = session.process(line)
                    try FileHandle.standardOutput.write(contentsOf: response + Data([10]))
                    pending.removeSubrange(...end)
                }
                guard pending.count <= PortableSession.maximumRequestBytes else { finish(2) }
            }
            // A truncated final request must never be interpreted as an edit.
            if !pending.isEmpty { finish(2) }
        } catch { finish(1) }
    }
    private static func finish(_ status: UInt32) -> Never {
        #if os(Windows)
        ExitProcess(status)
        #else
        exit(Int32(status))
        #endif
    }
}
