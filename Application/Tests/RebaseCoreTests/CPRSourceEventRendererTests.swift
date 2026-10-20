import AVFoundation
import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Candidate/source-state controls only. No reference program is executed.
struct CPRSourceEventRendererTests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private func le<T: FixedWidthInteger>(_ value: T) -> Data {
        var value = value.littleEndian
        return withUnsafeBytes(of: &value) { Data($0) }
    }
    private func source(_ name: String = "LoFi Hip Hop") throws -> Data {
        try Data(contentsOf: workspace.appendingPathComponent("research/targets/full-reference/expanded/Reference 15.app.pkg/Payload/Reference 15.app/Contents/Project Templates/Reference Pro/" + name + ".cpr"))
    }
    private func wave(samples: [Int32], frames: Int? = nil, channels: Int = 2) -> Data {
        let frameCount = frames ?? samples.count / channels, size = frameCount * channels * 3
        var result = Data("RIFF".utf8) + le(UInt32(36+size)) + Data("WAVEfmt ".utf8)
        result += le(UInt32(16)) + le(UInt16(1)) + le(UInt16(channels)) + le(UInt32(44100))
        result += le(UInt32(44100*channels*3)) + le(UInt16(channels*3)) + le(UInt16(24))
        result += Data("data".utf8) + le(UInt32(size)) + Data(repeating: 0, count: size)
        for (index, sample) in samples.enumerated() {
            let bits = UInt32(bitPattern: sample), offset = 44 + index*3
            result[offset] = UInt8(truncatingIfNeeded: bits)
            result[offset+1] = UInt8(truncatingIfNeeded: bits >> 8)
            result[offset+2] = UInt8(truncatingIfNeeded: bits >> 16)
        }
        return result
    }
    private func plan(_ data: Data? = nil) throws -> CPRSourceEventRenderPlan {
        let bytes = try data ?? source(), container = try CPRProject.readContainer(bytes)
        let sources = try CPRAudioEventArchive.read(container: container)
        let recovery = try CPRRecoveryV4(container: container).decode(sourceName: "Source.cpr")
        return try CPRSourceEventRenderPlan.make(source: #require(sources.first),
            retained: #require(recovery.recovery.project?.unresolvedAudioEvents.first),
            fades: CPRAutoFadeArchive.read(container: container))
    }
    private func temporary() throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("SourceRender-"+UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }
    private func floatBits(_ bytes: Data, at offset: Int) -> UInt32 {
        UInt32(bytes[offset]) | UInt32(bytes[offset+1]) << 8 | UInt32(bytes[offset+2]) << 16 | UInt32(bytes[offset+3]) << 24
    }

    @Test func PCM24AndSeparateGainMatchExactBinaryArithmeticAcrossBoundaries() throws {
        var samples: [Int32] = [-8388608,-8388607,-4194305,-4194304,-1,0,1,4194303,4194304,8388606,8388607]
        var seed: UInt32 = 0x193acb21
        for _ in 0..<20000 {
            seed = seed &* 1664525 &+ 1013904223
            samples.append(Int32(seed & 0xffffff)-8388608)
        }
        let data = wave(samples: samples, frames: samples.count, channels: 1).dropFirst(44)
        for gain: Float in [1, 0.5, 0.75, Float(bitPattern: 0x3f800001), 2, Float.greatestFiniteMagnitude] {
            var actual = [Float](repeating: .nan, count: samples.count)
            let status = data.withUnsafeBytes { input in actual.withUnsafeMutableBufferPointer { output in
                rb_cpr_event_pcm24_f32(input.baseAddress!.assumingMemoryBound(to: UInt8.self), output.baseAddress!, samples.count, gain.bitPattern)
            } }
            #expect(status == 0)
            for (sample, value) in zip(samples, actual) {
                // signed24/2^23 is exact; Float32*Float32 has <=48 significant
                // bits, so Double holds the exact product before final RN32.
                let expected = Float((Double(sample) / 8388608) * Double(gain))
                #expect(value.bitPattern == expected.bitPattern)
            }
        }
        #expect(Float(8388607)/8388608 != 1) // Detect the common 8388607 divisor.
    }

    @Test func KernelRejectsUnsupportedEnvironmentAndGainBeforeWriting() {
        let bytes: [UInt8] = [1,0,0]
        for gain in [Float.nan, .infinity, -.infinity, 0, -1, .leastNormalMagnitude, .leastNonzeroMagnitude] {
            var result: Float = -123
            let status = bytes.withUnsafeBufferPointer { rb_cpr_event_pcm24_f32($0.baseAddress!, &result, 1, gain.bitPattern) }
            #expect(status != 0 && result == -123)
        }
        let original = fegetround(); defer { fesetround(original) }
        for mode in [FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO] {
            fesetround(mode)
            var result: Float = -123
            let status = bytes.withUnsafeBufferPointer { rb_cpr_event_pcm24_f32($0.baseAddress!, &result, 1, Float(1).bitPattern) }
            #expect(status != 0 && result == -123)
        }
    }

    @Test func ForwardSourcePlanRejectsEnabledFadesWarpAndInversion() throws {
        let baseline = try source(), prepared = try plan(baseline)
        #expect(prepared.frames == 1_058_400 && prepared.rate == 44100 && prepared.channels == 2 && prepared.gain == 1)
        #expect(throws: RebaseCoreError.self) { try plan(source("Classic House")) }
        let container = try CPRProject.readContainer(baseline)
        let fades = try CPRAutoFadeArchive.read(container: container), setting = try #require(fades.projectSetting)
        var enabled = baseline
        enabled[setting.object.payloadOffset+1] = 1
        #expect(throws: RebaseCoreError.self) { try plan(enabled) }
        let event = try #require(CPRAudioEventArchive.read(container: container).first)
        let file = try #require(event.cluster.files.first)
        var oversizedChannels = baseline
        oversizedChannels[file.object.payloadOffset+12] = 0x7f
        oversizedChannels[file.object.payloadOffset+13] = 0xff
        #expect(throws: RebaseCoreError.self) { try plan(oversizedChannels) }
        let child = try #require(event.clipChildren.first)
        var pitchChild = baseline
        // Same-size unknown class in an entered child declaration. It remains
        // valid archival state but cannot satisfy the no-pitch render subset.
        pitchChild[child.declarationOffset+8] = Character("X").asciiValue!
        #expect(throws: RebaseCoreError.self) { try plan(pitchChild) }
        let tail = event.clip.payloadOffset + event.clip.payloadByteCount
        var inverted = baseline
        // Source reader layout: numeric count,priority,2null fades,snap,string,
        // legacy lane,volume,lane,inversion. Walk rather than search a literal.
        var cursor = CPRCursor(data: baseline, lower: tail, upper: event.event.payloadOffset+event.event.payloadByteCount)
        _ = try cursor.bytes(24); _ = try cursor.nativeString(); _ = try cursor.bytes(12)
        inverted[cursor.position+1] = 1
        #expect(throws: RebaseCoreError.self) { try plan(inverted) }
    }

    @Test func WAVParsingRejectsWrongFormatCountsAndAmbiguousChunks() throws {
        let reference = try plan()
        let small = CPRSourceEventRenderPlan(frames: 2, rate: 44100, channels: 2, gain: 1, file: reference.file)
        let valid = wave(samples: [-8388608, 8388607, -1, 1])
        let rendered = try CPRSourceEventRenderer.renderPCM24Wave(valid, plan: small)
        #expect(rendered.count == 58+16 && floatBits(rendered, at: 4) == rendered.count-8)
        for (i, sample) in [-8388608,8388607,-1,1].enumerated() {
            #expect(floatBits(rendered, at: 58+i*4) == Float(Double(sample)/8388608).bitPattern)
        }
        var cases = [Data(valid.dropLast()), valid+Data([0]), Data(valid.prefix(20))]
        for offset in [0,4,8,16,20,22,24,28,32,34,40] {
            var changed = valid; changed[offset] ^= 1; cases.append(changed)
        }
        var duplicate = valid + Data("data".utf8) + le(UInt32(0))
        duplicate.replaceSubrange(4..<8, with: le(UInt32(duplicate.count-8))); cases.append(duplicate)
        for bytes in cases { #expect(throws: RebaseCoreError.self) { try CPRSourceEventRenderer.renderPCM24Wave(bytes, plan: small) } }
    }

    @Test func AttachedSourceRenderWritesExactSamplesWithoutChangingPackageAndRejectsTampering() throws {
        let root = try temporary(); defer { try? FileManager.default.removeItem(at: root) }
        let cpr = root.appendingPathComponent("Source.cpr"), package = root.appendingPathComponent("Source.rebaseproj")
        try source().write(to: cpr)
        let imported = try CPRProject.importProject(from: cpr, to: package, allowPartial: true)
        let event = try #require(imported.project.unresolvedAudioEvents.first), media = root.appendingPathComponent("Selected.wav")
        let markers: [Int32] = [-8388608,8388607,-1,1,0,4194304,-4194304,3]
        var pcm = wave(samples: markers, frames: 1_058_400)
        // Final frame detects dropped/extra endpoints and channel order.
        pcm.replaceSubrange((pcm.count-6)..<pcm.count, with: Data([1,0,0,255,255,255]))
        try pcm.write(to: media)
        let project = try ProjectStore.attachCPRAudioMedia(from: media, to: event.id, in: imported.project, at: package)
        try ProjectStore.save(project, to: package)
        let snapshot = try [ProjectStore.manifestName, CPRProject.originalRelativePath, CPRProject.reportRelativePath].map { try Data(contentsOf: package.appendingPathComponent($0)) }
        let inspected = try CPRSourceAudioInspection.inspect(eventID: event.id, in: project, at: package)
        #expect(inspected.autoFadeOrigin == "Project" && inspected.autoFadeFlags == 0 && inspected.localRenderUnavailableReason == nil)
        let destination = root.appendingPathComponent("Rendered.wav")
        let result = try CPRSourceEventRenderer.render(eventID: event.id, in: project, at: package, to: destination)
        let bytes = try Data(contentsOf: destination)
        #expect(result.frameCount == 1_058_400 && result.sampleRate == 44100 && result.channelCount == 2)
        #expect(result.outputSHA256 == cprSHA256(bytes))
        var expected = Data(repeating: 0, count: result.frameCount*2*4)
        for (i, sample) in markers.enumerated() { expected.replaceSubrange(i*4..<(i*4+4), with: le(Float(Double(sample)/8388608).bitPattern)) }
        expected.replaceSubrange((expected.count-8)..<expected.count, with: le(Float(1.0/8388608).bitPattern)+le(Float(-1.0/8388608).bitPattern))
        #expect(bytes.dropFirst(58) == expected)
        let audio = try AVAudioFile(forReading: destination)
        #expect(audio.length == 1_058_400 && audio.fileFormat.sampleRate == 44100 && audio.fileFormat.channelCount == 2)
        let after = try [ProjectStore.manifestName, CPRProject.originalRelativePath, CPRProject.reportRelativePath].map { try Data(contentsOf: package.appendingPathComponent($0)) }
        #expect(snapshot == after && project.tracks.flatMap(\.clips).isEmpty)
        #expect(try ProjectStore.load(from: package) == project)
        #expect(throws: RebaseCoreError.self) { try project.requireResolvedAudioEvents() }
        let attachment = try #require(project.cprMediaAttachments.first)
        let copied = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: package)
        #expect(throws: RebaseCoreError.self) { try CPRSourceEventRenderer.render(eventID: event.id, in: project, at: package, to: copied) }
        var corrupted = pcm; corrupted[44] ^= 1; try corrupted.write(to: copied)
        #expect(throws: RebaseCoreError.self) { try CPRSourceEventRenderer.render(eventID: event.id, in: project, at: package, to: destination) }
        #expect(try Data(contentsOf: destination) == bytes)
    }
}
