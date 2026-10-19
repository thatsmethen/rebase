import Foundation
import RebaseTimingDSP

public enum NativeTempoClockError: LocalizedError {
    case invalid(String)
    case conversionRequired
    case unsupportedEnvironment
    public var errorDescription: String? {
        switch self {
        case .invalid(let detail): return "Invalid native tempo clock: " + detail
        case .conversionRequired: return "Use Rebase Timing explicitly before changing or exchanging the recovered native clock."
        case .unsupportedEnvironment: return "The recovered clock requires round-to-nearest floating-point mode."
        }
    }
}

/// An exact serialized jump-map record. Display BPM is a projection only: the
/// reciprocal Float32 period and Double anchors control native calculations.
public struct NativeTempoMapRecord: Codable, Equatable {
    public let periodBits: UInt32
    public let secondsBits: UInt64
    public let tickBits: UInt64
    public let kind: UInt16
    public let sourceRecordOffset: Int

    public init(periodBits: UInt32, secondsBits: UInt64, tickBits: UInt64,
                kind: UInt16, sourceRecordOffset: Int) {
        self.periodBits = periodBits; self.secondsBits = secondsBits
        self.tickBits = tickBits; self.kind = kind; self.sourceRecordOffset = sourceRecordOffset
    }
    public var period: Double { Double(Float(bitPattern: periodBits)) }
    public var seconds: Double { Double(bitPattern: secondsBits) }
    public var tick: Double { Double(bitPattern: tickBits) }
    public var beat: Double { tick / 480 }
    public var displayBPM: Double { 60 / period }
}

/// Separately versioned fixed and bounded jump-map arithmetic from the pinned
/// static reference. Neither contract represents target execution or ramps.
public struct NativeTempoClock: Codable, Equatable {
    public static let fixedContract = "cpr-15.0.30.287-arm64-fixed-v1"
    public static let mapContract = "cpr-15.0.30.287-arm64-jump-map-v1"
    public let contract: String
    /// Exact fixed-mode scalar; zero sentinel for the separately tagged map.
    public let fixedBPMBits: UInt32
    public let mapRecords: [NativeTempoMapRecord]?
    public let sourceSHA256: String
    public let sourceObjectOffset: Int
    public let interpretationProfile: String

    public var fixedBPM: Double { Double(Float(bitPattern: fixedBPMBits)) }

    public init(fixedBPMBits: UInt32, sourceSHA256: String, sourceObjectOffset: Int,
                interpretationProfile: String = "cpr-static-subset-v2") throws {
        contract = Self.fixedContract
        mapRecords = nil
        self.fixedBPMBits = fixedBPMBits; self.sourceSHA256 = sourceSHA256
        self.sourceObjectOffset = sourceObjectOffset; self.interpretationProfile = interpretationProfile
        try validate()
    }

    public init(mapRecords: [NativeTempoMapRecord], sourceSHA256: String, sourceObjectOffset: Int,
                interpretationProfile: String = "cpr-static-subset-v3") throws {
        contract = Self.mapContract; fixedBPMBits = 0; self.mapRecords = mapRecords
        self.sourceSHA256 = sourceSHA256; self.sourceObjectOffset = sourceObjectOffset
        self.interpretationProfile = interpretationProfile
        try validate()
    }

