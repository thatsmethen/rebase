import Testing
import Foundation
import AVFoundation
import RebaseCore

final class AudioValidityTests: AudioTestCase {
    private func expectAudioFailure<T>(_ expression: @autoclosure () throws -> T,
                                       sourceLocation: SourceLocation = #_sourceLocation) {
        do {
            _ = try expression()
            Issue.record("Expected a nonfinite-audio validation error", sourceLocation: sourceLocation)
        } catch RebaseCoreError.nonFiniteAudio(_) {
            // Other I/O or shape failures do not establish the validation claim.
        } catch {
            Issue.record(error, sourceLocation: sourceLocation)
        }
    }

    private func assertRenderAndExportReject(_ project: Project, sourceLocation: SourceLocation = #_sourceLocation) throws {
        expectAudioFailure(try OfflineRenderer.render(project: project, projectRoot: root), sourceLocation: sourceLocation)
        let existingDestination = try writeAudio([[0.125, -0.25]], name: "Existing-" + UUID().uuidString)
        let existingBytes = try Data(contentsOf: existingDestination)
        let before = Set(try FileManager.default.contentsOfDirectory(atPath: temporary.path))
        expectAudioFailure(try OfflineRenderer.export(project: project, projectRoot: root, to: existingDestination), sourceLocation: sourceLocation)
        expectEqual(try Data(contentsOf: existingDestination), existingBytes, sourceLocation: sourceLocation)
        expectEqual(Set(try FileManager.default.contentsOfDirectory(atPath: temporary.path)), before, sourceLocation: sourceLocation)
    }

    @Test func testNonfiniteDecodedSamplesAreRejectedWithoutReplacingExistingExport() throws {
        for invalid in [Float.nan, .infinity, -.infinity] {
            let source = try writeAudio([[0.25, invalid]])
            // Confirm the fixture really contains the malformed sample and the
            // decoder preserves it; a file-open error would not test validation.
            let file = try AVAudioFile(forReading: source, commonFormat: .pcmFormatFloat32, interleaved: false)
            let decoded = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: 2)!
            try file.read(into: decoded)
            expectEqual(decoded.frameLength, 2)
            expectTrue(!decoded.floatChannelData![0][1].isFinite)
            let media = root.appendingPathComponent("Media")
            let beforeImport = Set(try FileManager.default.contentsOfDirectory(atPath: media.path))
            expectAudioFailure(try ProjectStore.importAudio(from: source, into: root))
            expectEqual(Set(try FileManager.default.contentsOfDirectory(atPath: media.path)), beforeImport)
            // Bypass import to model media changed externally after a project
            // was saved. Loading and direct rendering must still reject it.
            let relative = "Media/" + UUID().uuidString + ".wav"
            try FileManager.default.copyItem(at: source, to: root.appendingPathComponent(relative))
            let clip = Clip(mediaPath: relative, name: "Invalid sample", duration: 2 / rate)
            let project = Project(tracks: [Track(name: "Input", pan: -1, clips: [clip])])
            try JSONEncoder().encode(project).write(to: root.appendingPathComponent(ProjectStore.manifestName))
            expectAudioFailure(try ProjectStore.load(from: root))
            try assertRenderAndExportReject(project)
        }
    }

    @Test func testFiniteSourceWhoseGainOverflowsIsRejected() throws {
        let finite = Float.greatestFiniteMagnitude
        expectTrue(finite.isFinite)
        let clip = try importClip([[0.25, finite]])
        let project = Project(tracks: [Track(name: "Gain overflow", gainDB: 24, pan: -1, clips: [clip])])
        try assertRenderAndExportReject(project)
    }

    @Test func testFiniteClipsWhoseOverlapOverflowsAreRejected() throws {
        let finite = Float.greatestFiniteMagnitude * 0.75
        let clip = try importClip([[0.25, finite], [-0.25, -finite]])
        let first = Track(name: "First", clips: [clip])
        // Each clip independently renders a finite value, with no pan attenuation
        // or gain increase. Only simultaneous accumulation causes overflow.
        let independentlyRendered = try OfflineRenderer.render(project: Project(tracks: [first]), projectRoot: root)
        expectEqual(independentlyRendered.floatChannelData![0][1], finite)
        expectEqual(independentlyRendered.floatChannelData![1][1], -finite)
        var secondClip = clip
        secondClip.id = UUID()
        let project = Project(tracks: [first, Track(name: "Second", clips: [secondClip])])
        try assertRenderAndExportReject(project)
    }
}
