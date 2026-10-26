import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

/// Forward-authored envelopes exercise the recovered decoder, not the native
/// product. No reference project, reference executable or old fixture is used.
@Suite struct CPRNativeProjectBindingsTests {
    private func report(_ options: BindingControl.Options = .init()) throws -> CPRNativeProjectBindingReport {
        try CPRNativeProjectBindings.read(container: CPRProject.readContainer(BindingControl.make(options)))
    }

    @Test func countedOrderReferencesAndUnknownsRemainSourceBound() throws {
        var options = BindingControl.Options(); options.extras = true
        let bytes = BindingControl.make(options), container = try CPRProject.readContainer(bytes)
        let value = try CPRNativeProjectBindings.read(container: container)
        let root = value.entries.filter { $0.path.count == 1 }
        #expect(root.map(\.path) == [[0], [1], [2], [3], [4]])
        #expect(root.map { $0.object?.className } == ["UnknownAuthoredNode", "MAudioTrackEvent", "MAudioTrackEvent", nil, "OtherAuthoredNode"])
        #expect(root.map(\.repeatedIdentity) == [false, false, true, false, false])
        #expect(root[1].object?.identityOffset == root[2].object?.identityOffset)
        #expect(root[1].token.byteCount > 4 && root[2].token.byteCount == 4)
        #expect(value.tracks.count == 1)
        #expect(value.sourceSHA256 == container.sha256 && value.sourceByteCount == bytes.count)
        for entry in value.entries {
            #expect(entry.token.sha256 == cprSHA256(bytes.subdata(in: entry.token.offset..<(entry.token.offset + entry.token.byteCount))))
            if let object = entry.object {
                #expect(object.payloadSHA256 == cprSHA256(bytes.subdata(in: object.payloadOffset..<(object.payloadOffset + object.payloadByteCount))))
            }
        }
        #expect(value.issues.contains { $0.code == "opaqueCountedEntry" })
        #expect(value.issues.contains { $0.code == "nullCountedEntry" })
        #expect(value.issues.contains { $0.code == "sharedTrack" })
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        #expect(try JSONDecoder().decode(CPRNativeProjectBindingReport.self, from: encoder.encode(value)) == value)
        #expect(container.originalBytes == bytes)
    }

    @Test func typedResourceAndConditionalSavedCandidates() throws {
        let value = try report(), track = try #require(value.tracks.first)
        #expect(track.resource?.className == "MAudioTrack")
        #expect(track.mTrackVersion == 2 && track.tag == 1 && track.providerIndex == -2)
        #expect(track.providerName == "Authored provider")
        #expect(track.stateRepresentation == "inlineFAttributes" && track.audioFlags == 0x20 && track.stateExtentKnown)
        #expect(track.outputBusValue?.integer == "27")
        #expect(track.outputBusValue?.encoding == "signed32-in-int64")
        #expect(track.volumeValue?.floatingPointBits == "3ff0000000000000")
        #expect(track.busCandidates.count == 1)
        #expect(track.busCandidates[0].savedUID?.integer == "11")
        #expect(track.busCandidates[0].children.map { $0.savedUID?.integer } == ["27", "28"])
        #expect(track.savedDestinationCandidates == [track.busCandidates[0].children[0].span])
        #expect(track.unresolved.contains("savedUIDCandidateOnly"))
        #expect(track.unresolved.contains("runtimeChannelReceiverUnresolved"))
        #expect(track.unresolved.contains("effectiveRoutingUnresolved"))
        #expect(track.unresolved.contains("processingUnresolved"))
        #expect(value.issues.contains { $0.code == "projectCompositionUnresolved" })
        let bytes = try JSONEncoder().encode(value)
        let text = String(decoding: bytes, as: UTF8.self)
        #expect(!text.contains("routeResolved") && !text.contains("canPlay") && !text.contains("gainDB"))
    }

