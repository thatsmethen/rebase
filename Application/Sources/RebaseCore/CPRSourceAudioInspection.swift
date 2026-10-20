import Foundation

/// Additional saved-state interpretation, separate from the frozen import.
/// Neither this record nor zero auto-fade flags authorizes project playback.
public struct CPRSourceAudioInspection: Identifiable, Equatable {
    public var id: UUID { eventID }
    public let eventID: UUID
    public let name: String
    public let sourceSHA256: String
    public let eventIdentity: Int
    public let trackIdentity: Int
    public let volume: Float
    public let inverted: Bool
    public let hasExplicitFadeIn: Bool
    public let hasExplicitFadeOut: Bool
    public let hasWarpState: Bool
    public let autoFadeOrigin: String
    public let autoFadeFlags: UInt16?
    public let autoFadeDuration: Double?
    public let autoFadeSettingIdentity: Int?
    public let localRenderUnavailableReason: String?
    public let timelinePlaybackUnavailableReason: String?
    public let sourceSampleRate: Double?
    public let projectSampleRate: Double
    public let rateConvertedPlaybackUnavailableReason: String?
    public let mode2PlaybackUnavailableReason: String?
    public let mode1PlaybackUnavailableReason: String?
    public let nativeTimelinePlaybackUnavailableReason: String?
    public let nativeTimelineRange: CPRSourceEventTimelineRange?

    public static func inspect(eventID: UUID, in project: Project, at root: URL) throws -> CPRSourceAudioInspection {
        let verified = try ProjectStore.verifiedCPRSourceEvent(eventID, in: project, at: root)
        let fades = try CPRAutoFadeArchive.read(container: verified.container)
        let source = verified.source, track = fades.tracks[source.trackIdentity]
        let setting = fades.effectiveSetting(forTrackIdentity: source.trackIdentity)
        let reason: String?
        let timelineReason: String?
        let rateReason: String?
        let mode2Reason: String?
        let mode1Reason: String?
        var sourceRate: Double?
        do {
            let plan = try CPRSourceEventRenderPlan.make(source: source, retained: verified.retained, fades: fades)
            sourceRate = Double(plan.rate)
            reason = project.attachedMedia(for: verified.retained) == nil ? "Attach matching PCM24 WAV media first." : nil
            timelineReason = reason ?? (plan.channels == 2 ? nil : "Timeline audition currently requires a stereo source; native mono output routing is unresolved.")
            rateReason = timelineReason ?? CPRRateConvertedStream.unavailableReason(sourceRate: Double(plan.rate), outputRate: project.sampleRate)
            mode2Reason = timelineReason ?? CPRRateConvertedStream.unavailableReason(
                sourceRate: Double(plan.rate), outputRate: project.sampleRate, algorithm: .nativeMode2)
            mode1Reason = timelineReason ?? CPRRateConvertedStream.unavailableReason(
                sourceRate: Double(plan.rate), outputRate: project.sampleRate, algorithm: .nativeMode1)
        } catch {
            reason = error.localizedDescription; timelineReason = reason
            rateReason = reason; mode2Reason = reason; mode1Reason = reason
        }
        let nativeReason: String?
        let nativeRange: CPRSourceEventTimelineRange?
        do {
            let plan = try CPRPlacedSourceEventPlan.make(container: verified.container, source: source,
                retained: verified.retained, fades: fades)
            sourceRate = Double(plan.media.rate)
            nativeRange = plan.range
            nativeReason = project.attachedMedia(for: verified.retained) == nil ? "Attach matching PCM24 WAV media first." : nil
        } catch {
            nativeReason = error.localizedDescription
            nativeRange = nil
        }
        return CPRSourceAudioInspection(eventID: eventID, name: verified.retained.name,
            sourceSHA256: verified.container.sha256, eventIdentity: source.event.identityOffset,
            trackIdentity: source.trackIdentity, volume: Float(bitPattern: source.volumeBits),
            inverted: source.invertedWord != 0, hasExplicitFadeIn: source.fadeIn != nil,
            hasExplicitFadeOut: source.fadeOut != nil, hasWarpState: source.attributes.contains { $0.name == "Warpscale" },
            autoFadeOrigin: track?.localSetting != nil ? "Track" : setting != nil ? "Project" : "Unresolved default",
            autoFadeFlags: setting?.flags, autoFadeDuration: setting.map { Double(bitPattern: $0.durationBits) },
            autoFadeSettingIdentity: setting?.object.identityOffset, localRenderUnavailableReason: reason,
            timelinePlaybackUnavailableReason: timelineReason, sourceSampleRate: sourceRate,
            projectSampleRate: project.sampleRate, rateConvertedPlaybackUnavailableReason: rateReason,
            mode2PlaybackUnavailableReason: mode2Reason, mode1PlaybackUnavailableReason: mode1Reason,
            nativeTimelinePlaybackUnavailableReason: nativeReason, nativeTimelineRange: nativeRange)
    }
}

