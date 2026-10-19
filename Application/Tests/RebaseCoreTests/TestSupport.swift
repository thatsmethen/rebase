import Testing
import Foundation
import AVFoundation
import RebaseCore

class AudioTestCase {
    var temporary: URL!
    var root: URL { temporary.appendingPathComponent("Session.rebase", isDirectory: true) }
    let rate: Double = 48_000

    init() throws {
        temporary = FileManager.default.temporaryDirectory.appendingPathComponent("RebaseTests-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
        _ = try ProjectStore.create(at: root, name: "Fixture")
    }

    deinit {
        if let temporary { try? FileManager.default.removeItem(at: temporary) }
    }

    func writeAudio(_ planes: [[Float]], rate: Double = 48_000, name: String = UUID().uuidString) throws -> URL {
        precondition(!planes.isEmpty && !planes[0].isEmpty && planes.allSatisfy { $0.count == planes[0].count })
        let url = temporary.appendingPathComponent(name).appendingPathExtension("wav")
        let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: AVAudioChannelCount(planes.count))!
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(planes[0].count))!
        buffer.frameLength = buffer.frameCapacity
        for channel in planes.indices {
            for frame in planes[channel].indices { buffer.floatChannelData![channel][frame] = planes[channel][frame] }
        }
        let file = try AVAudioFile(forWriting: url, settings: format.settings, commonFormat: .pcmFormatFloat32, interleaved: false)
        try file.write(from: buffer)
        return url
    }

    func importClip(_ planes: [[Float]], rate: Double = 48_000) throws -> Clip {
        let source = try writeAudio(planes, rate: rate)
        let imported = try ProjectStore.importAudio(from: source, into: root)
        return Clip(mediaPath: imported.mediaPath, name: imported.name, duration: imported.duration)
    }

    func assertPlane(_ buffer: AVAudioPCMBuffer, channel: Int, equals expected: [Float], accuracy: Float = 0.000_001,
                     sourceLocation: SourceLocation = #_sourceLocation) {
        expectEqual(Int(buffer.frameLength), expected.count, sourceLocation: sourceLocation)
        guard Int(buffer.frameLength) == expected.count, let samples = buffer.floatChannelData else { return }
        for frame in expected.indices {
            expectEqual(samples[channel][frame], expected[frame], accuracy: accuracy,
                           "channel \(channel), frame \(frame)", sourceLocation: sourceLocation)
        }
    }
}

// Small assertion adapters preserve readable frame-specific diagnostics while
// using the Swift Testing framework supplied by Command Line Tools.
func expectEqual<T: Equatable>(_ lhs: @autoclosure () throws -> T, _ rhs: @autoclosure () throws -> T,
                               sourceLocation: SourceLocation = #_sourceLocation) {
    do { let a = try lhs(); let b = try rhs(); #expect(a == b, sourceLocation: sourceLocation) }
    catch { Issue.record(error, sourceLocation: sourceLocation) }
}
func expectEqual(_ lhs: Float, _ rhs: Float, accuracy: Float, _ message: String = "",
                 sourceLocation: SourceLocation = #_sourceLocation) {
    #expect(abs(lhs - rhs) <= accuracy, Comment(rawValue: message), sourceLocation: sourceLocation)
}
func expectNotEqual<T: Equatable>(_ lhs: T, _ rhs: T, sourceLocation: SourceLocation = #_sourceLocation) {
    #expect(lhs != rhs, sourceLocation: sourceLocation)
}
func expectTrue(_ value: Bool, sourceLocation: SourceLocation = #_sourceLocation) {
    #expect(value, sourceLocation: sourceLocation)
}
func expectThrows<T>(_ expression: @autoclosure () throws -> T, _ message: String = "",
                     sourceLocation: SourceLocation = #_sourceLocation) {
    do { _ = try expression(); Issue.record(Comment(rawValue: "Expected an error. " + message), sourceLocation: sourceLocation) }
    catch { }
}
func expectNoThrow<T>(_ expression: @autoclosure () throws -> T, sourceLocation: SourceLocation = #_sourceLocation) {
    do { _ = try expression() } catch { Issue.record(error, sourceLocation: sourceLocation) }
}
