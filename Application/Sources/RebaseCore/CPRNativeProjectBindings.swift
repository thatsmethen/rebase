import Foundation

/// A range in the immutable original, never a path or a reserialized value.
public struct CPRNativeBindingSpan: Codable, Equatable {
    public let offset: Int
    public let byteCount: Int
    public let sha256: String
}

public struct CPRNativeRootEntry: Codable, Equatable {
    public let path: [Int]
    public let parentListIdentity: Int
    public let token: CPRNativeBindingSpan
    public let object: CPRObjectRecord?
    public let repeatedIdentity: Bool
    public let role: String
}

public struct CPRNativeListBinding: Codable, Equatable {
    public let object: CPRObjectRecord
    public let name: String
    public let datumKind: Int32
    public let timingObjects: [CPRObjectRecord?]
    public let scalarBits: String?
    public let compatibilityWord: UInt16?
    public let childCount: Int
}

/// The saved numeric representation is not a DSP unit. In particular, a
/// floating-point Volume is not the application's gainDB or a unity proof.
public struct CPRNativeSavedNumber: Codable, Equatable {
    public let encoding: String
    public let integer: String?
    public let floatingPointBits: String?
    public let finite: Bool
    public let span: CPRNativeBindingSpan
}

public struct CPRNativeBindingIssue: Codable, Equatable {
    public let code: String
    public let objectIdentity: Int?
    public let span: CPRNativeBindingSpan
    public let detail: String
}

public struct CPRNativeBusCandidate: Codable, Equatable {
    public let path: [String]
    public let span: CPRNativeBindingSpan
    public let savedUID: CPRNativeSavedNumber?
    public let busType: CPRNativeSavedNumber?
    public let name: String?
    public let children: [CPRNativeBusCandidate]
    /// The property has a conditional native bus receiver. This is not proof
    /// that the source project's channel selected that receiver at restoration.
    public let scope: String
}

public struct CPRNativeTrackBinding: Codable, Equatable {
    public let track: CPRObjectRecord
    public let resource: CPRObjectRecord?
    public let mTrackVersion: Int?
    public let tag: UInt16?
    public let providerName: String?
    public let providerIndex: Int32?
    public let secondaryName: String?
    public let stateRepresentation: String
    public let state: CPRNativeBindingSpan?
    public let stateExtentKnown: Bool
    public let retainedObject: CPRObjectRecord?
    public let retainedObjectWord: UInt16?
    public let audioFlags: UInt16?
    public let outputBusValue: CPRNativeSavedNumber?
    public let volumeValue: CPRNativeSavedNumber?
    public let busCandidates: [CPRNativeBusCandidate]
    public let savedDestinationCandidates: [CPRNativeBindingSpan]
    public let unresolved: [String]
}

/// The resource slot read by the verified common MTrackEvent reader. The
/// remaining subclass/version tail is retained, never searched for attributes.
public struct CPRNativeTrackResourceAssociation: Codable, Equatable {
    public let track: CPRObjectRecord
    public let resource: CPRObjectRecord?
    public let prefix: CPRNativeBindingSpan
    public let remainingTail: CPRNativeBindingSpan
    public let scope: String
}

/// Static saved-state observations only. This report deliberately has no
/// playable flag, host bus IDs or application mixer defaults. Existing import,
/// source auditions, playback and interpretation profiles are unchanged.
public struct CPRNativeProjectBindingReport: Codable, Equatable {
    public let schemaVersion: Int
    public let sourceSHA256: String
    public let sourceByteCount: Int
    public let section: CPRSection
    public let arrangement: CPRObjectRecord
    public let root: CPRObjectRecord
    public let rootList: CPRObjectRecord
    public let lists: [CPRNativeListBinding]
    public let entries: [CPRNativeRootEntry]
    public let tracks: [CPRNativeTrackBinding]
    public let resourceAssociations: [CPRNativeTrackResourceAssociation]
    public let issues: [CPRNativeBindingIssue]
    public let nativeObjects: [CPRObjectRecord]
}