/// A fresh source-state reconstruction of one event. Track/mixer processing,
/// host callbacks and external pitch context are not inputs to this operation.
struct CPRSourceEventRenderPlan {
    let frames: Int
    let rate: UInt32
    let channels: Int
    let gain: Float
    let file: CPRAudioFileReference

    static func make(source: CPRSourceAudioEvent, retained: UnresolvedCPRAudioEvent,
                     fades: CPRSourceAutoFadeArchive) throws -> CPRSourceEventRenderPlan {
        func unsupported(_ message: String) -> RebaseCoreError { .unsupportedAudio(message) }
        guard source.ancestorTracks.count == 1, source.ancestorTracks[0].identityOffset == source.trackIdentity,
              source.ancestorTracks[0].className == "MAudioTrackEvent", source.root == fades.root,
              let placement = retained.placement, placement.position.bitPattern == 0,
              placement.offset.bitPattern == 0, source.eventWord == 0,
              source.startBits == 0, source.offsetBits == 0 else {
            throw unsupported("Source rendering requires a direct audio track with verified zero-origin source timing.")
        }
        let media = try completeMedia(source: source, retained: retained, fades: fades)
        guard Double(bitPattern: source.lengthBits) == Double(media.frames),
              case .scalar(tag: 10, bits: let scalar) = source.clipDatum,
              placement.duration.bitPattern == ((Double(bitPattern: scalar) * Double(media.frames)) / 1.0).bitPattern else {
            throw unsupported("Source rendering requires one complete PCM24 segment at its original sample rate.")
        }
        return media
    }

    /// Validates the complete immutable media and processing state separately
    /// from event coordinates. Callers must additionally prove their own timing
    /// contract; this alone never admits an event to playback or export.
    static func completeMedia(source: CPRSourceAudioEvent, retained: UnresolvedCPRAudioEvent,
                              fades: CPRSourceAutoFadeArchive) throws -> CPRSourceEventRenderPlan {
        func unsupported(_ message: String) -> RebaseCoreError { .unsupportedAudio(message) }
        guard source.root == fades.root else {
            throw unsupported("Source and effective fades must belong to the same saved project.")
        }
        guard source.fadeIn == nil, source.fadeOut == nil, source.invertedWord == 0,
              source.priority == 1, source.lane == 0, source.legacyLane == 0 else {
            throw unsupported("Explicit fades, inversion, lanes or event-priority processing are not reconstructed.")
        }
        // CPRAudioEventArchive already requires empty numeric event attributes,
        // an empty volume curve and an empty edit history. Do not weaken those
        // reader gates when broadening this renderer.
        guard let setting = fades.effectiveSetting(forTrackIdentity: source.trackIdentity), setting.flags == 0 else {
            throw unsupported("Source rendering requires an explicit effective automatic-fade setting with zero flags.")
        }
        let allowed: Set<String> = ["AUID", "GridDef", "HPFilterMode", "HPPeakThreshold", "HPThreshold", "StretchPreset", "TransposeLock"]
        guard source.clipChildren.allSatisfy({ $0.className == "MHitPointEvent" && $0.version == 3 && $0.payloadByteCount == 26 }),
              source.attributes.allSatisfy({ allowed.contains($0.name) }),
              source.attributes.contains(where: { $0.name == "TransposeLock" && $0.value == .integer(1) }),
              source.attributes.contains(where: {
                  guard $0.name == "StretchPreset", case .object(let object) = $0.value else { return false }
                  return object?.className == "ElastiquePreset" && object?.version == 0
              }) else {
            throw unsupported("Warp, pitch, replacement or unverified clip-processing state prevents source rendering.")
        }
        guard retained.files.count == 1, retained.segments.count == 1,
              source.cluster.fileListWord == 2, source.cluster.segmentListWord == 1,
              let file = retained.files.first, let segment = retained.segments.first,
              segment.streamIdentity == file.object.identityOffset, segment.storedStart == 0, segment.storedOffset == 0,
              file.sampleSize == 24, (1...2).contains(file.channels), Int(file.frameSize) == Int(file.channels) * 3,
              let frames = Int(exactly: segment.storedLength), frames > 0, frames <= 16_000_000,
              file.frameCount == segment.storedLength,
              let rate = UInt32(exactly: file.sampleRate), (8_000...192_000).contains(rate),
              case .scalar(tag: 10, bits: let scalar) = source.clipDatum,
              Double(bitPattern: scalar).bitPattern == (1 / Double(rate)).bitPattern else {
            throw unsupported("Source rendering requires one complete PCM24 segment at its original sample rate.")
        }
        _ = try CPRSegmentReadPlan.project(segment: segment, clusterPosition: 0, requestedFrames: frames,
            sourceFrameCount: Int64(file.frameCount), frameSize: Int(file.frameSize))
        let gain = Float(bitPattern: source.volumeBits)
        guard gain.isFinite, gain >= Float.leastNormalMagnitude * 8_388_608 else {
            throw unsupported("Source event gain must keep PCM24 values in the finite normal Float32 range.")
        }
        return CPRSourceEventRenderPlan(frames: frames, rate: rate, channels: Int(file.channels), gain: gain, file: file)
    }
}
