import Foundation

/// Document edits contain values, never dialogs, file access, or device calls.
/// Snapping and source-duration inspection supply explicit context to the edit.
public enum ProjectEdit {
    case moveClip(UUID, position: Double)
    case trimClip(UUID, end: Double, availableSourceDuration: Double)
    case splitClip(UUID, at: Double, newClipID: UUID)
    case deleteEvent(UUID)
    case setGain(UUID, Double)
    case setPan(UUID, Double)
    case toggleMute(UUID)
    case toggleSolo(UUID)
    case replaceTempoMap(TempoMap)
    case replaceSignatureMap(SignatureMap)
    case applyMusicalMaps(TempoMap, SignatureMap, convertNativeTiming: Bool)
    case setTrackTimeBase(UUID, ClipTimeBase)
    case replaceAutomation(UUID, [AutomationLane])
    case setAutomation(UUID, AutomationLane)

    var coalescingKey: String? {
        switch self {
        case .setGain(let id, _): return "gain:\(id)"
        case .setPan(let id, _): return "pan:\(id)"
        default: return nil
        }
    }
}

public enum ProjectEditingError: LocalizedError {
    case invalidNumber
    case splitPosition
    public var errorDescription: String? {
        switch self {
        case .invalidNumber: "Edits require finite positions, durations and control values."
        case .splitPosition: "Place the playhead inside the selected clip to split"
        }
    }
}

public struct ProjectSelection: Equatable {
    public var trackID: UUID?
    public var clipID: UUID?
    public init(trackID: UUID? = nil, clipID: UUID? = nil) { self.trackID = trackID; self.clipID = clipID }

    public func selectingClip(_ id: UUID?, in project: Project) -> ProjectSelection {
        var result = self
        result.clipID = id
        if let id, let track = project.tracks.first(where: {
            $0.clips.contains { $0.id == id } || $0.unresolvedAudioEvents.contains { $0.id == id }
        }) { result.trackID = track.id }
        return result
    }

    public func selectingTrack(_ id: UUID, in project: Project) -> ProjectSelection {
        var result = self
        result.trackID = id
        guard let track = project.tracks.first(where: { $0.id == id }) else {
            result.clipID = nil
            return result
        }
        if !track.clips.contains(where: { $0.id == clipID }),
           !track.unresolvedAudioEvents.contains(where: { $0.id == clipID }) {
            result.clipID = track.clips.first?.id ?? track.unresolvedAudioEvents.first?.id
        }
        return result
    }

    public func reconciled(in project: Project) -> ProjectSelection {
        var result = self
        if !project.tracks.contains(where: { $0.id == trackID }) { result.trackID = project.tracks.first?.id }
        if let id = result.trackID { return result.selectingTrack(id, in: project) }
        result.clipID = nil
        return result
    }
}

public struct ProjectEditResult {
    public let project: Project
    public let selection: ProjectSelection
    /// Recompute these clip waveforms; an absent clip removes its cached entry.
    public let waveformClipIDs: [UUID]
}