/// Recovered entry points: MTrackList reader101759190/accessor101758eec;
/// MTrack reader101744d58; MAudioTrack reader1001fc8b0; channel state101d75bcc;
/// bus adapter101ee9d10→10045b2d0→101f2e314→101f30b34.
/// A conditional receiver is never promoted to effective channel/routing/DSP.
public enum CPRNativeProjectBindings {
    public static func inspect(from source: URL) throws -> CPRNativeProjectBindingReport {
        try read(container: CPRProject.readSource(source))
    }

    /// A fresh saved-binding view, separate from the historical import report
    /// and from subsequent application edits. This never rewrites either file.
    /// The caller still owns current application manifest/revision validation.
    public static func inspectPreserved(in projectRoot: URL) throws -> CPRNativeProjectBindingReport? {
        guard let baseline = try CPRProject.compatibilityReport(from: projectRoot) else { return nil }
        let root = projectRoot.standardizedFileURL.resolvingSymlinksInPath()
        let source = root.appendingPathComponent(CPRProject.originalRelativePath)
        let container = try CPRProject.readSource(source)
        guard container.sha256 == baseline.sourceSHA256,
              container.originalBytes.count == baseline.sourceByteCount,
              container.sections == baseline.sections else {
            throw CPRProjectError.invalid("The preserved source changed after compatibility verification.")
        }
        return try read(container: container)
    }

    public static func read(container: CPRContainer) throws -> CPRNativeProjectBindingReport {
        guard let section = container.sections.first(where: { $0.name == "Arrangement1" }),
              section.className == "PArrangement" else {
            throw CPRProjectError.unsupported("Native bindings require a counted PArrangement section.")
        }
        return try NativeBindingDecoder(container: container, section: section).read()
    }
}

private final class NativeBindingDecoder {
    let container: CPRContainer
    let section: CPRSection
    let archive: CPRArchive
    var knownOffsets: [Int: CPRNativeObject] = [:]
    var versions: [String: Set<Int>] = [:]
    var entries: [CPRNativeRootEntry] = []
    var lists: [CPRNativeListBinding] = []
    var audioBindings: [(ordinal: Int, binding: CPRNativeTrackBinding)] = []
    var resourceAssociations: [CPRNativeTrackResourceAssociation] = []
    var issues: [CPRNativeBindingIssue] = []
    var visited = Set<Int>()
    var active = Set<Int>()
    var occurrenceIDs = Set<Int>()
    var fieldBudget = 10_000
    let trackVersions = ["MFolderTrack": 0, "MDeviceTrackEvent": 0,
        "MAudioTrackEvent": 1, "MMidiTrackEvent": 4, "MInstrumentTrackEvent": 4,
        "MSamplerTrackEvent": 4, "MDrumTrackEvent": 4]

    init(container: CPRContainer, section: CPRSection) {
        self.container = container; self.section = section
        archive = CPRArchive(data: container.originalBytes, section: section)
    }

    func span(_ lower: Int, _ upper: Int) -> CPRNativeBindingSpan {
        CPRNativeBindingSpan(offset: lower, byteCount: upper - lower,
            sha256: cprSHA256(archive.data.subdata(in: lower..<upper)))
    }

    func issue(_ code: String, _ object: CPRNativeObject, _ detail: String) {
        issues.append(CPRNativeBindingIssue(code: code, objectIdentity: object.descriptor.identityOffset,
            span: span(object.descriptor.payloadOffset, object.end), detail: detail))
    }

    func object(_ reader: inout CPRCursor) throws -> CPRNativeObject? {
        if let known = knownOffsets[reader.position] {
            guard known.end <= reader.upper else { throw CPRProjectError.invalid("Binding object crosses its parent.") }
            reader.position = known.end; return known
        }
        let value = try archive.readObject(&reader)
        if let value, knownOffsets[value.descriptor.objectOffset] == nil {
            knownOffsets[value.descriptor.objectOffset] = value
            try captureDeclarations(value)
        }
        return value
    }

