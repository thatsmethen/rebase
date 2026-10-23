import Foundation

/// Adds source-backed audio-event identities to the frozen V3 recovery. Only
/// the separately verified zero-origin/type10 source coordinates are projected.
/// No source event is promoted to a playable Clip by this profile.
final class CPRRecoveryV4 {
    let container: CPRContainer
    init(container: CPRContainer) { self.container = container }

    func decode(sourceName: String) throws -> (recovery: CPRRecoveryResult, clock: NativeTempoClock?) {
        var baseline = try CPRRecoveryV3(container: container).decode(sourceName: sourceName)
        guard var project = baseline.recovery.project else { return baseline }
        do {
            let sources = try CPRAudioEventArchive.read(container: container)
            guard !sources.isEmpty else { return baseline }
            let roles: CPRClockRoles?
            do { roles = try CPRClockRoles.resolve(container: container) }
            catch CPRProjectError.unsupported { roles = nil }
            var placed = 0
            var records = baseline.recovery.objects
            for source in sources {
                guard let sourceTrack = baseline.recovery.objects.first(where: { $0.identityOffset == source.trackIdentity }),
                      let trackID = baseline.recovery.tracks.first(where: { $0.sourceOffset == sourceTrack.objectOffset })?.importedTrackID,
                      let index = project.tracks.firstIndex(where: { $0.id == trackID }) else {
                    throw CPRProjectError.invalid("A decoded audio event has no matching imported source track.")
                }
                let projection = try projectCoordinates(source, roles: roles, clock: baseline.clock)
                if projection.value != nil { placed += 1 }
                let tag: Int32, scalar: UInt64?
                switch source.clipDatum {
                case .scalar(let value, let bits): tag = value; scalar = bits
                case .interfaces(let value, _, _): tag = value; scalar = nil
                }
                let event = UnresolvedCPRAudioEvent(id: stableID("audio-event-v4-\(source.event.identityOffset)"),
                    sourceSHA256: container.sha256, event: source.event, clip: source.clip, cluster: source.cluster.object,
                    name: source.clipName, rawStartBits: source.startBits, rawLengthBits: source.lengthBits,
                    rawOffsetBits: source.offsetBits, datumTag: tag, datumScalarBits: scalar,
                    files: source.cluster.files.map {
                        CPRAudioFileReference(object: $0.object, filename: $0.path.filename, directory: $0.path.directory,
                            frameCount: $0.frameCount, sampleSize: $0.sampleSize, frameSize: $0.frameSize,
                            channels: $0.channels, sampleRateBits: $0.sampleRateBits)
                    }, segments: source.cluster.segments.map {
                        CPRAudioSegmentReference(object: $0.object, streamIdentity: $0.stream.identityOffset,
                            storedOffset: $0.storedOffset, storedLength: $0.storedLength, storedStart: $0.storedStart)
                    }, placement: projection.value, placementStatus: projection.reason)
                project.tracks[index].unresolvedAudioEvents.append(event)
                records += [source.event, source.clip, source.path.object, source.cluster.object, source.volumeCurve]
                records += source.clipChildren
                records += source.cluster.files.flatMap { [$0.object, $0.path.object] + ($0.additionalPath.map { [$0.object] } ?? []) }
                records += source.cluster.segments.map(\.object)
                records += [source.fadeIn, source.fadeOut, source.cluster.path?.object].compactMap { $0 }
                records += source.attributes.compactMap { if case .object(let value) = $0.value { return value }; return nil }
            }
            var unique: [Int: CPRObjectRecord] = [:]
            for record in records {
                if let previous = unique[record.identityOffset], previous != record {
                    throw CPRProjectError.invalid("Audio-event recovery produced inconsistent native object identity.")
                }
                unique[record.identityOffset] = record
            }
            try project.validate()
            baseline.recovery.project = project
            baseline.recovery.objects = unique.values.sorted { $0.identityOffset < $1.identityOffset }
            baseline.recovery.facts.append("Recovered \(sources.count) unresolved audio event\(sources.count == 1 ? "" : "s") with source object identities, linked media descriptors and segment fields. \(placed) has saved source coordinates in the arrangement. Media and playback processing remain unresolved.")
            baseline.recovery.unsupported = baseline.recovery.unsupported.compactMap { item in
                if item.category == "Unconverted event objects", let count = item.objectCount {
                    let remainder = count - sources.count
                    return remainder > 0 ? CPRUnsupportedItem(category: item.category, detail: item.detail, objectCount: remainder) : nil
                }
                if item.category == "Native state preserved only" {
                    return CPRUnsupportedItem(category: item.category,
                        detail: item.detail.replacingOccurrences(of: "Clip/media events, ", with: "Audio playback processing, "), objectCount: item.objectCount)
                }
                return item
            }
            baseline.recovery.unsupported.append(CPRUnsupportedItem(category: "Unresolved audio playback",
                detail: "Recovered audio events retain their media references but cannot play yet. Media, source mapping, gain/fades, warp processing and routing must be resolved before playback or export. Unplaced events have no inferred timeline duration.", objectCount: sources.count))
        } catch CPRProjectError.unsupported(let message) {
            baseline.recovery.unsupported.append(CPRUnsupportedItem(category: "Audio-event interpretation",
                detail: message + " Audio events remain in the preserved source.", objectCount: nil))
        }
        return baseline
    }

