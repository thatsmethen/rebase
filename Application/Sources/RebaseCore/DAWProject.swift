import Foundation
import AVFoundation
import ZIPFoundation

public enum DAWProjectError: LocalizedError {
    case invalid(String)
    case unsupported(String)
    public var errorDescription: String? {
        switch self {
        case .invalid(let text): return "Invalid DAWproject: " + text
        case .unsupported(let text): return "Unsupported DAWproject: " + text
        }
    }
}

/// Deliberately strict DAWproject 1.0 audio subset. No Reference runtime equivalence
/// is claimed. Project mix rate is not a DAWproject field: generic imports use
/// 48 kHz; our optional Arrangement comment preserves Rebase's own mix rate.
public enum DAWProject {
    private static let maximumArchiveBytes: UInt64 = 1_073_741_824
    private static let maximumEntryBytes: UInt64 = 268_435_456
    private static let maximumXMLBytes: UInt64 = 8_388_608

    public static func export(project: Project, projectRoot: URL, to destination: URL) throws {
        try project.validate()
        try project.requireResolvedAudioEvents()
        guard project.tempoMap.nativeClock == nil else {
            throw DAWProjectError.unsupported("Use Rebase Timing explicitly before exporting a recovered native clock; DAWproject cannot preserve its arithmetic contract.")
        }
        try project.tempoMap.validate(); try project.signatureMap.validate()
        try requireNew(destination)
        var assets: [URL: (path: String, channels: Int, rate: Double, duration: Double)] = [:]
        for track in project.tracks {
            guard track.timeBase == .seconds else { throw DAWProjectError.unsupported("Musical track anchors are not yet exchanged; convert the track to seconds explicitly first.") }
            for lane in track.automation {
                try lane.validate()
                guard lane.isReadEnabled else { throw DAWProjectError.unsupported("Disabled automation cannot be represented without losing its read state.") }
            }
            for clip in track.clips {
                guard clip.timeBase == .seconds else { throw DAWProjectError.unsupported("Musical clip anchors are not yet exchanged; convert to seconds explicitly first.") }
                let source = try ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: projectRoot)
                let file = try AVAudioFile(forReading: source)
                let format = file.fileFormat
                guard (1...2).contains(format.channelCount), format.sampleRate.isFinite,
                      (8_000...192_000).contains(format.sampleRate), format.sampleRate.rounded() == format.sampleRate else {
                    throw DAWProjectError.unsupported("Audio must be mono/stereo at an integral sample rate of 8–192 kHz; exchange does not resample media.")
                }
                let bounds = try AudioSampleValidation.scan(url: source, name: clip.name)
                try AudioSampleValidation.validateInterval(clip, sampleRate: bounds.sampleRate, frameCount: bounds.frameCount)
                if assets[source] == nil {
                    let ext = source.pathExtension.lowercased().filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
                    let path = "audio/" + UUID().uuidString + (ext.isEmpty ? "" : "." + ext)
                    assets[source] = (path, Int(file.processingFormat.channelCount), bounds.sampleRate,
                                      Double(bounds.frameCount) / bounds.sampleRate)
                }
            }
        }
        let xml = try projectXML(project, root: projectRoot, assets: assets)
        let metadata = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><MetaData><Title>\(escape(project.name))</Title></MetaData>"
        _ = try XMLTree.parse(Data(xml.utf8)); _ = try XMLTree.parse(Data(metadata.utf8))
        let temporary = destination.deletingLastPathComponent().appendingPathComponent(".rebase-exchange-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: temporary) }
        do {
            let archive = try Archive(url: temporary, accessMode: .create)
            try add(Data(xml.utf8), path: "project.xml", to: archive)
            try add(Data(metadata.utf8), path: "metadata.xml", to: archive)
            var total: UInt64 = UInt64(xml.utf8.count + metadata.utf8.count)
            for (source, asset) in assets.sorted(by: { $0.value.path < $1.value.path }) {
                let before = try source.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
                let size = UInt64(before.fileSize ?? 0)
                guard size <= maximumEntryBytes, total + size <= maximumArchiveBytes else {
                    throw DAWProjectError.unsupported("Audio exceeds the exchange size limits (256 MiB per file, 1 GiB total).")
                }
                total += size
                try archive.addEntry(with: asset.path, fileURL: source, compressionMethod: .none)
                let after = try source.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
                guard before.fileSize == after.fileSize, before.contentModificationDate == after.contentModificationDate else {
                    throw DAWProjectError.invalid("A source audio file changed while exporting.")
                }
            }
        }
        try requireNew(destination)
        try FileManager.default.moveItem(at: temporary, to: destination)
    }

