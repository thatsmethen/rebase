import Foundation

public struct Project: Codable, Equatable, Identifiable {
    public var id: UUID
    public var name: String
    public var tempoMap: TempoMap
    public var signatureMap: SignatureMap
    public var tempo: Double { tempoMap.events.first?.bpm ?? 120 }
    public var sampleRate: Double
    public var tracks: [Track]
    public var cprMediaAttachments: [CPRAudioMediaAttachment]

    public init(id: UUID = UUID(), name: String = "Untitled", tempo: Double = 120,
                sampleRate: Double = 48_000, tracks: [Track] = [],
                tempoMap: TempoMap? = nil, signatureMap: SignatureMap = SignatureMap(),
                cprMediaAttachments: [CPRAudioMediaAttachment] = []) {
        self.id = id; self.name = name
        self.tempoMap = tempoMap ?? TempoMap(events: [TempoEvent(beat: 0, bpm: tempo)])
        self.signatureMap = signatureMap
        self.sampleRate = sampleRate; self.tracks = tracks
        self.cprMediaAttachments = cprMediaAttachments
    }

    private enum CodingKeys: String, CodingKey { case id, name, tempo, tempoMap, signatureMap, sampleRate, tracks, cprMediaAttachments }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        let legacyTempo = try c.decodeIfPresent(Double.self, forKey: .tempo) ?? 120
        tempoMap = try c.decodeIfPresent(TempoMap.self, forKey: .tempoMap)
            ?? TempoMap(events: [TempoEvent(beat: 0, bpm: legacyTempo)])
        signatureMap = try c.decodeIfPresent(SignatureMap.self, forKey: .signatureMap) ?? SignatureMap()
        sampleRate = try c.decode(Double.self, forKey: .sampleRate)
        tracks = try c.decode([Track].self, forKey: .tracks)
        cprMediaAttachments = try c.decodeIfPresent([CPRAudioMediaAttachment].self, forKey: .cprMediaAttachments) ?? []
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id); try c.encode(name, forKey: .name)
        try c.encode(tempo, forKey: .tempo); try c.encode(tempoMap, forKey: .tempoMap)
        try c.encode(signatureMap, forKey: .signatureMap)
        try c.encode(sampleRate, forKey: .sampleRate); try c.encode(tracks, forKey: .tracks)
        if !cprMediaAttachments.isEmpty { try c.encode(cprMediaAttachments, forKey: .cprMediaAttachments) }
    }

    /// Musical audio anchors follow tempo; audio lengths and source samples do not stretch.
    public mutating func replaceTempoMap(_ map: TempoMap) throws {
        if let nativeClock = tempoMap.nativeClock, map.nativeClock != nativeClock {
            throw NativeTempoClockError.conversionRequired
        }
        try map.validate()
        var candidate = self
        candidate.tempoMap = map
        for t in candidate.tracks.indices {
            for c in candidate.tracks[t].clips.indices {
                if let beat = candidate.tracks[t].clips[c].musicalPosition,
                   candidate.tracks[t].clips[c].timeBase == .musical {
                    candidate.tracks[t].clips[c].position = try map.seconds(atBeat: beat)
                }
            }
        }
        try candidate.validate()
        self = candidate
    }

    public var duration: TimeInterval {
        tracks.flatMap(\.clips).map { $0.position + $0.duration }.max() ?? 0
    }

    public var unresolvedAudioEvents: [UnresolvedCPRAudioEvent] { tracks.flatMap(\.unresolvedAudioEvents) }
    public func attachedMedia(for event: UnresolvedCPRAudioEvent) -> CPRAudioMediaAttachment? {
        guard event.files.count == 1, let file = event.files.first else { return nil }
        return cprMediaAttachments.first { $0.matches(file, sourceSHA256: event.sourceSHA256) }
    }
    public mutating func removeUnusedCPRMediaAttachments() {
        let events = unresolvedAudioEvents
        cprMediaAttachments.removeAll { attachment in
            !events.contains { event in event.files.contains { attachment.matches($0, sourceSHA256: event.sourceSHA256) } }
        }
    }
    public var arrangementDuration: TimeInterval {
        max(duration, unresolvedAudioEvents.compactMap { $0.placement.map { $0.position + $0.duration } }.max() ?? 0)
    }

    public func requireResolvedAudioEvents() throws {
        guard unresolvedAudioEvents.isEmpty else {
            throw RebaseCoreError.invalidProject("This project contains unresolved Reference audio events. Native playback processing has not been reconstructed, even when media is attached. Remove those events explicitly before playback or export; the original CPR stays preserved.")
        }
    }

    public func validate() throws {
        try tempoMap.validate()
        try signatureMap.validate()
        guard tempo.isFinite, (20...400).contains(tempo), sampleRate.isFinite,
              (8_000...192_000).contains(sampleRate) else {
            throw RebaseCoreError.invalidProject("Tempo must be 20–400 BPM and sample rate 8–192 kHz.")
        }
        guard Set(tracks.map(\.id)).count == tracks.count else {
            throw RebaseCoreError.invalidProject("Track identifiers must be unique.")
        }
        let clips = tracks.flatMap(\.clips)
        let allEventIDs = clips.map(\.id) + unresolvedAudioEvents.map(\.id)
        guard Set(allEventIDs).count == allEventIDs.count else {
            throw RebaseCoreError.invalidProject("Clip identifiers must be unique.")
        }
        for event in unresolvedAudioEvents { try event.validate() }
        guard Set(cprMediaAttachments.map(\.id)).count == cprMediaAttachments.count,
              Set(cprMediaAttachments.map { $0.sourceSHA256 + ":" + String($0.sourceFileIdentity) }).count == cprMediaAttachments.count else {
            throw RebaseCoreError.invalidProject("Each CPR media reference can have one attachment, with a unique identifier.")
        }
        for attachment in cprMediaAttachments {
            guard let reference = unresolvedAudioEvents.first(where: { event in
                event.files.contains { attachment.matches($0, sourceSHA256: event.sourceSHA256) }
            })?.files.first(where: { $0.object.identityOffset == attachment.sourceFileIdentity }) else {
                throw RebaseCoreError.invalidProject("A CPR media attachment has no retained source event.")
            }
            try attachment.validate(reference: reference)
        }
        for track in tracks {
            guard Set(track.automation.map(\.parameter)).count == track.automation.count,
                  Set(track.automation.map(\.id)).count == track.automation.count else {
                throw RebaseCoreError.invalidProject("Each track can have one automation lane per parameter, with unique identifiers.")
            }
            for lane in track.automation { try lane.validate() }
            guard track.gainDB.isFinite, (-96...24).contains(track.gainDB),
                  track.pan.isFinite, (-1...1).contains(track.pan) else {
                throw RebaseCoreError.invalidProject("Track gain must be −96…24 dB and pan −1…1.")
            }
            for clip in track.clips {
                guard clip.timeBase == track.timeBase else {
                    throw RebaseCoreError.invalidProject("All clips on a track must use that track's time base.")
                }
                if clip.timeBase == .musical {
                    guard let beat = clip.musicalPosition, beat.isFinite, beat >= 0,
                          abs(try tempoMap.seconds(atBeat: beat) - clip.position) <= 1e-8 else {
                        throw RebaseCoreError.invalidProject("Musical clip anchors must match their tempo-map position.")
                    }
                } else if clip.musicalPosition != nil {
                    throw RebaseCoreError.invalidProject("Seconds-based clips cannot carry a musical anchor.")
                }
                guard clip.position.isFinite, clip.sourceOffset.isFinite, clip.duration.isFinite,
                      clip.position >= 0, clip.sourceOffset >= 0, clip.duration > 0,
                      (clip.sourceOffset + clip.duration).isFinite,
                      clip.position + clip.duration <= 86_400 else {
                    throw RebaseCoreError.invalidProject("Clips need a positive duration and valid positions within 24 hours.")
                }
            }
        }
    }
}