    /// Only registered envelope boundaries are visited; no class-name scan.
    func captureDeclarations(_ object: CPRNativeObject) throws {
        let record = object.descriptor
        var header = CPRCursor(data: archive.data, lower: record.objectOffset, upper: record.identityOffset)
        for _ in 0..<64 {
            let token = try header.u32()
            var declaration: CPRCursor
            if token == 0xffff_fffe || token == 0xffff_ffff { declaration = header }
            else if token & 0x8000_0000 != 0 {
                let offset = archive.start + Int(token & 0x7fff_ffff)
                guard offset >= archive.start, offset < record.objectOffset else {
                    throw CPRProjectError.invalid("Binding class reference is not backward.")
                }
                declaration = CPRCursor(data: archive.data, lower: offset, upper: archive.end)
                let marker = try declaration.u32()
                guard marker == 0xffff_ffff || marker == 0xffff_fffe else {
                    throw CPRProjectError.invalid("Binding class reference has no declaration.")
                }
            } else { throw CPRProjectError.invalid("Binding definition has no class header.") }
            let name = try declaration.className(), version = Int(try declaration.u16())
            versions[name, default: []].insert(version)
            if token == 0xffff_fffe { header = declaration; continue }
            if token == 0xffff_ffff { header = declaration }
            guard header.position == record.identityOffset, name == record.className, version == record.version else {
                throw CPRProjectError.invalid("Binding class header disagrees with its object.")
            }
            return
        }
        throw CPRProjectError.unsupported("Excessive binding class chain.")
    }

    func read() throws -> CPRNativeProjectBindingReport {
        var header = CPRCursor(data: archive.data, lower: archive.start, upper: archive.end)
        guard let arrangement = try object(&header), header.position == header.upper,
              arrangement.descriptor.className == "PArrangement", arrangement.descriptor.version == 4 else {
            throw CPRProjectError.unsupported("Native bindings require PArrangement version 4.")
        }
        var body = archive.body(arrangement)
        guard let root = try object(&body), root.descriptor.className == "MRoot", root.descriptor.version == 6 else {
            throw CPRProjectError.unsupported("Native bindings require MRoot version 6.")
        }
        guard versions["MEvent"] == [1], versions["MPartEvent"] == [1], versions["MGroupEvent"] == [0] else {
            throw CPRProjectError.unsupported("Root binding prefixes require observed MEvent v1, MPartEvent v1 and MGroupEvent v0 declarations.")
        }
        var fields = archive.body(root)
        _ = try fields.bytes(26)
        guard let list = try object(&fields), list.descriptor.className == "MTrackList", list.descriptor.version == 0 else {
            throw CPRProjectError.unsupported("Native bindings require a counted MTrackList version 0.")
        }
        try walk(list, path: [], depth: 0)
        // Resources are parsed at their byte position; report tracks retain
        // the counted hierarchy's preorder, including parent tracks.
        var bindings = audioBindings.sorted { $0.ordinal < $1.ordinal }.map(\.binding)
        // A conflicting declaration encountered later cannot retroactively
        // validate an earlier interpretation. The whole report is rejected.
        for name in ["MEvent", "MPartEvent", "MGroupEvent", "MTrackEvent", "MTrack"] where (versions[name]?.count ?? 0) > 1 {
            throw CPRProjectError.unsupported("Conflicting \(name) versions in native bindings.")
        }
        // Native collection lookup examines each parent and its direct children;
        // a deeper descendant is retained but cannot become a match here.
        let destinations = bindings.flatMap { $0.busCandidates }.flatMap { [$0] + $0.children }
        bindings = bindings.map { binding in
            let uid = binding.outputBusValue?.integer
            let candidates = uid == nil || uid == "0" ? [] : destinations.filter {
                $0.savedUID?.integer == uid && $0.savedUID?.encoding == "signed32-in-int64"
            }.map(\.span)
            var unresolved = binding.unresolved
            if let uid, uid != "0" {
                unresolved.append(candidates.count == 1 ? "savedUIDCandidateOnly" : candidates.isEmpty ? "savedDestinationMissing" : "savedDestinationAmbiguous")
            }
            return copy(binding, candidates: candidates, unresolved: unresolved)
        }
        issue("projectCompositionUnresolved", root,
            "Runtime channel receivers, full bus-registry membership, restoration options, processing, clocks and mix accumulation remain unproved; saved candidates do not authorize playback.")
        return CPRNativeProjectBindingReport(schemaVersion: 1, sourceSHA256: container.sha256,
            sourceByteCount: container.originalBytes.count, section: section,
            arrangement: arrangement.descriptor, root: root.descriptor, rootList: list.descriptor,
            lists: lists, entries: entries, tracks: bindings, resourceAssociations: resourceAssociations, issues: issues,
            nativeObjects: archive.objects.values.map(\.descriptor).sorted { $0.identityOffset < $1.identityOffset })
    }

