import Foundation
import Testing
#if canImport(RebaseCore)
import AVFoundation
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

struct SharedCPRAudioTests {
    private func workspace(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("SharedCPRAudio-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }

    private func attached(_ control: CPRAudioControl.Fixture) throws -> (Project, UUID) {
        let event = try #require(control.project.unresolvedAudioEvents.first)
        let project = try ProjectStore.attachCPRAudioMedia(from: control.media, to: event.id,
            in: control.project, at: control.root)
        return (project, event.id)
    }

    private func preserved(_ root: URL) throws -> [Data] {
        try [ProjectStore.manifestName, CPRProject.originalRelativePath, CPRProject.reportRelativePath].map {
            try Data(contentsOf: root.appendingPathComponent($0))
        }
    }

    @Test func authoredAttachmentRoundtripAndStereoAuditionPreserveExactSourceBytes() throws {
        try workspace { directory in
            let control = try CPRAudioControl.makePackage(in: directory)
            var (project, eventID) = try attached(control)
            project.sampleRate = 48_000
            project.tracks[0].gainDB = -12; project.tracks[0].pan = -0.75
            try ProjectStore.save(project, to: control.root)
            let before = try preserved(control.root)
            #expect(try ProjectStore.load(from: control.root) == project)
            let attachment = try #require(project.cprMediaAttachments.first)
            #expect(attachment.association == "user-selected" && attachment.bitsPerSample == 24)
            let copied = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: control.root)
            #expect(try Data(contentsOf: copied) == control.mediaBytes)
            let audio = try CPRSourceEventRenderer.prepareAudition(eventID: eventID, in: project, at: control.root)
            let expected = control.samples.map { Float((Double($0) / 8_388_608) * Double(Float(0.75))).bitPattern }
            #expect(audio.samples.map(\.bitPattern) == expected)
            #expect(audio.sampleRate == 44_100 && audio.channelCount == 2 && audio.frameCount == 8)
            #expect(audio.mediaSHA256 == attachment.mediaSHA256 && audio.sourceSHA256 == attachment.sourceSHA256)
            let output = directory.appendingPathComponent("Audition.wav")
            let rendered = try CPRSourceEventRenderer.renderAudition(eventID: eventID, in: project, at: control.root, to: output)
            let wave = try WAVPCMSource(url: output).read(from: 0, count: 8)
            let actual = (0..<8).flatMap { [wave.channels[0][$0].bitPattern, wave.channels[1][$0].bitPattern] }
            #expect(actual == expected)
            #expect(rendered.outputSHA256 == cprSHA256(try Data(contentsOf: output)))
            #expect(try preserved(control.root) == before)
            #expect(project.tracks.flatMap(\.clips).isEmpty)
            #expect(throws: (any Error).self) { try project.requireResolvedAudioEvents() }
            #if canImport(RebaseCore)
            let native = try CPRSourceEventPlayback.prepare(eventID: eventID, project: project, root: control.root)
            let buffer = try #require(native.audio.clips.first?.buffer)
            let channels = try #require(buffer.floatChannelData)
            let mac = (0..<8).flatMap { [channels[0][$0].bitPattern, channels[1][$0].bitPattern] }
            #expect(mac == expected && native.info.sampleRate == 44_100)
            #endif
        }
    }

    @Test func incompatibleStoredFormatNeverCreatesAnAssociationOrLeavesCopiedMedia() throws {
        try workspace { directory in
            let control = try CPRAudioControl.makePackage(in: directory)
            let event = try #require(control.project.unresolvedAudioEvents.first)
            let before = try preserved(control.root)
            let short = CPRAudioControl.wave(samples: Array(control.samples.dropLast(2)))
            let wrongRate = CPRAudioControl.wave(samples: control.samples, rate: 48_000)
            let float32 = try WAVPCMSource.encode(PCMBuffer(sampleRate: 44_100,
                channels: [Array(repeating: Float(0), count: 8), Array(repeating: Float(0), count: 8)]))
            for bytes in [short, wrongRate, float32, Data(control.mediaBytes.dropLast())] {
                try bytes.write(to: control.media)
                #expect(throws: (any Error).self) {
                    try ProjectStore.attachCPRAudioMedia(from: control.media, to: event.id, in: control.project, at: control.root)
                }
                #expect(try FileManager.default.contentsOfDirectory(atPath: control.root.appendingPathComponent("Media").path).isEmpty)
                #expect(try preserved(control.root) == before)
            }
        }
    }

