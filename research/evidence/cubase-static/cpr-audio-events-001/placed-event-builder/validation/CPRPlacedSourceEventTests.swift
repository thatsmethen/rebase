import AVFoundation
import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Expectations are independent original-instruction/Fraction controls and
/// integer-indexed PCM. Derived inputs are freshly imported CPR bytes, never
/// forged retained project events. Proprietary media/code is not executed.
@Suite(.serialized)
struct CPRPlacedSourceEventTests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private let originalSHA = "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495"
    private let oracleSHA = "060ca297846429da2264b1e5e68e65709b104c796ee1184ce5416765820d1711"
    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }
    private func original() throws -> Data {
        let data = try Data(contentsOf: workspace.appendingPathComponent("research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/Cubase 15.app/Contents/Project Templates/Cubase Pro/LoFi Hip Hop.cpr"))
        #expect(cprSHA256(data) == originalSHA)
        return data
    }
    private func oracle(_ key: String) throws -> [[String: Any]] {
        let data = try Data(contentsOf: workspace.appendingPathComponent("research/evidence/application/APP015/placed-source-oracle.json"))
        #expect(cprSHA256(data) == oracleSHA)
        let root = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return try #require(root[key] as? [[String: Any]])
    }
    private func bits(_ row: [String: Any], _ key: String) throws -> UInt64 {
        let text = try #require(row[key] as? String)
        return try #require(UInt64(text, radix: 16))
    }
    private func number(_ row: [String: Any], _ key: String) throws -> Double {
        Double(bitPattern: try bits(row, key))
    }
    private func integer(_ row: [String: Any], _ key: String) throws -> Int64 {
        try #require(row[key] as? NSNumber).int64Value
    }
    private func put<T: FixedWidthInteger>(_ value: T, at offset: Int, in bytes: inout Data) {
        var big = value.bigEndian
        withUnsafeBytes(of: &big) { bytes.replaceSubrange(offset..<(offset + $0.count), with: $0) }
    }
    private func source(_ bytes: Data) throws -> CPRSourceAudioEvent {
        try #require(try CPRAudioEventArchive.read(container: CPRProject.readContainer(bytes)).first)
    }
    private func changed(_ original: Data, start: UInt64? = nil, length: UInt64? = nil, offset: UInt64? = nil) throws -> Data {
        let event = try source(original).event
        #expect(event.identityOffset == 197761 && event.payloadOffset == 197765)
        var bytes = original
        if let start { put(start, at: event.payloadOffset + 2, in: &bytes) }
        if let length { put(length, at: event.payloadOffset + 10, in: &bytes) }
        if let offset { put(offset, at: event.payloadOffset + 18, in: &bytes) }
        return bytes
    }
    private func plan(_ bytes: Data) throws -> CPRPlacedSourceEventPlan {
        let container = try CPRProject.readContainer(bytes)
        let source = try #require(try CPRAudioEventArchive.read(container: container).first)
        let baseline = try CPRRecoveryV4(container: container).decode(sourceName: "Derived source")
        let retained = try #require(baseline.recovery.project?.unresolvedAudioEvents.first)
        return try CPRPlacedSourceEventPlan.make(container: container, source: source, retained: retained,
                                                 fades: CPRAutoFadeArchive.read(container: container))
    }

    @Test func BuilderMatchesIndependentIEEEControlsWithoutCollapsingRoundTrips() throws {
        let rows = try oracle("builder_vectors")
        #expect(rows.count == 180)
        #expect(rows.filter { $0["multiply_rate_discriminator"] as? Bool == true }.count == 82)
        #expect(rows.filter { $0["collapsed_offset_discriminator"] as? Bool == true }.count == 4)
        #expect(rows.filter { $0["builder_reader_vs_direct_discriminator"] as? Bool == true }.count == 81)
        for row in rows {
            var result = RBTimelineBuilderProjection()
            let code = try rb_cpr_timeline_builder_project(number(row,"event_start_bits"), number(row,"event_end_bits"),
                number(row,"context_offset_bits"), number(row,"window_start_bits"), number(row,"window_end_bits"),
                number(row,"rate_bits"), &result)
            #expect(code == 0)
            #expect(Int64(result.disposition) == (try integer(row,"disposition")))
            #expect(Int64(result.emptyReason) == (try integer(row,"empty_reason")))
            if result.emptyReason == RB_TIMELINE_BUILDER_NO_OVERLAP { continue }
            for (actual, key) in [(result.period,"period_bits"), (result.clippedStart,"clipped_start_bits"),
                (result.clippedEnd,"clipped_end_bits"), (result.clippedSourceOffset,"clipped_offset_bits")] {
                #expect(actual.bitPattern == (try bits(row,key)))
            }
            #expect(result.startFrame == (try integer(row,"start_frame")))
            #expect(result.endFrame == (try integer(row,"end_frame")))
            #expect(result.offsetFrame == (try integer(row,"offset_frame")))
            if result.disposition == RB_TIMELINE_BUILDER_EMPTY { continue }
            for (actual,key) in [(result.start,"start_bits"), (result.reconstructedEnd,"reconstructed_end_bits"),
                (result.length,"length_bits"), (result.sourceOffset,"offset_bits"), (result.getterEnd,"getter_end_bits")] {
                #expect(actual.bitPattern == (try bits(row,key)))
            }
            for (coordinate,key) in [(result.start,"reader_start"), (result.getterEnd,"reader_end"),
                                      (result.sourceOffset,"reader_offset")] {
                var frame: Int64 = -123
                #expect(rb_cpr_timeline_quantize(result.period, coordinate, &frame) == 0)
                #expect(frame == (try integer(row,key)))
            }
        }
    }

    private func le<T: FixedWidthInteger>(_ x: T) -> Data {
        var x = x.littleEndian
        return withUnsafeBytes(of: &x) { Data($0) }
    }
    private func sample(_ frame: Int, _ channel: Int) -> Int32 {
        Int32((frame * (channel == 0 ? 7919 : 104729) + channel * 12345) & 0xffffff) - 8388608
    }
    private func sampleBits(_ value: Int32) -> UInt32 {
        guard value != 0 else { return 0 }
        let magnitude = UInt32(value < 0 ? -value : value)
        let top = 31 - magnitude.leadingZeroBitCount
        return (value < 0 ? UInt32(0x80000000) : 0) | UInt32(top - 23 + 127) << 23
            | ((magnitude << (23 - top)) & 0x7fffff)
    }
    private func media() -> Data {
        let size = 1058400 * 6
        var data = Data("RIFF".utf8) + le(UInt32(size + 36)) + Data("WAVEfmt ".utf8)
        data += le(UInt32(16)) + le(UInt16(1)) + le(UInt16(2)) + le(UInt32(44100))
        data += le(UInt32(264600)) + le(UInt16(6)) + le(UInt16(24))
        data += Data("data".utf8) + le(UInt32(size)) + Data(repeating: 0, count: size)
        data.withUnsafeMutableBytes { raw in
            let bytes = raw.bindMemory(to: UInt8.self)
            for frame in 0..<1058400 { for channel in 0..<2 {
                let value = UInt32(bitPattern: sample(frame,channel)), p = 44 + (frame*2+channel)*3
                bytes[p] = UInt8(truncatingIfNeeded: value)
                bytes[p+1] = UInt8(truncatingIfNeeded: value >> 8)
                bytes[p+2] = UInt8(truncatingIfNeeded: value >> 16)
            }}
        }
        return data
    }
    private func temporary() throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("PlacedCPR-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder
    }
    private func imported(_ bytes: Data, mediaURL: URL, folder: URL, name: String) throws -> (Project,URL,UUID) {
        let source = folder.appendingPathComponent(name + ".cpr"), package = folder.appendingPathComponent(name + ".rebaseproj")
        try bytes.write(to: source)
        let result = try CPRProject.importProject(from: source, to: package, allowPartial: true)
        let event = try #require(result.project.unresolvedAudioEvents.first)
        let project = try ProjectStore.attachCPRAudioMedia(from: mediaURL, to: event.id, in: result.project, at: package)
        try ProjectStore.save(project, to: package)
        return (project,package,event.id)
    }
    private func snapshot(_ root: URL) throws -> [String:String] {
        // The path enumerator supplies relative names directly. Foundation URL
        // enumeration can mix /var and /private/var even after resolving aliases.
        let files = try #require(FileManager.default.enumerator(atPath: root.path))
        var result: [String:String] = [:]
        for case let relative as String in files {
            #expect(!relative.hasPrefix("/") && !relative.split(separator: "/").contains(".."))
            let url = root.appendingPathComponent(relative)
            guard try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true else { continue }
            result[relative] = cprSHA256(try Data(contentsOf: url))
        }
        return result
    }
    private func check(_ buffer: AVAudioPCMBuffer, at position: Int64, first: Int64, last: Int64, offset: Int64) {
        var equal = true
        for frame in 0..<Int(buffer.frameLength) {
            let timeline = position + Int64(frame)
            for channel in 0..<2 {
                let expected: UInt32 = timeline < first || timeline >= last ? 0 : sampleBits(sample(Int(timeline-first+offset),channel))
                if buffer.floatChannelData![channel][frame].bitPattern != expected { equal = false }
            }
        }
        #expect(equal)
    }

    @Test func SourceBackedPlacementTrimOffsetAndJumpClockMatchExactPCM() throws {
        let folder = try temporary(); defer { try? FileManager.default.removeItem(at: folder) }
        let original = try original(), pcm = media(), mediaURL = folder.appendingPathComponent("Synthetic.wav")
        try pcm.write(to: mediaURL)
        for row in try oracle("source_vectors") {
            let derived = try changed(original, start: bits(row,"raw_start_bits"), length: bits(row,"raw_length_bits"), offset: bits(row,"raw_offset_bits"))
            guard row["application_whole_frame_admitted"] as? Bool == true else {
                #expect(rejects { _ = try plan(derived) }); continue
            }
            let (project,package,id) = try imported(derived, mediaURL: mediaURL, folder: folder, name: #require(row["name"] as? String))
            let before = try snapshot(package), retained = try #require(project.unresolvedAudioEvents.first)
            #expect(retained.placement == nil && project.tracks.flatMap(\.clips).isEmpty)
            let prepared = try CPRSourceEventPlayback.prepare(eventID: id, project: project, root: package, mode: .nativeTimelineSourceRate)
            let range = try #require(prepared.info.timelineRange), stream = try #require(prepared.audio.nativeTimelineStream)
            #expect(range.contract == CPRPlacedSourceEventPlan.contract)
            #expect(range.position.bitPattern == (try bits(row,"start_bits")))
            #expect(range.duration.bitPattern == (try bits(row,"length_bits")))
            #expect(range.offset.bitPattern == (try bits(row,"offset_bits")))
            let first = try integer(row,"reader_start"), last = try integer(row,"reader_end"), offset = try integer(row,"reader_offset")
            #expect(prepared.info.frameCount == last && prepared.info.sourceSHA256 == cprSHA256(derived))
            #expect(prepared.info.mediaSHA256 == cprSHA256(pcm) && prepared.info.sampleRate == 44100)
            #expect(prepared.audio.clips.isEmpty && prepared.audio.sourceEventStream == nil)
            // Full compact arrangements, including gap zeros, use several host partitions.
            if last < 100000 {
                for block in [257,4096,8192] {
                    let cursor = try stream.cursor(from: 0); var position: Int64 = 0
                    while let output = try cursor.nextBuffer(maximumFrames: block) {
                        check(output,at: position,first: first,last: last,offset: offset)
                        position += Int64(output.frameLength)
                    }
                    #expect(position == last && cursor.isAtEnd)
                }
            }
            // Actual original 600-second knot cases seek directly, without allocating silence.
            for seek in Set([Int64(0),max(0,first-1),first,min(first+1,last),last-1,last]) {
                let cursor = try stream.cursor(from: seek)
                if let output = try cursor.nextBuffer(maximumFrames: 257) {
                    check(output,at: seek,first: first,last: last,offset: offset)
                } else { #expect(seek == last) }
            }
            for mode: CPRSourceEventPlaybackMode in [.sourceRate,.nativeMode0ProjectRate,.nativeMode1ProjectRate,.nativeMode2ProjectRate] {
                #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID: id,project: project,root: package,mode: mode) })
            }
            #expect(rejects { _ = try OfflineRenderer.render(project: project,projectRoot: package) })
            let report = try #require(try CPRProject.compatibilityReport(from: package))
            #expect(report.interpretationProfile == CPRProject.currentInterpretationProfile)
            #expect(try ProjectStore.load(from: package) == project)
            #expect(try snapshot(package) == before)
        }
        #expect(try self.original() == original)
    }

    @Test func DetachedAndEditedApplicationClockCannotReinterpretSavedTicks() throws {
        let folder = try temporary(); defer { try? FileManager.default.removeItem(at: folder) }
        let row = try #require(try oracle("source_vectors").first { $0["name"] as? String == "after-jump" })
        let bytes = try changed(original(),start: bits(row,"raw_start_bits"),length: bits(row,"raw_length_bits"),offset: bits(row,"raw_offset_bits"))
        let mediaURL = folder.appendingPathComponent("Synthetic.wav"); try media().write(to: mediaURL)
        let (baseline,package,id) = try imported(bytes,mediaURL: mediaURL,folder: folder,name: "Clock")
        let before = try snapshot(package)
        let original = try CPRSourceEventPlayback.prepare(eventID: id,project: baseline,root: package,mode: .nativeTimelineSourceRate)
        var edited = baseline
        try edited.convertToApplicationTiming()
        try edited.replaceTempoMap(TempoMap(events: [TempoEvent(beat: 0,bpm: 37)]))
        edited.sampleRate = 48000
        try ProjectStore.save(edited,to: package)
        let loaded = try ProjectStore.load(from: package)
        let prepared = try CPRSourceEventPlayback.prepare(eventID: id,project: loaded,root: package,mode: .nativeTimelineSourceRate)
        #expect(prepared.info.timelineRange == original.info.timelineRange && prepared.info.frameCount == original.info.frameCount)
        #expect(prepared.info.sampleRate == 44100 && loaded.tempoMap.nativeClock == nil)
        #expect(loaded.unresolvedAudioEvents == baseline.unresolvedAudioEvents)
        let after = try snapshot(package)
        #expect(after.filter { $0.key != "Project.json" } == before.filter { $0.key != "Project.json" })
        var forged = baseline
        let clock = try #require(baseline.tempoMap.nativeClock)
        forged.tempoMap.nativeClock = try NativeTempoClock(mapRecords: #require(clock.mapRecords),
            sourceSHA256: String(repeating: "0",count:64), sourceObjectOffset: clock.sourceObjectOffset)
        #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID: id,project: forged,root: package,mode: .nativeTimelineSourceRate) })
        #expect(try snapshot(package) == after)
    }

    @Test func UnknownAncestorsTrackShiftDatumsClockAndSourceBoundsReject() throws {
        let original = try original(), parsed = try source(original)
        let container = try CPRProject.readContainer(original), fades = try CPRAutoFadeArchive.read(container: container)
        let track = try #require(fades.tracks[parsed.trackIdentity]), roles = try CPRClockRoles.resolve(container: container)
        let tempo = try #require(roles.tempo).descriptor
        var cases: [(String,Data)] = []
        for object in [parsed.root] + parsed.ancestorTracks {
            for field in [2,18] { for word in [Double(1).bitPattern,UInt64(0x8000000000000000)] {
                var b = original; put(word,at: object.payloadOffset+field,in: &b); cases.append(("ancestor",b))
            }}
        }
        for word in [Double(1).bitPattern,UInt64(0x8000000000000000)] {
            var b = original
            put(word,at: track.resource.payloadOffset+track.resource.payloadByteCount+4,in: &b)
            cases.append(("saved-track-shift",b))
        }
        for (start,length,offset): (Double,Double,Double) in [
            (-1,257,0),(.leastNonzeroMagnitude,257,0),(.nan,257,0),
            (960,0,0),(960,0.5,0),(960,257.5,0),(960,257,-1),(960,257,0.5),
            (960,257,.infinity),(960,2,1058399),(960,1,1058400),(82752000,1,0)
        ] {
            cases.append(("source-range",try changed(original,start:start.bitPattern,length:length.bitPattern,offset:offset.bitPattern)))
        }
        var clip = CPRCursor(data: original,lower: parsed.clip.payloadOffset,upper: parsed.clip.payloadOffset+parsed.clip.payloadByteCount)
        _ = try clip.nativeString(); let clipTag = clip.position
        var b = original; put(Int32(1),at:clipTag,in:&b); cases.append(("clip-datum",b))
        b = original; put((1.0/44100).nextUp.bitPattern,at:clipTag+4,in:&b); cases.append(("reciprocal",b))
        let file = try #require(parsed.cluster.files.first)
        b = original; put(Float(48000).bitPattern,at:file.object.payloadOffset+14,in:&b); cases.append(("rate",b))
        var node = CPRCursor(data: original,lower:parsed.containingNode.payloadOffset,upper:parsed.containingNode.payloadOffset+parsed.containingNode.payloadByteCount)
        _ = try node.nativeString(); let nodeTag = node.position
        b = original; put(Int32(17),at:nodeTag,in:&b); cases.append(("containing-datum",b))
        b = original; put(Double(600).nextUp.bitPattern,at:tempo.payloadOffset+4+22+4,in:&b); cases.append(("noncanonical-clock",b))
        for (_, bytes) in cases { #expect(rejects { _ = try plan(bytes) }) }
        // Negative zero in event coordinates is explicitly normalized by the
        // native +0 start / negated-zero offset path; ancestor -0 stays rejected.
        let signedZero = try changed(original,start:0x8000000000000000,length:Double(257).bitPattern,offset:0x8000000000000000)
        let zeroPlan = try plan(signedZero)
        #expect(zeroPlan.range.position.bitPattern == 0 && zeroPlan.range.offset.bitPattern == 0)
    }

    @Test func FreshProofMediaAndRejectedPublicationLeavePackageIntact() throws {
        let folder = try temporary(); defer { try? FileManager.default.removeItem(at: folder) }
        let derived = try changed(original(),start:Double(960).bitPattern,length:Double(8193).bitPattern,offset:Double(441).bitPattern)
        let mediaURL = folder.appendingPathComponent("Synthetic.wav"); try media().write(to:mediaURL)
        let (project,package,id) = try imported(derived,mediaURL:mediaURL,folder:folder,name:"Custody")
        let before = try snapshot(package)
        let attachment = try #require(project.cprMediaAttachments.first)
        let asset = try ProjectStore.resolveMediaURL(attachment.mediaPath,projectRoot:package)
        for path in [asset,package.appendingPathComponent(CPRProject.originalRelativePath),package.appendingPathComponent(CPRProject.reportRelativePath)] {
            let bytes = try Data(contentsOf:path); var changed = bytes
            changed[path == asset ? 44 : changed.count-1] ^= 1
            try changed.write(to:path)
            #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID:id,project:project,root:package,mode:.nativeTimelineSourceRate) })
            try bytes.write(to:path)
        }
        let destination = folder.appendingPathComponent("Existing.wav"), sentinel = Data("preserve".utf8)
        try sentinel.write(to:destination)
        #expect(rejects { _ = try CPRSourceEventRenderer.render(eventID:id,in:project,at:package,to:destination) })
        #expect(rejects { _ = try OfflineRenderer.export(project:project,projectRoot:package,to:destination) })
        #expect(try Data(contentsOf:destination) == sentinel)
        let saved = fegetround(); defer { _ = fesetround(saved) }
        #expect(fesetround(FE_DOWNWARD) == 0)
        #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID:id,project:project,root:package,mode:.nativeTimelineSourceRate) })
        #expect(fesetround(saved) == 0)
        #expect(try snapshot(package) == before)
        let successful = try CPRSourceEventPlayback.prepare(eventID:id,project:project,root:package,mode:.nativeTimelineSourceRate)
        #expect(successful.info.timelineRange != nil)
    }
}
