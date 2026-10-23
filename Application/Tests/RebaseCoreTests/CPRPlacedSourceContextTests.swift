import Foundation
import Testing
@testable import RebaseCore

/// Reuse must preserve the exact single-event arithmetic and the immutable
/// source binding. These tests execute Rebase only, using read-only CPR input.
struct CPRPlacedSourceContextTests {
    private let workspace = PrivateResearchFixtures.root
    private func original() throws -> Data {
        let path = "templates/LoFi Hip Hop.cpr"
        let bytes = try Data(contentsOf: workspace.appendingPathComponent(path))
        #expect(cprSHA256(bytes) == "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495")
        return bytes
    }
    private func inputs(_ bytes: Data) throws -> (CPRContainer, CPRSourceAudioEvent, UnresolvedCPRAudioEvent, CPRSourceAutoFadeArchive) {
        let container = try CPRProject.readContainer(bytes)
        let source = try #require(CPRAudioEventArchive.read(container: container).first)
        let recovered = try CPRRecoveryV4(container: container).decode(sourceName: "Context control")
        let retained = try #require(recovered.recovery.project?.unresolvedAudioEvents.first)
        return (container, source, retained, try CPRAutoFadeArchive.read(container: container))
    }
    private func put(_ value: UInt64, at offset: Int, into bytes: inout Data) {
        var big = value.bigEndian
        bytes.replaceSubrange(offset..<(offset + 8), with: withUnsafeBytes(of: &big) { Data($0) })
    }
    private func bits(_ plan: CPRPlacedSourceEventPlan) -> [UInt64] {
        [plan.canonicalStart.bitPattern, plan.canonicalEnd.bitPattern,
         plan.range.position.bitPattern, plan.range.duration.bitPattern, plan.range.offset.bitPattern,
         plan.timelineRate.bitPattern, UInt64(plan.media.gain.bitPattern)]
    }
    private func rejects(_ work: () throws -> Void) -> Bool {
        do { try work(); return false } catch { return true }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func reusedSavedContextMatchesFreshSingleEventBitsBeforeAndAfterTempoJump() throws {
        let bytes = try original()
        let originalSource = try #require(CPRAudioEventArchive.read(container: CPRProject.readContainer(bytes)).first)
        for ticks in [0.0, 4_800.0, 500_000.0] {
            var changed = bytes
            put(ticks.bitPattern, at: originalSource.event.payloadOffset + 2, into: &changed)
            let (container, source, retained, fades) = try inputs(changed)
            let context = try CPRPlacedSourceEventPlan.savedProjectContext(container: container)
            let fresh = try CPRPlacedSourceEventPlan.makeSavedProjectClock(container: container,
                source: source, retained: retained, fades: fades)
            for _ in 0..<3 {
                let reused = try CPRPlacedSourceEventPlan.makeSavedProjectClock(context: context,
                    source: source, retained: retained, fades: fades)
                #expect(bits(reused.plan) == bits(fresh.plan))
                #expect(reused.plan.media.file == fresh.plan.media.file)
                #expect(reused.setup == fresh.setup && reused.setup == context.setup)
                #expect(reused.plan.range.contract == CPRPlacedSourceEventPlan.savedProjectClockContract)
            }
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func reusableContextRejectsForeignSourceRetainedHashAndDescriptorWithoutMutation() throws {
        let originalBytes = try original()
        let (container, source, retained, fades) = try inputs(originalBytes)
        let context = try CPRPlacedSourceEventPlan.savedProjectContext(container: container)
        let expected = try CPRPlacedSourceEventPlan.makeSavedProjectClock(context: context,
            source: source, retained: retained, fades: fades)
        var changedBytes = originalBytes
        put(Double(4_800).bitPattern, at: source.event.payloadOffset + 2, into: &changedBytes)
        let (changedContainer, changedSource, changedRetained, changedFades) = try inputs(changedBytes)
        #expect(rejects {
            _ = try CPRPlacedSourceEventPlan.makeSavedProjectClock(context: context,
                source: changedSource, retained: changedRetained, fades: changedFades)
        })
        #expect(rejects {
            _ = try CPRPlacedSourceEventPlan.makeSavedProjectClock(context: context,
                source: source, retained: retained, fades: changedFades)
        })
        // A different source remains valid in its own context; rejection above
        // is a provenance check, not a coincidental unsupported timing field.
        _ = try CPRPlacedSourceEventPlan.makeSavedProjectClock(container: changedContainer,
            source: changedSource, retained: changedRetained, fades: changedFades)
        let encoded = try JSONEncoder().encode(retained)
        for field in ["sourceSHA256", "event", "clip", "cluster"] {
            var value = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
            if field == "sourceSHA256" { value[field] = String(repeating: "0", count: 64) }
            else {
                var descriptor = try #require(value[field] as? [String: Any])
                descriptor["identityOffset"] = (try #require(descriptor["identityOffset"] as? Int)) + 4
                value[field] = descriptor
            }
            let forged = try JSONDecoder().decode(UnresolvedCPRAudioEvent.self,
                from: JSONSerialization.data(withJSONObject: value))
            #expect(rejects {
                _ = try CPRPlacedSourceEventPlan.makeSavedProjectClock(context: context,
                    source: source, retained: forged, fades: fades)
            })
        }
        let after = try CPRPlacedSourceEventPlan.makeSavedProjectClock(context: context,
            source: source, retained: retained, fades: fades)
        #expect(bits(after.plan) == bits(expected.plan))
        #expect(context.setup == expected.setup && container.originalBytes == originalBytes)
    }
}