    public static func importProject(from source: URL, to destination: URL) throws -> Project {
        try requireNew(destination)
        let archive = try Archive(url: source, accessMode: .read)
        let entries = try checkedEntries(archive, source: source)
        guard let projectEntry = entries["project.xml"] else { throw DAWProjectError.invalid("project.xml is missing.") }
        let tree = try XMLTree.parse(read(projectEntry, from: archive, limit: maximumXMLBytes))
        var name = source.deletingPathExtension().lastPathComponent
        if let entry = entries["metadata.xml"] {
            let metadata = try XMLTree.parse(read(entry, from: archive, limit: maximumXMLBytes))
            guard metadata.name == "MetaData" else { throw DAWProjectError.invalid("metadata.xml root must be MetaData.") }
            if let title = try metadata.child("Title") { name = title.text }
        }
        let parsed = try parseProject(tree, name: name)
        let staging = destination.deletingLastPathComponent().appendingPathComponent(".rebase-import-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: staging) }
        try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
        try FileManager.default.createDirectory(at: staging.appendingPathComponent("Media"), withIntermediateDirectories: false)
        var project = parsed.project
        var imported: [String: String] = [:]
        for pending in parsed.clips {
            guard let entry = entries[pending.path], entry.type == .file else {
                throw DAWProjectError.invalid("Referenced audio is missing: \(pending.path)")
            }
            let mediaPath: String
            if let existing = imported[pending.path] { mediaPath = existing }
            else {
                let ext = URL(fileURLWithPath: pending.path).pathExtension.lowercased().filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
                mediaPath = "Media/" + UUID().uuidString + (ext.isEmpty ? "" : "." + String(ext.prefix(12)))
                let url = staging.appendingPathComponent(mediaPath)
                FileManager.default.createFile(atPath: url.path, contents: nil)
                let handle = try FileHandle(forWritingTo: url)
                do {
                    var count: UInt64 = 0
                    let crc = try archive.extract(entry) { data in
                        count += UInt64(data.count)
                        guard count <= entry.uncompressedSize, count <= maximumEntryBytes else { throw DAWProjectError.invalid("Audio entry expanded beyond its declared size.") }
                        try handle.write(contentsOf: data)
                    }
                    try handle.close()
                    guard count == entry.uncompressedSize, crc == entry.checksum else { throw DAWProjectError.invalid("Audio size or CRC mismatch.") }
                } catch { try? handle.close(); throw error }
                imported[pending.path] = mediaPath
            }
            let url = staging.appendingPathComponent(mediaPath)
            let file = try AVAudioFile(forReading: url)
            let rate = file.processingFormat.sampleRate
            guard Int(file.processingFormat.channelCount) == pending.channels,
                  rate == pending.sampleRate,
                  abs(Double(file.length) / rate - pending.mediaDuration) <= 1 / rate else {
                throw DAWProjectError.invalid("Audio metadata does not match the referenced file: \(pending.path)")
            }
            var clip = pending.clip
            clip.mediaPath = mediaPath
            project.tracks[pending.track].clips.append(clip)
        }
        try ProjectStore.save(project, to: staging)
        _ = try ProjectStore.load(from: staging) // Validate all decoded samples and every clip interval.
        try requireNew(destination)
        try FileManager.default.moveItem(at: staging, to: destination)
        return project
    }

    private static func projectXML(_ project: Project, root: URL,
        assets: [URL: (path: String, channels: Int, rate: Double, duration: Double)]) throws -> String {
        let initialTempo = project.tempoMap.events[0], initialSignature = project.signatureMap.events[0]
        var xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Project version=\"1.0\"><Application name=\"Rebase\" version=\"1\"/>"
        xml += "<Transport><Tempo id=\"tempo\" unit=\"bpm\" value=\"\(initialTempo.bpm)\"/><TimeSignature id=\"signature\" numerator=\"\(initialSignature.numerator)\" denominator=\"\(initialSignature.denominator)\"/></Transport><Structure>"
        for (index, track) in project.tracks.enumerated() {
            xml += "<Track id=\"track\(index)\" name=\"\(escape(track.name))\" contentType=\"audio\" loaded=\"true\"><Channel id=\"channel\(index)\" role=\"regular\" audioChannels=\"2\" solo=\"\(track.isSolo)\"><Mute value=\"\(track.isMuted)\"/><Pan id=\"pan\(index)\" unit=\"normalized\" value=\"\((track.pan + 1) / 2)\"/><Volume id=\"gain\(index)\" unit=\"decibel\" value=\"\(track.gainDB)\"/></Channel></Track>"
        }
        xml += "</Structure><Arrangement name=\"\(escape(project.name))\" comment=\"Rebase.sampleRate=\(project.sampleRate)\"><Lanes timeUnit=\"seconds\">"
        for (index, track) in project.tracks.enumerated() {
            xml += "<Lanes track=\"track\(index)\"><Clips>"
            for clip in track.clips {
                let url = try ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root)
                guard let asset = assets[url] else { throw DAWProjectError.invalid("Missing export asset.") }
                xml += "<Clip name=\"\(escape(clip.name))\" time=\"\(clip.position)\" duration=\"\(clip.duration)\" contentTimeUnit=\"seconds\" playStart=\"\(clip.sourceOffset)\"><Audio timeUnit=\"seconds\" channels=\"\(asset.channels)\" sampleRate=\"\(Int(asset.rate))\" duration=\"\(asset.duration)\"><File path=\"\(escape(asset.path))\"/></Audio></Clip>"
            }
            xml += "</Clips>"
            for lane in track.automation {
                let gain = lane.parameter == .gainDB
                xml += "<Points timeUnit=\"seconds\" unit=\"\(gain ? "decibel" : "normalized")\"><Target parameter=\"\(gain ? "gain" : "pan")\(index)\"/>"
                for point in lane.points {
                    let value = gain ? point.value : (point.value + 1) / 2
                    xml += "<RealPoint time=\"\(point.time)\" value=\"\(value)\" interpolation=\"\(point.interpolation == .step ? "hold" : "linear")\"/>"
                }
                xml += "</Points>"
            }
            xml += "</Lanes>"
        }
        xml += "</Lanes><TempoAutomation timeUnit=\"beats\" unit=\"bpm\"><Target parameter=\"tempo\"/>"
        for event in project.tempoMap.events { xml += "<RealPoint time=\"\(event.beat)\" value=\"\(event.bpm)\" interpolation=\"hold\"/>" }
        xml += "</TempoAutomation><TimeSignatureAutomation timeUnit=\"beats\"><Target parameter=\"signature\"/>"
        for event in project.signatureMap.events { xml += "<TimeSignaturePoint time=\"\(event.beat)\" numerator=\"\(event.numerator)\" denominator=\"\(event.denominator)\"/>" }
        return xml + "</TimeSignatureAutomation></Arrangement></Project>"
    }

