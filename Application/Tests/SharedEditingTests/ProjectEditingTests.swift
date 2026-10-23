import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

struct ProjectEditingTests {
    // Evaluate mutating history calls before entering the assertion macro.
    private func required<Value>(_ value: Value?, sourceLocation: SourceLocation = #_sourceLocation) throws -> Value {
        try #require(value, sourceLocation: sourceLocation)
    }

    private func fixture() -> Project {
        Project(tracks: [Track(name: "Audio", clips: [
            Clip(mediaPath: "Media/control.wav", name: "Control", position: 1, sourceOffset: 0.25, duration: 4)
        ])])
    }

    @Test func moveTrimSplitUndoRedoPreserveSourceCoordinatesAndSelection() throws {
        let original = fixture(), trackID = original.tracks[0].id, clipID = original.tracks[0].clips[0].id
        var project = original, history = ProjectEditHistory()
        var selection = ProjectSelection(trackID: trackID, clipID: clipID)
        let moved = try required(history.apply(.moveClip(clipID, position: 3), to: project, selection: selection))
        project = moved.project
        #expect(project.tracks[0].clips[0].sourceOffset == 0.25)
        let trimmed = try required(history.apply(.trimClip(clipID, end: 10, availableSourceDuration: 2.5), to: project, selection: selection))
        project = trimmed.project
        #expect(project.tracks[0].clips[0].duration == 2.5 && trimmed.waveformClipIDs == [clipID])
        let newID = UUID()
        let split = try required(history.apply(.splitClip(clipID, at: 4, newClipID: newID), to: project, selection: selection))
        let beforeSplit = project
        project = split.project; selection = split.selection
        #expect(project.tracks[0].clips.map(\.duration) == [1, 1.5])
        #expect(project.tracks[0].clips.map(\.sourceOffset) == [0.25, 1.25])
        #expect(project.tracks[0].clips.map(\.position) == [3, 4])
        #expect(split.waveformClipIDs == [clipID, newID])
        #expect(selection == ProjectSelection(trackID: trackID, clipID: newID))
        let undone = try required(history.undo(current: project))
        #expect(undone == beforeSplit)
        #expect(selection.reconciled(in: undone) == ProjectSelection(trackID: trackID, clipID: clipID))
        #expect(try required(history.redo(current: undone)) == project)
        #expect(history.undoCount == 3 && !history.canRedo)
        project = try required(history.undo(current: project))
        project = try required(history.undo(current: project))
        project = try required(history.undo(current: project))
        #expect(project == original && !history.canUndo && history.redoCount == 3)
    }

    @Test func musicalMovesSplitsAndTempoEditsRetainAnchorsWithoutStretchingAudio() throws {
        var project = fixture()
        let trackID = project.tracks[0].id, clipID = project.tracks[0].clips[0].id
        project = try required(ProjectEditing.applying(.setTrackTimeBase(trackID, .musical), to: project)).project
        #expect(project.tracks[0].clips[0].musicalPosition == 2)
        project = try required(ProjectEditing.applying(.moveClip(clipID, position: 3), to: project)).project
        #expect(project.tracks[0].clips[0].musicalPosition == 6)
        project = try required(ProjectEditing.applying(.splitClip(clipID, at: 4, newClipID: UUID()), to: project)).project
        #expect(project.tracks[0].clips.map(\.musicalPosition) == [6, 8])
        let lengths = project.tracks[0].clips.map(\.duration), offsets = project.tracks[0].clips.map(\.sourceOffset)
        project = try required(ProjectEditing.applying(.replaceTempoMap(TempoMap(events: [TempoEvent(beat: 0, bpm: 60)])), to: project)).project
        #expect(project.tracks[0].clips.map(\.position) == [6, 8])
        #expect(project.tracks[0].clips.map(\.duration) == lengths && project.tracks[0].clips.map(\.sourceOffset) == offsets)
        project = try required(ProjectEditing.applying(.setTrackTimeBase(trackID, .seconds), to: project)).project
        #expect(project.tracks[0].clips.allSatisfy { $0.timeBase == .seconds && $0.musicalPosition == nil })
        project = try required(ProjectEditing.applying(.replaceTempoMap(TempoMap()), to: project)).project
        #expect(project.tracks[0].clips.map(\.position) == [6, 8])
    }

