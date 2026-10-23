import Foundation
import RebaseTimingDSP

/// Fresh saved-source interpretation, separate from frozen V4 recovery. This
/// reconstructs one direct event with an explicit builder/reader rate context
/// and fresh track-resource state. Supplied application clocks and independently
/// recovered saved audio configuration have distinct interpretation contracts.
struct CPRPlacedSourceEventPlan {
    static let contract = "cpr-15.0.30.287-direct-source-segment-v1"
    static let projectClockContract = "cpr-15.0.30.287-direct-project-clock-segment-v1"
    static let savedProjectClockContract = "cpr-15.0.30.287-direct-saved-project-clock-segment-v1"
    let media: CPRSourceEventRenderPlan
    let range: CPRSourceEventTimelineRange
    let timelineRate: Double
    // Before builder snapping. Track admission must check this interval as
    // well as the eventual integer reader window; rounding can hide overlap.
    let canonicalStart: Double
    let canonicalEnd: Double
    let canonicalSourceOffset: Double

    /// Unsnapped source coordinates survive every split. Original ranges are
    /// metadata; only projected audible fragments require complete reader reads.
    struct Canonical {
        let media: CPRSourceEventRenderPlan
        let timelineRate: Double
        let canonicalStart: Double
        let canonicalEnd: Double
        let canonicalSourceOffset: Double
        let contract: String

        func project(windowStart: Double, windowEnd: Double,
                     requireCompleteRead: Bool = true) throws -> CPRPlacedSourceEventPlan? {
            func unsupported(_ message: String) -> RebaseCoreError { .unsupportedAudio(message) }
            guard windowStart >= canonicalStart, windowEnd <= canonicalEnd,
                  windowStart <= windowEnd else {
                throw unsupported("A normalized source fragment does not belong to its original event.")
            }
            var projection = RBTimelineBuilderProjection()
            guard rb_cpr_timeline_builder_project(canonicalStart, canonicalEnd, canonicalSourceOffset,
                windowStart, windowEnd, timelineRate, &projection) == RB_TIMELINE_BUILDER_OK else {
                throw unsupported("The source event is outside the supported native segment-construction range.")
            }
            if projection.disposition == RB_TIMELINE_BUILDER_EMPTY { return nil }
            guard projection.disposition == RB_TIMELINE_BUILDER_SEGMENT else {
                throw unsupported("The source builder returned an unsupported segment disposition.")
            }
            var first: Int64 = 0, last: Int64 = 0, seek: Int64 = 0
            guard rb_cpr_timeline_quantize(projection.period, projection.start, &first) == 0,
                  rb_cpr_timeline_quantize(projection.period, projection.getterEnd, &last) == 0,
                  rb_cpr_timeline_quantize(projection.period, projection.sourceOffset, &seek) == 0,
                  first >= 0, last > first, last <= Int64(timelineRate) * 86_400, seek >= 0 else {
                throw unsupported("A source fragment has unsupported native reader coordinates.")
            }
            if requireCompleteRead {
                guard seek <= Int64(media.frames), last - first <= Int64(media.frames) - seek else {
                    throw unsupported("The unconverted timeline window exceeds the attached media or timeline bounds at this clock rate. Complete source reads are required; missing frames are not padded.")
                }
            }
            return CPRPlacedSourceEventPlan(media: media,
                range: CPRSourceEventTimelineRange(contract: contract, position: projection.start,
                    duration: projection.length, offset: projection.sourceOffset),
                timelineRate: timelineRate, canonicalStart: canonicalStart, canonicalEnd: canonicalEnd,
                canonicalSourceOffset: canonicalSourceOffset)
        }

        func completeEvent() throws -> CPRPlacedSourceEventPlan {
            guard let plan = try project(windowStart: canonicalStart, windowEnd: canonicalEnd) else {
                throw RebaseCoreError.unsupportedAudio("The source event is outside the supported native segment-construction range.")
            }
            return plan
        }
    }