    @Test func bothIndexWidthsAndRetainedStateVariants() throws {
        for version in [UInt16(0), 1, 2] {
            var options = BindingControl.Options(); options.mVersion = version
            options.index = -123; options.marker = version == 1 ? 3 : -88_888
            let track = try #require(report(options).tracks.first)
            #expect(track.mTrackVersion == Int(version) && track.providerIndex == -123)
            #expect(track.audioFlags == 0x20)
            #expect(track.stateRepresentation == (version == 1 ? "serializedStreamV1" : "inlineFAttributes"))
        }
        for marker in [Int32(0), -1, 3, -77_777] {
            var options = BindingControl.Options(); options.marker = marker
            let track = try #require(report(options).tracks.first)
            #expect(track.audioFlags == 0x20 && track.outputBusValue == nil)
            #expect(track.state != nil)
            if marker == -77_777 {
                #expect(track.retainedObject?.className == "OpaqueAuthoredState")
                #expect(track.retainedObjectWord == 9 && track.stateRepresentation == "retainedObject")
            } else if marker > 0 { #expect(track.stateRepresentation == "opaqueSerializedState") }
            else { #expect(track.stateRepresentation == "noRetainedState") }
        }
    }

    @Test func associationTagsNeverInventAChannel() throws {
        for tag in [UInt16(0), 1, 2, 3, 4, 7, 8, 9] {
            var options = BindingControl.Options(); options.tag = tag
            let track = try #require(report(options).tracks.first)
            #expect(track.tag == tag && track.audioFlags == 0x20)
            #expect(track.unresolved.contains("runtimeChannelReceiverUnresolved"))
            #expect(track.secondaryName == (tag == 3 ? "Secondary authored association" : nil))
        }
        for tag in [UInt16(5), 6] {
            var options = BindingControl.Options(); options.tag = tag
            let track = try #require(report(options).tracks.first)
            #expect(track.tag == tag && track.audioFlags == nil)
            #expect(track.stateRepresentation == "legacyAuxiliaryState")
            #expect(track.state != nil && track.outputBusValue == nil)
        }
    }

    @Test func missingZeroNonfiniteAndOutOfRangeStayDistinct() throws {
        var options = BindingControl.Options(); options.fields = []
        let absent = try #require(report(options).tracks.first)
        #expect(absent.outputBusValue == nil && absent.volumeValue == nil)
        options.fields = [.object("OutputBusValue", [.integer("Value", 0)]), .object("Volume", [.number("Value", 0x8000_0000_0000_0000)])]
        let zero = try #require(report(options).tracks.first)
        #expect(zero.outputBusValue?.integer == "0" && zero.savedDestinationCandidates.isEmpty)
        #expect(zero.volumeValue?.floatingPointBits == "8000000000000000" && zero.volumeValue?.finite == true)
        options.fields = [.object("OutputBusValue", [.integer("Value", Int64.max)]), .object("Volume", [.number("Value", 0x7ff8_0000_0000_0042)])]
        let invalid = try #require(report(options).tracks.first)
        #expect(invalid.outputBusValue?.integer == String(Int64.max))
        #expect(invalid.outputBusValue?.encoding == "int64-outside-signed32")
        #expect(invalid.unresolved.contains("outputBusValueOutsideSigned32"))
        #expect(invalid.volumeValue?.floatingPointBits == "7ff8000000000042" && invalid.volumeValue?.finite == false)
        #expect(invalid.unresolved.contains("nonfiniteVolumeValue") && invalid.savedDestinationCandidates.isEmpty)
    }

    @Test func candidateSearchDoesNotInventRecursiveRuntimeLookup() throws {
        var options = BindingControl.Options()
        options.fields = [.object("OutputBusValue", [.integer("Value", 33)]), .object("OutputBus", [
            .integer("Bus UID", 11), .list("Child Bus", [[.integer("Bus UID", 22), .list("Child Bus", [[.integer("Bus UID", 33)]])]])])]
        let track = try #require(report(options).tracks.first)
        #expect(track.busCandidates[0].children[0].children[0].savedUID?.integer == "33")
        #expect(track.savedDestinationCandidates.isEmpty)
        #expect(track.unresolved.contains("savedDestinationMissing"))
        options.fields = [.object("OutputBusValue", [.integer("Value", 11)]),
            .object("OutputBus", [.integer("Bus UID", 11)]), .object("OwnInputBus", [.integer("Bus UID", 11)])]
        let ambiguous = try #require(report(options).tracks.first)
        #expect(ambiguous.savedDestinationCandidates.count == 2)
        #expect(ambiguous.unresolved.contains("savedDestinationAmbiguous"))
    }

    @Test func decoyFieldsAndForeignTypedReceiversAreNotRecovered() throws {
        var options = BindingControl.Options()
        options.fields = [.typed("OutputBusValue", "UnrelatedPlugin", [.integer("Value", 27)]),
            .object("InsertFolder", [.object("Volume", [.number("Value", 1.0.bitPattern)])]),
            .typed("OutputBus", "UnrelatedPlugin", [.integer("Bus UID", 27)])]
        let track = try #require(report(options).tracks.first)
        #expect(track.outputBusValue == nil && track.volumeValue == nil && track.busCandidates.isEmpty)
        #expect(track.unresolved.contains("unsupportedBusProperty:OutputBus"))
        options.resourceClass = "NotAnAudioResource"
        let foreign = try #require(report(options).tracks.first)
        #expect(foreign.resource?.className == "NotAnAudioResource")
        #expect(foreign.tag == nil && foreign.outputBusValue == nil)
    }

    @Test func opaqueCompoundDoesNotPublishAParsedPrefix() throws {
        var options = BindingControl.Options()
        options.fields = [.object("OutputBusValue", [.integer("Value", 27)]), .unsupported("UnprovedBlob")]
        let value = try report(options), track = try #require(value.tracks.first)
        #expect(track.tag == 1 && track.providerIndex == -2)
        #expect(track.state != nil && !track.stateExtentKnown && track.outputBusValue == nil && track.audioFlags == nil)
        #expect(value.issues.contains { $0.code == "unsupportedTrackBinding" })
    }

    @Test func bareDictionariesAndReferencesAreNotTypedBusArrayElements() throws {
        for field in [BindingControl.Field.bareList("Child Bus", [[.integer("Bus UID", 27)]]),
                      .referenceList("Child Bus")] {
            var options = BindingControl.Options()
            options.fields = [.object("OutputBusValue", [.integer("Value", 27)]),
                .object("OutputBus", [.integer("Bus UID", 11), field])]
            let track = try #require(report(options).tracks.first)
            #expect(track.outputBusValue == nil && track.busCandidates.isEmpty && !track.stateExtentKnown)
            #expect(track.unresolved.contains("retainedUnsupportedState"))
        }
        var options = BindingControl.Options()
        options.fields = [.object("OutputBusValue", [.integer("Value", 27)]),
            .object("OutputBus", [.integer("Bus UID", 11), .objectList("Child Bus", [[.integer("Bus UID", 27)]])])]
        let objectList = try #require(report(options).tracks.first)
        #expect(objectList.stateExtentKnown && objectList.outputBusValue?.integer == "27")
        #expect(objectList.busCandidates.isEmpty && objectList.savedDestinationCandidates.isEmpty)
        #expect(objectList.unresolved.contains("retainedUnsupportedState"))
    }

    @Test func auxiliaryNumericArraysAreBoundedAndCannotBecomeScalarCandidates() throws {
        var options = BindingControl.Options()
        options.fields = [.object("OutputBusValue", [.numericArray("Value", 2, [27])]),
            .object("Volume", [.numericArray("Value", 3, [(1.0).bitPattern])]),
            .list("UnrelatedSublists", [[.numericArray("Type", 2, [1, 2])]])]
        let track = try #require(report(options).tracks.first)
        #expect(track.stateExtentKnown && track.audioFlags == 0x20)
        #expect(track.outputBusValue == nil && track.volumeValue == nil)
        options.fields = [.invalidArray("Bad numeric array", 2), .invalidArray("Bad sublist", 5)]
        #expect(throws: CPRProjectError.self) { try report(options) }
        options.fields = [.invalidArray("Bad sublist", 5)]
        #expect(throws: CPRProjectError.self) { try report(options) }
    }

    @Test func auxiliaryStringsAndBinaryStateAreBoundedWithoutInterpretingPayloads() throws {
        var options = BindingControl.Options()
        options.fields = [.blob("Input state", Array("OutputBusValue Volume Bus UID".utf8)),
            .stringList("Labels", ["OutputBusValue", "Volume", "Bus UID"]),
            .object("Volume", [.number("Value", 0.25.bitPattern)])]
        let track = try #require(report(options).tracks.first)
        #expect(track.stateExtentKnown && track.outputBusValue == nil && track.busCandidates.isEmpty)
        #expect(track.volumeValue?.floatingPointBits == "3fd0000000000000")
        for code in [UInt16(4), 7] {
            options.fields = [.invalidArray("Truncated auxiliary state", code)]
            #expect(throws: CPRProjectError.self) { try report(options) }
        }
        options.fields = [.blob("Empty", []), .stringList("Empty", [])]
        #expect(throws: CPRProjectError.self) { try report(options) } // duplicate keys remain invalid
        options.fields = [.blob("Empty blob", []), .stringList("Empty strings", [])]
        #expect(try report(options).tracks.first?.stateExtentKnown == true)
    }

    @Test func malformedExtentsAndDuplicateFieldsFailClosed() throws {
        var options = BindingControl.Options(); options.omitFlags = true
        #expect(throws: CPRProjectError.self) { try report(options) }
        options = .init(); options.resourceTrailing = true
        #expect(throws: CPRProjectError.self) { try report(options) }
        options = .init(); options.fields = [.integer("Duplicate", 1), .integer("Duplicate", 2)]
        #expect(throws: CPRProjectError.self) { try report(options) }
        options = .init(); options.badCount = true
        #expect(throws: CPRProjectError.self) { try report(options) }
        options = .init(); options.hugeFieldCount = true
        #expect(throws: CPRProjectError.self) { try report(options) }
        options = .init(); options.unknownReference = true
        #expect(throws: CPRProjectError.self) { try report(options) }
        options = .init(); options.baseVersions = false
        #expect(throws: CPRProjectError.self) { try report(options) }
    }

    @Test func missingBaseVersionAndUnknownTrackVersionStayOpaque() throws {
        var options = BindingControl.Options(); options.mVersion = nil
        let track = try #require(report(options).tracks.first)
        #expect(track.resource != nil && track.mTrackVersion == nil && track.tag == nil)
        options = .init(); options.trackVersion = 2
        let value = try report(options)
        #expect(value.tracks.isEmpty)
        #expect(value.entries.first?.object?.className == "MAudioTrackEvent")
        #expect(value.entries.first?.object?.version == 2 && value.entries.first?.role == "opaque")
    }

    @Test func emptyAndCyclicHierarchyPreserveStructuralLimits() throws {
        var options = BindingControl.Options(); options.empty = true
        #expect(try report(options).entries.isEmpty)
        options = .init(); options.cyclicFolder = true
        let value = try report(options)
        #expect(value.entries.count == 2 && value.tracks.count == 1)
        #expect(value.issues.contains { $0.code == "cyclicList" })
        options = .init(); options.listWord = 123
        #expect(try report(options).tracks.count == 1)
    }

    @Test func originalChangesInvalidateEverySourceBoundObservation() throws {
        var options = BindingControl.Options()
        let first = try report(options)
        options.index = -3
        let second = try report(options)
        #expect(first.sourceSHA256 != second.sourceSHA256)
        #expect(first.tracks[0].resource?.payloadSHA256 != second.tracks[0].resource?.payloadSHA256)
        #expect(first.entries[0].token.sha256 != second.entries[0].token.sha256)
        #expect(first.tracks[0].outputBusValue == second.tracks[0].outputBusValue)
        #expect(first.tracks[0].providerIndex == -2 && second.tracks[0].providerIndex == -3)
    }

    @Test func rootAncestryIsSeparateFromLaterTrackDeclarations() throws {
        // The forward-authored root declares its own bases; MTrackEvent is
        // first declared at the later audio track, as in the retained headers.
        #expect(try report().tracks.count == 1)
        var options = BindingControl.Options(); options.empty = true
        #expect(try report(options).entries.isEmpty)
        for key in ["MEvent", "MPartEvent", "MGroupEvent"] {
            options = .init(); options.rootBaseOverride = key
            #expect(throws: CPRProjectError.self) { try report(options) }
        }
        options = .init(); options.trackBaseVersion = 3
        let unknown = try report(options)
        #expect(unknown.tracks.isEmpty)
        #expect(unknown.issues.contains { $0.code == "unsupportedTrackBase" })
    }

    @Test func earlierDeviceResourceRegistersBaseWithoutScanningItsOpaqueTail() throws {
        var options = BindingControl.Options(); options.precedingDevice = true; options.mVersion = nil
        let bytes = BindingControl.make(options), value = try report(options)
        let association = try #require(value.resourceAssociations.first)
        #expect(value.resourceAssociations.count == 1)
        #expect(association.track.className == "MDeviceTrackEvent" && association.resource?.className == "MTrack")
        #expect(association.resource?.version == 2 && association.remainingTail.byteCount == 7)
        #expect(association.remainingTail.sha256 == cprSHA256(bytes.subdata(in: association.remainingTail.offset..<(association.remainingTail.offset + association.remainingTail.byteCount))))
        #expect(value.tracks.first?.mTrackVersion == 2)
        #expect(value.tracks.first?.outputBusValue?.integer == "27")
        #expect(value.tracks.first?.unresolved.contains("effectiveRoutingUnresolved") == true)
        options.deviceVersion = 1
        let unknown = try report(options)
        #expect(unknown.resourceAssociations.isEmpty && unknown.tracks.first?.mTrackVersion == nil)
        #expect(unknown.tracks.first?.outputBusValue == nil)
        options.deviceVersion = 0; options.truncatedDevice = true
        #expect(throws: CPRProjectError.self) { try report(options) }
    }

    @Test func laterDeclarationsCannotValidateAnEarlierResource() throws {
        var options = BindingControl.Options(); options.mVersion = nil; options.followingDevice = true
        let laterDevice = try report(options)
        #expect(laterDevice.resourceAssociations.count == 1)
        #expect(laterDevice.tracks.count == 1)
        #expect(laterDevice.tracks[0].mTrackVersion == nil)
        #expect(laterDevice.tracks[0].outputBusValue == nil)
        #expect(laterDevice.tracks[0].volumeValue == nil)
        #expect(laterDevice.tracks[0].busCandidates.isEmpty)
        #expect(laterDevice.tracks[0].unresolved.contains("retainedUnsupportedState"))
        options.followingDevice = false; options.tailMTrackVersion = 2
        let laterTail = try report(options)
        #expect(laterTail.tracks[0].mTrackVersion == nil)
        #expect(laterTail.tracks[0].outputBusValue == nil)
        #expect(laterTail.tracks[0].volumeValue == nil)
        #expect(laterTail.tracks[0].busCandidates.isEmpty)
        // A later matching declaration is harmless when this resource already
        // declares its base; a later conflict still rejects the whole report.
        options.mVersion = 2
        #expect(try report(options).tracks[0].outputBusValue?.integer == "27")
        options.tailMTrackVersion = 1
        #expect(throws: CPRProjectError.self) { try report(options) }
    }

    @Test func immediateResourceParsingPreservesCountedTrackPreorder() throws {
        var options = BindingControl.Options(); options.nestedAudio = true
        let value = try report(options)
        #expect(value.entries.map(\.path) == [[0], [0, 0]])
        #expect(value.tracks.map { $0.track.identityOffset } == value.entries.compactMap { $0.object?.identityOffset })
        #expect(value.tracks.count == 2 && value.tracks.allSatisfy { $0.outputBusValue?.integer == "27" })
    }

    @Test func publicInspectionRevalidatesSourceAndHistoricalReportWithoutWriting() throws {
        let fm = FileManager.default
        let base = ProcessInfo.processInfo.environment["REBASE_TEST_WORK_ROOT"].map { URL(fileURLWithPath: $0) } ?? fm.temporaryDirectory
        let root = base.appendingPathComponent("BindingInspection-" + UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        #expect(try CPRNativeProjectBindings.inspectPreserved(in: root) == nil)
        let source = root.appendingPathComponent("AuthoredBindings.cpr")
        let bytes = BindingControl.make(.init()); try bytes.write(to: source)
        let original = try CPRNativeProjectBindings.inspect(from: source)
        var changedOptions = BindingControl.Options(); changedOptions.index = -37
        let changedBytes = BindingControl.make(changedOptions)
        try changedBytes.write(to: source)
        #expect(try CPRNativeProjectBindings.inspect(from: source).sourceSHA256 != original.sourceSHA256)

        let container = try CPRProject.readContainer(bytes)
        let recovery = try CPRRecoveryV1(container: container).decode(sourceName: "AuthoredBindings.cpr")
        let historical = CPRInspection(schemaVersion: 1, interpretationProfile: nil, nativeClock: nil,
            sourceName: "AuthoredBindings.cpr", sourceSHA256: container.sha256,
            sourceByteCount: bytes.count, sections: container.sections,
            recoveredFacts: recovery.facts, metadataFacts: recovery.metadata,
            recoveredTracks: recovery.tracks, nativeObjects: recovery.objects,
            applicationDefaults: recovery.defaults, unsupported: recovery.unsupported,
            recoveredProject: recovery.project)
        let preserved = root.appendingPathComponent(CPRProject.originalRelativePath)
        let reportURL = root.appendingPathComponent(CPRProject.reportRelativePath)
        try fm.createDirectory(at: preserved.deletingLastPathComponent(), withIntermediateDirectories: true)
        try bytes.write(to: preserved)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let reportBytes = try encoder.encode(historical); try reportBytes.write(to: reportURL)
        #expect(try CPRProject.compatibilityReport(from: root) == historical)
        #expect(try CPRNativeProjectBindings.inspectPreserved(in: root) == original)
        #expect(try Data(contentsOf: preserved) == bytes)
        #expect(try Data(contentsOf: reportURL) == reportBytes)
        try changedBytes.write(to: preserved)
        #expect(throws: CPRProjectError.self) { try CPRNativeProjectBindings.inspectPreserved(in: root) }
        try bytes.write(to: preserved)
        var tampered = try #require(JSONSerialization.jsonObject(with: reportBytes) as? [String: Any])
        tampered["applicationDefaults"] = ["Unverified changed historical meaning"]
        let tamperedBytes = try JSONSerialization.data(withJSONObject: tampered, options: [.sortedKeys])
        try tamperedBytes.write(to: reportURL)
        #expect(throws: CPRProjectError.self) { try CPRNativeProjectBindings.inspectPreserved(in: root) }
        #expect(try Data(contentsOf: reportURL) == tamperedBytes)
    }
}

enum BindingControl {
    indirect enum Field {
        case integer(String, Int64)
        case number(String, UInt64)
        case text(String, String)
        case object(String, [Field])
        case typed(String, String, [Field])
        case list(String, [[Field]])
        case objectList(String, [[Field]])
        case numericArray(String, UInt16, [UInt64])
        case invalidArray(String, UInt16)
        case blob(String, [UInt8])
        case stringList(String, [String])
        case bareList(String, [[Field]])
        case referenceList(String)
        case unsupported(String)
    }
    struct Options {
        var mVersion: UInt16? = 2
        var tag: UInt16 = 1
        var index: Int32 = -2
        var marker: Int32 = -88_888
        var resourceClass = "MAudioTrack"
        var trackVersion: UInt16 = 1
        var fields: [Field] = [
            .object("OutputBusValue", [.integer("Value", 27)]),
            .object("Volume", [.number("Value", 1.0.bitPattern)]),
            .object("OutputBus", [.integer("Bus UID", 11), .integer("Bus Type", 1), .text("Name", "Authored output"),
                .list("Child Bus", [[.integer("Bus UID", 27)], [.integer("Bus UID", 28)]])])]
        var extras = false
        var omitFlags = false
        var resourceTrailing = false
        var badCount = false
        var hugeFieldCount = false
        var unknownReference = false
        var empty = false
        var baseVersions = true
        var rootBaseOverride: String?
        var trackBaseVersion: UInt16 = 2
        var precedingDevice = false
        var followingDevice = false
        var tailMTrackVersion: UInt16?
        var nestedAudio = false
        var deviceVersion: UInt16 = 0
        var truncatedDevice = false
        var cyclicFolder = false
        var listWord: UInt16 = 0
    }
    /// A historical authored package lets app inspections exercise frozen
    /// replay without pretending that the current importer admitted this shape.
    static func package(at root: URL, options: Options = .init()) throws -> Project {
        let bytes = make(options), container = try CPRProject.readContainer(bytes)
        let recovery = try CPRRecoveryV1(container: container).decode(sourceName: "AuthoredBindings.cpr")
        let report = CPRInspection(schemaVersion: 1, interpretationProfile: nil, nativeClock: nil,
            sourceName: "AuthoredBindings.cpr", sourceSHA256: container.sha256, sourceByteCount: bytes.count,
            sections: container.sections, recoveredFacts: recovery.facts, metadataFacts: recovery.metadata,
            recoveredTracks: recovery.tracks, nativeObjects: recovery.objects, applicationDefaults: recovery.defaults,
            unsupported: recovery.unsupported, recoveredProject: recovery.project)
        let source = root.appendingPathComponent(CPRProject.originalRelativePath)
        try FileManager.default.createDirectory(at: source.deletingLastPathComponent(), withIntermediateDirectories: true)
        try bytes.write(to: source)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(report).write(to: root.appendingPathComponent(CPRProject.reportRelativePath))
        let project = Project(name: "Authored structure review", tracks: [Track(name: "Application track")])
        try ProjectStore.save(project, to: root)
        return project
    }
    static func make(_ options: Options) -> Data {
        let writer = Writer()
        func device() {
            writer.base("MTrackEvent", options.trackBaseVersion)
            writer.object("device", "MDeviceTrackEvent", version: options.deviceVersion) {
                writer.zeros(26)
                writer.object("deviceNode", "MListNode") {
                    writer.string("Authored device"); writer.u32(1); writer.u64(1.0.bitPattern); writer.u32(0)
                }
                if !options.truncatedDevice {
                    writer.u32(0)
                    writer.object("deviceResource", "MTrack", version: 2) { writer.zeros(3) }
                    writer.zeros(7) // Explicitly opaque common/subclass tail.
                }
            }
        }
        func resource() {
            if let version = options.mVersion { writer.base("MTrack", version) }
            writer.object("resource", options.resourceClass) {
                writer.u16(options.tag); writer.string("Authored provider")
                if (options.mVersion ?? 2) >= 1 { writer.u32(UInt32(bitPattern: options.index)) }
                else { writer.u16(UInt16(bitPattern: Int16(options.index))) }
                if [1, 8].contains(options.tag) {
                    writer.u32(UInt32(bitPattern: options.marker))
                    if options.mVersion == 1 {
                        if options.marker > 0 { writer.zeros(Int(options.marker)) }
                    } else if options.marker == -88_888 {
                        if options.hugeFieldCount { writer.u32(10_001) } else { writer.fields(options.fields) }
                    } else if options.marker == -77_777 {
                        writer.object("retained", "OpaqueAuthoredState") { writer.zeros(3) }; writer.u16(9)
                    } else if options.marker > 0 { writer.zeros(Int(options.marker)) }
                } else if options.tag == 3 { writer.string("Secondary authored association") }
                else if [5, 6].contains(options.tag) { writer.zeros(7) }
                if !options.omitFlags { writer.u16(0x20) }
                if options.resourceTrailing { writer.zeros(1) }
            }
        }
        writer.object("arrangement", "PArrangement", version: 4) {
            if options.baseVersions {
                for (name, version) in [("MGroupEvent", UInt16(0)), ("MPartEvent", 1), ("MEvent", 1)] {
                    writer.base(name, options.rootBaseOverride == name ? version + 1 : version)
                }
            }
            writer.object("root", "MRoot", version: 6) {
                writer.zeros(26)
                writer.object("rootList", "MTrackList") {
                    writer.string(""); writer.u32(1); writer.u64(1.0.bitPattern); writer.u16(options.listWord)
                    writer.u32(options.badCount ? 999 : options.empty ? 0 : options.extras ? 5 : options.cyclicFolder || options.precedingDevice || options.followingDevice ? 2 : 1)
                    if !options.empty {
                        if options.extras { writer.object("unknown", "UnknownAuthoredNode") { writer.zeros(3) } }
                        if options.precedingDevice { device() }
                        writer.base("MTrackEvent", options.trackBaseVersion)
                        writer.object("audio", "MAudioTrackEvent", version: options.trackVersion) {
                            writer.zeros(26)
                            if options.unknownReference { writer.u32(0x123456) }
                            else {
                                writer.object("audioList", "MListNode") {
                                    writer.string("Authored track"); writer.u32(1); writer.u64(1.0.bitPattern); writer.u32(options.nestedAudio ? 1 : 0)
                                    if options.nestedAudio {
                                        writer.base("MTrackEvent", options.trackBaseVersion)
                                        writer.object("nestedAudio", "MAudioTrackEvent", version: options.trackVersion) {
                                            writer.zeros(26)
                                            writer.object("nestedList", "MListNode") {
                                                writer.string("Authored child track"); writer.u32(1); writer.u64(1.0.bitPattern); writer.u32(0)
                                            }
                                            writer.u32(0); resource(); writer.u32(0); writer.u64(0)
                                            writer.object("nestedAutomation", "MAutomationNode", version: 1) {}; writer.u32(0)
                                        }
                                    }
                                }
                            }
                            writer.u32(0); resource(); writer.u32(0); writer.u64(0)
                            if let version = options.tailMTrackVersion { writer.base("MTrack", version) }
                            writer.object("automation", "MAutomationNode", version: 1) {}; writer.u32(0)
                        }
                        if options.followingDevice { device() }
                        if options.extras {
                            writer.reference("audio"); writer.u32(0)
                            writer.object("other", "OtherAuthoredNode") { writer.string("OutputBusValue") }
                        }
                        if options.cyclicFolder {
                            writer.object("folder", "MFolderTrack") { writer.zeros(26); writer.reference("rootList") }
                        }
                    }
                }
            }
        }
        return writer.container()
    }

    private final class Writer {
        var bytes = Data(), identities: [String: Int] = [:]
        func integer<T: FixedWidthInteger>(_ value: T) { var v = value.bigEndian; bytes.append(withUnsafeBytes(of: &v) { Data($0) }) }
        func u16(_ value: UInt16) { integer(value) }
        func u32(_ value: UInt32) { integer(value) }
        func u64(_ value: UInt64) { integer(value) }
        func zeros(_ count: Int) { bytes.append(Data(repeating: 0, count: count)) }
        func string(_ text: String) { u32(UInt32(text.utf8.count + 1)); bytes.append(contentsOf: text.utf8); bytes.append(0) }
        func base(_ name: String, _ version: UInt16) { u32(0xffff_fffe); string(name); u16(version) }
        func reference(_ name: String) { u32(UInt32(identities[name]!)) }
        func object(_ label: String, _ name: String, version: UInt16 = 0, body: () -> Void) {
            u32(.max); string(name); u16(version)
            let identity = bytes.count; identities[label] = identity; u32(0)
            let start = bytes.count; body()
            var size = UInt32(bytes.count - start).bigEndian
            bytes.replaceSubrange(identity..<(identity + 4), with: withUnsafeBytes(of: &size) { Data($0) })
        }
        func fields(_ fields: [Field]) {
            u32(UInt32(fields.count))
            for field in fields {
                switch field {
                case .integer(let name, let value): string(name); u16(1); u64(UInt64(bitPattern: value))
                case .number(let name, let bits): string(name); u16(4); u64(bits)
                case .text(let name, let value): string(name); u16(8); string(value)
                case .object(let name, let nested): string(name); u16(2); u16(6); self.fields(nested)
                case .typed(let name, let type, let nested): string(name); u16(2); u16(20); string(type); u64(123); self.fields(nested)
                case .list(let name, let items):
                    string(name); u16(2); u16(5); u32(UInt32(items.count))
                    for item in items { self.fields(item) }
                case .objectList(let name, let items):
                    string(name); u16(2); u16(201); u32(UInt32(items.count))
                    for (index, item) in items.enumerated() { u16(20); string("FAttributes"); u64(UInt64(index + 1)); self.fields(item) }
                case .numericArray(let name, let type, let values):
                    string(name); u16(2); u16(type); u32(UInt32(values.count)); for value in values { u64(value) }
                case .invalidArray(let name, let type): string(name); u16(2); u16(type); u32(UInt32.max)
                case .blob(let name, let value): string(name); u16(2); u16(7); u32(UInt32(value.count)); bytes.append(contentsOf: value)
                case .stringList(let name, let values): string(name); u16(2); u16(4); u32(UInt32(values.count)); for value in values { string(value) }
                case .bareList(let name, let items):
                    string(name); u16(2); u16(201); u32(UInt32(items.count))
                    for item in items { u16(6); self.fields(item) }
                case .referenceList(let name): string(name); u16(2); u16(201); u32(1); u16(21); u64(1)
                case .unsupported(let name): string(name); u16(2); u16(9); zeros(4)
                }
            }
        }
        func container() -> Data {
            func word(_ value: UInt32) -> Data { var v = value.bigEndian; return withUnsafeBytes(of: &v) { Data($0) } }
            func name(_ text: String) -> Data { word(UInt32(text.utf8.count)) + Data(text.utf8) }
            let root = name("Arrangement1") + name("PArrangement")
            let sections = Data("ROOT".utf8) + word(UInt32(root.count)) + root + Data("ARCH".utf8) + word(UInt32(bytes.count)) + bytes
            return Data("RIFF".utf8) + word(UInt32(sections.count)) + Data("NUND".utf8) + sections
        }
    }
}
