import Foundation
import RebaseTimingDSP

/// Fresh saved-source interpretation, separate from frozen V4 recovery. This
/// reconstructs one direct event with a source-rate builder context and fresh
/// track-resource state. It is not the hosted project/channel configuration.
struct CPRPlacedSourceEventPlan {
    static let contract = "cpr-15.0.30.287-direct-source-segment-v1"
    let media: CPRSourceEventRenderPlan
    let range: CPRSourceEventTimelineRange

    static func make(container: CPRContainer, source: CPRSourceAudioEvent,
                     retained: UnresolvedCPRAudioEvent,
                     fades: CPRSourceAutoFadeArchive) throws -> CPRPlacedSourceEventPlan {
        func unsupported(_ message: String) -> RebaseCoreError { .unsupportedAudio(message) }
        guard source.eventWord == 0,
              source.ancestorTracks.count == 1,
              source.ancestorTracks[0].identityOffset == source.trackIdentity,
              source.ancestorTracks[0].className == "MAudioTrackEvent",
              source.containingNode.className == "MListNode", source.containingNode.version == 0,
              let track = fades.tracks[source.trackIdentity], track.numberBits == 0 else {
            throw unsupported("Native timeline audition requires a direct audio track with zero saved track delay.")
        }
        for object in [source.root] + source.ancestorTracks {
            var prefix = CPRCursor(data: container.originalBytes, lower: object.payloadOffset,
                                   upper: object.payloadOffset + object.payloadByteCount)
            let word = try prefix.u16(), start = try prefix.u64()
            let length = try prefix.number(), offset = try prefix.u64()
            guard word == 0, start == 0, offset == 0, length.isFinite else {
                throw unsupported("Nonzero or unsupported ancestor coordinates prevent native source placement.")
            }
        }
        let roles = try CPRClockRoles.resolve(container: container)
        // Always replay the source clock. Explicitly editing/detaching the app
        // tempo map cannot silently reinterpret preserved source-event ticks.
        let baseline = try CPRRecoveryV3(container: container).decode(sourceName: "Source timeline")
        guard let clock = baseline.clock, let tempo = roles.tempo, let signature = roles.signature,
              clock.sourceSHA256 == container.sha256,
              clock.sourceObjectOffset == tempo.descriptor.identityOffset,
              case .interfaces(tag: 0, tempo: let eventTempo, signature: let eventSignature) = source.containingDatum,
              eventTempo == tempo.descriptor, eventSignature == signature.descriptor else {
            throw unsupported("The source track does not resolve an accepted native tempo clock.")
        }
        let media = try CPRSourceEventRenderPlan.completeMedia(source: source, retained: retained, fades: fades)
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
        let start = try clock.seconds(atNativeTick: ticks + 0.0) / 1.0
        let durationProduct = scalar * length
        let duration = durationProduct / 1.0
        let negativeOffsetProduct = (-offset) * scalar
        let sourceOffset = offset == 0 ? -0.0 : -(negativeOffsetProduct / 1.0)
        let end = start + duration
        var projection = RBTimelineBuilderProjection()
        guard rb_cpr_timeline_builder_project(start, end, sourceOffset, start, end,
                    Double(media.rate), &projection) == RB_TIMELINE_BUILDER_OK,
              projection.disposition == RB_TIMELINE_BUILDER_SEGMENT else {
            throw unsupported("The source event is outside the supported native segment-construction range.")
        }
        // Builder snapping and reader quantization are distinct. Check the
        // actual reader coordinates, including its concrete start+length getter,
        // against media capacity before any samples are scheduled.
        var first: Int64 = 0, last: Int64 = 0, seek: Int64 = 0
        guard rb_cpr_timeline_quantize(projection.period, projection.start, &first) == 0,
              rb_cpr_timeline_quantize(projection.period, projection.getterEnd, &last) == 0,
              rb_cpr_timeline_quantize(projection.period, projection.sourceOffset, &seek) == 0,
              first >= 0, last > first, last <= Int64(media.rate) * 86_400,
              seek >= 0, seek <= Int64(media.frames), last - first <= Int64(media.frames) - seek else {
            throw unsupported("The reconstructed native source window exceeds the attached media or timeline bounds.")
        }
        return CPRPlacedSourceEventPlan(media: media,
            range: CPRSourceEventTimelineRange(contract: contract, position: projection.start,
                duration: projection.length, offset: projection.sourceOffset))
    }
}