    /// One immutable source interpretation shared by all events in a track.
    /// Construction remains file-private so a caller cannot substitute a clock
    /// or a different container after the source identity has been checked.
    fileprivate struct SourceContext {
        let container: CPRContainer
        let sourceSHA256: String
        let root: CPRObjectRecord
        let tempo: CPRObjectRecord
        let signature: CPRObjectRecord
        let clock: NativeTempoClock
    }

    struct SavedProjectContext {
        let setup: CPRProjectAudioSetup
        let rate: Double
        fileprivate let source: SourceContext
    }

    static func savedProjectContext(container: CPRContainer) throws -> SavedProjectContext {
        let setup = try CPRProjectAudioSetup.read(container: container)
        let rate = try setup.supportedSampleRate()
        let source = try sourceContext(container: container, root: setup.root)
        guard source.sourceSHA256 == setup.sourceSHA256 else {
            throw CPRProjectError.invalid("Saved audio configuration and placement context have different source identities.")
        }
        return SavedProjectContext(setup: setup, rate: rate, source: source)
    }

    private static func sourceContext(container: CPRContainer, root: CPRObjectRecord) throws -> SourceContext {
        let roles = try CPRClockRoles.resolve(container: container)
        // Replay the preserved source, never an edited application tempo map.
        let baseline = try CPRRecoveryV3(container: container).decode(sourceName: "Source timeline")
        let sourceSHA256 = container.sha256
        guard let clock = baseline.clock, let tempo = roles.tempo, let signature = roles.signature,
              clock.sourceSHA256 == sourceSHA256,
              clock.sourceObjectOffset == tempo.descriptor.identityOffset,
              root.className == "MRoot", root.version == 6,
              roles.objects.contains(root) else {
            throw RebaseCoreError.unsupportedAudio("The source track does not resolve an accepted native tempo clock.")
        }
        return SourceContext(container: container, sourceSHA256: sourceSHA256, root: root,
            tempo: tempo.descriptor, signature: signature.descriptor, clock: clock)
    }

    static func makeSavedProjectClock(container: CPRContainer, source: CPRSourceAudioEvent,
                                     retained: UnresolvedCPRAudioEvent, fades: CPRSourceAutoFadeArchive) throws
        -> (plan: CPRPlacedSourceEventPlan, setup: CPRProjectAudioSetup) {
        try makeSavedProjectClock(context: savedProjectContext(container: container),
            source: source, retained: retained, fades: fades)
    }

    static func makeSavedProjectClock(context: SavedProjectContext, source: CPRSourceAudioEvent,
                                     retained: UnresolvedCPRAudioEvent, fades: CPRSourceAutoFadeArchive) throws
        -> (plan: CPRPlacedSourceEventPlan, setup: CPRProjectAudioSetup) {
        let canonical = try savedProjectCanonical(context: context, source: source, retained: retained,
            fades: fades, priorityPolicy: .requireDefault)
        return (try canonical.completeEvent(), context.setup)
    }

    static func savedProjectCanonical(context: SavedProjectContext, source: CPRSourceAudioEvent,
                                      retained: UnresolvedCPRAudioEvent, fades: CPRSourceAutoFadeArchive,
                                      priorityPolicy: CPRSourceEventRenderPlan.PriorityPolicy) throws -> Canonical {
        guard context.setup.root == source.root else {
            throw CPRProjectError.invalid("The saved audio setup and source event belong to different arrangement roots.")
        }
        return try canonical(context: context.source, source: source, retained: retained, fades: fades,
            timelineRate: context.rate, contract: savedProjectClockContract, priorityPolicy: priorityPolicy)
    }

    static func make(container: CPRContainer, source: CPRSourceAudioEvent,
                     retained: UnresolvedCPRAudioEvent,
                     fades: CPRSourceAutoFadeArchive,
                     timelineRate suppliedRate: Double? = nil) throws -> CPRPlacedSourceEventPlan {
        try canonical(context: sourceContext(container: container, root: source.root),
            source: source, retained: retained, fades: fades, timelineRate: suppliedRate,
            contract: suppliedRate == nil ? contract : projectClockContract,
            priorityPolicy: .requireDefault).completeEvent()
    }