    private struct PendingClip {
        var track: Int; var clip: Clip; var path: String
        var channels: Int; var sampleRate: Double; var mediaDuration: Double
    }

    private static func parseProject(_ root: XMLTree, name: String) throws -> (project: Project, clips: [PendingClip]) {
        guard root.name == "Project", root.attributes["version"] == "1.0" else { throw DAWProjectError.unsupported("Only Project version1.0 is supported.") }
        try root.check(children: ["Application", "Transport", "Structure", "Arrangement", "Scenes"], attributes: ["version"])
        guard let application = try root.child("Application") else { throw DAWProjectError.invalid("Application is missing.") }
        try application.check(children: [], attributes: ["version", "name"])
        if let scenes = try root.child("Scenes"), !scenes.children.isEmpty { throw DAWProjectError.unsupported("Clip-launcher scenes.") }
        let transport = try root.child("Transport")
        try transport?.check(children: ["Tempo", "TimeSignature"], attributes: [])
        let tempo = try transport?.child("Tempo"), signature = try transport?.child("TimeSignature")
        try tempo?.check(children: [], attributes: ["unit", "value", "min", "max", "parameterID"])
        try signature?.check(children: [], attributes: ["numerator", "denominator", "parameterID"])
        if let tempo, tempo.attributes["unit"] != "bpm" { throw DAWProjectError.unsupported("Tempo must use bpm.") }
        let bpm = try tempo?.number("value") ?? 120
        var project = Project(name: name, tempo: bpm)
        project.tempoMap = TempoMap(events: [TempoEvent(beat: 0, bpm: bpm)])
        project.signatureMap = SignatureMap(events: [SignatureEvent(beat: 0, numerator: try signature?.integer("numerator") ?? 4, denominator: try signature?.integer("denominator") ?? 4)])
        guard let structure = try root.child("Structure") else { throw DAWProjectError.invalid("Structure is missing.") }
        try structure.check(children: ["Track"], attributes: [])
        var trackIndices: [String: Int] = [:], targets: [String: (Int, AutomationParameter)] = [:]
        var masterID: String?, destinations: [String?] = []
        for trackNode in structure.children {
            try trackNode.check(children: ["Channel"], attributes: ["contentType", "loaded"])
            guard try trackNode.boolean("loaded", default: true),
                  Set((trackNode.attributes["contentType"] ?? "audio").split(separator: " ").map(String.init)).isSubset(of: ["audio", "automation"]) else { throw DAWProjectError.unsupported("Only loaded audio tracks are supported.") }
            guard let channel = try trackNode.child("Channel") else { throw DAWProjectError.invalid("A track has no channel.") }
            try channel.check(children: ["Mute", "Pan", "Volume", "Devices", "Sends"], attributes: ["audioChannels", "destination", "role", "solo"])
            for tag in ["Devices", "Sends"] {
                if let node = try channel.child(tag), !node.children.isEmpty { throw DAWProjectError.unsupported("Devices and sends must be rendered or removed before exchange.") }
            }
            guard try channel.integer("audioChannels", default: 2) == 2 else { throw DAWProjectError.unsupported("Only stereo mixer channels are supported (audio files may be mono or stereo).") }
            let mute = try channel.child("Mute"), pan = try channel.child("Pan"), volume = try channel.child("Volume")
            try mute?.check(children: [], attributes: ["value", "parameterID"])
            for node in [pan, volume].compactMap({ $0 }) { try node.check(children: [], attributes: ["value", "unit", "min", "max", "parameterID"]) }
            let gain = try volume.map { try gainDB(value: $0.number("value"), unit: $0.required("unit")) } ?? 0
            let panValue: Double
            if let pan {
                guard pan.attributes["unit"] == "normalized" else { throw DAWProjectError.unsupported("Pan must use normalized0...1.") }
                panValue = try pan.number("value") * 2 - 1
            } else { panValue = 0 }
            let muted = try mute?.boolean("value", default: false) ?? false
            let solo = try channel.boolean("solo", default: false)
            let role = channel.attributes["role"] ?? "regular"
            if role == "master" {
                guard masterID == nil, gain == 0, panValue == 0, !muted, !solo,
                      channel.attributes["destination"] == nil else { throw DAWProjectError.unsupported("Only one neutral master channel is supported.") }
                masterID = try channel.required("id")
                continue
            }
            guard role == "regular" else { throw DAWProjectError.unsupported("Group, effect and VCA mixer routing.") }
            let index = project.tracks.count
            let id = try trackNode.required("id")
            trackIndices[id] = index
            project.tracks.append(Track(name: trackNode.attributes["name"] ?? "Audio", gainDB: gain, pan: panValue, isMuted: muted, isSolo: solo))
            destinations.append(channel.attributes["destination"])
            if let id = volume?.attributes["id"] { targets[id] = (index, .gainDB) }
            if let id = pan?.attributes["id"] { targets[id] = (index, .pan) }
        }
        for destination in destinations.compactMap({ $0 }) where destination != masterID { throw DAWProjectError.unsupported("Non-master routing destination: \(destination)") }
        var pending: [PendingClip] = []
        if let arrangement = try root.child("Arrangement") {
            try arrangement.check(children: ["Lanes", "TempoAutomation", "TimeSignatureAutomation"], attributes: [])
            if application.attributes["name"] == "Rebase", let comment = arrangement.attributes["comment"], comment.hasPrefix("Rebase.sampleRate=") {
                guard let rate = Double(comment.dropFirst("Rebase.sampleRate=".count)), rate.isFinite else { throw DAWProjectError.invalid("Rebase mix-rate metadata.") }
                project.sampleRate = rate
            }
            if let points = try arrangement.child("TempoAutomation") {
                try points.check(children: ["Target", "RealPoint"], attributes: ["timeUnit", "unit"])
                try requireTarget(points, id: tempo?.attributes["id"])
                guard points.attributes["timeUnit"] ?? "beats" == "beats", points.attributes["unit"] == "bpm" else { throw DAWProjectError.unsupported("Tempo automation must use beat time and bpm values.") }
                var events: [TempoEvent] = []
                for point in points.children where point.name == "RealPoint" {
                    try point.check(children: [], attributes: ["time", "value", "interpolation"])
                    // The format documentation and observed Reference importer
                    // disagree about the omitted default. Require explicit data.
                    guard try point.required("interpolation") == "hold" else { throw DAWProjectError.unsupported("Tempo ramps or ambiguous interpolation.") }
                    events.append(TempoEvent(beat: try point.number("time"), bpm: try point.number("value")))
                }
                if events.first?.beat != 0 { events.insert(TempoEvent(beat: 0, bpm: bpm), at: 0) }
                project.tempoMap = TempoMap(events: events)
            }
            if let points = try arrangement.child("TimeSignatureAutomation") {
                try points.check(children: ["Target", "TimeSignaturePoint"], attributes: ["timeUnit"])
                try requireTarget(points, id: signature?.attributes["id"])
                guard points.attributes["timeUnit"] ?? "beats" == "beats" else { throw DAWProjectError.unsupported("Time signatures must use beat time.") }
                var events: [SignatureEvent] = []
                for point in points.children where point.name == "TimeSignaturePoint" {
                    try point.check(children: [], attributes: ["time", "numerator", "denominator"])
                    events.append(SignatureEvent(beat: try point.number("time"), numerator: try point.integer("numerator"), denominator: try point.integer("denominator")))
                }
                if events.first?.beat != 0 { events.insert(project.signatureMap.events[0], at: 0) }
                project.signatureMap = SignatureMap(events: events)
            }
            if let lanes = try arrangement.child("Lanes") {
                try parseLanes(lanes, inheritedUnit: "beats", inheritedTrack: nil, trackIndices: trackIndices, targets: targets, project: &project, clips: &pending)
            }
        }
        try project.validate(); try project.tempoMap.validate(); try project.signatureMap.validate()
        return (project, pending)
    }

