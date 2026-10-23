import AppKit
import AVFoundation
import Combine
import RebaseCore
import UniformTypeIdentifiers

@MainActor
final class StudioSession: ObservableObject {
    @Published var project = Project()
    @Published var selectedClipID: UUID?
    @Published var selectedTrackID: UUID?
    @Published var playhead = 0.0
    @Published var isPlaying = false
    @Published var outputPeaks: [Float] = [0, 0]
    @Published var isDirty = false
    @Published var snapMode: SnapMode = .off
    @Published var gridRelative = false
    @Published var musicalRuler = true
    @Published var showTempoEditor = false
    @Published var showAutomationEditor = false
    @Published var cprImportPreview: CPRImportPreview?
    @Published private(set) var cprCompatibility: CPRInspection?
    @Published var status = "Ready"
    @Published var errorMessage: String?
    @Published var waveformPeaks: [UUID: [Float]] = [:]
    @Published private var undoStack: [Project] = []
    @Published private var redoStack: [Project] = []
    private var projectRoot: URL!
    private var isScratch = true
    private let engine = AudioTransportEngine()
    private var timer: Timer?
    private var refreshTask: DispatchWorkItem?
    private var lastEditKey: String?
    private var lastEditTime = Date.distantPast

    var canUndo: Bool { !undoStack.isEmpty }
    var canRedo: Bool { !redoStack.isEmpty }
    var selectedTrack: Track? { project.tracks.first { $0.id == selectedTrackID } }
    var selectedClip: Clip? { project.tracks.flatMap(\.clips).first { $0.id == selectedClipID } }

