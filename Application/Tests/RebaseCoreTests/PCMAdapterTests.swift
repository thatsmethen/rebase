import Foundation
import AVFoundation
import Testing
@testable import RebaseCore

struct PCMAdapterTests {
    @Test func exampleWaveDecoderAndSharedRendererMatchAVFoundationExactly() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Examples/Rebase Preview.rebaseproj")
        let project = try ProjectStore.load(from: root)
        let portable = try PCMRenderer.prepare(project) { clip in
            try WAVPCMSource(url: ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root))
        }
        let native = try AudioPreparation.prepare(project, root: root)
        #expect(portable.frameCount == 960_000 && native.frameCount == portable.frameCount)
        #expect(portable.clips.count == 11 && native.clips.count == portable.clips.count)
        for (a, b) in zip(portable.clips, native.clips) {
            #expect(a.startFrame == b.startFrame)
            #expect(a.buffer.frameCount == Int(b.buffer.frameLength))
            for channel in 0..<2 {
                let samples = UnsafeBufferPointer(start: b.buffer.floatChannelData![channel], count: Int(b.buffer.frameLength))
                #expect(a.buffer.channels[channel].map(\.bitPattern) == samples.map(\.bitPattern))
            }
        }
        // Independent adapter path: the existing AV buffer mixer and owned PCM
        // mixer must agree across a clip boundary and a final partial block.
        for start: Int64 in [0, 8191, 239_999, 479_999, 959_983] {
            let count = Int(min(8192, native.frameCount - start))
            let a = try PCMRenderer.mix(portable.clips, sampleRate: 48_000, from: start, count: count)
            let b = try AudioPreparation.buffer(format: native.format, frames: count)
            try OfflineRenderer.mix(native.clips, into: b, from: start)
            for channel in 0..<2 {
                let samples = UnsafeBufferPointer(start: b.floatChannelData![channel], count: count)
                #expect(a.channels[channel].map(\.bitPattern) == samples.map(\.bitPattern))
            }
        }
    }

    @Test func portableFloatWAVIsReadableByAVFoundation() throws {
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent("rebase-wave-\(UUID().uuidString).wav")
        defer { try? FileManager.default.removeItem(at: destination) }
        let source = try PCMBuffer(sampleRate: 48_000, channels: [[0.125, -0.5, 0, 1], [-0.25, 0.5, -1, 0]])
        try WAVPCMSource.encode(source).write(to: destination)
        let file = try AVAudioFile(forReading: destination, commonFormat: .pcmFormatFloat32, interleaved: false)
        let output = try AudioPreparation.buffer(format: file.processingFormat, frames: 4)
        try file.read(into: output)
        #expect(file.length == 4 && file.processingFormat.channelCount == 2)
        for channel in 0..<2 {
            #expect(Array(UnsafeBufferPointer(start: output.floatChannelData![channel], count: 4)) == source.channels[channel])
        }
    }
}