    private static func parseLanes(_ node: XMLTree, inheritedUnit: String, inheritedTrack: String?,
        trackIndices: [String: Int], targets: [String: (Int, AutomationParameter)],
        project: inout Project, clips: inout [PendingClip]) throws {
        let unit = node.attributes["timeUnit"] ?? inheritedUnit
        let trackID = node.attributes["track"] ?? inheritedTrack
        guard ["seconds", "beats"].contains(unit) else { throw DAWProjectError.invalid("Unknown timeline time unit.") }
        if let trackID, trackIndices[trackID] == nil { throw DAWProjectError.unsupported("Timeline targets an unknown or master track.") }
        switch node.name {
        case "Lanes":
            try node.check(children: ["Lanes", "Clips", "Points"], attributes: ["timeUnit", "track"])
            for child in node.children { try parseLanes(child, inheritedUnit: unit, inheritedTrack: trackID, trackIndices: trackIndices, targets: targets, project: &project, clips: &clips) }
        case "Clips":
            try node.check(children: ["Clip"], attributes: ["timeUnit", "track"])
            guard unit == "seconds", let trackID, let index = trackIndices[trackID] else { throw DAWProjectError.unsupported("Audio clips must have a regular track and seconds time unit.") }
            for clipNode in node.children {
                try clipNode.check(children: ["Audio"], attributes: ["time", "duration", "contentTimeUnit", "playStart", "playStop", "fadeInTime", "fadeOutTime", "fadeTimeUnit", "enable"])
                guard try clipNode.boolean("enable", default: true),
                      clipNode.attributes["contentTimeUnit"] ?? unit == "seconds",
                      try clipNode.number("fadeInTime", default: 0) == 0,
                      try clipNode.number("fadeOutTime", default: 0) == 0,
                      let audio = try clipNode.child("Audio") else { throw DAWProjectError.unsupported("Only enabled, unfaded direct audio clips in seconds are supported.") }
                try audio.check(children: ["File"], attributes: ["timeUnit", "duration", "channels", "sampleRate"])
                guard audio.attributes["timeUnit"] ?? "seconds" == "seconds", let file = try audio.child("File") else { throw DAWProjectError.invalid("Audio needs a File and seconds content.") }
                try file.check(children: [], attributes: ["path", "external"])
                guard try !file.boolean("external", default: false) else { throw DAWProjectError.unsupported("External audio references.") }
                let path = try file.required("path"); try safePath(path)
                let offset = try clipNode.number("playStart", default: 0)
                let stop = try clipNode.optionalNumber("playStop")
                let duration = try clipNode.optionalNumber("duration") ?? stop.map { $0 - offset }
                guard let duration else { throw DAWProjectError.invalid("Clip needs duration or playStop.") }
                if let stop, abs((stop - offset) - duration) > 1e-9 { throw DAWProjectError.unsupported("Clip duration/playStop disagreement.") }
                let channels = try audio.integer("channels"), rate = try audio.number("sampleRate")
                guard (1...2).contains(channels), rate >= 8_000, rate <= 192_000, rate.rounded() == rate else { throw DAWProjectError.unsupported("Audio must be mono/stereo at8–192kHz.") }
                let clip = Clip(mediaPath: "", name: clipNode.attributes["name"] ?? URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent,
                                position: try clipNode.number("time"), sourceOffset: offset, duration: duration)
                clips.append(PendingClip(track: index, clip: clip, path: path, channels: channels, sampleRate: rate, mediaDuration: try audio.number("duration")))
            }
        case "Points":
            try node.check(children: ["Target", "RealPoint"], attributes: ["timeUnit", "track", "unit"])
            guard unit == "seconds", let target = try node.child("Target") else { throw DAWProjectError.unsupported("Track automation must use seconds and a parameter target.") }
            try target.check(children: [], attributes: ["parameter"])
            guard let binding = targets[try target.required("parameter")] else { throw DAWProjectError.unsupported("Automation target is not track gain or pan.") }
            if let trackID, trackIndices[trackID] != binding.0 { throw DAWProjectError.invalid("Automation target disagrees with its track.") }
            let valueUnit = try node.required("unit")
            guard valueUnit == (binding.1 == .gainDB ? "decibel" : "normalized") else { throw DAWProjectError.unsupported("Gain automation requires decibels and pan requires normalized values; nonlinear conversion would change the curve.") }
            guard !project.tracks[binding.0].automation.contains(where: { $0.parameter == binding.1 }) else { throw DAWProjectError.unsupported("Multiple automation lanes for one parameter.") }
            var points: [AutomationPoint] = []
            for child in node.children where child.name == "RealPoint" {
                try child.check(children: [], attributes: ["time", "value", "interpolation"])
                let interpolation = try child.required("interpolation")
                guard ["hold", "linear"].contains(interpolation) else { throw DAWProjectError.unsupported("Automation interpolation: \(interpolation)") }
                let raw = try child.number("value")
                points.append(AutomationPoint(time: try child.number("time"), value: binding.1 == .gainDB ? raw : raw * 2 - 1,
                                              interpolation: interpolation == "hold" ? .step : .linear))
            }
            let lane = AutomationLane(parameter: binding.1, points: points)
            try lane.validate(); project.tracks[binding.0].automation.append(lane)
        default: throw DAWProjectError.unsupported("Timeline element \(node.name).")
        }
    }