    private static func canonical(context: SourceContext, source: CPRSourceAudioEvent,
                                  retained: UnresolvedCPRAudioEvent, fades: CPRSourceAutoFadeArchive,
                                  timelineRate suppliedRate: Double?, contract: String,
                                  priorityPolicy: CPRSourceEventRenderPlan.PriorityPolicy) throws -> Canonical {
        func unsupported(_ message: String) -> RebaseCoreError { .unsupportedAudio(message) }
        guard source.root == context.root, fades.root == context.root,
              retained.sourceSHA256 == context.sourceSHA256,
              retained.event == source.event, retained.clip == source.clip,
              retained.cluster == source.cluster.object else {
            throw CPRProjectError.invalid("Source placement does not match its immutable source context and retained descriptors.")
        }
        guard source.eventWord == 0,
              source.ancestorTracks.count == 1,
              source.ancestorTracks[0].identityOffset == source.trackIdentity,
              source.ancestorTracks[0].className == "MAudioTrackEvent",
              source.containingNode.className == "MListNode", source.containingNode.version == 0,
              let track = fades.tracks[source.trackIdentity], track.numberBits == 0 else {
            throw unsupported("Native timeline audition requires a direct audio track with zero saved track delay.")
        }
        for object in [source.root] + source.ancestorTracks {
            var prefix = CPRCursor(data: context.container.originalBytes, lower: object.payloadOffset,
                                   upper: object.payloadOffset + object.payloadByteCount)
            let word = try prefix.u16(), start = try prefix.u64()
            let length = try prefix.number(), offset = try prefix.u64()
            guard word == 0, start == 0, offset == 0, length.isFinite else {
                throw unsupported("Nonzero or unsupported ancestor coordinates prevent native source placement.")
            }
        }
        guard case .interfaces(tag: 0, tempo: let eventTempo, signature: let eventSignature) = source.containingDatum,
              eventTempo == context.tempo, eventSignature == context.signature else {
            throw unsupported("The source track does not resolve an accepted native tempo clock.")
        }
        let media = try CPRSourceEventRenderPlan.completeMedia(source: source, retained: retained,
            fades: fades, priorityPolicy: priorityPolicy)
        let timelineRate = suppliedRate ?? Double(media.rate)
        guard timelineRate.rounded() == timelineRate, (8_000...192_000).contains(timelineRate) else {
            throw unsupported("Native timeline playback requires a whole project clock rate from 8000 to 192000 Hz.")
        }
        guard media.channels == 2 else {
            throw unsupported("Native timeline audition requires stereo PCM24 media; mono routing is unresolved.")
        }
        let ticks = Double(bitPattern: source.startBits)
        let length = Double(bitPattern: source.lengthBits)
        let offset = Double(bitPattern: source.offsetBits)
        guard ticks.isFinite, ticks >= 0, ticks == 0 || ticks.isNormal,
              length.isFinite, length >= 1, length.rounded() == length,
              offset.isFinite, offset >= 0, offset.rounded() == offset,
              offset <= Double(media.frames), length <= Double(media.frames) - offset,
              case .scalar(tag: 10, bits: let scalarBits) = source.clipDatum else {
            throw unsupported("Native source placement requires nonnegative ticks and a whole-frame trim inside the complete attached media.")
        }
        let scalar = Double(bitPattern: scalarBits)
        // Containing-datum Start and clip-datum Length/Offset are different
        // domains. Keep the recovered separate arithmetic and negation order.
        let start = try context.clock.seconds(atNativeTick: ticks + 0.0) / 1.0
        let durationProduct = scalar * length
        let duration = durationProduct / 1.0
        let negativeOffsetProduct = (-offset) * scalar
        let sourceOffset = offset == 0 ? -0.0 : -(negativeOffsetProduct / 1.0)
        let end = start + duration
        guard start.isFinite, start >= 0, end.isFinite, end > start, end <= 86_400,
              start == 0 || start.isNormal, end.isNormal,
              sourceOffset == 0 || sourceOffset.isNormal else {
            throw unsupported("Canonical source coordinates exceed the supported finite timeline bounds.")
        }
        return Canonical(media: media, timelineRate: timelineRate, canonicalStart: start,
            canonicalEnd: end, canonicalSourceOffset: sourceOffset, contract: contract)
    }
}