    func walk(_ list: CPRNativeObject, path: [Int], depth: Int) throws {
        guard depth <= 32 else { throw CPRProjectError.unsupported("Binding hierarchy exceeds 32 levels.") }
        let identity = list.descriptor.identityOffset
        if active.contains(identity) { issue("cyclicList", list, "Counted list cycle retained without recursion."); return }
        if !visited.insert(identity).inserted { issue("sharedList", list, "Repeated counted list retained without duplicating its descendants."); return }
        guard ["MTrackList", "MListNode"].contains(list.descriptor.className), list.descriptor.version == 0 else {
            issue("unsupportedList", list, "Unknown counted-node class/version retained."); return
        }
        active.insert(identity); defer { active.remove(identity) }
        var reader = archive.body(list)
        let name = try reader.nativeString(), datumKind = try reader.i32()
        var timing: [CPRObjectRecord?] = [], scalar: String?
        switch datumKind {
        case 0, 17: timing = [try object(&reader)?.descriptor, try object(&reader)?.descriptor]
        case 1: scalar = String(format: "%016llx", try reader.number().bitPattern)
        default: issue("unsupportedDatum", list, "Unknown list datum leaves the complete list body opaque."); return
        }
        let word = list.descriptor.className == "MTrackList" ? try reader.u16() : nil
        let count = Int(try reader.u32())
        guard count <= 10_000 - entries.count, count <= (reader.upper - reader.position) / 4 else {
            throw CPRProjectError.invalid("Excessive or truncated counted binding list.")
        }
        lists.append(CPRNativeListBinding(object: list.descriptor, name: name, datumKind: datumKind,
            timingObjects: timing, scalarBits: scalar, compatibilityWord: word, childCount: count))
        for ordinal in 0..<count {
            guard entries.count < 10_000 else { throw CPRProjectError.unsupported("Binding occurrences exceed 10000.") }
            let start = reader.position, child = try object(&reader), nextPath = path + [ordinal]
            let repeated = child.map { !occurrenceIDs.insert($0.descriptor.identityOffset).inserted } ?? false
            let supportedTrack = child.map { trackVersions[$0.descriptor.className] == $0.descriptor.version } ?? false
            entries.append(CPRNativeRootEntry(path: nextPath, parentListIdentity: identity,
                token: span(start, reader.position), object: child?.descriptor, repeatedIdentity: repeated,
                role: child == nil ? "null" : supportedTrack ? "track" : "opaque"))
            guard let child else { issue("nullCountedEntry", list, "Null child retained at its counted ordinal."); continue }
            guard supportedTrack else { issue("opaqueCountedEntry", child, "Unknown or non-track counted object is retained, not assumed inaudible."); continue }
            if repeated { issue("sharedTrack", child, "Repeated track identity retained without duplicate semantic decoding."); continue }
            guard versions["MEvent"] == [1], versions["MTrackEvent"] == [2] else {
                issue("unsupportedTrackBase", child, "Track prefixes require observed MEvent v1 and MTrackEvent v2 declarations."); continue
            }
            let bindingOrdinal = entries.count - 1
            var event = archive.body(child)
            _ = try event.bytes(26)
            guard let node = try object(&event) else { throw CPRProjectError.invalid("Counted track has no node.") }
            try walk(node, path: nextPath, depth: depth + 1)
            // The resource follows its counted node in the saved stream.
            // Decode now: a later sibling cannot supply missing declarations.
            if child.descriptor.className == "MAudioTrackEvent" {
                audioBindings.append((bindingOrdinal, try readTrack(child)))
            }
            // MDeviceTrackEvent's verified primary +0x98 slot is directly
            // MTrackEvent reader10174b638. Consume only its common resource
            // prefix to register declarations before later track resources.
            if child.descriptor.className == "MDeviceTrackEvent" {
                try skipNumericAttributes(&event)
                let resource = try object(&event)
                resourceAssociations.append(CPRNativeTrackResourceAssociation(track: child.descriptor,
                    resource: resource?.descriptor, prefix: span(child.descriptor.payloadOffset, event.position),
                    remainingTail: span(event.position, event.upper),
                    scope: "savedMTrackSlot;runtimeReceiverAndRemainingTailUnresolved"))
            }
        }
        guard reader.position == reader.upper else { throw CPRProjectError.invalid("Trailing counted binding-list bytes.") }
    }

