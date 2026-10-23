import Foundation

/// A fresh source-state reconstruction of one event. Track/mixer processing,
/// host callbacks and external pitch context are not inputs to this operation.
struct CPRSourceEventRenderPlan {
    enum PriorityPolicy: Equatable {
        case requireDefault
        /// The complete-track caller must normalize the recovered signed
        /// priority and original collector order before constructing playback.
        case normalizedTrack
    }
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
                              fades: CPRSourceAutoFadeArchive,
                              priorityPolicy: PriorityPolicy = .requireDefault) throws -> CPRSourceEventRenderPlan {
        func unsupported(_ message: String) -> RebaseCoreError { .unsupportedAudio(message) }
        guard source.root == fades.root else {
            throw unsupported("Source and effective fades must belong to the same saved project.")
        }
        guard source.fadeIn == nil, source.fadeOut == nil, source.invertedWord == 0,
              (priorityPolicy == .normalizedTrack || source.priority == 1),
              source.lane == 0, source.legacyLane == 0 else {
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