public struct Track: Codable, Equatable, Identifiable {
    public var id: UUID
    public var name: String
    public var gainDB: Double
    public var pan: Double
    public var isMuted: Bool
    public var isSolo: Bool
    public var clips: [Clip]
    public var unresolvedAudioEvents: [UnresolvedCPRAudioEvent]
    public var automation: [AutomationLane]
    public var timeBase: ClipTimeBase

    public init(id: UUID = UUID(), name: String, gainDB: Double = 0, pan: Double = 0,
                isMuted: Bool = false, isSolo: Bool = false, clips: [Clip] = [], automation: [AutomationLane] = [], timeBase: ClipTimeBase = .seconds,
                unresolvedAudioEvents: [UnresolvedCPRAudioEvent] = []) {
        self.id = id; self.name = name; self.gainDB = gainDB; self.pan = pan
        self.isMuted = isMuted; self.isSolo = isSolo; self.clips = clips; self.automation = automation; self.timeBase = timeBase
        self.unresolvedAudioEvents = unresolvedAudioEvents
    }
    private enum CodingKeys: String, CodingKey { case id, name, gainDB, pan, isMuted, isSolo, clips, automation, timeBase, unresolvedAudioEvents }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id); name = try c.decode(String.self, forKey: .name)
        gainDB = try c.decode(Double.self, forKey: .gainDB); pan = try c.decode(Double.self, forKey: .pan)
        isMuted = try c.decode(Bool.self, forKey: .isMuted); isSolo = try c.decode(Bool.self, forKey: .isSolo)
        clips = try c.decode([Clip].self, forKey: .clips)
        unresolvedAudioEvents = try c.decodeIfPresent([UnresolvedCPRAudioEvent].self, forKey: .unresolvedAudioEvents) ?? []
        automation = try c.decodeIfPresent([AutomationLane].self, forKey: .automation) ?? []
        timeBase = try c.decodeIfPresent(ClipTimeBase.self, forKey: .timeBase) ?? .seconds
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id); try c.encode(name, forKey: .name)
        try c.encode(gainDB, forKey: .gainDB); try c.encode(pan, forKey: .pan)
        try c.encode(isMuted, forKey: .isMuted); try c.encode(isSolo, forKey: .isSolo)
        try c.encode(clips, forKey: .clips); try c.encode(automation, forKey: .automation)
        try c.encode(timeBase, forKey: .timeBase)
        if !unresolvedAudioEvents.isEmpty { try c.encode(unresolvedAudioEvents, forKey: .unresolvedAudioEvents) }
    }
}