    func readTrack(_ track: CPRNativeObject) throws -> CPRNativeTrackBinding {
        var resource: CPRNativeObject?
        var mVersion: Int?, tag: UInt16?, provider: String?, index: Int32?, secondary: String?
        var representation = "unresolved", state: CPRNativeBindingSpan?, retained: CPRObjectRecord?, retainedWord: UInt16?, flags: UInt16?
        var stateExtentKnown = false
        var route: CPRNativeSavedNumber?, volume: CPRNativeSavedNumber?, buses: [CPRNativeBusCandidate] = []
        var unresolved = ["runtimeChannelReceiverUnresolved", "effectiveRoutingUnresolved", "processingUnresolved"]
        do {
            guard versions["MEvent"] == [1], versions["MTrackEvent"] == [2] else {
                throw CPRProjectError.unsupported("Track bindings require observed MEvent v1 and MTrackEvent v2 base declarations.")
            }
            var wrapper = archive.body(track)
            _ = try wrapper.bytes(26); _ = try object(&wrapper)
            try skipNumericAttributes(&wrapper)
            resource = try object(&wrapper)
            // Include this resource's own header, but never declarations from
            // subsequent automation or fade objects in the track tail.
            let resourceVersions = versions["MTrack"]
            guard let resource, resource.descriptor.className == "MAudioTrack", resource.descriptor.version == 0 else {
                throw CPRProjectError.unsupported("Audio-track resource is not typed MAudioTrack v0.")
            }
            _ = try wrapper.i32(); _ = try wrapper.u64()
            guard let automation = try object(&wrapper), automation.descriptor.className == "MAutomationNode", automation.descriptor.version == 1 else {
                throw CPRProjectError.unsupported("Unknown automation-node envelope in audio-track tail.")
            }
            _ = try object(&wrapper) // Local auto-fade is preserved, not evaluated here.
            guard wrapper.position == wrapper.upper else { throw CPRProjectError.invalid("Trailing audio-track binding tail.") }
            guard let observed = resourceVersions, observed.count == 1, let version = observed.first,
                  [0, 1, 2].contains(version) else {
                throw CPRProjectError.unsupported("Missing, conflicting or unverified MTrack base version.")
            }
            mVersion = version
            var reader = archive.body(resource)
            tag = try reader.u16(); provider = try reader.nativeString()
            index = version >= 1 ? try reader.i32() : Int32(Int16(bitPattern: try reader.u16()))
            var fields: [BindingField]?
            switch tag! {
            case 1, 8:
                let markerStart = reader.position, marker = try reader.i32()
                // If an unknown compound prevents determining the state end,
                // retain the complete remaining resource rather than a guessed
                // boundary. Successful parsing narrows this span below.
                state = span(markerStart, reader.upper)
                if version == 1 {
                    representation = "serializedStreamV1"
                    if marker > 0 { _ = try reader.bytes(Int(marker)) }
                } else if marker == -88_888 {
                    representation = "inlineFAttributes"
                    fields = try readFields(&reader, depth: 0)
                } else if marker == -77_777 {
                    representation = "retainedObject"
                    retained = try object(&reader)?.descriptor; retainedWord = try reader.u16()
                    unresolved.append("retainedObjectRestorationUnresolved")
                } else if marker > 0 {
                    representation = "opaqueSerializedState"
                    _ = try reader.bytes(Int(marker)); unresolved.append("serializedStateUnresolved")
                } else { representation = "noRetainedState" }
                state = span(markerStart, reader.position)
                stateExtentKnown = true
            case 3: secondary = try reader.nativeString(); representation = "secondaryName"
            case 5, 6:
                representation = "legacyAuxiliaryState"
                state = span(reader.position, reader.upper)
                throw CPRProjectError.unsupported("Legacy auxiliary association conversion is retained opaque.")
            default: representation = "noRetainedState"
            }
            flags = try reader.u16()
            guard reader.position == reader.upper else { throw CPRProjectError.invalid("Trailing MAudioTrack resource bytes.") }
            if let fields {
                route = try savedValue(fields, property: "OutputBusValue", integer: true)
                volume = try savedValue(fields, property: "Volume", integer: false)
                for key in ["OutputBus", "OwnInputBus", "RecorderBus"] {
                    if let field = fields.first(where: { $0.name == key }) {
                        if let values = attributeObject(field.value) {
                            buses.append(try bus(values, path: [key], range: field.range, depth: 0))
                        } else { unresolved.append("unsupportedBusProperty:" + key) }
                    }
                }
                if route == nil { unresolved.append("outputBusValueMissingOrUnsupported") }
                if volume == nil { unresolved.append("volumeValueMissingOrUnsupported") }
                if route?.encoding == "int64-outside-signed32" { unresolved.append("outputBusValueOutsideSigned32") }
                if volume?.finite == false { unresolved.append("nonfiniteVolumeValue") }
            }
        } catch CPRProjectError.unsupported(let detail) {
            unresolved.append("retainedUnsupportedState")
            issue("unsupportedTrackBinding", resource ?? track, detail)
        }
        return CPRNativeTrackBinding(track: track.descriptor, resource: resource?.descriptor, mTrackVersion: mVersion,
            tag: tag, providerName: provider, providerIndex: index, secondaryName: secondary,
            stateRepresentation: representation, state: state, stateExtentKnown: stateExtentKnown, retainedObject: retained, retainedObjectWord: retainedWord,
            audioFlags: flags, outputBusValue: route, volumeValue: volume, busCandidates: buses,
            savedDestinationCandidates: [], unresolved: unresolved)
    }

