import Testing
import Foundation
import AVFoundation
import RebaseCore

final class OfflineRendererTests: AudioTestCase {
    @Test func testTrimAndPositionSelectExactFramesAndLeaveTimelineGapSilent() throws {
        var clip = try importClip([[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]])
        clip.sourceOffset = 2 / rate
        clip.duration = 4 / rate
        clip.position = 3 / rate
        let project = Project(tracks: [Track(name: "Trim", pan: -1, clips: [clip])])
        let output = try OfflineRenderer.render(project: project, projectRoot: root)
        assertPlane(output, channel: 0, equals: [0, 0, 0, 0.3, 0.4, 0.5, 0.6])
        assertPlane(output, channel: 1, equals: Array(repeating: 0, count: 7))
    }

    @Test func testOverlappingClipsAndTrackGainSumRatherThanOverwrite() throws {
        let clip = try importClip([[0.25, -0.5, 0.75, -1]])
        var second = clip
        second.id = UUID()
        let halfGainDB = -6.020599913279624
        let project = Project(tracks: [Track(name: "A", gainDB: halfGainDB, pan: -1, clips: [clip]),
                                      Track(name: "B", pan: -1, clips: [second])])
        let output = try OfflineRenderer.render(project: project, projectRoot: root)
        assertPlane(output, channel: 0, equals: [0.375, -0.75, 1.125, -1.5])
        assertPlane(output, channel: 1, equals: [0, 0, 0, 0])
    }

    @Test func testSoloExcludesOtherTracksAndMuteOverridesSolo() throws {
        let left = try importClip([[0.2, 0.2]])
        let right = try importClip([[0.1, 0.1]])
        let excluded = try importClip([[0.7, 0.7]])
        let muted = try importClip([[0.6, 0.6]])
        let project = Project(tracks: [Track(name: "Left", pan: -1, isSolo: true, clips: [left]),
                                      Track(name: "Right", pan: 1, isSolo: true, clips: [right]),
                                      Track(name: "Excluded", clips: [excluded]),
                                      Track(name: "Muted solo", isMuted: true, isSolo: true, clips: [muted])])
        let output = try OfflineRenderer.render(project: project, projectRoot: root)
        assertPlane(output, channel: 0, equals: [0.2, 0.2])
        assertPlane(output, channel: 1, equals: [0.1, 0.1])
    }

    @Test func testMonoCenterPreservesEnergyAndStereoCenterPreservesEachChannel() throws {
        let mono = try importClip([[0.5, -0.5]])
        let monoOutput = try OfflineRenderer.render(project: Project(tracks: [Track(name: "Mono", clips: [mono])]), projectRoot: root)
        let center: Float = 0.3535533905932738
        assertPlane(monoOutput, channel: 0, equals: [center, -center])
        assertPlane(monoOutput, channel: 1, equals: [center, -center])
        let stereo = try importClip([[0.25, -0.25], [0.75, -0.75]])
        for pan in [-1.0, 0, 1] {
            let output = try OfflineRenderer.render(project: Project(tracks: [Track(name: "Stereo", pan: pan, clips: [stereo])]), projectRoot: root)
            assertPlane(output, channel: 0, equals: pan == 1 ? [0, 0] : [0.25, -0.25])
            assertPlane(output, channel: 1, equals: pan == -1 ? [0, 0] : [0.75, -0.75])
        }
    }

    @Test func testLinearResamplingReconstructsRampBetweenSourceSamples() throws {
        let clip = try importClip([[0, 0.2, 0.4, 0.6]], rate: 24_000)
        let output = try OfflineRenderer.render(project: Project(tracks: [Track(name: "Ramp", pan: -1, clips: [clip])]), projectRoot: root)
        expectEqual(output.frameLength, 8)
        let expected: [Float] = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        for frame in expected.indices {
            expectEqual(output.floatChannelData![0][frame], expected[frame], accuracy: 0.000_001)
        }
    }

    @Test func testExportedWAVContainsStereoFloatMix() throws {
        let clip = try importClip([[0.125, -0.25, 0.5, -0.75]])
        let project = Project(tracks: [Track(name: "Export", pan: 1, clips: [clip])])
        let destination = temporary.appendingPathComponent("mix.wav")
        expectEqual(try OfflineRenderer.export(project: project, projectRoot: root, to: destination), destination)
        let file = try AVAudioFile(forReading: destination, commonFormat: .pcmFormatFloat32, interleaved: false)
        expectEqual(file.processingFormat.sampleRate, rate)
        expectEqual(file.processingFormat.channelCount, 2)
        expectEqual(file.fileFormat.settings[AVLinearPCMIsFloatKey] as? Bool, true)
        let readback = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length))!
        try file.read(into: readback)
        assertPlane(readback, channel: 0, equals: [0, 0, 0, 0])
        assertPlane(readback, channel: 1, equals: [0.125, -0.25, 0.5, -0.75])
    }

    @Test func testSourceOverrunAndEmptyTimelineFailExplicitly() throws {
        var clip = try importClip([[0.1, 0.2, 0.3, 0.4]])
        clip.sourceOffset = 3 / rate
        clip.duration = 2 / rate
        expectThrows(try OfflineRenderer.render(project: Project(tracks: [Track(name: "Overrun", clips: [clip])]), projectRoot: root))
        expectThrows(try OfflineRenderer.render(project: Project(), projectRoot: root))
    }

    @Test func testExportCrossesChunkBoundaryReplacesMixAndPreservesSource() throws {
        var clip = try importClip([[0.2, 0.4, 0.6]])
        let sourceURL = try ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root)
        let sourceBytes = try Data(contentsOf: sourceURL)
        clip.position = 8_191 / rate
        var project = Project(tracks: [Track(name: "Boundary", pan: -1, clips: [clip])])
        let destination = temporary.appendingPathComponent("replace.wav")
        try OfflineRenderer.export(project: project, projectRoot: root, to: destination)
        project.tracks[0].pan = 1
        try OfflineRenderer.export(project: project, projectRoot: root, to: destination)
        let file = try AVAudioFile(forReading: destination, commonFormat: .pcmFormatFloat32, interleaved: false)
        expectEqual(file.length, 8_194)
        file.framePosition = 8_189
        let tail = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: 5)!
        try file.read(into: tail)
        assertPlane(tail, channel: 0, equals: [0, 0, 0, 0, 0])
        assertPlane(tail, channel: 1, equals: [0, 0, 0.2, 0.4, 0.6])
        expectThrows(try OfflineRenderer.export(project: project, projectRoot: root, to: sourceURL))
        expectEqual(try Data(contentsOf: sourceURL), sourceBytes)
    }
}
