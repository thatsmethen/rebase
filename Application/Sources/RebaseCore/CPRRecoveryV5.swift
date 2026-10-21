import Foundation

/// Adds typed saved audio configuration without changing any earlier profile,
/// native tempo descriptor, retained audio-event identity, or source placement.
final class CPRRecoveryV5 {
    let container: CPRContainer
    init(container: CPRContainer) { self.container = container }

    func decode(sourceName: String) throws
        -> (recovery: CPRRecoveryResult, clock: NativeTempoClock?, audioSetup: CPRProjectAudioSetup?) {
        var baseline = try CPRRecoveryV4(container: container).decode(sourceName: sourceName)
        var audioSetup: CPRProjectAudioSetup?
        do {
            let setup = try CPRProjectAudioSetup.read(container: container)
            audioSetup = setup
            var records: [Int: CPRObjectRecord] = [:]
            for record in baseline.recovery.objects + [setup.arrangement, setup.root, setup.setup] {
                if let existing = records[record.identityOffset], existing != record {
                    throw CPRProjectError.invalid("Audio setup produced inconsistent source object identity.")
                }
                records[record.identityOffset] = record
            }
            baseline.recovery.objects = records.values.sorted { $0.identityOffset < $1.identityOffset }
            let rate = try setup.supportedSampleRate()
            if var project = baseline.recovery.project {
                project.sampleRate = rate
                try project.validate()
                baseline.recovery.project = project
                baseline.recovery.defaults = baseline.recovery.defaults.compactMap { value in
                    if value == "48 kHz is an application default; source metadata tags are not used as timing-map evidence." { return nil }
                    return value.replacingOccurrences(of: "48 kHz and 4/4 are application defaults;", with: "4/4 is an application default;")
                }
            }
            baseline.recovery.facts.append("Recovered the saved project audio base rate at \(Int(rate)) Hz with a rate factor of 1. This is saved configuration, not a measurement of the hosted or device clock.")
        } catch CPRProjectError.unsupported(let message) {
            baseline.recovery.unsupported.append(CPRUnsupportedItem(category: "Saved project audio setup",
                detail: message + " Any application sample-rate default remains explicitly separate from the saved native configuration.", objectCount: 1))
        }
        return (baseline.recovery, baseline.clock, audioSetup)
    }
}
