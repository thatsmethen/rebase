import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

struct AutomationRenderingTests {
    private struct ConstantSource: PCMSourceReader {
        let sampleRate: Double = 24_000
        let channelCount: Int
        let frameCount: Int64 = 100
        func read(from start: Int64, count: Int) throws -> PCMBuffer {
            try PCMBuffer(sampleRate: sampleRate, channels: Array(repeating: Array(repeating: 0.25, count: count), count: channelCount))
        }
    }
    private func project(_ lanes: [AutomationLane], gain: Double = 6, pan: Double = -1) -> Project {
        Project(sampleRate: 48_000, tracks: [Track(name: "Authored constant source", gainDB: gain, pan: pan,
            clips: [Clip(mediaPath: "Media/constant.wav", name: "Constant", position: 2.4 / 48_000,
                sourceOffset: 3.5 / 24_000, duration: 8.0 / 48_000)], automation: lanes)])
    }
    private func render(_ project: Project, channels: Int = 1) throws -> PCMBuffer {
        let prepared = try PCMRenderer.prepare(project) { _ in ConstantSource(channelCount: channels) }
        #expect(prepared.clips[0].startFrame == 2 && prepared.frameCount == 10)
        return try PCMRenderer.mix(prepared.clips, sampleRate: prepared.sampleRate, from: 0, count: 10)
    }
    private func close(_ actual: Float, _ expected: Double) -> Bool { abs(Double(actual) - expected) < 0.000_000_1 }

    @Test func gainCurveRendersDBLinearAndOutgoingStepAtAbsoluteRoundedProjectFrames() throws {
        let lane = AutomationLane(parameter: .gainDB, points: [
            AutomationPoint(time: 0, value: -24),
            AutomationPoint(time: 4.0 / 48_000, value: 0, interpolation: .step),
            AutomationPoint(time: 6.0 / 48_000, value: -18),
            AutomationPoint(time: 8.0 / 48_000, value: -6)
        ])
        let audio = try render(project([lane]))
        #expect(audio.channels[0][0...1] == [0, 0])
        // Analytic expected dB values at project frames 2...9. The clip starts
        // at 2.4 frames and reads a different source offset/rate; neither shifts
        // these automation boundaries. Manual +6 dB is replaced, not added.
        let expectedDB = [-12.0, -6, 0, 0, -18, -12, -6, -6]
        for (index, db) in expectedDB.enumerated() {
            #expect(close(audio.channels[0][index + 2], 0.25 * pow(10, db / 20)))
            #expect(audio.channels[1][index + 2] == 0)
        }
        #expect(!close(audio.channels[0][2], 0.25 * (pow(10, -24.0 / 20) + 1) / 2))
    }

    @Test func readOffAndEmptyLaneRenderManualGainWithoutChangingStoredPoints() throws {
        let points = [AutomationPoint(time: 0, value: 24), AutomationPoint(time: 1, value: -96)]
        let disabled = AutomationLane(parameter: .gainDB, isReadEnabled: false, points: points)
        for lanes in [[], [disabled], [AutomationLane(parameter: .gainDB)]] {
            let input = project(lanes, gain: -6, pan: 0.5), audio = try render(input)
            for frame in 2..<10 {
                #expect(close(audio.channels[0][frame], 0.25 * pow(10, -6.0 / 20) * 0.5))
                #expect(close(audio.channels[1][frame], 0.25 * pow(10, -6.0 / 20) * sqrt(0.75)))
            }
            #expect(input.tracks[0].automation == lanes)
        }
        #expect(disabled.points == points)
    }

    @Test func panStepAndReadToggleRenderIndependentOfVolumeForMonoAndStereo() throws {
        let volume = AutomationLane(parameter: .gainDB, points: [AutomationPoint(time: 0, value: -12)])
        let pan = AutomationLane(parameter: .pan, points: [
            AutomationPoint(time: 0, value: -1, interpolation: .step),
            AutomationPoint(time: 4.0 / 48_000, value: 1)
        ])
        for channels in [1, 2] {
            var input = project([volume, pan], gain: 18, pan: 0)
            let automated = try render(input, channels: channels), amplitude = 0.25 * pow(10, -12.0 / 20)
            #expect(close(automated.channels[0][3], amplitude) && automated.channels[1][3] == 0)
            #expect(automated.channels[0][4] == 0 && close(automated.channels[1][4], amplitude))
            input.tracks[0].automation[1].isReadEnabled = false
            let manualPan = try render(input, channels: channels)
            for frame in 2..<10 {
                let expected = amplitude * (channels == 1 ? sqrt(0.5) : 1)
                #expect(close(manualPan.channels[0][frame], expected) && close(manualPan.channels[1][frame], expected))
            }
            #expect(input.tracks[0].automation[0] == volume && input.tracks[0].automation[1].points == pan.points)
        }
    }
}