public enum ClipTimeBase: String, Codable { case seconds, musical }

public struct Clip: Codable, Equatable, Identifiable {
    public var id: UUID
    public var mediaPath: String
    public var name: String
    public var position: TimeInterval
    public var sourceOffset: TimeInterval
    public var duration: TimeInterval
    public var timeBase: ClipTimeBase
    public var musicalPosition: Double?

    public init(id: UUID = UUID(), mediaPath: String, name: String, position: TimeInterval = 0,
                sourceOffset: TimeInterval = 0, duration: TimeInterval,
                timeBase: ClipTimeBase = .seconds, musicalPosition: Double? = nil) {
        self.id = id; self.mediaPath = mediaPath; self.name = name
        self.position = position; self.sourceOffset = sourceOffset; self.duration = duration
        self.timeBase = timeBase; self.musicalPosition = musicalPosition
    }
    private enum CodingKeys: String, CodingKey { case id, mediaPath, name, position, sourceOffset, duration, timeBase, musicalPosition }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id); mediaPath = try c.decode(String.self, forKey: .mediaPath)
        name = try c.decode(String.self, forKey: .name); position = try c.decode(Double.self, forKey: .position)
        sourceOffset = try c.decode(Double.self, forKey: .sourceOffset); duration = try c.decode(Double.self, forKey: .duration)
        timeBase = try c.decodeIfPresent(ClipTimeBase.self, forKey: .timeBase) ?? .seconds
        musicalPosition = try c.decodeIfPresent(Double.self, forKey: .musicalPosition)
    }
}

public enum RebaseCoreError: LocalizedError {
    case invalidProject(String)
    case invalidMediaPath(String)
    case unsupportedAudio(String)
    case nonFiniteAudio(String)
    case mediaTooLarge
    case noAudio
    case notConfigured

    public var errorDescription: String? {
        switch self {
        case .invalidProject(let message), .unsupportedAudio(let message), .nonFiniteAudio(let message): return message
        case .invalidMediaPath(let path): return "Media must be a regular file inside this project's Media folder: \(path)"
        case .mediaTooLarge: return "This version supports up to 16 million decoded frames per clip and 32 million prepared frames per project. Trim long clips before playback or export."
        case .noAudio: return "The project has no timeline duration to render."
        case .notConfigured: return "Load a project before starting playback."
        }
    }
}
