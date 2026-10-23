import Foundation
import CryptoKit
import RebaseCore

// Input preparation through the frozen compiled public APIs, not a GUI import
// observation or a native-valid CPR claim. All sources are symbolic controls.
func digest(_ url: URL) throws -> String {
    SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined()
}
func require(_ condition: Bool, _ message: String) throws {
    if !condition { throw NSError(domain: "APP020.GUIInputHelper", code: 1,
                                 userInfo: [NSLocalizedDescriptionKey: message]) }
}

let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let here = root.appendingPathComponent("research/evidence/application/APP020", isDirectory: true)
let media = here.appendingPathComponent("track-controls-01/Symbolic Track Signal.wav")
try require(try digest(media) == "0f22730ee27f5803ceefdefe014fa72b0220d2aee98d223873ae8e64c6c30f07", "Media identity changed")
let requests: [(String, String, String, Int, Bool)] = [
    ("Three Track QA.rebaseproj", "track-controls-01/three-events.cpr",
     "045a18e1185ec174e060058658537aab4d1c0dc603dcfa347b3a520c7deb278c", 3, false),
    ("Unknown Track QA.rebaseproj", "track-controls-01/unknown-child.cpr",
     "c952fb147ffdfe1205378118f75735620350578e342b3f4af4d76f55e34d74a6", 2, false),
    ("Saved32 Track QA.rebaseproj", "track-controls-saved32k/two-events-saved32k.cpr",
     "bc74b4fbcfbce1bdacd9f26df1bffd734268140cc1bfcd07200ceb097121669b", 2, true)
]
for request in requests {
    try require(!FileManager.default.fileExists(atPath: here.appendingPathComponent(request.0).path),
                "Refusing existing package: \(request.0)")
    try require(try digest(here.appendingPathComponent(request.1)) == request.2,
                "Source identity changed: \(request.1)")
}

var results: [[String: Any]] = []
for (name, relativeSource, sourceSHA, count, editClock) in requests {
    let destination = here.appendingPathComponent(name, isDirectory: true)
    let imported = try CPRProject.importProject(from: here.appendingPathComponent(relativeSource),
                                                to: destination, allowPartial: true)
    var project = imported.project
    try require(project.unresolvedAudioEvents.count == count, "Unexpected event count: \(name)")
    guard let anchor = project.unresolvedAudioEvents.first?.id else {
        throw NSError(domain: "APP020.GUIInputHelper", code: 2)
    }
    project = try ProjectStore.attachCPRAudioMedia(from: media, to: anchor,
                                                  in: project, at: destination)
    if editClock {
        try require(project.sampleRate == 32000 && project.tempo == 120,
                    "Unexpected saved-clock baseline")
        project.sampleRate = 48000
        project.tempoMap = TempoMap(events: [TempoEvent(beat: 0, bpm: 37)])
    }
    try ProjectStore.save(project, to: destination)
    let loaded = try ProjectStore.load(from: destination)
    try require(loaded == project, "Saved project differs from API result")
    let inspection = try CPRSourceAudioInspection.inspect(eventID: anchor, in: loaded, at: destination)
    if name.hasPrefix("Unknown") {
        try require(inspection.nativeTrackPlaybackUnavailableReason != nil && inspection.nativeTrackEventCount == nil,
                    "Unknown contributor incorrectly admitted")
    } else {
        try require(inspection.nativeTrackPlaybackUnavailableReason == nil && inspection.nativeTrackEventCount == count,
                    "Complete control track was not admitted")
    }
    try require(try digest(destination.appendingPathComponent(CPRProject.originalRelativePath)) == sourceSHA,
                "Preserved source changed")
    results.append([
        "package": name,
        "source": relativeSource,
        "source_sha256": sourceSHA,
        "retained_events": count,
        "anchor_id": anchor.uuidString,
        "media_attachments": loaded.cprMediaAttachments.count,
        "current_sample_rate": loaded.sampleRate,
        "current_tempo": loaded.tempo,
        "current_native_clock": loaded.tempoMap.nativeClock != nil,
        "clock_edit": editClock ? "sampleRate 32000 to 48000; replace current TempoMap with detached 37 BPM" : "none",
        "complete_track_events": inspection.nativeTrackEventCount as Any? ?? NSNull(),
        "complete_track_unavailable_reason": inspection.nativeTrackPlaybackUnavailableReason as Any? ?? NSNull()
    ])
}
let record: [String: Any] = [
    "status": "prepared through existing compiled public application APIs",
    "target_executed": false,
    "gui_import_observed": false,
    "native_validity_established": false,
    "packages": results
]
let data = try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data("\n".utf8))
