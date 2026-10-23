import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

/// Entirely authored structural controls, never derived from a shipped project
/// or reference output. These validate the implementation's admitted subset.
enum CPRAudioControl {
    struct Options {
        var frames = 8
        var channels = 2
        var rate = 44_100
        var gain: Float = 0.75
        var autoFadeFlags: UInt16 = 0
        var transposeLock: UInt64 = 1
        var inverted: UInt16 = 0
        var priority: UInt32 = 1
        var position: Double = 0
        var secondSegmentLength: UInt64? = nil
    }

    struct Fixture {
        let root: URL
        let project: Project
        let media: URL
        let mediaBytes: Data
        let samples: [Int32]
    }

    static func makePackage(in directory: URL, name: String = "Control", options: Options = Options()) throws -> Fixture {
        let source = directory.appendingPathComponent(name + ".cpr")
        let bytes = archive(options)
        try bytes.write(to: source)
        let report = try CPRProject.inspect(from: source)
        let project = try #require(report.recoveredProject)
        let root = directory.appendingPathComponent(name + ".rebaseproj")
        let original = root.appendingPathComponent(CPRProject.originalRelativePath)
        try FileManager.default.createDirectory(at: original.deletingLastPathComponent(), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: root.appendingPathComponent("Media"), withIntermediateDirectories: false)
        try bytes.write(to: original)
        try JSONEncoder().encode(report).write(to: root.appendingPathComponent(CPRProject.reportRelativePath))
        try ProjectStore.save(project, to: root)
        let markers: [Int32] = [-8_388_608, 8_388_607, -1, 1, 0, 4_194_304, -4_194_304, 3,
                                17, -31, 8_388_606, -8_388_607, 5, -7, 123_456, -654_321]
        let samples = (0..<(options.frames * options.channels)).map { markers[$0 % markers.count] }
        let media = directory.appendingPathComponent(name + ".wav")
        let mediaBytes = wave(samples: samples, channels: options.channels, rate: options.rate)
        try mediaBytes.write(to: media)
        return Fixture(root: root, project: project, media: media, mediaBytes: mediaBytes, samples: samples)
    }

    static func wave(samples: [Int32], channels: Int = 2, rate: Int = 44_100) -> Data {
        func le<T: FixedWidthInteger>(_ value: T) -> Data {
            var value = value.littleEndian
            return withUnsafeBytes(of: &value) { Data($0) }
        }
        let size = samples.count * 3
        var data = Data("RIFF".utf8) + le(UInt32(36 + size + (size & 1))) + Data("WAVEfmt ".utf8)
        data += le(UInt32(16)) + le(UInt16(1)) + le(UInt16(channels)) + le(UInt32(rate))
        data += le(UInt32(rate * channels * 3)) + le(UInt16(channels * 3)) + le(UInt16(24))
        data += Data("data".utf8) + le(UInt32(size))
        for sample in samples {
            let bits = UInt32(bitPattern: sample)
            data.append(UInt8(truncatingIfNeeded: bits))
            data.append(UInt8(truncatingIfNeeded: bits >> 8))
            data.append(UInt8(truncatingIfNeeded: bits >> 16))
        }
        if size & 1 != 0 { data.append(0) }
        return data
    }

