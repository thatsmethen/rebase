import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

/// Opt-in authored fixture generation, never reference application output.
enum SourceAuditionFixtureGenerator {
    static func generate(at destination: URL) throws {
        let fm = FileManager.default
        guard !fm.fileExists(atPath: destination.path) else {
            throw RebaseCoreError.invalidProject("Fixture generation requires a new destination directory.")
        }
        let work = fm.temporaryDirectory.appendingPathComponent("SourceAuditionGenerator-" + UUID().uuidString)
        try fm.createDirectory(at: work, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: work) }
        var options = CPRAudioControl.Options()
        options.frames = 44_100
        options.gain = 0.0625
        let control = try CPRAudioControl.makePackage(in: work, name: "AuthoredSource", options: options)
        let reportURL = control.root.appendingPathComponent(CPRProject.reportRelativePath)
        let report = try JSONDecoder().decode(CPRInspection.self, from: Data(contentsOf: reportURL))
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(report).write(to: reportURL)
        let project = try ProjectStore.load(from: control.root)
        let event = try #require(project.unresolvedAudioEvents.first)
        #expect(project.cprMediaAttachments.isEmpty && project.sampleRate == 48_000)

        // Independent expectation: signed authored integer / 2^23, times the
        // exactly represented gain, rounded once to Float32. No DSP decoder call.
        let samples = control.samples.map { Float(Double($0) / 8_388_608 * Double(options.gain)) }
        let pcm = littleEndianPCM(samples)
        let expectedWave = floatWave(pcm: pcm, frames: options.frames, rate: options.rate, channels: options.channels)
        let verifiedRoot = work.appendingPathComponent("Verification.rebaseproj")
        try fm.copyItem(at: control.root, to: verifiedRoot)
        let attached = try ProjectStore.attachCPRAudioMedia(from: control.media, to: event.id, in: project, at: verifiedRoot)
        try ProjectStore.save(attached, to: verifiedRoot)
        #expect(try ProjectStore.load(from: verifiedRoot) == attached)
        let renderedURL = work.appendingPathComponent("Verification.wav")
        _ = try CPRSourceEventRenderer.renderAudition(eventID: event.id, in: attached, at: verifiedRoot, to: renderedURL)
        #expect(try Data(contentsOf: renderedURL) == expectedWave)

        let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let generatorFiles = ["CPRAudioControl.swift", "SourceAuditionFixtureGenerator.swift"]
        var generatorHashes: [String: String] = [:]
        for file in generatorFiles { generatorHashes[file] = cprSHA256(try Data(contentsOf: here.appendingPathComponent(file))) }
        let expected: [String: Any] = [
            "schemaVersion": 1,
            "evidenceClass": "authored-synthetic-control",
            "project": "AuthoredSource.rebaseproj", "media": "SelectedSource.wav",
            "eventID": event.id.uuidString,
            "sourceSHA256": report.sourceSHA256,
            "mediaSHA256": cprSHA256(control.mediaBytes),
            "outputSHA256": cprSHA256(expectedWave),
            "pcmSHA256": cprSHA256(pcm),
            "frames": options.frames, "sampleRate": options.rate, "channels": options.channels,
            "inputBitsPerSample": 24, "outputBitsPerSample": 32, "outputFormatTag": 3,
            "eventGain": Double(options.gain), "projectSampleRate": project.sampleRate,
            "outputBytes": expectedWave.count,
            "manifestSHA256": cprSHA256(try Data(contentsOf: control.root.appendingPathComponent(ProjectStore.manifestName))),
            "reportSHA256": cprSHA256(try Data(contentsOf: reportURL)),
            "generatorSHA256": generatorHashes,
            "expectation": "RN32((signedPCM24 / 8388608) * 0.0625), interleaved stereo, original 44100 Hz; IEEE-float WAVEFORMATEX with fact frame count"
        ]
        try fm.createDirectory(at: destination, withIntermediateDirectories: false)
        do {
            try fm.copyItem(at: control.root, to: destination.appendingPathComponent("AuthoredSource.rebaseproj"))
            try control.mediaBytes.write(to: destination.appendingPathComponent("SelectedSource.wav"), options: .withoutOverwriting)
            try JSONSerialization.data(withJSONObject: expected, options: [.prettyPrinted, .sortedKeys])
                .write(to: destination.appendingPathComponent("expected.json"), options: .withoutOverwriting)
        } catch {
            try? fm.removeItem(at: destination)
            throw error
        }
    }

    private static func littleEndianPCM(_ values: [Float]) -> Data {
        var data = Data()
        for value in values {
            let word = value.bitPattern
            for shift in stride(from: 0, to: 32, by: 8) { data.append(UInt8(truncatingIfNeeded: word >> shift)) }
        }
        return data
    }

    private static func floatWave(pcm: Data, frames: Int, rate: Int, channels: Int) -> Data {
        var data = Data()
        func tag(_ value: String) { data.append(contentsOf: value.utf8) }
        func word(_ value: Int, bytes: Int) {
            for shift in stride(from: 0, to: bytes * 8, by: 8) { data.append(UInt8(truncatingIfNeeded: value >> shift)) }
        }
        tag("RIFF"); word(50 + pcm.count, bytes: 4); tag("WAVEfmt "); word(18, bytes: 4)
        word(3, bytes: 2); word(channels, bytes: 2); word(rate, bytes: 4)
        word(rate * channels * 4, bytes: 4); word(channels * 4, bytes: 2); word(32, bytes: 2); word(0, bytes: 2)
        tag("fact"); word(4, bytes: 4); word(frames, bytes: 4); tag("data"); word(pcm.count, bytes: 4)
        data.append(pcm)
        return data
    }
}
