import Foundation

/// A fresh structural inventory, separate from every frozen CPR recovery
/// profile. All counted children of each visited node are represented. A known
/// class is not proof that its body can render, or that native collection would
/// select it. Unknown bodies and track tails remain opaque and source-hashed.
struct CPRTrackContributorArchive: Equatable {
    let sourceSHA256: String
    let arrangement: CPRObjectRecord
    let root: CPRObjectRecord
    let rootNode: CPRTrackContributorNode
    /// Counted hierarchy order, before any temporal or priority selection.
    let tracks: [CPRTrackContributorInventory]

    static func read(container: CPRContainer) throws -> CPRTrackContributorArchive {
        let sections = container.sections.filter { $0.name == "Arrangement1" }
        guard sections.count == 1, let section = sections.first,
              section.className == "PArrangement" else {
            throw CPRProjectError.unsupported("Contributor inventory requires one typed Arrangement1 section.")
        }
        let archive = CPRArchive(data: container.originalBytes, section: section)
        let arrangement = try archive.root(expectedClass: "PArrangement")
        guard arrangement.descriptor.version == 4 else {
            throw CPRProjectError.unsupported("Contributor inventory requires PArrangement version 4.")
        }
        var body = archive.body(arrangement)
        guard let root = try archive.readObject(&body), root.descriptor.className == "MRoot",
              root.descriptor.version == 6 else {
            throw CPRProjectError.unsupported("Contributor inventory requires MRoot version 6.")
        }
        var fields = archive.body(root)
        _ = try fields.bytes(26)
        guard let node = try archive.readObject(&fields), node.descriptor.className == "MTrackList" else {
            throw CPRProjectError.unsupported("The arrangement root has no supported counted track list.")
        }
        let walker = CPRContributorWalker(archive: archive, enclosingObjects: [
            arrangement.descriptor.identityOffset, root.descriptor.identityOffset
        ])
        let rootNode = try walker.visit(node, ancestors: [], depth: 0)
        return CPRTrackContributorArchive(sourceSHA256: container.sha256,
            arrangement: arrangement.descriptor, root: root.descriptor, rootNode: rootNode,
            tracks: walker.tracks.sorted { $0.traversalOrdinal < $1.traversalOrdinal })
    }
}

struct CPRTrackContributorInventory: Equatable {
    let track: CPRObjectRecord
    /// Includes this owner, matching CPRSourceAudioEvent.ancestorTracks.
    let ancestorTracks: [CPRObjectRecord]
    let traversalOrdinal: Int
    let node: CPRTrackContributorNode
    var name: String { node.name }
    var isDirectAudioTrack: Bool {
        ancestorTracks.count == 1 && ancestorTracks.first == track &&
            track.className == "MAudioTrackEvent" && track.version == 1
    }
}

struct CPRTrackContributorNode: Equatable {
    let object: CPRObjectRecord
    let name: String
    let datum: CPRSourceDatum
    let declaredChildCount: Int
    let children: [CPRTrackContributor]
    var audioEventCount: Int { children.filter { $0.classification == .audioEvent }.count }
    var trackCount: Int { children.filter { $0.classification == .track }.count }
    var knownNonAudioCount: Int { children.filter { $0.classification == .knownNonAudio }.count }
    var unknownCount: Int { children.filter { $0.classification == .unknown }.count }
}

struct CPRTrackContributor: Equatable {
    enum Classification: Equatable {
        /// Exact MAudioEvent v6 identity only; its body is not decoded here.
        case audioEvent
        /// Exact supported track class/version whose counted node is visited.
        case track
        /// Exact tempo/signature class/version, not an inaudibility assertion.
        case knownNonAudio
        /// Includes unobserved versions of otherwise recognized classes.
        case unknown
    }
    /// Zero-based serialized child index in this containing node.
    let ordinal: Int
    /// Zero-based preorder across counted children of all visited nodes. This
    /// is not the native collector's runtime ordinal or a priority tie-break.
    let traversalOrdinal: Int
    /// Position of this particular declaration/reference token in the source.
    let tokenOffset: Int
    let object: CPRObjectRecord
    let classification: Classification
}

private final class CPRContributorWalker {
    private let archive: CPRArchive
    private let enclosingObjects: Set<Int>
    private var seenNodes = Set<Int>()
    private var seenChildren = Set<Int>()
    private var nextTraversalOrdinal = 0
    private(set) var tracks: [CPRTrackContributorInventory] = []
    private let trackVersions = ["MFolderTrack": 0, "MDeviceTrackEvent": 0, "MAudioTrackEvent": 1,
        "MMidiTrackEvent": 4, "MInstrumentTrackEvent": 4, "MSamplerTrackEvent": 4, "MDrumTrackEvent": 4]

