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
    public let nativeProjectClockPlaybackUnavailableReason: String?
    public let nativeProjectClockRange: CPRSourceEventTimelineRange?
    public let savedProjectAudioSetup: CPRProjectAudioSetup?
    public let nativeSavedProjectClockPlaybackUnavailableReason: String?
    public let nativeSavedProjectClockRange: CPRSourceEventTimelineRange?
    public let nativeTrackPlaybackUnavailableReason: String?
    public let nativeTrackEventCount: Int?
    public let nativeTrackFragmentCount: Int?
    public let nativeTrackSnappedEmptyFragmentCount: Int?

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
        let projectClockReason: String?
        let projectClockRange: CPRSourceEventTimelineRange?
        do {
            let plan = try CPRPlacedSourceEventPlan.make(container: verified.container, source: source,
                retained: verified.retained, fades: fades, timelineRate: project.sampleRate)
            sourceRate = Double(plan.media.rate)
            projectClockRange = plan.range
            projectClockReason = project.attachedMedia(for: verified.retained) == nil ? "Attach matching PCM24 WAV media first." : nil
        } catch {
            projectClockReason = error.localizedDescription
            projectClockRange = nil
        }
        var savedSetup: CPRProjectAudioSetup?
        let savedClockReason: String?
        let savedClockRange: CPRSourceEventTimelineRange?
        do {
            // Retain raw source configuration for inspection even when its rate
            // or factor is outside the narrower playback policy.
            savedSetup = try CPRProjectAudioSetup.read(container: verified.container)
            let saved = try CPRPlacedSourceEventPlan.makeSavedProjectClock(container: verified.container,
                source: source, retained: verified.retained, fades: fades)
            savedClockRange = saved.plan.range
            savedClockReason = project.attachedMedia(for: verified.retained) == nil ? "Attach matching PCM24 WAV media first." : nil
        } catch {
            savedClockReason = error.localizedDescription
            savedClockRange = nil
        }
        let trackReason: String?
        let trackCount: Int?
        let fragmentCount: Int?
        let snappedEmptyCount: Int?
        do {
            let track = try CPRSourceTrackPlan.make(eventID: eventID, project: project, root: root)
            trackCount = track.entries.count
            if let selected = track.entries.first(where: { $0.retained.id == eventID }) {
                sourceRate = Double(selected.canonical.media.rate)
            }
            fragmentCount = track.fragments.count
            snappedEmptyCount = track.snappedEmptyFragmentCount
            trackReason = nil
        } catch {
            trackCount = nil
            fragmentCount = nil
            snappedEmptyCount = nil
            trackReason = error.localizedDescription
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
            nativeTimelinePlaybackUnavailableReason: nativeReason, nativeTimelineRange: nativeRange,
            nativeProjectClockPlaybackUnavailableReason: projectClockReason, nativeProjectClockRange: projectClockRange,
            savedProjectAudioSetup: savedSetup, nativeSavedProjectClockPlaybackUnavailableReason: savedClockReason,
            nativeSavedProjectClockRange: savedClockRange,
            nativeTrackPlaybackUnavailableReason: trackReason, nativeTrackEventCount: trackCount,
            nativeTrackFragmentCount: fragmentCount, nativeTrackSnappedEmptyFragmentCount: snappedEmptyCount)
    }
}