public enum ProjectEditing {
    /// Builds and validates the complete candidate before publishing any state.
    /// A missing target, or an unchanged combined map edit, returns nil.
    public static func applying(_ edit: ProjectEdit, to project: Project,
                                selection: ProjectSelection = ProjectSelection()) throws -> ProjectEditResult? {
        var candidate = project
        var selected = selection
        var waveforms: [UUID] = []
        func clipIndex(_ id: UUID) -> (Int, Int)? {
            for t in project.tracks.indices {
                if let c = project.tracks[t].clips.firstIndex(where: { $0.id == id }) { return (t, c) }
            }
            return nil
        }
        func finite(_ values: Double...) throws {
            guard values.allSatisfy(\.isFinite) else { throw ProjectEditingError.invalidNumber }
        }
        switch edit {
        case .moveClip(let id, let position):
            guard let (t, c) = clipIndex(id) else { return nil }
            try finite(position)
            candidate.tracks[t].clips[c].position = max(0, position)
            candidate.tracks[t].clips[c].musicalPosition = candidate.tracks[t].clips[c].timeBase == .musical
                ? try project.tempoMap.beat(atSeconds: max(0, position)) : nil
        case .trimClip(let id, let end, let available):
            guard let (t, c) = clipIndex(id) else { return nil }
            try finite(end, available)
            let clip = project.tracks[t].clips[c]
            candidate.tracks[t].clips[c].duration = min(available, max(1 / project.sampleRate, end - clip.position))
            waveforms = [id]
        case .splitClip(let id, let position, let newID):
            guard let (t, c) = clipIndex(id) else { return nil }
            try finite(position)
            let old = project.tracks[t].clips[c], offset = position - old.position
            guard offset > 1 / project.sampleRate, offset < old.duration - 1 / project.sampleRate else {
                throw ProjectEditingError.splitPosition
            }
            var right = old
            right.id = newID; right.position = position; right.sourceOffset += offset; right.duration -= offset
            if right.timeBase == .musical { right.musicalPosition = try project.tempoMap.beat(atSeconds: position) }
            candidate.tracks[t].clips[c].duration = offset
            candidate.tracks[t].clips.insert(right, at: c + 1)
            selected = selection.selectingClip(newID, in: candidate)
            waveforms = [id, newID]
        case .deleteEvent(let id):
            guard project.tracks.contains(where: {
                $0.clips.contains { $0.id == id } || $0.unresolvedAudioEvents.contains { $0.id == id }
            }) else { return nil }
            for t in candidate.tracks.indices {
                candidate.tracks[t].clips.removeAll { $0.id == id }
                candidate.tracks[t].unresolvedAudioEvents.removeAll { $0.id == id }
            }
            candidate.removeUnusedCPRMediaAttachments()
            selected.clipID = nil
            waveforms = [id]
        case .setGain(let id, let value):
            guard let t = project.tracks.firstIndex(where: { $0.id == id }) else { return nil }
            try finite(value)
            candidate.tracks[t].gainDB = min(24, max(-96, value))
        case .setPan(let id, let value):
            guard let t = project.tracks.firstIndex(where: { $0.id == id }) else { return nil }
            try finite(value)
            candidate.tracks[t].pan = min(1, max(-1, value))
        case .toggleMute(let id):
            guard let t = project.tracks.firstIndex(where: { $0.id == id }) else { return nil }
            candidate.tracks[t].isMuted.toggle()
        case .toggleSolo(let id):
            guard let t = project.tracks.firstIndex(where: { $0.id == id }) else { return nil }
            candidate.tracks[t].isSolo.toggle()
        case .replaceTempoMap(let map):
            try candidate.replaceTempoMap(map)
        case .replaceSignatureMap(let map):
            candidate.signatureMap = map
        case .applyMusicalMaps(let tempo, let signatures, let convert):
            guard convert || tempo != project.tempoMap || signatures != project.signatureMap else { return nil }
            if convert { try candidate.convertToApplicationTiming() }
            candidate.signatureMap = signatures
            try candidate.replaceTempoMap(tempo)
            guard candidate != project else { return nil }
        case .setTrackTimeBase(let id, let base):
            guard let t = project.tracks.firstIndex(where: { $0.id == id }) else { return nil }
            candidate.tracks[t].timeBase = base
            for c in candidate.tracks[t].clips.indices {
                let time = candidate.tracks[t].clips[c].position
                candidate.tracks[t].clips[c].timeBase = base
                candidate.tracks[t].clips[c].musicalPosition = base == .musical ? try project.tempoMap.beat(atSeconds: time) : nil
            }
        case .replaceAutomation(let id, let lanes):
            guard let t = project.tracks.firstIndex(where: { $0.id == id }) else { return nil }
            candidate.tracks[t].automation = lanes
        case .setAutomation(let id, let lane):
            guard let t = project.tracks.firstIndex(where: { $0.id == id }) else { return nil }
            if let i = candidate.tracks[t].automation.firstIndex(where: { $0.parameter == lane.parameter }) {
                candidate.tracks[t].automation[i] = lane
            } else { candidate.tracks[t].automation.append(lane) }
        }
        try candidate.validate()
        return ProjectEditResult(project: candidate, selection: selected, waveformClipIDs: waveforms)
    }

    public static func snappedTime(_ seconds: Double, in project: Project, grid: GridSnap?,
                                   relativeTo origin: Double? = nil) throws -> Double {
        guard let grid else { return seconds }
        let beat = try project.tempoMap.beat(atSeconds: seconds)
        let relative = try origin.map { try project.tempoMap.beat(atSeconds: $0) }
        let snapped = try grid.snappedBeat(beat, signatures: project.signatureMap, relativeTo: relative)
        return try project.tempoMap.seconds(atBeat: snapped)
    }
}

/// Snapshot history shared by every host. UI notifications, media access and
/// recovery saves stay outside it. Tests supply time explicitly for coalescing.
public struct ProjectEditHistory {
    private var undoStack: [Project] = []
    private var redoStack: [Project] = []
    private var lastEditKey: String?
    private var lastEditTime = Date.distantPast
    public var canUndo: Bool { !undoStack.isEmpty }
    public var canRedo: Bool { !redoStack.isEmpty }
    public var undoCount: Int { undoStack.count }
    public var redoCount: Int { redoStack.count }
    public init() {}

    public mutating func reset() { self = ProjectEditHistory() }

    public mutating func record(_ project: Project, coalescingKey: String? = nil, at now: Date = Date()) {
        let elapsed = now.timeIntervalSince(lastEditTime)
        // A wall-clock adjustment must start a new undo group, not merge edits
        // separated by an unknown interval.
        if let key = coalescingKey, key == lastEditKey, elapsed >= 0, elapsed < 0.5 {
            lastEditTime = now
            return
        }
        lastEditKey = coalescingKey; lastEditTime = now
        undoStack.append(project)
        if undoStack.count > 100 { undoStack.removeFirst() }
        redoStack.removeAll()
    }

    public mutating func apply(_ edit: ProjectEdit, to project: Project,
                               selection: ProjectSelection = ProjectSelection(), at now: Date = Date()) throws -> ProjectEditResult? {
        guard let result = try ProjectEditing.applying(edit, to: project, selection: selection) else { return nil }
        record(project, coalescingKey: edit.coalescingKey, at: now)
        return result
    }

    public mutating func undo(current project: Project) -> Project? {
        guard let previous = undoStack.popLast() else { return nil }
        lastEditKey = nil
        redoStack.append(project)
        return previous
    }

    public mutating func redo(current project: Project) -> Project? {
        guard let next = redoStack.popLast() else { return nil }
        lastEditKey = nil
        undoStack.append(project)
        return next
    }
}