    @Test func sharedFileAssociationChecksEveryRetainedEventInterval() throws {
        try workspace { directory in
            var options = CPRAudioControl.Options(); options.secondSegmentLength = 9
            let invalid = try CPRAudioControl.makePackage(in: directory, name: "OutOfBounds", options: options)
            let before = try preserved(invalid.root)
            #expect(invalid.project.unresolvedAudioEvents.count == 2)
            #expect(throws: (any Error).self) { try attached(invalid) }
            #expect(try FileManager.default.contentsOfDirectory(atPath: invalid.root.appendingPathComponent("Media").path).isEmpty)
            #expect(try preserved(invalid.root) == before)
            options.secondSegmentLength = 8
            let valid = try CPRAudioControl.makePackage(in: directory, name: "Shared", options: options)
            var (project, eventID) = try attached(valid)
            #expect(project.cprMediaAttachments.count == 1 && project.unresolvedAudioEvents.count == 2)
            project.tracks[0].unresolvedAudioEvents.removeAll { $0.id == eventID }
            try ProjectStore.save(project, to: valid.root)
            #expect(try ProjectStore.load(from: valid.root) == project)
            let remaining = try #require(project.unresolvedAudioEvents.first)
            #expect(try CPRSourceEventRenderer.prepareAudition(eventID: remaining.id, in: project, at: valid.root).frameCount == 8)
        }
    }