    init(archive: CPRArchive, enclosingObjects: Set<Int>) {
        self.archive = archive
        self.enclosingObjects = enclosingObjects
    }

    func visit(_ node: CPRNativeObject, ancestors: [CPRObjectRecord], depth: Int) throws -> CPRTrackContributorNode {
        let identity = node.descriptor.identityOffset
        guard depth <= 32, seenNodes.count < 10_000,
              !enclosingObjects.contains(identity), !seenChildren.contains(identity),
              seenNodes.insert(identity).inserted,
              node.descriptor.version == 0,
              ["MTrackList", "MListNode"].contains(node.descriptor.className) else {
            throw CPRProjectError.unsupported("Shared, cyclic or unsupported contributor node hierarchy.")
        }
        var body = archive.body(node)
        let name = try body.nativeString()
        let nodeDatum = try datum(&body)
        if node.descriptor.className == "MTrackList", try body.u16() != 0 {
            throw CPRProjectError.unsupported("Unverified contributor track-list compatibility word.")
        }
        let count = Int(try body.u32())
        guard count <= 10_000, count <= (body.upper - body.position) / 4,
              count <= 10_000 - nextTraversalOrdinal else {
            throw CPRProjectError.invalid("Invalid or excessive counted contributor membership.")
        }
        var children: [CPRTrackContributor] = []
        for ordinal in 0..<count {
            // Descendant visits also consume the shared total-entry budget.
            guard nextTraversalOrdinal < 10_000 else {
                throw CPRProjectError.unsupported("Contributor hierarchy exceeds its total entry bound.")
            }
            let tokenOffset = body.position
            guard let child = try archive.readObject(&body) else {
                throw CPRProjectError.invalid("Null counted contributor at byte \(tokenOffset).")
            }
            let descriptor = child.descriptor
            guard !enclosingObjects.contains(descriptor.identityOffset),
                  !seenNodes.contains(descriptor.identityOffset),
                  seenChildren.insert(descriptor.identityOffset).inserted else {
                throw CPRProjectError.unsupported("A shared or cyclic counted child has ambiguous contributor ownership.")
            }
            let traversalOrdinal = nextTraversalOrdinal
            nextTraversalOrdinal += 1
            let kind = classification(descriptor)
            children.append(CPRTrackContributor(ordinal: ordinal, traversalOrdinal: traversalOrdinal,
                tokenOffset: tokenOffset, object: descriptor, classification: kind))
            if kind == .track {
                var trackBody = archive.body(child)
                _ = try trackBody.bytes(26)
                guard let childNode = try archive.readObject(&trackBody) else {
                    throw CPRProjectError.invalid("A counted track has no node.")
                }
                let childAncestors = ancestors + [descriptor]
                let inventory = try visit(childNode, ancestors: childAncestors, depth: depth + 1)
                tracks.append(CPRTrackContributorInventory(track: descriptor, ancestorTracks: childAncestors,
                    traversalOrdinal: traversalOrdinal, node: inventory))
            }
        }
        guard body.position == body.upper else {
            throw CPRProjectError.unsupported("Unconsumed counted contributor-node bytes.")
        }
        return CPRTrackContributorNode(object: node.descriptor, name: name, datum: nodeDatum,
            declaredChildCount: count, children: children)
    }

    private func classification(_ descriptor: CPRObjectRecord) -> CPRTrackContributor.Classification {
        if trackVersions[descriptor.className] == descriptor.version { return .track }
        if descriptor.className == "MAudioEvent", descriptor.version == 6 { return .audioEvent }
        if ["MTempoTrackEvent", "MSignatureTrackEvent"].contains(descriptor.className), descriptor.version == 3 {
            return .knownNonAudio
        }
        return .unknown
    }

    private func datum(_ reader: inout CPRCursor) throws -> CPRSourceDatum {
        let tag = try reader.i32()
        switch tag {
        case 0, 17:
            let tempo = try archive.readObject(&reader), signature = try archive.readObject(&reader)
            guard tempo.map({ $0.descriptor.className == "MTempoTrackEvent" && $0.descriptor.version == 3 }) ?? true,
                  signature.map({ $0.descriptor.className == "MSignatureTrackEvent" && $0.descriptor.version == 3 }) ?? true else {
                throw CPRProjectError.unsupported("Unverified contributor-node timing interface pair.")
            }
            return .interfaces(tag: tag, tempo: tempo?.descriptor, signature: signature?.descriptor)
        case 1, 10:
            let bits = try reader.u64()
            guard Double(bitPattern: bits).isFinite else {
                throw CPRProjectError.invalid("Nonfinite contributor-node scalar datum.")
            }
            return .scalar(tag: tag, bits: bits)
        default:
            throw CPRProjectError.unsupported("Unverified contributor-node datum type.")
        }
    }
}
