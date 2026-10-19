import Foundation

/// V2 composes the frozen hierarchy recovery with separately bounded clock and
/// origin-meter projections. Timing roles come from consistent interface pairs
/// in the counted track hierarchy, never a scan or a device's display name.
final class CPRRecoveryV2 {
    let container: CPRContainer
    init(container: CPRContainer) { self.container = container }

    func decode(sourceName: String) throws -> (recovery: CPRRecoveryResult, clock: NativeTempoClock?) {
        var result = try CPRRecoveryV1(container: container).decode(sourceName: sourceName)
        let clock = try fixedClock(result: &result)
        let signature = try CPRSignatureRecovery.recover(container: container)
        result.facts.append(contentsOf: signature.facts)
        result.unsupported.append(contentsOf: signature.unsupported)
        try merge(signature.objects, into: &result)
        if let origin = signature.signature, var project = result.project {
            project.signatureMap = SignatureMap(events: [origin])
            try project.validate()
            result.project = project
            result.defaults = result.defaults.map { sentence in
                sentence == "48 kHz and 4/4 are application defaults; source metadata tags are not used as timing-map evidence."
                    ? "48 kHz is an application default; source metadata tags are not used as timing-map evidence."
                    : sentence
            }
            result.unsupported = result.unsupported.map { item in
                guard item.category == "Native state preserved only" else { return item }
                return CPRUnsupportedItem(category: item.category,
                    detail: "Clip/media events, MIDI and instrument content, plugins, mixer controls, routing, automation, tempo-event coordinates, remaining signature changes, display state and layouts remain in the preserved CPR. Imported audio tracks do not reproduce the source mix.",
                    objectCount: item.objectCount)
            }
        }
        return (result, clock)
    }

    private func fixedClock(result: inout CPRRecoveryResult) throws -> NativeTempoClock? {
        let objects = result.objects.filter { $0.className == "MTempoTrackEvent" }
        guard !objects.isEmpty else { return nil }
        guard objects.count == 1, let object = objects.first, object.version == 3 else {
            throw CPRProjectError.unsupported("The native fixed clock requires one version-3 tempo object shared by the supported track timing interfaces.")
        }
        do {
            let roles = try CPRClockRoles.resolve(container: container)
            guard roles.tempo?.descriptor.identityOffset == object.identityOffset else {
                throw CPRProjectError.unsupported("The visited tempo object is not the shared track timing interface.")
            }
            try merge(roles.objects, into: &result)
        } catch CPRProjectError.unsupported(let reason) {
            // V1's single-visited-object convention is historical behavior, not
            // proof of the stronger V2 shared interface role. Do not promote
            // its scalar tempo when the role check fails.
            result.facts.removeAll { $0.hasPrefix("Recovered active fixed tempo:") || $0.hasPrefix("The native tempo track selects its event map") }
            result.unsupported.removeAll { $0.category == "Tempo event map" }
            if var project = result.project {
                let text = Array(cprSHA256(Data((container.sha256 + ":tempo-unbound-default-v2").utf8)).prefix(32))
                let id = UUID(uuidString: String(text[0..<8])+"-"+String(text[8..<12])+"-"+String(text[12..<16])+"-"+String(text[16..<20])+"-"+String(text[20..<32]))!
                project.tempoMap = TempoMap(events: [TempoEvent(id: id, beat: 0, bpm: 120)])
                try project.validate()
                result.project = project
                result.defaults.removeAll { $0.hasPrefix("120 BPM is an application default") }
                result.defaults.append("120 BPM is an application default because the visited tempo object has no supported shared track timing role.")
            }
            result.unsupported.append(CPRUnsupportedItem(category: "Native clock role",
                detail: reason + " Its tempo values remain preserved only; they are not promoted into the imported timing map.", objectCount: 1))
            return nil
        }
        var fields = CPRCursor(data: container.originalBytes, lower: object.payloadOffset,
                               upper: object.payloadOffset + object.payloadByteCount)
        let count = Int(try fields.u32())
        guard count > 0, count <= 10_000, fields.upper - fields.position >= 6,
              count <= (fields.upper - fields.position - 6) / 22 else {
            throw CPRProjectError.invalid("Invalid native fixed-clock record extent.")
        }
        _ = try fields.bytes(count * 22)
        let bits = try fields.u32()
        guard try fields.u16() != 0 else { return nil }
        let clock = try NativeTempoClock(fixedBPMBits: bits, sourceSHA256: container.sha256,
                                         sourceObjectOffset: object.identityOffset)
        if var project = result.project {
            project.tempoMap = TempoMap(events: project.tempoMap.events, nativeClock: clock)
            try project.validate()
            result.project = project
        }
        result.facts.append("Recovered the fixed-tempo clock at \(clock.fixedBPM) BPM. Its native timing arithmetic is retained; tempo editing or DAWproject export requires an explicit timing conversion.")
        return clock
    }

    private func merge(_ objects: [CPRObjectRecord], into result: inout CPRRecoveryResult) throws {
        var records: [Int: CPRObjectRecord] = [:]
        for record in result.objects + objects {
            if let existing = records[record.identityOffset], existing != record {
                throw CPRProjectError.invalid("Timing recovery produced an inconsistent native object identity.")
            }
            records[record.identityOffset] = record
        }
        result.objects = records.values.sorted { $0.identityOffset < $1.identityOffset }
    }
}