    @Test func sourceReportAndMediaTamperingAreRecheckedBeforeEverySnapshot() throws {
        try workspace { directory in
            let control = try CPRAudioControl.makePackage(in: directory)
            let (project, eventID) = try attached(control)
            try ProjectStore.save(project, to: control.root)
            let manifest = try Data(contentsOf: control.root.appendingPathComponent(ProjectStore.manifestName))
            let attachment = try #require(project.cprMediaAttachments.first)
            let media = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: control.root)
            let output = directory.appendingPathComponent("Accepted.wav")
            _ = try CPRSourceEventRenderer.renderAudition(eventID: eventID, in: project, at: control.root, to: output)
            let accepted = try Data(contentsOf: output)
            for path in [media, control.root.appendingPathComponent(CPRProject.originalRelativePath),
                         control.root.appendingPathComponent(CPRProject.reportRelativePath)] {
                let bytes = try Data(contentsOf: path)
                var changed = bytes; changed[changed.count - 1] ^= 1
                try changed.write(to: path)
                #expect(throws: (any Error).self) {
                    try CPRSourceEventRenderer.prepareAudition(eventID: eventID, in: project, at: control.root)
                }
                #expect(throws: (any Error).self) { try ProjectStore.save(project, to: control.root) }
                #expect(throws: (any Error).self) { try ProjectStore.load(from: control.root) }
                #expect(try Data(contentsOf: control.root.appendingPathComponent(ProjectStore.manifestName)) == manifest)
                #expect(try Data(contentsOf: output) == accepted)
                try bytes.write(to: path)
                #expect(try CPRSourceEventRenderer.prepareAudition(eventID: eventID, in: project, at: control.root).frameCount == 8)
            }
        }
    }

    @Test func unsupportedSourceProcessingAndMonoNeverEnterStereoAudition() throws {
        try workspace { directory in
            var controls: [CPRAudioControl.Options] = []
            var option = CPRAudioControl.Options(); option.autoFadeFlags = 1; controls.append(option)
            option = .init(); option.transposeLock = 0; controls.append(option)
            option = .init(); option.inverted = 1; controls.append(option)
            option = .init(); option.priority = 2; controls.append(option)
            option = .init(); option.position = 1; controls.append(option)
            option = .init(); option.channels = 1; controls.append(option)
            for (index, option) in controls.enumerated() {
                let control = try CPRAudioControl.makePackage(in: directory, name: "Rejected\(index)", options: option)
                let (project, eventID) = try attached(control)
                let before = try preserved(control.root)
                let output = directory.appendingPathComponent("Rejected\(index).wav.preview")
                #expect(throws: (any Error).self) {
                    try CPRSourceEventRenderer.prepareAudition(eventID: eventID, in: project, at: control.root)
                }
                #expect(throws: (any Error).self) {
                    try CPRSourceEventRenderer.renderAudition(eventID: eventID, in: project, at: control.root, to: output)
                }
                #expect(!FileManager.default.fileExists(atPath: output.path))
                #expect(try preserved(control.root) == before)
            }
        }
    }

    @Test func auditionPublicationRefusesOverwriteAndPackageContainment() throws {
        try workspace { directory in
            let control = try CPRAudioControl.makePackage(in: directory)
            let (project, eventID) = try attached(control)
            let output = directory.appendingPathComponent("Existing.wav")
            let sentinel = Data([5, 7, 11, 13]); try sentinel.write(to: output)
            let manifest = control.root.appendingPathComponent(ProjectStore.manifestName)
            let inside = control.root.appendingPathComponent("Media/Output.wav")
            for destination in [output, manifest, inside, control.root] {
                #expect(throws: (any Error).self) {
                    try CPRSourceEventRenderer.renderAudition(eventID: eventID, in: project, at: control.root, to: destination)
                }
            }
            #expect(try Data(contentsOf: output) == sentinel)
            #expect(!FileManager.default.fileExists(atPath: inside.path))
            let redirect = control.root.appendingPathComponent("Redirected")
            try FileManager.default.createSymbolicLink(at: redirect, withDestinationURL: directory)
            let escaped = redirect.appendingPathComponent("Escaped.wav")
            #expect(throws: (any Error).self) {
                try CPRSourceEventRenderer.renderAudition(eventID: eventID, in: project, at: control.root, to: escaped)
            }
            #expect(!FileManager.default.fileExists(atPath: directory.appendingPathComponent("Escaped.wav").path))
            let linked = directory.appendingPathComponent("Linked.wav")
            try FileManager.default.createSymbolicLink(at: linked, withDestinationURL: output)
            #expect(throws: (any Error).self) {
                try CPRSourceEventRenderer.renderAudition(eventID: eventID, in: project, at: control.root, to: linked)
            }
            #expect(try Data(contentsOf: output) == sentinel)
            #expect(try !FileManager.default.contentsOfDirectory(atPath: directory.path).contains { $0.hasPrefix(".rebase-source-audition-") })
        }
    }

    @Test func attachedMediaLinksAreRejectedEvenWhenTheirBytesMatch() throws {
        try workspace { directory in
            let control = try CPRAudioControl.makePackage(in: directory)
            let (project, eventID) = try attached(control)
            let attachment = try #require(project.cprMediaAttachments.first)
            let copied = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: control.root)
            let real = control.root.appendingPathComponent("Media/Real.wav")
            try FileManager.default.moveItem(at: copied, to: real)
            try FileManager.default.createSymbolicLink(at: copied, withDestinationURL: real)
            #expect(throws: (any Error).self) { try ProjectStore.save(project, to: control.root) }
            #expect(throws: (any Error).self) {
                try CPRSourceEventRenderer.prepareAudition(eventID: eventID, in: project, at: control.root)
            }
            #expect(try Data(contentsOf: real) == control.mediaBytes)
        }
    }

    @Test func strictPCM24DecoderRejectsMalformedAndAmbiguousWaves() throws {
        let container = try CPRProject.readContainer(CPRAudioControl.archive())
        let source = try #require(CPRAudioEventArchive.read(container: container).first)
        let recovered = try CPRRecoveryV4(container: container).decode(sourceName: "Authored.cpr")
        let event = try #require(recovered.recovery.project?.unresolvedAudioEvents.first)
        let plan = try CPRSourceEventRenderPlan.make(source: source, retained: event,
            fades: CPRAutoFadeArchive.read(container: container))
        let valid = CPRAudioControl.wave(samples: Array(repeating: 1, count: 16))
        var cases = [Data(valid.dropLast()), valid + Data([0]), Data(valid.prefix(20))]
        for offset in [0, 4, 8, 16, 20, 22, 24, 28, 32, 34, 40] {
            var changed = valid; changed[offset] ^= 1; cases.append(changed)
        }
        var duplicate = valid + Data("data".utf8) + Data(repeating: 0, count: 4)
        var count = UInt32(duplicate.count - 8).littleEndian
        duplicate.replaceSubrange(4..<8, with: withUnsafeBytes(of: &count) { Data($0) }); cases.append(duplicate)
        for bytes in cases {
            #expect(throws: (any Error).self) { try CPRSourceEventRenderer.renderPCM24Wave(bytes, plan: plan) }
        }
        #expect(try CPRSourceEventRenderer.renderPCM24Wave(valid, plan: plan).count == 58 + 16 * 4)
    }
}