    private enum CodingKeys: String, CodingKey {
        case contract, fixedBPMBits, mapRecords, sourceSHA256, sourceObjectOffset, interpretationProfile
    }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        contract = try values.decode(String.self, forKey: .contract)
        fixedBPMBits = try values.decode(UInt32.self, forKey: .fixedBPMBits)
        mapRecords = try values.decodeIfPresent([NativeTempoMapRecord].self, forKey: .mapRecords)
        sourceSHA256 = try values.decode(String.self, forKey: .sourceSHA256)
        sourceObjectOffset = try values.decode(Int.self, forKey: .sourceObjectOffset)
        interpretationProfile = try values.decode(String.self, forKey: .interpretationProfile)
        try validate()
    }

    public func validate() throws {
        guard sourceSHA256.utf8.count == 64,
              sourceSHA256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              sourceObjectOffset >= 0, sourceObjectOffset < CPRProject.maximumFileBytes else {
            throw NativeTempoClockError.invalid("Unsupported source identity.")
        }
        if contract == Self.fixedContract {
            guard interpretationProfile == "cpr-static-subset-v2", mapRecords == nil,
                  fixedBPM.isFinite, (20...400).contains(fixedBPM) else {
                throw NativeTempoClockError.invalid("Unsupported fixed clock descriptor.")
            }
            _ = try periodBits()
        } else if contract == Self.mapContract {
            guard interpretationProfile == "cpr-static-subset-v3", fixedBPMBits == 0,
                  let records = mapRecords, (1...2).contains(records.count) else {
                throw NativeTempoClockError.invalid("Unsupported jump-map descriptor.")
            }
            for (index, record) in records.enumerated() {
                guard record.kind == 0, record.displayBPM.isFinite, (20...400).contains(record.displayBPM),
                      index != 0 || record.sourceRecordOffset == sourceObjectOffset + 8,
                      record.sourceRecordOffset <= CPRProject.maximumFileBytes - 22,
                      index == 0 || record.sourceRecordOffset == records[index - 1].sourceRecordOffset + 22 else {
                    throw NativeTempoClockError.invalid("Unsupported jump-map record or source extent.")
                }
                try validTick(record.tick)
            }
            let points = cPoints(records)
            let status = points.withUnsafeBufferPointer { rb_native_map_validate($0.baseAddress, UInt32($0.count)) }
            if status == RB_NATIVE_TEMPO_INVALID {
                throw NativeTempoClockError.invalid("Jump-map points require positive periods, ordered finite anchors and exact native cache consistency.")
            }
            try check(status)
        } else {
            throw NativeTempoClockError.invalid("Unsupported native clock contract.")
        }
    }

    public func periodBits() throws -> UInt32 {
        guard contract == Self.fixedContract else {
            throw NativeTempoClockError.invalid("A jump map has a separate reciprocal period for each record.")
        }
        var result: UInt32 = 0
        try check(rb_native_fixed_period(fixedBPMBits, &result))
        return result
    }

    public func seconds(atNativeTick tick: Double) throws -> Double {
        try validate(); try validTick(tick)
        var result = 0.0
        if let mapRecords {
            let points = cPoints(mapRecords)
            try check(points.withUnsafeBufferPointer { rb_native_map_seconds($0.baseAddress, UInt32($0.count), tick, &result) })
        } else {
            try check(rb_native_fixed_seconds(fixedBPMBits, tick, &result))
        }
        return result
    }

    public func nativeTick(atSeconds seconds: Double) throws -> Double {
        try validate()
        guard seconds.isFinite, seconds >= 0 else { throw NativeTempoClockError.invalid("Seconds must be finite and nonnegative.") }
        var result = 0.0
        if let mapRecords {
            let points = cPoints(mapRecords)
            try check(points.withUnsafeBufferPointer { rb_native_map_ticks($0.baseAddress, UInt32($0.count), seconds, &result) })
        } else {
            try check(rb_native_fixed_ticks(fixedBPMBits, seconds, &result))
        }
        try validTick(result)
        return result
    }

    /// Display/edit projection must remain tied to every native record. Source
    /// identity is independently replayed by ProjectStore before persistence.
    public func matches(events: [TempoEvent]) -> Bool {
        if let records = mapRecords {
            return events.count == records.count && zip(events, records).allSatisfy {
                $0.beat == $1.beat && $0.bpm == $1.displayBPM && $0.curve == .jump
            }
        }
        return events.count == 1 && events[0].beat == 0 && events[0].bpm == fixedBPM && events[0].curve == .jump
    }

    private func cPoints(_ records: [NativeTempoMapRecord]) -> [rb_native_jump_point] {
        records.map { rb_native_jump_point(period_bits: $0.periodBits, seconds: $0.seconds, ticks: $0.tick) }
    }

    private func validTick(_ tick: Double) throws {
        guard tick.isFinite, tick >= 0, tick <= TempoMap.maximumBeat * 480 else {
            throw NativeTempoClockError.invalid("Native tick position is outside the supported range.")
        }
    }
    private func check(_ status: Int32) throws {
        switch Int(status) {
        case RB_NATIVE_TEMPO_OK: return
        case RB_NATIVE_TEMPO_FP_ENVIRONMENT: throw NativeTempoClockError.unsupportedEnvironment
        default: throw NativeTempoClockError.invalid("Arithmetic input or result is outside the finite normal-or-zero subset.")
        }
    }
}

public extension Project {
    /// Explicitly detach native arithmetic while retaining quarter-note anchors.
    /// A canceled UI edit can discard the candidate without changing this project.
    mutating func convertToApplicationTiming() throws {
        guard tempoMap.nativeClock != nil else { return }
        var candidate = self
        candidate.tempoMap = try tempoMap.convertedToApplicationTiming()
        try candidate.replaceTempoMap(candidate.tempoMap)
        self = candidate
    }
}