    private func projectCoordinates(_ event: CPRSourceAudioEvent, roles: CPRClockRoles?, clock: NativeTempoClock?) throws
        -> (value: CPRAudioSourcePlacement?, reason: String) {
        func unresolved(_ reason: String) -> (CPRAudioSourcePlacement?, String) { (nil, reason) }
        guard event.ancestorTracks.count == 1, event.ancestorTracks[0].className == "MAudioTrackEvent",
              event.containingNode.className == "MListNode", event.containingNode.version == 0 else {
            return unresolved("Saved coordinates require a direct audio track under the project root.")
        }
        for object in [event.root] + event.ancestorTracks + [event.event] {
            var prefix = CPRCursor(data: container.originalBytes, lower: object.payloadOffset,
                                   upper: object.payloadOffset + object.payloadByteCount)
            let word = try prefix.u16(), start = try prefix.u64(), length = try prefix.number(), offset = try prefix.u64()
            guard word == 0, start == 0, offset == 0, length.isFinite else {
                return unresolved("Saved coordinates have nonzero or unsupported ancestor/event offsets.")
            }
        }
        guard let roles, let clock, let tempo = roles.tempo, let signature = roles.signature,
              clock.sourceObjectOffset == tempo.descriptor.identityOffset,
              case .interfaces(let tag, let eventTempo, let eventSignature) = event.containingDatum,
              tag == 0, eventTempo == tempo.descriptor, eventSignature == signature.descriptor else {
            return unresolved("The containing track does not resolve the accepted shared native clock.")
        }
        guard case .scalar(let tag, let bits) = event.clipDatum, tag == 10 else {
            return unresolved("This clip uses a musical or unsupported duration datum; its saved duration is not converted.")
        }
        let scalar = Double(bitPattern: bits), length = Double(bitPattern: event.lengthBits)
        guard scalar.isFinite, scalar > 0, length.isFinite, length >= 1,
              event.cluster.files.count == 1, let file = event.cluster.files.first else {
            return unresolved("The saved rate or duration is outside the verified source-coordinate subset.")
        }
        let rate = Double(Float(bitPattern: file.sampleRateBits))
        guard rate.isFinite, rate > 0, (1.0 / rate).bitPattern == bits else {
            return unresolved("The saved clip datum does not match the declared media sample rate.")
        }
        let product = scalar * length
        let seconds = product / 1.0
        guard seconds.isFinite, seconds > 0, seconds <= 86_400 else {
            return unresolved("The saved duration exceeds the supported arrangement range.")
        }
        return (CPRAudioSourcePlacement(contract: CPRAudioSourcePlacement.contractName,
                    position: 0, duration: seconds, offset: 0),
                "Saved source coordinates recovered. Media and playback processing remain unresolved.")
    }

    private func stableID(_ label: String) -> UUID {
        let chars = Array(cprSHA256(Data((container.sha256 + ":" + label).utf8)).prefix(32))
        return UUID(uuidString: String(chars[0..<8])+"-"+String(chars[8..<12])+"-"+String(chars[12..<16])+"-"+String(chars[16..<20])+"-"+String(chars[20..<32]))!
    }
}
