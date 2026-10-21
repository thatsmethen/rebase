import Foundation

/// Saved PArrangement audio configuration, independently replayed from the
/// preserved source. It is not a device-rate or effective hosted-state claim.
public struct CPRProjectAudioSetup: Codable, Equatable {
    public static let contractName = "cpr-15.0.30.287-parrangement-audio-setup-v1"
    public let contract: String
    public let sourceSHA256: String
    public let arrangement: CPRObjectRecord
    public let root: CPRObjectRecord
    public let setup: CPRObjectRecord
    public let baseRateBits: UInt32
    public let factorBits: UInt64
    public let baseRateOffset: Int
    public let factorOffset: Int

    public var baseRate: Double { Double(Float(bitPattern: baseRateBits)) }
    public var factor: Double { Double(bitPattern: factorBits) }

    /// Deliberately narrower than the native reader: do not turn its 44100-Hz
    /// out-of-range fallback, unchecked factor, or runtime providers into saved
    /// source-rate evidence. Factor one also avoids an unverified rate context.
    public func supportedSampleRate() throws -> Double {
        guard contract == Self.contractName,
              arrangement.className == "PArrangement", arrangement.version == 4,
              root.className == "MRoot", root.version == 6,
              setup.className == "PArrangeSetup", setup.version == 8,
              sourceSHA256.utf8.count == 64,
              sourceSHA256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              baseRate.isFinite, baseRate.rounded() == baseRate,
              (10_000...192_000).contains(baseRate),
              factorBits == 0x3ff0_0000_0000_0000 else {
            throw CPRProjectError.unsupported("Saved project-clock playback requires an explicit integral base rate from 10000 to 192000 Hz and an exact +1 rate factor; native fallback and other factors are not interpreted.")
        }
        return baseRate
    }

    /// Follow only the typed attachment read by PArrangement. The MRoot body
    /// remains opaque here; unrelated or nested setup objects are not searched.
    static func read(container: CPRContainer) throws -> CPRProjectAudioSetup {
        guard let section = container.sections.first(where: { $0.name == "Arrangement1" }),
              section.className == "PArrangement" else {
            throw CPRProjectError.unsupported("No supported arrangement audio setup.")
        }
        let archive = CPRArchive(data: container.originalBytes, section: section)
        let arrangement = try archive.root(expectedClass: "PArrangement")
        guard arrangement.descriptor.version == 4 else {
            throw CPRProjectError.unsupported("Saved audio setup requires PArrangement version 4.")
        }
        var fields = archive.body(arrangement)
        guard let root = try archive.readObject(&fields),
              root.descriptor.className == "MRoot", root.descriptor.version == 6 else {
            throw CPRProjectError.unsupported("Saved audio setup requires the arrangement's MRoot version 6.")
        }
        guard fields.position < fields.upper else {
            throw CPRProjectError.unsupported("The arrangement has no explicit saved audio setup.")
        }
        // A positive identity could refer into the deliberately opaque MRoot.
        // Do not scan it or invent object registrations to resolve that variant.
        var setupToken = fields
        let token = try setupToken.u32()
        guard token == 0 || token & 0x8000_0000 != 0 else {
            throw CPRProjectError.unsupported("A referenced arrangement audio setup is outside the supported direct-definition subset.")
        }
        guard let setup = try archive.readObject(&fields),
              setup.descriptor.className == "PArrangeSetup", setup.descriptor.version == 8 else {
            throw CPRProjectError.unsupported("Saved audio setup requires an explicit PArrangeSetup version 8.")
        }
        for _ in 0..<7 { _ = try fields.nativeString() }
        guard fields.position == fields.upper else {
            throw CPRProjectError.invalid("Unconsumed PArrangement audio-setup suffix.")
        }

        var body = archive.body(setup)
        try scalarCoordinate(&body)
        try scalarCoordinate(&body)
        _ = try body.u32() // +70
        _ = try body.u32() // +74
        let baseRateOffset = body.position
        let baseRateBits = try body.u32() // +ac; preserve even unsupported bits.
        _ = try body.u32() // legacy format, mapped to +c8 by the native reader.
        try scalarCoordinate(&body)
        for _ in 0..<4 { _ = try body.u32() } // +cc, +160, +a8, discarded.
        let factorOffset = body.position
        let factorBits = try body.u64() // +b0
        _ = try body.u64() // +c0
        _ = try body.u32() // +158
        _ = try body.u16() // +ba
        _ = try body.u16() // +b8
        _ = try body.u32() // Inline FFileType discriminator, not an object.
        for _ in 0..<3 { _ = try body.nativeString() }
        // The native bounded token reader also accepts newline; this subset
        // supports only a terminating NUL and at most nine ASCII payload bytes.
        var terminated = false
        for _ in 0..<10 {
            let byte = try body.bytes(1).first!
            if byte == 0 { terminated = true; break }
            guard byte >= 0x20 && byte < 0x7f else {
                throw CPRProjectError.unsupported("Unsupported saved audio-format token.")
            }
        }
        guard terminated else { throw CPRProjectError.unsupported("Saved audio-format token exceeds the bounded subset.") }
        _ = try body.u32() // +15c
        guard body.position == body.upper else {
            throw CPRProjectError.invalid("Unconsumed PArrangeSetup version-8 payload.")
        }
        return CPRProjectAudioSetup(contract: contractName, sourceSHA256: container.sha256,
            arrangement: arrangement.descriptor, root: root.descriptor, setup: setup.descriptor,
            baseRateBits: baseRateBits, factorBits: factorBits,
            baseRateOffset: baseRateOffset, factorOffset: factorOffset)
    }

    private static func scalarCoordinate(_ body: inout CPRCursor) throws {
        _ = try body.u64() // Coordinate value; not used to infer the audio rate.
        let tag = try body.i32()
        guard tag == 1 || tag == 10 else {
            throw CPRProjectError.unsupported("Saved audio setup has an unsupported embedded datum.")
        }
        _ = try body.u64() // Scalar; no interface or global compatibility branch.
    }
}