    static func archive(_ options: Options = Options()) -> Data {
        let f = AuthoredCPRArchive()
        func path() {
            f.object("path", "FNPath") {
                f.string("authored.wav"); f.u32(0)
                for _ in 0..<3 { f.string("") }
                f.u32(0); f.u16(0); f.string("/unresolved/authored/")
            }
        }
        func event(_ index: Int) {
            f.object("event\(index)", "MAudioEvent", version: 6) {
                f.u16(0); f.u64(options.position.bitPattern); f.u64(Double(options.frames).bitPattern); f.u64(0)
                f.object("clip\(index)", "PAudioClip", version: 4) {
                    f.string("Authored source \(index)"); f.u32(10); f.u64((1.0 / Double(options.rate)).bitPattern); f.u32(0)
                    if index == 0 { path() } else { f.reference("path") }
                    f.string(""); f.u16(0); f.u32(0); f.u64(0); f.u32(2)
                    f.string("TransposeLock"); f.u16(1); f.u64(options.transposeLock)
                    f.string("StretchPreset"); f.u16(0x12)
                    f.object("preset\(index)", "ElastiquePreset") {}
                    f.object("cluster\(index)", "AudioCluster") {
                        f.u32(0); f.u16(2); f.u32(1)
                        if index == 0 {
                            f.object("file", "AudioFile", version: 1) {
                                f.u64(UInt64(options.frames)); f.u16(24); f.u16(UInt16(options.channels * 3))
                                f.u16(UInt16(options.channels)); f.u32(Float(options.rate).bitPattern)
                                f.reference("path"); f.u32(0)
                            }
                        } else { f.reference("file") }
                        f.u16(1); f.u32(1)
                        f.object("segment\(index)", "AClusterSegment") {
                            f.reference("file"); f.u64(0)
                            f.u64(index == 0 ? UInt64(options.frames) : options.secondSegmentLength!)
                            f.u64(0)
                        }
                    }
                    f.u16(1); f.u32(0)
                }
                f.u32(0); f.u32(options.priority); f.u32(0); f.u32(0); f.u64(0); f.string("")
                f.u32(0); f.u32(options.gain.bitPattern); f.u32(0); f.u16(options.inverted)
                f.object("curve\(index)", "VolumeCurveDataNode") {
                    f.string(""); f.u32(1); f.u64(Double(1).bitPattern); f.u32(0)
                }
            }
        }
        f.object("arrangement", "PArrangement", version: 4) {
            f.base("MEvent", 1); f.base("MTrackEvent", 2)
            f.object("root", "MRoot", version: 6) {
                f.zeros(26)
                f.object("rootList", "MTrackList") {
                    // A shared fixed clock and a well-bounded compact meter.
                    // Typed meter replacement is deliberately absent; source
                    // placement does not promote that unresolved meter state.
                    f.string(""); f.u32(0)
                    f.object("tempo", "MTempoTrackEvent", version: 3) {
                        f.u32(1); f.u32(Float(0.5).bitPattern); f.u64(0); f.u64(0); f.u16(0)
                        f.u32(Float(120).bitPattern); f.u16(1)
                    }
                    f.object("signature", "MSignatureTrackEvent", version: 3) {
                        f.u32(1); f.u32(0); f.u16(4); f.u16(4)
                        f.u16(0); f.u16(0); f.u16(0); f.u16(8); f.u32(0)
                    }
                    f.u16(0); f.u32(1)
                    f.object("audio", "MAudioTrackEvent", version: 1) {
                        f.zeros(26)
                        f.object("audioList", "MListNode") {
                            f.string("Authored audio"); f.u32(0); f.reference("tempo"); f.reference("signature")
                            f.u32(options.secondSegmentLength == nil ? 1 : 2)
                            event(0)
                            if options.secondSegmentLength != nil { event(1) }
                        }
                        f.u32(0); f.object("resource", "MAudioTrack") {}
                        f.u32(0); f.u64(0); f.object("automation", "MAutomationNode", version: 1) {}
                        f.u32(0)
                    }
                }
                f.u32(0); f.u16(0); f.u32(0)
                f.object("rootPath", "FNPath") {}; f.object("pool", "PPool", version: 5) {}
                f.u32(0); f.reference("tempo"); f.reference("signature")
                f.object("fades", "MAutoFadeSetting") {
                    f.u16(options.autoFadeFlags); f.u64(Double(0.01).bitPattern)
                    for _ in 0..<4 { f.u32(0) }
                }
                f.u16(0); f.u32(0)
            }
        }
        return f.container()
    }
}

private final class AuthoredCPRArchive {
    private var data = Data()
    private var identities: [String: Int] = [:]
    private func integer<T: FixedWidthInteger>(_ value: T) {
        var value = value.bigEndian
        data.append(withUnsafeBytes(of: &value) { Data($0) })
    }
    func u16(_ value: UInt16) { integer(value) }
    func u32(_ value: UInt32) { integer(value) }
    func u64(_ value: UInt64) { integer(value) }
    func zeros(_ count: Int) { data.append(Data(repeating: 0, count: count)) }
    func string(_ value: String) { u32(UInt32(value.utf8.count + 1)); data.append(Data(value.utf8)); data.append(0) }
    func base(_ name: String, _ version: UInt16) { u32(0xffff_fffe); string(name); u16(version) }
    func reference(_ name: String) { u32(UInt32(identities[name]!)) }
    func object(_ label: String, _ name: String, version: UInt16 = 0, body: () -> Void) {
        precondition(identities[label] == nil)
        u32(.max); string(name); u16(version)
        let identity = data.count; identities[label] = identity; u32(0)
        let start = data.count; body()
        var length = UInt32(data.count - start).bigEndian
        data.replaceSubrange(identity..<(identity + 4), with: withUnsafeBytes(of: &length) { Data($0) })
    }
    func container() -> Data {
        func u32(_ value: UInt32) -> Data { var value = value.bigEndian; return withUnsafeBytes(of: &value) { Data($0) } }
        func text(_ value: String) -> Data { u32(UInt32(value.utf8.count)) + Data(value.utf8) }
        func chunk(_ name: String, _ payload: Data) -> Data { Data(name.utf8) + u32(UInt32(payload.count)) + payload }
        let sections = chunk("ROOT", text("Arrangement1") + text("PArrangement")) + chunk("ARCH", data)
        return Data("RIFF".utf8) + u32(UInt32(sections.count)) + Data("NUND".utf8) + sections
    }
}