    private static func requireTarget(_ points: XMLTree, id: String?) throws {
        guard let id, let target = try points.child("Target") else { throw DAWProjectError.invalid("Automation target parameter is missing.") }
        try target.check(children: [], attributes: ["parameter"])
        guard target.attributes["parameter"] == id else { throw DAWProjectError.invalid("Automation target does not match its transport parameter.") }
    }
    private static func gainDB(value: Double, unit: String) throws -> Double {
        if unit == "decibel" { return value }
        guard unit == "linear", value > 0 else { throw DAWProjectError.unsupported("Constant volume must use finite decibels or positive linear amplitude.") }
        return 20 * log10(value)
    }
    private static func escape(_ value: String) -> String {
        value.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;").replacingOccurrences(of: "\"", with: "&quot;").replacingOccurrences(of: "'", with: "&apos;")
    }
    private static func requireNew(_ url: URL) throws {
        guard !FileManager.default.fileExists(atPath: url.path), (try? url.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) != true else { throw DAWProjectError.invalid("Destination already exists: \(url.lastPathComponent)") }
    }
    private static func add(_ data: Data, path: String, to archive: Archive) throws {
        try archive.addEntry(with: path, type: .file, uncompressedSize: Int64(data.count), compressionMethod: .deflate) { offset, size in
            data.subdata(in: Int(offset)..<min(Int(offset) + size, data.count))
        }
    }
    private static func safePath(_ path: String) throws {
        let parts = path.split(separator: "/", omittingEmptySubsequences: false)
        guard !path.isEmpty, !path.contains("\\"), !path.contains(":"), !path.contains("\0"),
              parts.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }) else { throw DAWProjectError.invalid("Unsafe archive path: \(path)") }
    }
    private static func read(_ entry: Entry, from archive: Archive, limit: UInt64) throws -> Data {
        guard entry.type == .file, entry.uncompressedSize <= limit else { throw DAWProjectError.invalid("XML entry is not a bounded regular file.") }
        var result = Data()
        let crc = try archive.extract(entry) { chunk in
            guard UInt64(result.count) + UInt64(chunk.count) <= min(limit, entry.uncompressedSize) else { throw DAWProjectError.invalid("Entry expands beyond declared size.") }
            result.append(chunk)
        }
        guard UInt64(result.count) == entry.uncompressedSize, crc == entry.checksum else { throw DAWProjectError.invalid("Entry size or CRC mismatch.") }
        return result
    }

    /// ZIPFoundation's iterator can end early on malformed headers. A separate
    /// bounded central-directory pass checks the declared count and local names.
    /// ZIP64 and split/encrypted archives are explicitly outside this subset.
    private static func checkedEntries(_ archive: Archive, source: URL) throws -> [String: Entry] {
        let size = try source.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size >= 22, UInt64(size) <= maximumArchiveBytes else { throw DAWProjectError.invalid("Archive size is outside22bytes...1GiB.") }
        let handle = try FileHandle(forReadingFrom: source); defer { try? handle.close() }
        func bytes(_ offset: Int, _ length: Int) throws -> Data {
            guard offset >= 0, length >= 0, offset <= size - length else { throw DAWProjectError.invalid("Truncated ZIP structure.") }
            try handle.seek(toOffset: UInt64(offset))
            let data = try handle.read(upToCount: length) ?? Data()
            guard data.count == length else { throw DAWProjectError.invalid("Truncated ZIP structure.") }; return data
        }
        let tailOffset = max(0, size - 65_557), tail = try bytes(tailOffset, size - tailOffset)
        var eocd: Int?
        for index in stride(from: tail.count - 22, through: 0, by: -1) {
            if tail.u32(index) == 0x06054b50, index + 22 + Int(tail.u16(index + 20)) == tail.count { eocd = index; break }
        }
        guard let eocd else { throw DAWProjectError.invalid("ZIP end record is missing.") }
        let count = Int(tail.u16(eocd + 10)), centralSize = Int(tail.u32(eocd + 12)), centralOffset = Int(tail.u32(eocd + 16))
        guard tail.u16(eocd + 4) == 0, tail.u16(eocd + 6) == 0, Int(tail.u16(eocd + 8)) == count,
              count > 0, count <= 4096, centralSize <= 32_000_000,
              centralOffset + centralSize == tailOffset + eocd else { throw DAWProjectError.unsupported("Split, ZIP64, excessive-entry or inconsistent archive directory.") }
        let central = try bytes(centralOffset, centralSize)
        var offset = 0, expected: [(UInt32, UInt64)] = [], localOffsets = Set<Int>()
        for _ in 0..<count {
            guard offset + 46 <= central.count, central.u32(offset) == 0x02014b50 else { throw DAWProjectError.invalid("Invalid central directory.") }
            let flags = central.u16(offset + 8), method = central.u16(offset + 10)
            let compressed = Int(central.u32(offset + 20)), uncompressed = UInt64(central.u32(offset + 24))
            let nameCount = Int(central.u16(offset + 28)), extraCount = Int(central.u16(offset + 30)), commentCount = Int(central.u16(offset + 32))
            let local = Int(central.u32(offset + 42))
            guard flags & 0x41 == 0, method == 0 || method == 8,
                  central.u16(offset + 34) == 0, uncompressed <= maximumEntryBytes,
                  compressed < Int(UInt32.max), local < centralOffset, localOffsets.insert(local).inserted,
                  offset + 46 + nameCount + extraCount + commentCount <= central.count else { throw DAWProjectError.unsupported("Encrypted, oversized or inconsistent ZIP entry.") }
            let header = try bytes(local, 30)
            guard header.u32(0) == 0x04034b50, header.u16(6) == flags, header.u16(8) == method,
                  Int(header.u16(26)) == nameCount else { throw DAWProjectError.invalid("Local/central ZIP header mismatch.") }
            let localName = try bytes(local + 30, nameCount)
            guard localName == central.subdata(in: (offset + 46)..<(offset + 46 + nameCount)),
                  local + 30 + nameCount + Int(header.u16(28)) + compressed <= centralOffset else { throw DAWProjectError.invalid("Local entry name or bounds mismatch.") }
            expected.append((central.u32(offset + 16), uncompressed))
            offset += 46 + nameCount + extraCount + commentCount
        }
        guard offset == central.count else { throw DAWProjectError.invalid("Unexpected central-directory bytes.") }
        let list = Array(archive)
        guard list.count == count else { throw DAWProjectError.invalid("ZIP entry iteration was incomplete.") }
        var result: [String: Entry] = [:], canonical = Set<String>(), total: UInt64 = 0
        for (index, entry) in list.enumerated() {
            guard entry.type != .symlink else { throw DAWProjectError.invalid("Symbolic links are not allowed in an exchange archive.") }
            let path = entry.type == .directory && entry.path.hasSuffix("/") ? String(entry.path.dropLast()) : entry.path
            try safePath(path)
            let key = path.precomposedStringWithCanonicalMapping.lowercased()
            guard canonical.insert(key).inserted, entry.uncompressedSize == expected[index].1,
                  entry.checksum == expected[index].0 else { throw DAWProjectError.invalid("Duplicate path or inconsistent entry size/CRC fields.") }
            total += entry.uncompressedSize
            guard total <= maximumArchiveBytes else { throw DAWProjectError.unsupported("Expanded archive exceeds1GiB.") }
            result[entry.path] = entry
        }
        return result
    }
}