    @Test func mixerAndAutomationCommandsKeepControlDomainsAndLaneIdentity() throws {
        var project = fixture()
        let id = project.tracks[0].id
        for edit in [ProjectEdit.setGain(id, 200), .setPan(id, -5), .toggleMute(id), .toggleSolo(id)] {
            project = try required(ProjectEditing.applying(edit, to: project)).project
        }
        #expect(project.tracks[0].gainDB == 24 && project.tracks[0].pan == -1)
        #expect(project.tracks[0].isMuted && project.tracks[0].isSolo)
        let gain = AutomationLane(parameter: .gainDB, points: [AutomationPoint(time: 0, value: -12)])
        let pan = AutomationLane(parameter: .pan, points: [AutomationPoint(time: 1, value: 0.5)])
        project = try required(ProjectEditing.applying(.replaceAutomation(id, [gain]), to: project)).project
        project = try required(ProjectEditing.applying(.setAutomation(id, pan), to: project)).project
        var replacement = gain; replacement.points[0].value = -3
        project = try required(ProjectEditing.applying(.setAutomation(id, replacement), to: project)).project
        #expect(project.tracks[0].automation == [replacement, pan])
        #expect(project.tracks[0].automation[0].id == gain.id)
    }

    @Test func coalescingUsesSameControlAndRollingHalfSecondWindow() throws {
        var project = fixture(), history = ProjectEditHistory()
        let original = project, id = project.tracks[0].id, start = Date(timeIntervalSince1970: 1_000)
        for (offset, value) in [(0.0, -3.0), (0.25, -6), (0.5, -9)] {
            project = try required(history.apply(.setGain(id, value), to: project, at: start.addingTimeInterval(offset))).project
        }
        #expect(history.undoCount == 1)
        let groupEnd = project
        project = try required(history.apply(.setGain(id, -12), to: project, at: start.addingTimeInterval(1))).project
        #expect(history.undoCount == 2)
        project = try required(history.apply(.setPan(id, 0.5), to: project, at: start.addingTimeInterval(1.1))).project
        #expect(history.undoCount == 3)
        project = try required(history.undo(current: project))
        project = try required(history.undo(current: project))
        #expect(project == groupEnd && history.redoCount == 2)
        project = try required(history.undo(current: project))
        #expect(project == original)
        project = try required(history.apply(.setGain(id, -24), to: project, at: start.addingTimeInterval(1.2))).project
        #expect(history.undoCount == 1 && !history.canRedo)
        #expect(try required(history.undo(current: project)) == original)
    }

    @Test func invalidEditsLeaveHistoryRedoAndSelectionUntouched() throws {
        let original = fixture(), id = original.tracks[0].id, clip = original.tracks[0].clips[0]
        let selection = ProjectSelection(trackID: id, clipID: clip.id)
        var history = ProjectEditHistory()
        let edited = try required(history.apply(.setGain(id, -6), to: original)).project
        #expect(try required(history.undo(current: edited)) == original)
        let invalid: [ProjectEdit] = [
            .moveClip(clip.id, position: .nan), .trimClip(clip.id, end: 2, availableSourceDuration: -1),
            .splitClip(clip.id, at: 2, newClipID: clip.id), .splitClip(clip.id, at: 1, newClipID: UUID()),
            .setGain(id, .infinity), .setPan(id, .nan),
            .replaceTempoMap(TempoMap(events: [TempoEvent(beat: 0, bpm: 0)])),
            .replaceSignatureMap(SignatureMap(events: [SignatureEvent(beat: 0, numerator: 4, denominator: 0)])),
            .replaceAutomation(id, [AutomationLane(parameter: .pan), AutomationLane(parameter: .pan)])
        ]
        for edit in invalid {
            #expect(throws: (any Error).self) { try history.apply(edit, to: original, selection: selection) }
            #expect(history.undoCount == 0 && history.redoCount == 1)
            #expect(selection == ProjectSelection(trackID: id, clipID: clip.id))
        }
        #expect(try history.apply(.moveClip(UUID(), position: 2), to: original) == nil)
        #expect(history.undoCount == 0 && history.redoCount == 1)
        #expect(try required(history.redo(current: original)) == edited)
    }

    @Test func backwardClockStartsANewUndoGroup() throws {
        let original = fixture(), id = original.tracks[0].id
        let now = Date(timeIntervalSince1970: 1_000)
        var history = ProjectEditHistory()
        let first = try required(history.apply(.setGain(id, -3), to: original, at: now)).project
        let second = try required(history.apply(.setGain(id, -6), to: first, at: now.addingTimeInterval(-10))).project
        #expect(history.undoCount == 2)
        #expect(try required(history.undo(current: second)) == first)
        #expect(try required(history.undo(current: first)) == original)
    }

    @Test func historyBoundAndResetDoNotLeakCoalescingAcrossDocuments() throws {
        var project = fixture(), history = ProjectEditHistory()
        let id = project.tracks[0].id
        let first = try required(history.apply(.toggleMute(id), to: project)).project
        project = first
        for _ in 0..<100 { project = try required(history.apply(.toggleMute(id), to: project)).project }
        #expect(history.undoCount == 100)
        for _ in 0..<100 { project = try required(history.undo(current: project)) }
        #expect(project == first && !history.canUndo)
        history.reset()
        let now = Date(timeIntervalSince1970: 2_000)
        _ = try history.apply(.setGain(id, -3), to: project, at: now)
        history.reset()
        _ = try history.apply(.setGain(id, -6), to: project, at: now.addingTimeInterval(0.1))
        #expect(history.undoCount == 1 && !history.canRedo)
    }

