import Foundation

/// Shared timing roles in the supported counted track hierarchy. This does not
/// infer project-global authority from a device name or a loose object scan.
struct CPRClockRoles {
    let archive: CPRArchive
    let tempo: CPRNativeObject?
    let signature: CPRNativeObject?
    let trackNodeCount: Int
    let pairedNodeCount: Int
    var objects: [CPRObjectRecord] { archive.objects.values.map(\.descriptor).sorted { $0.identityOffset < $1.identityOffset } }

    static func resolve(container: CPRContainer) throws -> CPRClockRoles {
        guard let section = container.sections.first(where: { $0.name == "Arrangement1" }) else {
            throw CPRProjectError.unsupported("No supported counted arrangement timing roles.")
        }
        let archive = CPRArchive(data:container.originalBytes,section:section)
        let arrangement = try archive.root(expectedClass:section.className)
        guard section.className == "PArrangement", arrangement.descriptor.version == 4 else {
            throw CPRProjectError.unsupported("Shared timing requires PArrangement version 4.")
        }
        var body = archive.body(arrangement)
        guard let root = try archive.readObject(&body), root.descriptor.className == "MRoot", root.descriptor.version == 6 else {
            throw CPRProjectError.unsupported("Shared timing requires MRoot version 6.")
        }
        var fields = archive.body(root)
        _ = try fields.bytes(26)
        guard let list = try archive.readObject(&fields), list.descriptor.className == "MTrackList" else {
            throw CPRProjectError.unsupported("Missing root counted track list.")
        }
        let walker = ClockRoleWalker(archive:archive)
        try walker.visit(list,depth:0)
        guard let pair = walker.pair else {
            throw CPRProjectError.unsupported("No concrete shared tempo/signature interface pair in the supported track nodes.")
        }
        return CPRClockRoles(archive:archive,tempo:pair.0,signature:pair.1,
                             trackNodeCount:walker.nodeCount,pairedNodeCount:walker.pairedNodeCount)
    }
}

private final class ClockRoleWalker {
    let archive: CPRArchive
    var pair: (CPRNativeObject?,CPRNativeObject?)?
    var nodeCount = 0
    var pairedNodeCount = 0
    private var active = Set<Int>()
    private var seenTracks = Set<Int>()
    private let trackVersions = ["MFolderTrack":0,"MDeviceTrackEvent":0,"MAudioTrackEvent":1,
                                 "MMidiTrackEvent":4,"MInstrumentTrackEvent":4,"MSamplerTrackEvent":4,"MDrumTrackEvent":4]
    init(archive: CPRArchive) { self.archive = archive }

    func visit(_ object: CPRNativeObject, depth: Int) throws {
        let identity = object.descriptor.identityOffset
        guard depth <= 32, nodeCount < 10_000, !active.contains(identity), object.descriptor.version == 0,
              ["MTrackList","MListNode"].contains(object.descriptor.className) else {
            throw CPRProjectError.unsupported("Unsupported or cyclic shared-timing track-list layout.")
        }
        nodeCount += 1
        active.insert(identity); defer { active.remove(identity) }
        var body = archive.body(object)
        _ = try body.nativeString()
        switch try body.i32() {
        case 0,17:
            let first = try archive.readObject(&body)
            let second = try archive.readObject(&body)
            guard first.map({ $0.descriptor.className == "MTempoTrackEvent" && $0.descriptor.version == 3 }) ?? true,
                  second.map({ $0.descriptor.className == "MSignatureTrackEvent" && $0.descriptor.version == 3 }) ?? true else {
                throw CPRProjectError.unsupported("A track timing pair has an unverified non-null tempo/signature interface.")
            }
            pairedNodeCount += 1
            if let pair {
                guard pair.0?.descriptor.identityOffset == first?.descriptor.identityOffset,
                      pair.1?.descriptor.identityOffset == second?.descriptor.identityOffset else {
                    throw CPRProjectError.unsupported("Traversed track nodes do not share one concrete tempo/signature pair.")
                }
            } else { pair = (first,second) }
        case 1: _ = try body.number() // Scalar structural nodes are neutral.
        default: throw CPRProjectError.unsupported("Unverified track datum cannot establish a shared timing pair.")
        }
        if object.descriptor.className == "MTrackList", try body.u16() != 0 {
            throw CPRProjectError.unsupported("Unverified track-list compatibility word.")
        }
        let count = Int(try body.u32())
        guard count <= 10_000, count <= (body.upper-body.position)/4 else {
            throw CPRProjectError.invalid("Invalid counted timing-role hierarchy.")
        }
        for _ in 0..<count {
            guard let child = try archive.readObject(&body) else { throw CPRProjectError.invalid("Null counted hierarchy object.") }
            if let version = trackVersions[child.descriptor.className] {
                guard child.descriptor.version == version, seenTracks.insert(child.descriptor.identityOffset).inserted else {
                    throw CPRProjectError.unsupported("Unsupported, shared or cyclic track object in timing-role hierarchy.")
                }
                var event = archive.body(child)
                _ = try event.bytes(26)
                guard let node = try archive.readObject(&event) else { throw CPRProjectError.invalid("A track has no counted node.") }
                try visit(node,depth:depth+1)
            }
            // Non-track children stay opaque. Their class-name bytes or nested
            // signatures cannot manufacture a track timing role.
        }
        guard body.position == body.upper else { throw CPRProjectError.unsupported("Unconsumed counted track-list bytes.") }
    }
}
