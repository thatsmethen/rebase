import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

/// New forward-authored structural controls for the portable audition modes.
/// These are not native-valid projects or observations of reference playback.
/// The previously locked SourceAudition generator and its bytes remain unchanged.
enum CPRAuditionModesControl {
    struct Event {
        var frames: Int = 16_403
        var rate: Int = 48_000
        var gain: Float = 0.0625
        var priority: Int32 = 1
        var startTicks: Double = 0
        var lengthFrames: Int? = nil
        var offsetFrames: Int = 0
    }
    struct Options {
        var events: [Event] = [Event()]
        var savedRate: Int? = 32_000
        var projectRate: Double = 44_100
        var autoFadeFlags: UInt16 = 0
        var factor: Double = 1
    }
    struct Fixture {
        let root: URL
        let project: Project
        let media: [URL]
        let samples: [[Int32]]
    }

    static func sample(frame: Int, channel: Int, ordinal: Int) -> Int32 {
        Int32(((Int64(frame) * (channel == 0 ? 7_919 : 104_729)
            + Int64(channel * 12_345 + ordinal * 131_071)) & 0xfffff) - 524_288)
    }

    static func makePackage(in directory: URL, name: String = "AuthoredModes",
                            options: Options = Options(), attachMedia: Bool = true) throws -> Fixture {
        let bytes = archive(options)
        let source = directory.appendingPathComponent(name + ".cpr")
        try bytes.write(to: source, options: .withoutOverwriting)
        let report = try CPRProject.inspect(from: source)
        var project = try #require(report.recoveredProject)
        let root = directory.appendingPathComponent(name + ".rebaseproj")
        let original = root.appendingPathComponent(CPRProject.originalRelativePath)
        try FileManager.default.createDirectory(at: original.deletingLastPathComponent(), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: root.appendingPathComponent("Media"), withIntermediateDirectories: false)
        try bytes.write(to: original, options: .withoutOverwriting)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(report).write(to: root.appendingPathComponent(CPRProject.reportRelativePath), options: .withoutOverwriting)
        // An ordinary app setting deliberately differs from the immutable saved
        // setup. Source replay must preserve that distinction on both platforms.
        project.sampleRate = options.projectRate
        try ProjectStore.save(project, to: root)
        let events = project.unresolvedAudioEvents
        #expect(events.count == options.events.count)
        var media: [URL] = [], samples: [[Int32]] = []
        for (ordinal, settings) in options.events.enumerated() {
            let pcm = (0..<(settings.frames * 2)).map { sample(frame: $0 / 2, channel: $0 % 2, ordinal: ordinal) }
            let url = directory.appendingPathComponent("AuthoredModeSignal-\(ordinal).wav")
            try CPRAudioControl.wave(samples: pcm, rate: settings.rate).write(to: url, options: .withoutOverwriting)
            media.append(url); samples.append(pcm)
            if attachMedia {
                project = try ProjectStore.attachCPRAudioMedia(from: url, to: events[ordinal].id, in: project, at: root)
            }
        }
        try ProjectStore.save(project, to: root)
        return Fixture(root: root, project: project, media: media, samples: samples)
    }

    static func archive(_ options: Options = Options()) -> Data {
        precondition(!options.events.isEmpty)
        let f = AuditionModeArchive()
        func path(_ index: Int) {
            f.object("path\(index)", "FNPath") {
                f.string("AuthoredModeSignal-\(index).wav"); f.u32(0)
                for _ in 0..<3 { f.string("") }
                f.u32(0); f.u16(0); f.string("/unresolved/authored-modes/")
            }
        }
        func event(_ index: Int) {
            let e = options.events[index]
            precondition(e.frames > 0 && e.rate > 0)
            f.object("event\(index)", "MAudioEvent", version: 6) {
                f.u16(0); f.u64(e.startTicks.bitPattern)
                f.u64(Double(e.lengthFrames ?? e.frames).bitPattern); f.u64(Double(e.offsetFrames).bitPattern)
                f.object("clip\(index)", "PAudioClip", version: 4) {
                    f.string("Authored mode source \(index)"); f.u32(10); f.u64((1.0 / Double(e.rate)).bitPattern); f.u32(0)
                    path(index); f.string(""); f.u16(0); f.u32(0); f.u64(0); f.u32(2)
                    f.string("TransposeLock"); f.u16(1); f.u64(1)
                    f.string("StretchPreset"); f.u16(0x12)
                    f.object("preset\(index)", "ElastiquePreset") {}
                    f.object("cluster\(index)", "AudioCluster") {
                        f.u32(0); f.u16(2); f.u32(1)
                        f.object("file\(index)", "AudioFile", version: 1) {
                            f.u64(UInt64(e.frames)); f.u16(24); f.u16(6); f.u16(2)
                            f.u32(Float(e.rate).bitPattern); f.reference("path\(index)"); f.u32(0)
                        }
                        f.u16(1); f.u32(1)
                        f.object("segment\(index)", "AClusterSegment") {
                            f.reference("file\(index)"); f.u64(0); f.u64(UInt64(e.frames)); f.u64(0)
                        }
                    }
                    f.u16(1); f.u32(0)
                }
                f.u32(0); f.u32(UInt32(bitPattern: e.priority)); f.u32(0); f.u32(0); f.u64(0); f.string("")
                f.u32(0); f.u32(e.gain.bitPattern); f.u32(0); f.u16(0)
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
                            f.string("Authored mode track"); f.u32(0); f.reference("tempo"); f.reference("signature")
                            f.u32(UInt32(options.events.count))
                            for index in options.events.indices { event(index) }
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
            if let rate = options.savedRate {
                f.object("setup", "PArrangeSetup", version: 8) {
                    func scalar() { f.u64(0); f.u32(10); f.u64(0) }
                    scalar(); scalar(); f.u32(0); f.u32(0); f.u32(Float(rate).bitPattern); f.u32(0)
                    scalar(); for _ in 0..<4 { f.u32(0) }
                    f.u64(options.factor.bitPattern); f.u64(0); f.u32(0); f.u16(0); f.u16(0); f.u32(0)
                    for _ in 0..<3 { f.string("") }
                    f.zeros(1); f.u32(0)
                }
                for _ in 0..<7 { f.string("") }
            }
        }
        return f.container()
    }
}

private final class AuditionModeArchive {
    private var data = Data()
    private var identities: [String: Int] = [:]
    private func integer<T: FixedWidthInteger>(_ value: T) {
        var value = value.bigEndian; data.append(withUnsafeBytes(of: &value) { Data($0) })
    }
    func u16(_ value: UInt16) { integer(value) }
    func u32(_ value: UInt32) { integer(value) }
    func u64(_ value: UInt64) { integer(value) }
    func zeros(_ count: Int) { data.append(Data(repeating: 0, count: count)) }
    func string(_ value: String) { u32(UInt32(value.utf8.count + 1)); data.append(contentsOf: value.utf8); data.append(0) }
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
