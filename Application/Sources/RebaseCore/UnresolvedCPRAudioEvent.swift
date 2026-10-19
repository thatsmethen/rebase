import Foundation

/// A source-backed event awaiting media and playback interpretation. It is not
/// a playable Clip. Coordinates, when present, describe the saved source under
/// the bounded static contract, not a measurement of a running Reference instance.
public struct UnresolvedCPRAudioEvent: Codable, Equatable, Identifiable {
    public let id: UUID
    public let sourceSHA256: String
    public let event: CPRObjectRecord
    public let clip: CPRObjectRecord
    public let cluster: CPRObjectRecord
    public let name: String
    public let rawStartBits: UInt64
    public let rawLengthBits: UInt64
    public let rawOffsetBits: UInt64
    public let datumTag: Int32
    public let datumScalarBits: UInt64?
    public let files: [CPRAudioFileReference]
    public let segments: [CPRAudioSegmentReference]
    public let placement: CPRAudioSourcePlacement?
    public let placementStatus: String

    func validate() throws {
        guard sourceSHA256.count == 64, sourceSHA256.allSatisfy({ $0.isHexDigit && !$0.isUppercase }),
              event.className == "MAudioEvent", event.version == 6,
              clip.className == "PAudioClip", clip.version == 4,
              cluster.className == "AudioCluster", cluster.version == 0,
              [rawStartBits, rawLengthBits, rawOffsetBits].allSatisfy({ Double(bitPattern: $0).isFinite }) else {
            throw RebaseCoreError.invalidProject("Invalid preserved CPR audio-event identity or fields.")
        }
        if let placement {
            guard placement.contract == CPRAudioSourcePlacement.contractName,
                  placement.position.bitPattern == 0, placement.offset.bitPattern == 0,
                  placement.duration.isFinite, placement.duration > 0, placement.duration <= 86_400,
                  datumTag == 10, let bits = datumScalarBits,
                  Double(bitPattern: bits).isFinite, Double(bitPattern: bits) > 0 else {
                throw RebaseCoreError.invalidProject("Invalid CPR source-coordinate projection.")
            }
        }
    }
}

public struct CPRAudioSourcePlacement: Codable, Equatable {
    public static let contractName = "cpr-15.0.30.287-audio-source-zero-type10-v1"
    public let contract: String
    public let position: Double
    public let duration: Double
    public let offset: Double
}

/// Original path text is metadata only. It is never resolved or opened as a
/// local media path; imported media must separately pass project containment.
public struct CPRAudioFileReference: Codable, Equatable {
    public let object: CPRObjectRecord
    public let filename: String
    public let directory: String
    public let frameCount: UInt64
    public let sampleSize: Int16
    public let frameSize: Int16
    public let channels: Int16
    public let sampleRateBits: UInt32
    public var sampleRate: Double { Double(Float(bitPattern: sampleRateBits)) }
}

public struct CPRAudioSegmentReference: Codable, Equatable {
    public let object: CPRObjectRecord
    public let streamIdentity: Int
    public let storedOffset: UInt64
    public let storedLength: UInt64
    public let storedStart: UInt64
}