private extension Data {
    func u16(_ i: Int) -> UInt16 { UInt16(self[i]) | UInt16(self[i + 1]) << 8 }
    func u32(_ i: Int) -> UInt32 { UInt32(u16(i)) | UInt32(u16(i + 2)) << 16 }
}

private final class XMLTree: NSObject, XMLParserDelegate {
    var name = ""; var attributes: [String: String] = [:]; var children: [XMLTree] = []; var text = ""
    private var stack: [XMLTree] = []; private var root: XMLTree?; private var failure: Error?; private var count = 0
    static func parse(_ data: Data) throws -> XMLTree {
        guard let string = String(data: data, encoding: .utf8), !string.contains("\0"),
              !string.uppercased().contains("<!DOCTYPE"), !string.uppercased().contains("<!ENTITY") else { throw DAWProjectError.invalid("XML must be UTF-8 without DTDs or entities.") }
        if let declaration = string.range(of: "<?xml"), let end = string.range(of: "?>", range: declaration.lowerBound..<string.endIndex) {
            let header = String(string[declaration.lowerBound..<end.upperBound]).lowercased()
            let expression = try NSRegularExpression(pattern: "encoding\\s*=\\s*['\"]([^'\"]+)['\"]")
            if let match = expression.firstMatch(in: header, range: NSRange(header.startIndex..., in: header)),
               let range = Range(match.range(at: 1), in: header), header[range] != "utf-8" {
                throw DAWProjectError.unsupported("Only UTF-8 XML encoding is supported.")
            }
        }
        let delegate = XMLTree(), parser = XMLParser(data: data)
        parser.shouldResolveExternalEntities = false; parser.delegate = delegate
        guard parser.parse(), delegate.failure == nil, let root = delegate.root else { throw delegate.failure ?? DAWProjectError.invalid(parser.parserError?.localizedDescription ?? "Malformed XML.") }
        var ids = Set<String>()
        func verify(_ node: XMLTree) throws {
            if let id = node.attributes["id"], !ids.insert(id).inserted { throw DAWProjectError.invalid("Duplicate XML identifier: \(id)") }
            for child in node.children { try verify(child) }
        }
        try verify(root); return root
    }
    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String]) {
        count += 1
        guard stack.count < 64, count <= 100_000, !elementName.contains(":"), namespaceURI == nil else {
            failure = DAWProjectError.invalid("XML nesting, namespace or element limit."); parser.abortParsing(); return
        }
        let node = XMLTree(); node.name = elementName; node.attributes = attributeDict
        if let parent = stack.last { parent.children.append(node) } else { root = node }
        stack.append(node)
    }
    func parser(_ parser: XMLParser, foundCharacters string: String) { stack.last?.text += string }
    func parser(_ parser: XMLParser, foundCDATA CDATABlock: Data) {
        if let string = String(data: CDATABlock, encoding: .utf8) { stack.last?.text += string }
        else { failure = DAWProjectError.invalid("Invalid UTF-8 CDATA."); parser.abortParsing() }
    }
    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) { if !stack.isEmpty { stack.removeLast() } }
    func parser(_ parser: XMLParser, resolveExternalEntityName name: String, systemID: String?) -> Data? {
        failure = DAWProjectError.invalid("External XML entities are not permitted."); parser.abortParsing(); return nil
    }
    func check(children allowedChildren: Set<String>, attributes allowedAttributes: Set<String>) throws {
        let metadata: Set<String> = ["id", "name", "color", "comment"]
        guard Set(children.map(\.name)).isSubset(of: allowedChildren), Set(attributes.keys).isSubset(of: allowedAttributes.union(metadata)), text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw DAWProjectError.unsupported("Unrepresented attributes, content or child elements in \(name).")
        }
    }
    func child(_ name: String) throws -> XMLTree? {
        let matches = children.filter { $0.name == name }
        guard matches.count <= 1 else { throw DAWProjectError.invalid("Duplicate \(name) elements.") }; return matches.first
    }
    func required(_ name: String) throws -> String {
        guard let value = attributes[name], !value.isEmpty else { throw DAWProjectError.invalid("\(self.name).\(name) is required.") }; return value
    }
    func optionalNumber(_ name: String) throws -> Double? {
        guard let raw = attributes[name] else { return nil }
        guard let value = Double(raw), value.isFinite else { throw DAWProjectError.invalid("\(self.name).\(name) must be finite.") }; return value
    }
    func number(_ name: String, default fallback: Double? = nil) throws -> Double {
        guard let value = try optionalNumber(name) ?? fallback else { throw DAWProjectError.invalid("\(self.name).\(name) is required.") }; return value
    }
    func integer(_ name: String, default fallback: Int? = nil) throws -> Int {
        guard let raw = attributes[name] else {
            if let fallback { return fallback }; throw DAWProjectError.invalid("\(self.name).\(name) is required.")
        }
        guard let value = Int(raw) else { throw DAWProjectError.invalid("\(self.name).\(name) must be an integer.") }; return value
    }
    func boolean(_ name: String, default fallback: Bool) throws -> Bool {
        guard let raw = attributes[name] else { return fallback }
        switch raw { case "true", "1": return true; case "false", "0": return false
        default: throw DAWProjectError.invalid("\(self.name).\(name) must be Boolean.") }
    }
}
