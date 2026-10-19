import Testing
import Foundation
import AVFoundation
import RebaseCore

final class ProjectBehaviorTests: AudioTestCase {
    @Test func tempoMapRetimesOnlyMusicalStartsTransactionally() throws {
        var seconds = try importClip([[0.25, 0.5]])
        seconds.position = 4
        var musical = seconds; musical.id = UUID(); musical.timeBase = .musical; musical.musicalPosition = 8
        var project = Project(tracks: [Track(name: "Linear", clips: [seconds]), Track(name: "Musical", clips: [musical], timeBase: .musical)])
        let oldLength = musical.duration
        try project.replaceTempoMap(TempoMap(events: [TempoEvent(beat: 0, bpm: 120), TempoEvent(beat: 4, bpm: 60)]))
        #expect(project.tracks[0].clips[0].position == 4)
        #expect(project.tracks[1].clips[0].position == 6)
        #expect(project.tracks[1].clips[0].duration == oldLength)
        #expect(project.tracks[1].clips[0].sourceOffset == 0)
        let before = project
        expectThrows(try project.replaceTempoMap(TempoMap(events: [TempoEvent(beat: 0, bpm: 0)])))
        #expect(project == before)
        try ProjectStore.save(project, to: root)
        #expect(try ProjectStore.load(from: root) == project)
    }

    @Test func automationUsesAbsoluteSampleTimeAcrossClipAndExportBoundary() throws {
        var clip = try importClip([Array(repeating: 0.5, count: 8)])
        clip.position = 8190 / rate
        let gain = AutomationLane(parameter: .gainDB, points: [
            AutomationPoint(time: 8190 / rate, value: -12),
            AutomationPoint(time: 8194 / rate, value: 0, interpolation: .step),
            AutomationPoint(time: 8196 / rate, value: -6)])
        let pan = AutomationLane(parameter: .pan, points: [
            AutomationPoint(time: 8190 / rate, value: -1), AutomationPoint(time: 8194 / rate, value: 1)])
        let project = Project(tracks: [Track(name: "Automated", clips: [clip], automation: [gain, pan])])
        let output = try OfflineRenderer.render(project: project, projectRoot: root)
        let destination = temporary.appendingPathComponent("automation.wav")
        try OfflineRenderer.export(project: project, projectRoot: root, to: destination)
        let file = try AVAudioFile(forReading: destination)
        let readback = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: UInt32(file.length))!
        try file.read(into: readback)
        let expectedDB = [-12.0, -9, -6, -3, 0, 0, -6, -6]
        let expectedPan = [-1.0, -0.5, 0, 0.5, 1, 1, 1, 1]
        for frame in 0..<8 {
            for channel in 0..<2 {
                let power = channel == 0 ? (1 - expectedPan[frame]) / 2 : (1 + expectedPan[frame]) / 2
                let expected = Float(0.5 * pow(10, expectedDB[frame] / 20) * sqrt(power))
                expectEqual(output.floatChannelData![channel][8190 + frame], expected, accuracy: 0.000001)
                #expect(output.floatChannelData![channel][8190 + frame].bitPattern == readback.floatChannelData![channel][8190 + frame].bitPattern)
            }
        }
        #expect(output.floatChannelData![0][8189] == 0)
    }

    @Test func automationReadOffUsesManualAndRejectsDuplicateParameterLanes() throws {
        let clip = try importClip([[0.5, -0.5]])
        let lane = AutomationLane(parameter: .gainDB, isReadEnabled: false, points: [AutomationPoint(time: 0, value: -96)])
        var project = Project(tracks: [Track(name: "Read off", gainDB: 0, pan: -1, clips: [clip], automation: [lane])])
        assertPlane(try OfflineRenderer.render(project: project, projectRoot: root), channel: 0, equals: [0.5, -0.5])
        project.tracks[0].automation.append(AutomationLane(parameter: .gainDB))
        expectThrows(try project.validate())
    }

    @Test func legacyProjectDefaultsAndStaleAnchorReject() throws {
        let clip = try importClip([[0.5]])
        let original = Project(tracks: [Track(name: "Legacy", clips: [clip])])
        var object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(original)) as! [String: Any]
        object.removeValue(forKey: "tempoMap"); object.removeValue(forKey: "signatureMap")
        var tracks = object["tracks"] as! [[String: Any]]
        tracks[0].removeValue(forKey: "automation")
        var clips = tracks[0]["clips"] as! [[String: Any]]; clips[0].removeValue(forKey: "timeBase")
        tracks[0]["clips"] = clips; object["tracks"] = tracks
        var loaded = try JSONDecoder().decode(Project.self, from: JSONSerialization.data(withJSONObject: object))
        try loaded.validate()
        #expect(loaded.tempo == 120 && loaded.tracks[0].automation.isEmpty)
        #expect(loaded.tracks[0].clips[0].timeBase == .seconds)
        loaded.tracks[0].clips[0].timeBase = .musical
        loaded.tracks[0].clips[0].musicalPosition = 1
        expectThrows(try loaded.validate())
    }
}