    func skipNumericAttributes(_ reader: inout CPRCursor) throws {
        let count = Int(try reader.u32())
        guard count <= 10_000, count <= (reader.upper - reader.position) / 6 else {
            throw CPRProjectError.invalid("Invalid numeric track-attribute count.")
        }
        var keys = Set<UInt32>()
        for _ in 0..<count {
            guard keys.insert(try reader.u32()).inserted else { throw CPRProjectError.invalid("Duplicate numeric track attribute.") }
            switch try reader.u16() {
            case 1, 0x801: _ = try reader.i64()
            case 2, 0x12, 0x22, 0x92: _ = try object(&reader)
            case 8:
                guard let text = try object(&reader), text.descriptor.className == "CmString", text.descriptor.version == 0 else {
                    throw CPRProjectError.unsupported("Unverified numeric string attribute.")
                }
            default: throw CPRProjectError.unsupported("Unverified numeric attribute encoding.")
            }
        }
    }

    func readFields(_ reader: inout CPRCursor, depth: Int) throws -> [BindingField] {
        guard depth <= 32 else { throw CPRProjectError.unsupported("Native binding attributes exceed 32 levels.") }
        let count = Int(try reader.u32())
        guard count <= fieldBudget, count <= (reader.upper - reader.position) / 8 else {
            throw CPRProjectError.invalid("Excessive or truncated native binding attributes.")
        }
        fieldBudget -= count
        var fields: [BindingField] = [], names = Set<String>()
        for _ in 0..<count {
            let begin = reader.position, name = try reader.className()
            guard names.insert(name).inserted else { throw CPRProjectError.invalid("Duplicate named binding attribute.") }
            let code = try reader.u16(), value: BindingValue
            let valueStart = reader.position
            switch code {
            case 1: value = .integer(try reader.i64(), span(valueStart, valueStart + 8))
            case 4: value = .number(try reader.u64(), span(valueStart, valueStart + 8))
            case 8: value = .text(try reader.nativeString())
            case 2: value = try compound(&reader, depth: depth + 1)
            default: throw CPRProjectError.unsupported("Unknown named binding attribute type \(code).")
            }
            fields.append(BindingField(name: name, value: value, range: span(begin, reader.position)))
        }
        return fields
    }

