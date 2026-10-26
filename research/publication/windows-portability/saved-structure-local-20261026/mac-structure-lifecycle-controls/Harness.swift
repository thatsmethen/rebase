import AppKit
import Foundation
import RebaseCore

@main
struct StructureLifecycleHarness {
    @MainActor static func main() async {
        let args = CommandLine.arguments
        guard args.count == 3 else { fatalError("Expected authored package and receipt path") }
        let root = URL(fileURLWithPath: args[1])
        let receipt = URL(fileURLWithPath: args[2])
        var checks: [String] = []
        var ownedRuntimeScratch: [URL] = []
        func check(_ condition: Bool, _ label: String) throws {
            guard condition else { throw NSError(domain: "StructureLifecycleControl", code: 1,
                userInfo: [NSLocalizedDescriptionKey: label]) }
            checks.append(label)
        }
        func reflectedRoot(_ session: StudioSession) -> URL? {
            for child in Mirror(reflecting: session).children where child.label == "projectRoot" {
                if let value = child.value as? URL { return value }
                return Mirror(reflecting: child.value).children.first?.value as? URL
            }
            return nil
        }
        func generation(_ session: StudioSession) -> UUID? {
            Mirror(reflecting: session).children.first(where: { $0.label == "projectStructureGeneration" })?.value as? UUID
        }
        func settle(_ session: StudioSession, status: String) async throws {
            // Bounded executable observation, not an exposed join of discarded Tasks.
            // Static generation guards establish the complementary all-completion path.
            for _ in 0..<50 {
                try await Task.sleep(nanoseconds: 20_000_000)
                guard session.cprProjectStructure == nil, !session.inspectingProjectStructure,
                      session.status == status, session.errorMessage == nil else {
                    throw NSError(domain: "StructureLifecycleControl", code: 2,
                        userInfo: [NSLocalizedDescriptionKey: "A stale inspection published or changed lifecycle state"])
                }
            }
        }
        func finishInspection(_ session: StudioSession) async throws {
            for _ in 0..<500 {
                if session.cprProjectStructure != nil {
                    try check(!session.inspectingProjectStructure, "successful-inspection-completes-busy-state")
                    return
                }
                guard session.inspectingProjectStructure, session.errorMessage == nil else {
                    throw NSError(domain: "StructureLifecycleControl", code: 3,
                        userInfo: [NSLocalizedDescriptionKey: "Fresh inspection stopped before publication"])
                }
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            throw NSError(domain: "StructureLifecycleControl", code: 4,
                userInfo: [NSLocalizedDescriptionKey: "Fresh inspection exceeded ten-second bound"])
        }
        var outcome = "failed", failure: String?
        do {
            NSApplication.shared.setActivationPolicy(.prohibited)
            let session = StudioSession()
            if let initial = reflectedRoot(session) { ownedRuntimeScratch.append(initial) }
            session.openURL(root)
            let original = session.project
            try check(session.errorMessage == nil && !session.isDirty, "authored-project-opened")
            session.showCPRProjectStructure()
            let oldGeneration = generation(session)
            try check(session.inspectingProjectStructure, "first-request-admitted")
            session.openURL(root)
            try check(session.project == original && generation(session) != oldGeneration,
                      "equal-value-reopen-changes-generation")
            let openedStatus = session.status
            try await settle(session, status: openedStatus)
            try check(session.cprProjectStructure == nil, "equal-value-reopen-stale-result-not-published-bounded")
            session.showCPRProjectStructure()
            try await finishInspection(session)
            try check(session.cprProjectStructure?.snapshot.projectID == original.id,
                      "fresh-request-after-reopen-publishes")
            session.openURL(root)
            try check(session.cprProjectStructure == nil, "visible-inspector-clears-on-reopen")
            session.showCPRProjectStructure()
            let editGeneration = generation(session)
            guard let track = session.project.tracks.first else { fatalError("Authored track missing") }
            session.setGain(track.id, -6)
            session.undo()
            try check(session.project == original && generation(session) != editGeneration,
                      "edit-undo-restores-value-but-invalidates-generation")
            let undoStatus = session.status
            try await settle(session, status: undoStatus)
            try check(session.cprProjectStructure == nil, "edit-undo-stale-result-not-published-bounded")
            let dirty = session.isDirty, redo = session.canRedo
            session.showCPRProjectStructure()
            try await finishInspection(session)
            try check(session.isDirty == dirty && session.canRedo == redo,
                      "fresh-inspection-preserves-dirty-and-history")
            let saveGeneration = generation(session)
            try check(session.saveProject(), "accepted-save-succeeds")
            try check(session.cprProjectStructure == nil && generation(session) != saveGeneration,
                      "accepted-save-clears-visible-inspector")
            session.showCPRProjectStructure()
            try check(session.saveProject(), "save-during-pending-inspection-succeeds")
            try await settle(session, status: session.status)
            try check(session.cprProjectStructure == nil, "accepted-save-revokes-pending-result-bounded")
            session.showCPRProjectStructure()
            try await finishInspection(session)
            try check(session.cprProjectStructure != nil, "fresh-request-after-save-publishes")
            session.newProject()
            if let replacement = reflectedRoot(session) { ownedRuntimeScratch.append(replacement) }
            try check(session.project.id != original.id && session.cprProjectStructure == nil && !session.inspectingProjectStructure,
                      "visible-inspector-clears-on-new-project")
            outcome = "passed"
        } catch { failure = error.localizedDescription }
        for item in ownedRuntimeScratch { try? FileManager.default.removeItem(at: item) }
        let result: [String: Any] = ["schema": "rebase.mac.structure-lifecycle-control.v1",
            "outcome": outcome, "checks": checks, "check_count": checks.count,
            "failure": failure as Any? ?? NSNull(),
            "actual_current_app_sources": true, "native_window_rendered": false,
            "proprietary_reference_executed": false, "settle_observation_seconds": 1,
            "limitations": ["Discarded detached tasks are not exposed/joinable; stale-response checks combine bounded one-second executable observations with read-only generation-guard review.",
                            "This is a native executable control of current app session sources, not an independently rendered UI or proprietary runtime equivalence test."]]
        do { try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]).write(to: receipt, options: .withoutOverwriting) }
        catch { fatalError("Receipt publication failed") }
        print("Mac lifecycle controls: \(outcome), \(checks.count) checks")
        if outcome != "passed" { exit(1) }
    }
}
