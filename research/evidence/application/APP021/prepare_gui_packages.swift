import Foundation
import CryptoKit
import RebaseCore

// Input preparation using frozen compiled public APIs. This is neither a GUI
// import observation nor proof of native-valid project restoration/playback.
func require(_ condition: Bool, _ message: String) throws {
    if !condition { throw NSError(domain: "APP021.GUIInputHelper", code: 1,
        userInfo: [NSLocalizedDescriptionKey: message]) }
}
func digest(_ url: URL) throws -> String {
    SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined()
}
try require(CommandLine.arguments.count == 2, "Expected absolute workspace path")
let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true).standardizedFileURL
let here = root.appendingPathComponent("research/evidence/application/APP021", isDirectory: true)
let controls = here.appendingPathComponent("overlap-controls-01", isDirectory: true)

func pin(_ file: URL) throws -> [String: Any] {
    let prefix = root.path + "/"
    try require(file.path.hasPrefix(prefix), "File outside workspace")
    let values = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
    try require(values.isRegularFile == true && values.isSymbolicLink != true, "Expected regular file")
    return ["path": String(file.path.dropFirst(prefix.count)),
            "bytes": values.fileSize ?? 0, "sha256": try digest(file)]
}
func packagePins(_ folder: URL) throws -> [[String: Any]] {
    guard let enumerator = FileManager.default.enumerator(at: folder,
        includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey], options: []) else {
        throw NSError(domain: "APP021.GUIInputHelper", code: 2)
    }
    var files: [URL] = []
    for case let file as URL in enumerator {
        let values = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
        try require(values.isSymbolicLink != true, "Unexpected package symlink")
        if values.isRegularFile == true { files.append(file) }
    }
    return try files.sorted { $0.path < $1.path }.map(pin)
}

let mediaHashes = [
    "0f22730ee27f5803ceefdefe014fa72b0220d2aee98d223873ae8e64c6c30f07",
    "6eada8973e183f835b98413e28d60f729eaa95894b7476e3abb927ca8b915b78"
]
// destination, control, source hash, expected fragments, edited current clock
let requests: [(String, String, String, Int, Bool)] = [
    ("Nested Overlap QA.rebaseproj", "nested-tail.cpr",
     "4a920c2593392db3b660ea040960eac2ea0b7602d76e7a4fcd04cc65a4d49620", 3, false),
    ("Covered Anchor QA.rebaseproj", "covered-anchor.cpr",
     "2e6db952d129270a179e722c1a5b3d20ed2332c763801c0ce7ff27702ed11255", 1, false),
    ("Signed Priority QA.rebaseproj", "signed-earlier-wins.cpr",
     "eef15826335a29280e894688b6252f5fa93862491a7d43b5da176522ee59ab85", 2, false),
    ("Saved32 Overlap QA.rebaseproj", "saved32k-original-offset.cpr",
     "4b3037f7084ed3769732523baab3e28e89af3f8d6107fafc990d2a3a7f0132fd", 3, true)
]
// Validate every destination and fixed input before creating any package.
for request in requests {
    try require(!FileManager.default.fileExists(atPath: here.appendingPathComponent(request.0).path),
                "Refusing existing package: \(request.0)")
    try require(try digest(controls.appendingPathComponent(request.1)) == request.2,
                "Source identity changed: \(request.1)")
}
for (ordinal, hash) in mediaHashes.enumerated() {
    try require(try digest(controls.appendingPathComponent("Overlap Signal \(ordinal).wav")) == hash,
                "Media identity changed: \(ordinal)")
}

var results: [[String: Any]] = []
for (name, sourceName, sourceSHA, fragmentCount, editClock) in requests {
    let source = controls.appendingPathComponent(sourceName)
    let destination = here.appendingPathComponent(name, isDirectory: true)
    var project = try CPRProject.importProject(from: source, to: destination, allowPartial: true).project
    let events = project.unresolvedAudioEvents
    try require(events.count == 2, "Unexpected contributor count: \(name)")
    guard let anchor = events.first?.id else { throw NSError(domain: "APP021.GUIInputHelper", code: 3) }
    for (ordinal, event) in events.enumerated() {
        project = try ProjectStore.attachCPRAudioMedia(
            from: controls.appendingPathComponent("Overlap Signal \(ordinal).wav"),
            to: event.id, in: project, at: destination)
    }
    try require(project.cprMediaAttachments.count == 2, "Each contributor needs a distinct media binding")
    if editClock {
        try require(project.sampleRate == 32000 && project.tempo == 120, "Unexpected saved-clock baseline")
        project.sampleRate = 48000
        project.tempoMap = TempoMap(events: [TempoEvent(beat: 0, bpm: 37)])
    } else {
        try require(project.sampleRate == 44100 && project.tempo == 120, "Unexpected unchanged current clock")
    }
    try ProjectStore.save(project, to: destination)
    let loaded = try ProjectStore.load(from: destination)
    try require(loaded == project, "Saved package differs from API result")
    let inspection = try CPRSourceAudioInspection.inspect(eventID: anchor, in: loaded, at: destination)
    try require(inspection.nativeTrackPlaybackUnavailableReason == nil
        && inspection.nativeTrackEventCount == 2 && inspection.nativeTrackFragmentCount == fragmentCount
        && inspection.nativeTrackSnappedEmptyFragmentCount == 0, "Unexpected complete-track admission")
    guard let saved = inspection.savedProjectAudioSetup else { throw NSError(domain: "APP021.GUIInputHelper", code: 4) }
    try require(try saved.supportedSampleRate() == (editClock ? 32000 : 44100), "Saved source clock changed")
    try require(try digest(destination.appendingPathComponent(CPRProject.originalRelativePath)) == sourceSHA,
                "Preserved project source changed")
    let files = try packagePins(destination)
    try require(files.count == 5, "Expected project, report, original and two independent media files")
    results.append([
        "package": name, "source": try pin(source), "files": files,
        "retained_events": events.count, "anchor_id": anchor.uuidString,
        "event_ids": events.map { $0.id.uuidString }, "event_identities": events.map { $0.event.identityOffset },
        "media_attachments": loaded.cprMediaAttachments.count,
        "current_sample_rate": loaded.sampleRate, "current_tempo": loaded.tempo,
        "current_native_clock": loaded.tempoMap.nativeClock != nil,
        "saved_sample_rate": try saved.supportedSampleRate(),
        "clock_edit": editClock ? "Current32000 to48000; replace current TempoMap with detached37BPM" : "none",
        "complete_track_events": inspection.nativeTrackEventCount as Any? ?? NSNull(),
        "complete_track_fragments": inspection.nativeTrackFragmentCount as Any? ?? NSNull(),
        "snapped_empty_fragments": inspection.nativeTrackSnappedEmptyFragmentCount as Any? ?? NSNull(),
        "complete_track_unavailable_reason": inspection.nativeTrackPlaybackUnavailableReason as Any? ?? NSNull()
    ])
}
let record: [String: Any] = [
    "status": "prepared through existing compiled public application APIs",
    "target_executed": false, "gui_import_observed": false, "native_validity_established": false,
    "transport_started": false,
    "scope": "Preparation and read-only inspection of synthetic overlap packages; subsequent GUI evidence is separate.",
    "packages": results
]
FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys]))
FileHandle.standardOutput.write(Data("\n".utf8))