    func compound(_ reader: inout CPRCursor, depth: Int, arrayElement: Bool = false) throws -> BindingValue {
        guard depth <= 32 else { throw CPRProjectError.unsupported("Native binding compounds exceed 32 levels.") }
        let code = try reader.u16()
        // Reader1031ab5b8 at1031aba48..1031abb7c creates an object array for
        // subtype201, then reads only typed20 objects or deferred21 references.
        // Bare6 dictionaries are valid fields, not object-array elements.
        guard !arrayElement || code == 20 else {
            throw CPRProjectError.unsupported("Binding object arrays require explicit typed objects; references and other element codes remain unresolved.")
        }
        switch code {
        case 4:
            // Counted native strings; the same bounded ASCII/marked UTF-8
            // decoder applies. These remain auxiliary state, not bus names.
            let count = Int(try reader.u32())
            guard count <= fieldBudget, count <= (reader.upper - reader.position) / 4 else {
                throw CPRProjectError.invalid("Excessive or truncated binding string array.")
            }
            fieldBudget -= count
            for _ in 0..<count { _ = try reader.nativeString() }
            return .opaque
        case 2, 3:
            // Counted signed64 / binary64 arrays in reader1031abc50/1031abcb0.
            // Their values are not promoted to scalar routing or gain fields.
            let count = Int(try reader.u32())
            guard count <= fieldBudget, count <= (reader.upper - reader.position) / 8 else {
                throw CPRProjectError.invalid("Excessive or truncated binding numeric array.")
            }
            fieldBudget -= count
            _ = try reader.bytes(count * 8)
            return .opaque
        case 5:
            // FSubList: count followed by anonymous FAttributes dictionaries.
            // The Child Bus getter1031a0ce8 checks this exact runtime class.
            let count = Int(try reader.u32())
            guard count <= fieldBudget, count <= (reader.upper - reader.position) / 4 else {
                throw CPRProjectError.invalid("Excessive or truncated binding sublist.")
            }
            fieldBudget -= count
            var items: [BindingValue] = []
            for _ in 0..<count {
                let start = reader.position, fields = try readFields(&reader, depth: depth + 1)
                items.append(.ranged(.attributes(nil, fields), span(start, reader.position)))
            }
            return .list(items)
        case 6: return .attributes(nil, try readFields(&reader, depth: depth))
        case 7:
            // Reader1031abe44 passes this byte count to the freshly constructed
            // memory stream's +e8 reader103182948 (fallback103170c8c). The
            // payload is copied as bytes; plugin contents stay uninterpreted.
            let count = Int(try reader.u32())
            _ = try reader.bytes(count)
            return .opaque
        case 20:
            let type = try reader.className(); _ = try reader.u64()
            return .attributes(type, try readFields(&reader, depth: depth))
        case 201:
            let count = Int(try reader.u32())
            guard count <= fieldBudget, count <= (reader.upper - reader.position) / 2 else {
                throw CPRProjectError.invalid("Excessive or truncated binding object list.")
            }
            fieldBudget -= count
            var items: [BindingValue] = []
            for _ in 0..<count {
                let start = reader.position, value = try compound(&reader, depth: depth + 1, arrayElement: true)
                items.append(.ranged(value, span(start, reader.position)))
            }
            return .objectList(items)
        default: throw CPRProjectError.unsupported("Unverified binding compound subtype \(code) retained opaque.")
        }
    }