    @Test func trackSelectionAndDeleteReconcileWithoutChoosingAnotherTrack() throws {
        var project = fixture()
        let first = project.tracks[0], second = Track(name: "Second", clips: [Clip(mediaPath: "Media/second.wav", name: "Second", duration: 1)])
        project.tracks.append(second)
        var selection = ProjectSelection(trackID: first.id, clipID: first.clips[0].id)
        selection = selection.selectingClip(second.clips[0].id, in: project)
        #expect(selection.trackID == second.id)
        let deleted = try required(ProjectEditing.applying(.deleteEvent(second.clips[0].id), to: project, selection: selection))
        #expect(deleted.selection == ProjectSelection(trackID: second.id))
        #expect(deleted.selection.reconciled(in: deleted.project) == deleted.selection)
        #expect(deleted.selection.reconciled(in: project).clipID == second.clips[0].id)
        #expect(ProjectSelection(trackID: UUID(), clipID: UUID()).reconciled(in: project) ==
                ProjectSelection(trackID: first.id, clipID: first.clips[0].id))
    }

    @Test func deletingUnresolvedEventsRetainsSharedAttachmentUntilItsLastReference() throws {
        let digest = String(repeating: "a", count: 64)
        func record(_ name: String, _ version: Int, _ identity: Int) -> CPRObjectRecord {
            CPRObjectRecord(className: name, version: version, declarationOffset: identity, objectOffset: identity,
                identityOffset: identity, payloadOffset: identity + 4, payloadByteCount: 0, payloadSHA256: digest)
        }
        let file = CPRAudioFileReference(object: record("MAudioFile", 0, 40), filename: "control.wav", directory: "",
            frameCount: 100, sampleSize: 24, frameSize: 6, channels: 2, sampleRateBits: Float(48_000).bitPattern)
        func event(_ identity: Int) -> UnresolvedCPRAudioEvent {
            UnresolvedCPRAudioEvent(id: UUID(), sourceSHA256: digest, event: record("MAudioEvent", 6, identity),
                clip: record("PAudioClip", 4, 20), cluster: record("AudioCluster", 0, 30), name: "Unresolved",
                rawStartBits: 0, rawLengthBits: Double(100).bitPattern, rawOffsetBits: 0, datumTag: 1,
                datumScalarBits: nil, files: [file], segments: [], placement: nil, placementStatus: "Unresolved")
        }
        let first = event(10), second = event(11)
        let attachment = CPRAudioMediaAttachment(id: UUID(), association: "user-selected", sourceSHA256: digest,
            sourceFileIdentity: 40, mediaPath: "Media/control.wav", mediaSHA256: digest, selectedFilename: "control.wav",
            frameCount: 100, sampleRate: 48_000, channels: 2, bitsPerSample: 24, bytesPerFrame: 6)
        let original = Project(tracks: [Track(name: "Source", unresolvedAudioEvents: [first, second])], cprMediaAttachments: [attachment])
        try original.validate()
        var history = ProjectEditHistory()
        let one = try required(history.apply(.deleteEvent(first.id), to: original)).project
        #expect(one.unresolvedAudioEvents == [second] && one.cprMediaAttachments == [attachment])
        let none = try required(history.apply(.deleteEvent(second.id), to: one)).project
        #expect(none.unresolvedAudioEvents.isEmpty && none.cprMediaAttachments.isEmpty)
        #expect(try required(history.undo(current: none)) == one)
        #expect(try required(history.undo(current: one)) == original)
    }

    @Test func nativeTimingRequiresExplicitConversionAndNoopMapsDoNotAddHistory() throws {
        let clock = try NativeTempoClock(fixedBPMBits: Float(120).bitPattern,
            sourceSHA256: String(repeating: "b", count: 64), sourceObjectOffset: 16)
        let original = Project(tempoMap: TempoMap(nativeClock: clock))
        var history = ProjectEditHistory()
        #expect(throws: NativeTempoClockError.self) { try history.apply(.replaceTempoMap(TempoMap()), to: original) }
        #expect(!history.canUndo)
        #expect(try history.apply(.applyMusicalMaps(original.tempoMap, original.signatureMap, convertNativeTiming: false), to: original) == nil)
        let converted = try required(history.apply(.applyMusicalMaps(TempoMap(), original.signatureMap, convertNativeTiming: true), to: original)).project
        #expect(converted.tempoMap.nativeClock == nil && original.tempoMap.nativeClock == clock)
        #expect(try required(history.undo(current: converted)) == original)
        #expect(try ProjectEditing.snappedTime(0.7, in: Project(), grid: .beat) == 0.5)
        #expect(try ProjectEditing.snappedTime(0.7, in: Project(), grid: .beat, relativeTo: 0.1) == 0.6)
    }
}