    init() {
        newProject()
        let args = ProcessInfo.processInfo.arguments
        if let i = args.firstIndex(of: "--project"), args.indices.contains(i + 1) {
            do { try load(URL(fileURLWithPath: args[i + 1])) } catch { show(error) }
        }
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.isPlaying else { return }
                self.playhead = min(self.project.duration, self.engine.currentTime)
                self.outputPeaks = self.engine.outputPeaks
                if !self.engine.isPlaying || self.playhead >= self.project.duration {
                    self.engine.stop()
                    self.isPlaying = false
                    self.outputPeaks = [0, 0]
                    self.status = "Stopped"
                }
            }
        }
    }

    func newProject() {
        guard confirmProjectReplacement() else { return }
        stop()
        do {
            let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            let root = support.appendingPathComponent("Rebase/Sessions/\(UUID().uuidString).rebaseproj", isDirectory: true)
            project = try ProjectStore.create(at: root, name: "Untitled")
            projectRoot = root
            isScratch = true
            isDirty = false
            cprCompatibility = nil
            selectedClipID = nil; selectedTrackID = nil
            waveformPeaks = [:]; undoStack = []; redoStack = []
            status = "Ready — import audio to begin"
        } catch { show(error) }
    }

    func openProject() {
        let panel = NSOpenPanel()
        panel.title = "Open Rebase Project"
        panel.canChooseDirectories = true
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        if url.pathExtension.lowercased() == "cpr" { inspectCPRProject(url); return }
        do { try load(url) } catch { show(error) }
    }
    func openURL(_ url: URL) {
        if url.pathExtension.lowercased() == "cpr" { inspectCPRProject(url); return }
        do { try load(url) } catch { show(error) }
    }

    private func load(_ url: URL) throws {
        let root = url.lastPathComponent == "Project.json" ? url.deletingLastPathComponent() : url
        guard confirmProjectReplacement() else { return }
        let loaded = try ProjectStore.load(from: root)
        let compatibility = try CPRProject.compatibilityReport(from: root)
        stop()
        project = loaded; projectRoot = root
        cprCompatibility = compatibility
        isScratch = false; isDirty = false
        undoStack = []; redoStack = []; waveformPeaks = [:]
        selectedTrackID = loaded.tracks.first?.id
        selectedClipID = loaded.tracks.first?.clips.first?.id
        rebuildWaveforms()
        status = "Opened \(loaded.name)"
    }

    @discardableResult
    func saveProject() -> Bool {
        guard projectRoot != nil else { return false }
        if isScratch { return saveProjectAs() }
        do {
            try ProjectStore.save(project, to: projectRoot)
            isDirty = false; status = "Saved \(project.name)"; return true
        } catch { show(error); return false }
    }

    @discardableResult
    func saveProjectAs() -> Bool {
        guard projectRoot != nil else { return false }
        let panel = NSSavePanel()
        panel.title = "Save Rebase Project"
        panel.nameFieldStringValue = project.name + ".rebaseproj"
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, var destination = panel.url else { return false }
        if destination.pathExtension != "rebaseproj" { destination.appendPathExtension("rebaseproj") }
        destination = destination.standardizedFileURL.resolvingSymlinksInPath()
        let original = projectRoot.standardizedFileURL.resolvingSymlinksInPath()
        var createdDestination = false
        do {
            if destination != original {
                guard !FileManager.default.fileExists(atPath: destination.path) else {
                    throw SessionError.message("A project already exists at this location. Choose a new name to preserve it.")
                }
                guard !destination.path.hasPrefix(original.path + "/") else {
                    throw SessionError.message("Save the new project outside the current project package.")
                }
                try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: false,
                                                        attributes: [.posixPermissions: 0o700])
                createdDestination = true
                for child in try FileManager.default.contentsOfDirectory(at: original, includingPropertiesForKeys: nil) {
                    guard child.lastPathComponent != ProjectStore.manifestName else { continue }
                    try FileManager.default.copyItem(at: child, to: destination.appendingPathComponent(child.lastPathComponent))
                }
            }
            var saved = project
            saved.name = destination.deletingPathExtension().lastPathComponent
            try ProjectStore.save(saved, to: destination)
            project = saved; projectRoot = destination
            isScratch = false; isDirty = false; status = "Saved \(project.name)"
            return true
        } catch {
            if createdDestination { try? FileManager.default.removeItem(at: destination) }
            show(error); return false
        }
    }

    func confirmProjectReplacement() -> Bool {
        guard isDirty else { return true }
        let alert = NSAlert()
        alert.messageText = "Save changes to \(project.name)?"
        alert.informativeText = "Save your edits before closing this project."
        alert.addButton(withTitle: "Save")
        alert.addButton(withTitle: "Keep Editing")
        alert.addButton(withTitle: "Discard Changes")
        switch alert.runModal() {
        case .alertFirstButtonReturn: return saveProject()
        case .alertThirdButtonReturn: return true
        default: return false
        }
    }

    func importAudio() {
        let panel = NSOpenPanel()
        panel.title = "Import Audio"
        panel.allowedContentTypes = [.audio]
        panel.allowsMultipleSelection = true
        guard panel.runModal() == .OK else { return }
        importURLs(panel.urls)
    }

    func importURLs(_ urls: [URL]) {
        guard projectRoot != nil else { return }
        stopKeepingPosition()
        var successes = 0
        for url in urls {
            do {
                let imported = try ProjectStore.importAudio(from: url, into: projectRoot)
                guard imported.channelCount <= 2 else { throw SessionError.message("Timeline tracks accept mono or stereo audio. Use File → Convert Ambisonics for 4-, 9-, or 16-channel conversion.") }
                let clip = Clip(mediaPath: imported.mediaPath, name: imported.name, position: try snappedTime(playhead), sourceOffset: 0, duration: imported.duration)
                let track = Track(name: imported.name, clips: [clip])
                var candidate = project
                candidate.tracks.append(track)
                try candidate.validate()
                remember(); project = candidate
                selectedTrackID = track.id; selectedClipID = clip.id
                waveformPeaks[clip.id] = peaks(for: clip)
                successes += 1
            } catch { show(error) }
        }
        if successes > 0 { changed(); status = "Imported \(successes) audio \(successes == 1 ? "file" : "files")" }
    }

    func selectClip(_ id: UUID?) {
        selectedClipID = id
        if let id, let t = project.tracks.first(where: { $0.clips.contains { $0.id == id } }) { selectedTrackID = t.id }
    }
    func selectTrack(_ id: UUID) {
        selectedTrackID = id
        guard let track = selectedTrack else { selectedClipID = nil; return }
        if !track.clips.contains(where: { $0.id == selectedClipID }) { selectedClipID = track.clips.first?.id }
    }
    private func reconcileSelection() {
        if !project.tracks.contains(where: { $0.id == selectedTrackID }) { selectedTrackID = project.tracks.first?.id }
        if let id = selectedTrackID { selectTrack(id) } else { selectedClipID = nil }
    }

    func togglePlayback() {
        if isPlaying { stopKeepingPosition(); return }
        guard project.duration > 0, projectRoot != nil else { status = "Import audio before playback"; return }
        do {
            refreshTask?.cancel()
            if playhead >= project.duration { playhead = 0 }
            try engine.configure(project: project, projectRoot: projectRoot)
            try engine.play(from: playhead)
            isPlaying = true; status = "Playing"
        } catch { show(error); isPlaying = false }
    }

    func stop() { refreshTask?.cancel(); engine.stop(); isPlaying = false; outputPeaks = [0, 0]; playhead = 0; status = "Stopped" }
    func returnToStart() {
        let resume = isPlaying
        stop()
        if resume { togglePlayback() }
    }
    private func stopKeepingPosition() {
        if isPlaying { playhead = min(project.duration, engine.currentTime) }
        engine.stop(); isPlaying = false; outputPeaks = [0, 0]; status = "Paused"
    }
    func seek(_ seconds: Double) {
        let resume = isPlaying
        stopKeepingPosition()
        playhead = max(0, seconds)
        if resume { togglePlayback() }
    }

    func moveClip(_ id: UUID, to position: Double) {
        guard let clip = project.tracks.flatMap(\.clips).first(where: { $0.id == id }) else { return }
        do {
            let time = try snappedTime(max(0, position), relativeTo: gridRelative ? clip.position : nil)
            let beat = clip.timeBase == .musical ? try project.tempoMap.beat(atSeconds: time) : nil
            editClip(id) { $0.position = time; $0.musicalPosition = beat }
        } catch { show(error) }
    }
    func trimClip(_ id: UUID, duration: Double) {
        guard let clip = project.tracks.flatMap(\.clips).first(where: { $0.id == id }) else { return }
        do {
            let file = try AVAudioFile(forReading: projectRoot.appendingPathComponent(clip.mediaPath))
            let remaining = Double(file.length) / file.processingFormat.sampleRate - clip.sourceOffset
            let snappedEnd = try snappedTime(max(clip.position, clip.position + duration))
            editClip(id) { $0.duration = min(remaining, max(1 / project.sampleRate, snappedEnd - clip.position)) }
            if let updated = selectedClip, updated.id == id { waveformPeaks[id] = peaks(for: updated) }
        } catch { show(error) }
    }
    func splitSelected() {
        guard let id = selectedClipID else { return }
        for t in project.tracks.indices {
            guard let c = project.tracks[t].clips.firstIndex(where: { $0.id == id }) else { continue }
            let old = project.tracks[t].clips[c]
            let offset = playhead - old.position
            guard offset > 1 / project.sampleRate, offset < old.duration - 1 / project.sampleRate else {
                status = "Place the playhead inside the selected clip to split"; return
            }
            remember()
            var right = old; right.id = UUID(); right.position = playhead; right.sourceOffset += offset; right.duration -= offset
            if right.timeBase == .musical { right.musicalPosition = try? project.tempoMap.beat(atSeconds: playhead) }
            project.tracks[t].clips[c].duration = offset
            project.tracks[t].clips.insert(right, at: c + 1)
            waveformPeaks[id] = peaks(for: project.tracks[t].clips[c]); waveformPeaks[right.id] = peaks(for: right)
            selectedClipID = right.id
            changed(); return
        }
    }
    func deleteSelected() {
        guard let id = selectedClipID else { return }
        remember()
        for i in project.tracks.indices { project.tracks[i].clips.removeAll { $0.id == id } }
        waveformPeaks[id] = nil; selectedClipID = nil; changed()
    }
    private func editClip(_ id: UUID, _ edit: (inout Clip) -> Void) {
        for t in project.tracks.indices {
            guard let c = project.tracks[t].clips.firstIndex(where: { $0.id == id }) else { continue }
            var candidate = project
            edit(&candidate.tracks[t].clips[c])
            do { try candidate.validate(); remember(); project = candidate; changed() }
            catch { show(error) }
            return
        }
    }
    private func editTrack(_ id: UUID, kind: String? = nil, _ edit: (inout Track) -> Void) {
        guard let t = project.tracks.firstIndex(where: { $0.id == id }) else { return }
        var candidate = project
        edit(&candidate.tracks[t])
        do { try candidate.validate(); remember(key: kind.map { "\($0):\(id)" }); project = candidate; changed() }
        catch { show(error) }
    }
    func setGain(_ id: UUID, _ value: Double) { editTrack(id, kind: "gain") { $0.gainDB = min(24, max(-96, value)) } }
    func setPan(_ id: UUID, _ value: Double) { editTrack(id, kind: "pan") { $0.pan = min(1, max(-1, value)) } }
    func toggleMute(_ id: UUID) { editTrack(id) { $0.isMuted.toggle() } }
    func toggleSolo(_ id: UUID) { editTrack(id) { $0.isSolo.toggle() } }
    func setTempo(_ value: Double) {
        guard value.isFinite, (20...400).contains(value) else { return }
        var map = project.tempoMap
        map.events[0].bpm = value
        updateTempoMap(map)
    }

    func applyMusicalMaps(tempo: TempoMap, signatures: SignatureMap) {
        do {
            var candidate = project
            candidate.signatureMap = signatures
            try candidate.replaceTempoMap(tempo)
            remember(); project = candidate; changed()
        } catch { show(error) }
    }
    func applyAutomation(_ trackID: UUID, lanes: [AutomationLane]) {
        do {
            for lane in lanes { try lane.validate() }
            editTrack(trackID) { $0.automation = lanes }
        } catch { show(error) }
    }
    func updateTempoMap(_ map: TempoMap) {
        do {
            var candidate = project
            try candidate.replaceTempoMap(map)
            remember(); project = candidate; changed()
        } catch { show(error) }
    }
    func updateSignatureMap(_ map: SignatureMap) {
        do {
            try map.validate()
            remember(); project.signatureMap = map; changed()
        } catch { show(error) }
    }
    func setTrackTimeBase(_ id: UUID, _ base: ClipTimeBase) {
        guard let index = project.tracks.firstIndex(where: { $0.id == id }) else { return }
        do {
            var candidate = project
            candidate.tracks[index].timeBase = base
            for c in candidate.tracks[index].clips.indices {
                let time = candidate.tracks[index].clips[c].position
                candidate.tracks[index].clips[c].timeBase = base
                candidate.tracks[index].clips[c].musicalPosition = base == .musical ? try project.tempoMap.beat(atSeconds: time) : nil
            }
            try candidate.validate()
            remember(); project = candidate; changed()
        } catch { show(error) }
    }
    func setAutomation(_ trackID: UUID, lane: AutomationLane) {
        do {
            try lane.validate()
            editTrack(trackID) { track in
                if let i = track.automation.firstIndex(where: { $0.parameter == lane.parameter }) { track.automation[i] = lane }
                else { track.automation.append(lane) }
            }
        } catch { show(error) }
    }
    func snappedTime(_ seconds: Double, relativeTo origin: Double? = nil) throws -> Double {
        guard let grid = snapMode.grid else { return seconds }
        let beat = try project.tempoMap.beat(atSeconds: seconds)
        let relative = try origin.map { try project.tempoMap.beat(atSeconds: $0) }
        let snapped = try grid.snappedBeat(beat, signatures: project.signatureMap, relativeTo: relative)
        return try project.tempoMap.seconds(atBeat: snapped)
    }
    var musicalPositionText: String {
        guard let beat = try? project.tempoMap.beat(atSeconds: playhead),
              let p = try? project.signatureMap.position(atBeat: beat) else { return "—" }
        return "\(p.bar).\(p.beat).\(p.sixteenth).\(p.tick)"
    }
    func importDAWProject() {
        let panel = NSOpenPanel()
        panel.title = "Import DAWproject"
        panel.allowedContentTypes = [UTType(filenameExtension: "dawproject") ?? .data]
        guard panel.runModal() == .OK, let source = panel.url else { return }
        guard confirmProjectReplacement() else { return }
        let destination = NSSavePanel()
        destination.title = "Save Imported Project"
        destination.nameFieldStringValue = source.deletingPathExtension().lastPathComponent + ".rebaseproj"
        guard destination.runModal() == .OK, var root = destination.url else { return }
        if root.pathExtension != "rebaseproj" { root.appendPathExtension("rebaseproj") }
        do {
            let loaded = try DAWProject.importProject(from: source, to: root)
            stop(); project = loaded; projectRoot = root
            cprCompatibility = nil
            isScratch = false; isDirty = false; undoStack = []; redoStack = []
            selectedTrackID = loaded.tracks.first?.id; selectedClipID = loaded.tracks.first?.clips.first?.id
            rebuildWaveforms(); status = "Imported \(source.lastPathComponent)"
        } catch { show(error) }
    }
    func exportDAWProject() {
        let panel = NSSavePanel()
        panel.title = "Export DAWproject"
        panel.nameFieldStringValue = project.name + ".dawproject"
        guard panel.runModal() == .OK, var url = panel.url else { return }
        if url.pathExtension != "dawproject" { url.appendPathExtension("dawproject") }
        do {
            try DAWProject.export(project: project, projectRoot: projectRoot, to: url)
            status = "Exported \(url.lastPathComponent)"
        } catch { show(error) }
    }

    func importCPRProject() {
        let panel = NSOpenPanel()
        panel.title = "Import Cubase Project"
        panel.allowedContentTypes = [UTType(filenameExtension: "cpr") ?? .data]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let source = panel.url else { return }
        inspectCPRProject(source)
    }

    private func inspectCPRProject(_ source: URL) {
        do {
            let report = try CPRProject.inspect(from: source)
            cprImportPreview = cprPreview(report, source: source)
        } catch { show(error) }
    }

    func showCPRCompatibility() {
        guard let projectRoot else { return }
        do {
            guard let report = try CPRProject.compatibilityReport(from: projectRoot) else { return }
            cprCompatibility = report
            cprImportPreview = cprPreview(report,
                source: projectRoot.appendingPathComponent(CPRProject.originalRelativePath), historical: true)
        } catch { show(error) }
    }

    private func cprPreview(_ report: CPRInspection, source: URL, historical: Bool = false) -> CPRImportPreview {
        CPRImportPreview(source: source, sourceName: report.sourceName, sourceSHA256: report.sourceSHA256,
            byteCount: report.sourceByteCount, recovered: report.recoveredFacts, metadata: report.metadataFacts,
            tracks: report.recoveredTracks.map {
                CPRPreviewFact(label: $0.name, value: $0.kind + ($0.importedTrackID == nil ? " · not restored" : " · empty track restored"))
            }, unresolved: report.unsupported.map { "\($0.category): \($0.detail)" },
            defaults: report.applicationDefaults, canImport: report.canImport && !historical,
            recoveryDescription: historical
                ? "Supported data recovered from \(report.sourceName). This is a partial import."
                : "Review the data Rebase can restore from this file. Native Cubase features listed below remain in the preserved source.",
            isImportReport: historical)
    }

    func confirmCPRImport(_ preview: CPRImportPreview) {
        guard preview.canImport, !preview.isImportReport else { return }
        cprImportPreview = nil
        // Let the SwiftUI sheet close before presenting native file panels.
        DispatchQueue.main.async { [weak self] in self?.performCPRImport(preview) }
    }

    private func performCPRImport(_ preview: CPRImportPreview) {
        guard confirmProjectReplacement() else { return }
        let panel = NSSavePanel()
        panel.title = "Save Imported Cubase Project"
        panel.nameFieldStringValue = preview.source.deletingPathExtension().lastPathComponent + ".rebaseproj"
        guard panel.runModal() == .OK, var root = panel.url else { return }
        if root.pathExtension != "rebaseproj" { root.appendPathExtension("rebaseproj") }
        do {
            let result = try CPRProject.importProject(from: preview.source, to: root,
                allowPartial: true, expectedSHA256: preview.sourceSHA256)
            stop(); project = result.project; projectRoot = root
            cprCompatibility = result.report
            isScratch = false; isDirty = false; undoStack = []; redoStack = []; waveformPeaks = [:]
            selectedTrackID = project.tracks.first?.id
            selectedClipID = project.tracks.first?.clips.first?.id
            rebuildWaveforms()
            status = "Imported supported data from \(preview.source.lastPathComponent)"
        } catch { show(error) }
    }

    private func remember(key: String? = nil) {
        let now = Date()
        if let key, key == lastEditKey, now.timeIntervalSince(lastEditTime) < 0.5 {
            lastEditTime = now
            return
        }
        lastEditKey = key; lastEditTime = now
        undoStack.append(project)
        if undoStack.count > 100 { undoStack.removeFirst() }
        redoStack.removeAll()
    }
    func undo() {
        guard let previous = undoStack.popLast() else { return }
        lastEditKey = nil
        redoStack.append(project); project = previous; reconcileSelection(); rebuildWaveforms(); changed()
    }
    func redo() {
        guard let next = redoStack.popLast() else { return }
        lastEditKey = nil
        undoStack.append(project); project = next; reconcileSelection(); rebuildWaveforms(); changed()
    }
    private func changed() {
        isDirty = true
        // Scratch sessions retain a recovery copy. Named projects change on Save.
        if isScratch {
            do { try ProjectStore.save(project, to: projectRoot) } catch { show(error) }
        }
        guard isPlaying else { return }
        refreshTask?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.isPlaying else { return }
            self.stopKeepingPosition()
            self.togglePlayback()
        }
        refreshTask = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.16, execute: work)
    }

    func exportMix() {
        guard project.duration > 0 else { status = "Import audio before export"; return }
        let panel = NSSavePanel()
        panel.title = "Export Stereo Mixdown"
        panel.allowedContentTypes = [.wav]
        panel.nameFieldStringValue = project.name + ".wav"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        stopKeepingPosition()
        do {
            _ = try OfflineRenderer.export(project: project, projectRoot: projectRoot, to: url)
            status = "Exported \(url.lastPathComponent)"
            NSWorkspace.shared.activateFileViewerSelecting([url])
        } catch { show(error) }
    }

    private func rebuildWaveforms() {
        waveformPeaks = [:]
        for clip in project.tracks.flatMap(\.clips) { waveformPeaks[clip.id] = peaks(for: clip) }
    }
    private func peaks(for clip: Clip) -> [Float] {
        do {
            let file = try AVAudioFile(forReading: projectRoot.appendingPathComponent(clip.mediaPath))
            let rate = file.processingFormat.sampleRate
            let sourceFrame = clip.sourceOffset * rate
            let durationFrames = clip.duration * rate
            guard sourceFrame.isFinite, durationFrames.isFinite, sourceFrame >= 0,
                  sourceFrame < Double(file.length), sourceFrame < Double(Int64.max),
                  durationFrames > 0 else { return [] }
            let start = AVAudioFramePosition(sourceFrame)
            let boundedFrames = min(Double(file.length - start), durationFrames)
            guard boundedFrames < Double(Int64.max) else { return [] }
            let count = AVAudioFramePosition(boundedFrames)
            guard count > 0 else { return [] }
            file.framePosition = start
            guard let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: 16384) else { return [] }
            let bins = min(1600, Int(count))
            var peaks = [Float](repeating: 0, count: bins)
            var position: AVAudioFramePosition = 0
            while position < count {
                try file.read(into: buffer, frameCount: AVAudioFrameCount(min(16384, count - position)))
                guard buffer.frameLength > 0, let channels = buffer.floatChannelData else { break }
                for f in 0..<Int(buffer.frameLength) {
                    let bin = min(bins - 1, Int((position + Int64(f)) * Int64(bins) / count))
                    for c in 0..<Int(buffer.format.channelCount) { peaks[bin] = max(peaks[bin], abs(channels[c][f])) }
                }
                position += AVAudioFramePosition(buffer.frameLength)
            }
            return peaks
        } catch { return [] }
    }
    private func show(_ error: Error) { errorMessage = error.localizedDescription; status = "Action could not be completed" }
}

enum SessionError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
}

enum SnapMode: String, CaseIterable, Identifiable {
    case off = "Off", bar = "Bar", beat = "Beat", eighth = "1/8", sixteenth = "1/16"
    var id: String { rawValue }
    var grid: GridSnap? {
        switch self {
        case .off: return nil
        case .bar: return .bar
        case .beat: return .beat
        case .eighth: return .quantize(0.5)
        case .sixteenth: return .quantize(0.25)
        }
    }
}