    func attributeObject(_ value: BindingValue) -> [BindingField]? {
        if case .attributes(let type, let fields) = value, type == nil || type == "FAttributes" { return fields }
        return nil
    }

    func number(_ value: BindingValue, integer: Bool) -> CPRNativeSavedNumber? {
        switch value {
        case .integer(let number, let range) where integer:
            return CPRNativeSavedNumber(encoding: Int32(exactly: number) == nil ? "int64-outside-signed32" : "signed32-in-int64",
                integer: String(number), floatingPointBits: nil, finite: true, span: range)
        case .number(let bits, let range) where !integer:
            return CPRNativeSavedNumber(encoding: "float64", integer: nil,
                floatingPointBits: String(format: "%016llx", bits), finite: Double(bitPattern: bits).isFinite, span: range)
        default: return nil
        }
    }

    func savedValue(_ fields: [BindingField], property: String, integer: Bool) throws -> CPRNativeSavedNumber? {
        guard let field = fields.first(where: { $0.name == property }),
              let nested = attributeObject(field.value), let value = nested.first(where: { $0.name == "Value" }) else { return nil }
        return number(value.value, integer: integer)
    }

    func bus(_ fields: [BindingField], path: [String], range: CPRNativeBindingSpan, depth: Int) throws -> CPRNativeBusCandidate {
        guard depth <= 32 else { throw CPRProjectError.unsupported("Saved bus graph exceeds 32 levels.") }
        let uid = fields.first { $0.name == "Bus UID" }.flatMap { number($0.value, integer: true) }
        let type = fields.first { $0.name == "Bus Type" }.flatMap { number($0.value, integer: true) }
        let name: String?
        if let field = fields.first(where: { $0.name == "Name" }), case .text(let text) = field.value { name = text } else { name = nil }
        var children: [CPRNativeBusCandidate] = []
        if let child = fields.first(where: { $0.name == "Child Bus" }) {
            if case .list(let items) = child.value {
                for (ordinal, item) in items.enumerated() {
                    guard case .ranged(let value, let itemRange) = item, let nested = attributeObject(value) else {
                        throw CPRProjectError.unsupported("Saved child bus has an unverified typed receiver.")
                    }
                    children.append(try bus(nested, path: path + ["Child Bus", String(ordinal)], range: itemRange, depth: depth + 1))
                }
            } else { throw CPRProjectError.unsupported("Saved Child Bus field is not the verified FSubList representation.") }
        }
        return CPRNativeBusCandidate(path: path, span: range, savedUID: uid, busType: type, name: name,
            children: children, scope: "conditionalSavedBusReceiver;runtimeRegistryMembershipUnresolved")
    }

    func copy(_ b: CPRNativeTrackBinding, candidates: [CPRNativeBindingSpan], unresolved: [String]) -> CPRNativeTrackBinding {
        CPRNativeTrackBinding(track: b.track, resource: b.resource, mTrackVersion: b.mTrackVersion, tag: b.tag,
            providerName: b.providerName, providerIndex: b.providerIndex, secondaryName: b.secondaryName,
            stateRepresentation: b.stateRepresentation, state: b.state, stateExtentKnown: b.stateExtentKnown, retainedObject: b.retainedObject,
            retainedObjectWord: b.retainedObjectWord, audioFlags: b.audioFlags, outputBusValue: b.outputBusValue,
            volumeValue: b.volumeValue, busCandidates: b.busCandidates, savedDestinationCandidates: candidates, unresolved: unresolved)
    }
}

private struct BindingField {
    let name: String
    let value: BindingValue
    let range: CPRNativeBindingSpan
}

private indirect enum BindingValue {
    case integer(Int64, CPRNativeBindingSpan)
    case number(UInt64, CPRNativeBindingSpan)
    case text(String)
    case attributes(String?, [BindingField])
    case list([BindingValue])
    case objectList([BindingValue])
    case opaque
    case ranged(BindingValue, CPRNativeBindingSpan)
}
