import Testing
import Foundation
import AVFoundation
import ZIPFoundation
import RebaseCore

/// Synthetic exchange fixtures; neither self-roundtrip nor XSD validation proves
/// successful import by Reference or equivalent mixer/pan behavior in another DAW.
final class DAWProjectTests: AudioTestCase {
    private func archive(xml: String, audio: URL? = nil, extra: [(String, Data, Entry.EntryType)] = []) throws -> URL {
        let url = temporary.appendingPathComponent(UUID().uuidString + ".dawproject")
        let zip = try Archive(url: url, accessMode: .create)
        func add(_ name: String, _ data: Data, _ type: Entry.EntryType = .file) throws {
            try zip.addEntry(with: name, type: type, uncompressedSize: Int64(data.count), compressionMethod: .none) { offset, size in
                data.subdata(in: Int(offset)..<min(Int(offset) + size, data.count))
            }
        }
        try add("project.xml", Data(xml.utf8))
        if let audio { try add("audio/source.wav", Data(contentsOf: audio)) }
        for (path, data, type) in extra { try add(path, data, type) }
        return url
    }

    private func fixture() -> String {
        // Authored independently from DAWProject.export; constant Volume is
        // linear amplitude while its automation points explicitly use decibels.
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Project version="1.0"><Application name="Independent fixture" version="1"/>
        <Transport><Tempo id="tempo" unit="bpm" value="120"/><TimeSignature id="sig" numerator="4" denominator="4"/></Transport>
        <Structure><Track id="audio-track" contentType="audio" name="Fixture &amp; audio">
          <Channel id="channel" audioChannels="2" role="regular" solo="false">
            <Mute value="false"/><Pan id="pan" unit="normalized" value="0"/>
            <Volume id="volume" unit="linear" value="0.5"/>
          </Channel></Track></Structure>
        <Arrangement><Lanes timeUnit="seconds"><Lanes track="audio-track"><Clips>
          <Clip time="\(2 / rate)" duration="\(2 / rate)" playStart="\(1 / rate)" contentTimeUnit="seconds" name="Trimmed">
            <Audio channels="1" sampleRate="48000" duration="\(4 / rate)"><File path="audio/source.wav"/></Audio>
          </Clip></Clips>
          <Points unit="decibel"><Target parameter="volume"/>
            <RealPoint time="0" value="\(20 * log10(0.5))" interpolation="hold"/>
          </Points>
        </Lanes></Lanes>
        <TempoAutomation timeUnit="beats" unit="bpm"><Target parameter="tempo"/>
          <RealPoint time="0" value="120" interpolation="hold"/><RealPoint time="4" value="60" interpolation="hold"/>
        </TempoAutomation>
        <TimeSignatureAutomation timeUnit="beats"><Target parameter="sig"/>
          <TimeSignaturePoint time="0" numerator="4" denominator="4"/><TimeSignaturePoint time="8" numerator="3" denominator="4"/>
        </TimeSignatureAutomation></Arrangement></Project>
        """
    }

    private func assertRejects(_ source: URL, sourceLocation: SourceLocation = #_sourceLocation) throws {
        let destination = temporary.appendingPathComponent("Rejected-" + UUID().uuidString + ".rebaseproj")
        let before = Set(try FileManager.default.contentsOfDirectory(atPath: temporary.path))
        do {
            _ = try DAWProject.importProject(from: source, to: destination)
            Issue.record("Expected exchange rejection", sourceLocation: sourceLocation)
        } catch { }
        #expect(!FileManager.default.fileExists(atPath: destination.path), sourceLocation: sourceLocation)
        #expect(Set(try FileManager.default.contentsOfDirectory(atPath: temporary.path)) == before, sourceLocation: sourceLocation)
    }

    @Test func independentFixtureImportsTrimMixAndJumpMaps() throws {
        let audio = try writeAudio([[0.1, 0.2, 0.3, 0.4]])
        let source = try archive(xml: fixture(), audio: audio,
                                 extra: [("unused.wav", Data("not audio; never extracted".utf8), .file)])
        let destination = temporary.appendingPathComponent("Independent.rebaseproj")
        let project = try DAWProject.importProject(from: source, to: destination)
        #expect(project.tracks[0].name == "Fixture & audio")
        #expect(abs(project.tracks[0].gainDB - 20 * log10(0.5)) < 1e-12)
        #expect(project.tracks[0].pan == -1)
        #expect(project.tracks[0].automation[0].points[0].interpolation == .step)
        #expect(try project.tempoMap.seconds(atBeat: 8) == 6)
        #expect(project.signatureMap.events[1].numerator == 3)
        #expect(try FileManager.default.contentsOfDirectory(atPath: destination.appendingPathComponent("Media").path).count == 1)
        let output = try OfflineRenderer.render(project: project, projectRoot: destination)
        assertPlane(output, channel: 0, equals: [0, 0, 0.1, 0.15])
        assertPlane(output, channel: 1, equals: [0, 0, 0, 0])
    }

    @Test func selfRoundtripPreservesAudioCurvesAndMaps() throws {
        _ = try roundtrip()
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason),
          .enabled(if: FileManager.default.isExecutableFile(atPath: "/usr/bin/xmllint"), "Requires the system xmllint executable."))
    func exportedRoundtripXMLMatchesExternalSchema() throws {
        let xmlURL = try roundtrip()
        let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/xmllint")
        process.arguments = ["--nonet", "--noout", "--schema",
            PrivateResearchFixtures.root.appendingPathComponent("references/dawproject/Project.xsd").path, xmlURL.path]
        let log = Pipe(); process.standardError = log; try process.run(); process.waitUntilExit()
        let message = String(data: log.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        #expect(process.terminationStatus == 0, Comment(rawValue: message))
    }

    private func roundtrip() throws -> URL {
        var a = try importClip([[0.1, -0.2, 0.3, -0.4, 0.5, -0.6]])
        a.name = "Name <&> \"quote\""; a.position = 2 / rate; a.sourceOffset = 1 / rate; a.duration = 4 / rate
        let b = try importClip([[0.2, 0.4, 0.6], [0.1, 0.3, 0.5]])
        let gain = AutomationLane(parameter: .gainDB, points: [AutomationPoint(time: 0, value: -12), AutomationPoint(time: 5 / rate, value: -6, interpolation: .step)])
        let pan = AutomationLane(parameter: .pan, points: [AutomationPoint(time: 0, value: -1, interpolation: .step), AutomationPoint(time: 3 / rate, value: 0.5)])
        var project = Project(name: "Exchange & test", sampleRate: 48_000, tracks: [
            Track(name: "Mono", gainDB: -6, pan: 0, clips: [a], automation: [gain, pan]),
            Track(name: "Stereo", gainDB: -9, pan: 0.25, isMuted: true, isSolo: false, clips: [b])
        ])
        project.tempoMap = TempoMap(events: [TempoEvent(beat: 0, bpm: 120), TempoEvent(beat: 4, bpm: 80)])
        project.signatureMap = SignatureMap(events: [SignatureEvent(beat: 0, numerator: 4, denominator: 4), SignatureEvent(beat: 8, numerator: 3, denominator: 4)])
        let archiveURL = temporary.appendingPathComponent("Export.dawproject")
        try DAWProject.export(project: project, projectRoot: root, to: archiveURL)
        let zip = try Archive(url: archiveURL, accessMode: .read)
        let entry = try #require(zip["project.xml"])
        var xml = Data(); _ = try zip.extract(entry) { xml.append($0) }
        let xmlURL = temporary.appendingPathComponent("export.xml"); try xml.write(to: xmlURL)
        let importedRoot = temporary.appendingPathComponent("Roundtrip.rebaseproj")
        let imported = try DAWProject.importProject(from: archiveURL, to: importedRoot)
        #expect(imported.name == project.name)
        #expect(imported.sampleRate == project.sampleRate)
        #expect(imported.tracks.map(\.name) == project.tracks.map(\.name))
        #expect(imported.tracks[1].isMuted)
        #expect(imported.tracks[0].clips[0].sourceOffset == a.sourceOffset)
        #expect(imported.tracks[0].automation[0].points.map(\.interpolation) == gain.points.map(\.interpolation))
        #expect(imported.tempoMap.events.map(\.bpm) == [120, 80])
        let before = try OfflineRenderer.render(project: project, projectRoot: root)
        let after = try OfflineRenderer.render(project: imported, projectRoot: importedRoot)
        #expect(before.frameLength == after.frameLength)
        for channel in 0..<2 {
            let expected = Array(UnsafeBufferPointer(start: before.floatChannelData![channel], count: Int(before.frameLength)))
            assertPlane(after, channel: channel, equals: expected)
        }
        return xmlURL
    }

    @Test func unsupportedSemanticsAndAmbiguousInterpolationRejectTransactionally() throws {
        let audio = try writeAudio([[0.1, 0.2, 0.3, 0.4]])
        for xml in [fixture().replacingOccurrences(of: "<Clip time=", with: "<Clip loopEnd=\"1\" time="),
                    fixture().replacingOccurrences(of: "<Mute value=", with: "<Devices><Vst3Plugin/></Devices><Mute value="),
                    fixture().replacingOccurrences(of: "interpolation=\"hold\"", with: "interpolation=\"linear\""),
                    fixture().replacingOccurrences(of: " interpolation=\"hold\"", with: ""),
                    fixture().replacingOccurrences(of: "<Points unit=\"decibel\"", with: "<Points unit=\"linear\""),
                    fixture().replacingOccurrences(of: "<File path=", with: "<File external=\"true\" path="),
                    fixture().replacingOccurrences(of: "<Audio channels=\"1\"", with: "<Audio channels=\"2\"") ] {
            try assertRejects(archive(xml: xml, audio: audio))
        }
    }

    @Test func archiveTraversalDuplicateSymlinkAndDTDRejectBeforePublishing() throws {
        let audio = try writeAudio([[0.1, 0.2, 0.3, 0.4]])
        for extra in [[("../escape.wav", Data(), Entry.EntryType.file)],
                      [("PROJECT.XML", Data(), .file)],
                      [("link.wav", Data("/tmp/outside".utf8), .symlink)]] {
            try assertRejects(archive(xml: fixture(), audio: audio, extra: extra))
        }
        let dtd = fixture().replacingOccurrences(of: "<Project", with: "<!DOCTYPE Project [<!ENTITY unsafe SYSTEM 'file:///not-read'>]><Project")
        try assertRejects(archive(xml: dtd, audio: audio))
        try assertRejects(archive(xml: fixture().replacingOccurrences(of: "id=\"channel\"", with: "id=\"audio-track\""), audio: audio))
    }

    @Test func consumedAudioCRCAndTruncatedDirectoryReject() throws {
        let audio = try writeAudio([[0.1, 0.2, 0.3, 0.4]])
        let source = try archive(xml: fixture(), audio: audio)
        var bytes = try Data(contentsOf: source)
        let needle = try Data(contentsOf: audio)
        let range = try #require(bytes.range(of: needle))
        bytes[range.lowerBound + needle.count - 1] ^= 0x01
        try bytes.write(to: source)
        try assertRejects(source)
        let other = try archive(xml: fixture(), audio: audio)
        var broken = try Data(contentsOf: other)
        // Increase both classic EOCD entry counts without adding a directory entry.
        broken[broken.count - 22 + 8] += 1; broken[broken.count - 22 + 10] += 1
        try broken.write(to: other)
        try assertRejects(other)
    }

    @Test func exportUnsupportedReadStateAndExistingDestinationsRemainUnchanged() throws {
        let clip = try importClip([[0.1, 0.2]])
        var project = Project(tracks: [Track(name: "Audio", clips: [clip], automation: [AutomationLane(parameter: .gainDB, isReadEnabled: false)])])
        let out = temporary.appendingPathComponent("Out.dawproject")
        #expect(throws: DAWProjectError.self) { try DAWProject.export(project: project, projectRoot: root, to: out) }
        #expect(!FileManager.default.fileExists(atPath: out.path))
        project.tracks[0].automation = []
        let sentinel = Data("existing destination".utf8); try sentinel.write(to: out)
        #expect(throws: DAWProjectError.self) { try DAWProject.export(project: project, projectRoot: root, to: out) }
        #expect(try Data(contentsOf: out) == sentinel)
        let source = try archive(xml: fixture())
        #expect(throws: DAWProjectError.self) { _ = try DAWProject.importProject(from: source, to: root) }
        #expect(try ProjectStore.load(from: root).name == "Fixture")
    }

    @Test func exportRejectsMusicalTracksIncludingEmptyTracks() throws {
        var clip = try importClip([[0.1, 0.2]])
        clip.timeBase = .musical; clip.musicalPosition = 0
        for clips in [[], [clip]] {
            let project = Project(tracks: [Track(name: "Musical", clips: clips, timeBase: .musical)])
            try project.validate() // Reach the exchange guard with a valid model.
            let out = temporary.appendingPathComponent(UUID().uuidString + ".dawproject")
            #expect(throws: DAWProjectError.self) { try DAWProject.export(project: project, projectRoot: root, to: out) }
            #expect(!FileManager.default.fileExists(atPath: out.path))
        }
    }

    @Test func exportRejectsUnrepresentableSourceAudioFormat() throws {
        for (sourceRate, channels) in [(44_100.5, 1), (4_000.0, 1), (384_000.0, 1), (48_000.0, 4)] {
            let relative = "Media/" + UUID().uuidString + ".caf"
            let url = root.appendingPathComponent(relative)
            // Construct the file directly: AVAudioFormat's standard initializer
            // normalizes out-of-range rates and does not support four channels.
            // CAFFile.h defines big-endian headers and LPCM flags 1=float, 2=little-endian.
            var data = Data("caff".utf8)
            func big<T: FixedWidthInteger>(_ value: T) {
                var bytes = value.bigEndian
                withUnsafeBytes(of: &bytes) { data.append(contentsOf: $0) }
            }
            big(UInt16(1)); big(UInt16(0))
            data.append(Data("desc".utf8)); big(UInt64(32)); big(sourceRate.bitPattern)
            data.append(Data("lpcm".utf8)); big(UInt32(3)); big(UInt32(channels * 4))
            big(UInt32(1)); big(UInt32(channels)); big(UInt32(32))
            data.append(Data("data".utf8)); big(UInt64(4 + channels * 8)); big(UInt32(0))
            for value: Float in [0.1, 0.2] {
                for _ in 0..<channels {
                    var bits = value.bitPattern.littleEndian
                    withUnsafeBytes(of: &bits) { data.append(contentsOf: $0) }
                }
            }
            try data.write(to: url)
            let decoded = try AVAudioFile(forReading: url)
            #expect(decoded.fileFormat.sampleRate == sourceRate)
            #expect(Int(decoded.fileFormat.channelCount) == channels)
            #expect(decoded.length == 2)
            let clip = Clip(mediaPath: relative, name: "Unsupported CAF", duration: 2 / sourceRate)
            let project = Project(tracks: [Track(name: "Audio", clips: [clip])])
            try project.validate()
            let before = Set(try FileManager.default.contentsOfDirectory(atPath: temporary.path))
            let out = temporary.appendingPathComponent(UUID().uuidString + ".dawproject")
            #expect(throws: DAWProjectError.self) { try DAWProject.export(project: project, projectRoot: root, to: out) }
            #expect(!FileManager.default.fileExists(atPath: out.path))
            #expect(Set(try FileManager.default.contentsOfDirectory(atPath: temporary.path)) == before)
        }
    }
}
