import Foundation

/// Application timing model informed by Reference 15's documented musical ruler,
/// step tempo and grid-relative behavior. Default arithmetic is application
/// policy; an optional NativeTempoClock supplies its separately bounded recovered
/// fixed or bounded jump-map arithmetic. Coordinates are quarter notes from project start; negative time,
/// pickup bars, ramp interpolation and signature-relative cross-boundary drags
/// are deliberately unsupported. See musical-time-001/official-docs.json.
public enum MusicalTimeError: LocalizedError, Equatable {
    case invalidTempoMap(String)
    case invalidSignatureMap(String)
    case invalidPosition(String)
    case unsupportedRamp
    case unsupportedRelativeSignatureChange

    public var errorDescription: String? {
        switch self {
        case .invalidTempoMap(let text), .invalidSignatureMap(let text), .invalidPosition(let text): return text
        case .unsupportedRamp: return "Tempo ramps are not supported until their interpolation contract is established."
        case .unsupportedRelativeSignatureChange: return "Relative snapping across a time-signature change is not supported."
        }
    }
}

public enum TempoCurve: String, Codable, Equatable {
    case jump, ramp
}

public struct TempoEvent: Codable, Equatable, Identifiable {
    public var id: UUID
    public var beat: Double
    public var bpm: Double
    /// Describes the change arriving at this event. Only jump is implemented.
    public var curve: TempoCurve

    public init(id: UUID = UUID(), beat: Double, bpm: Double, curve: TempoCurve = .jump) {
        self.id = id; self.beat = beat; self.bpm = bpm; self.curve = curve
    }
}

public struct TempoMap: Codable, Equatable {
    /// A representability/resource bound for this app, not a Reference limit.
    public static let maximumBeat: Double = 1_000_000_000
    public var events: [TempoEvent]
    /// Optional recovered arithmetic. Events remain its checked display/edit
    /// projection; original serialized values control clock calculations.
    public var nativeClock: NativeTempoClock?

    public init(events: [TempoEvent] = [TempoEvent(beat: 0, bpm: 120)], nativeClock: NativeTempoClock? = nil) {
        self.events = events; self.nativeClock = nativeClock
    }

    public func validate() throws {
        guard !events.isEmpty, events[0].beat == 0,
              Set(events.map(\.id)).count == events.count else {
            throw MusicalTimeError.invalidTempoMap("A tempo map needs a beat-zero event and unique identifiers.")
        }
        var previous = -1.0
        for event in events {
            guard event.beat.isFinite, event.beat >= 0, event.beat <= Self.maximumBeat,
                  event.beat > previous, event.bpm.isFinite, (20...400).contains(event.bpm) else {
                throw MusicalTimeError.invalidTempoMap("Tempo events must increase in position and use 20–400 BPM.")
            }
            guard event.curve == .jump else { throw MusicalTimeError.unsupportedRamp }
            previous = event.beat
        }
        if let nativeClock {
            try nativeClock.validate()
            guard nativeClock.matches(events: events) else {
                throw NativeTempoClockError.conversionRequired
            }
        }
    }

    public func convertedToApplicationTiming() throws -> TempoMap {
        try validate()
        return TempoMap(events: events)
    }

    public func seconds(atBeat beat: Double) throws -> Double {
        try validate(); try validBeat(beat)
        if let nativeClock { return try nativeClock.seconds(atNativeTick: beat * 480) }
        var elapsed = 0.0
        for index in events.indices {
            let event = events[index]
            let end = index + 1 < events.count ? min(beat, events[index + 1].beat) : beat
            if end > event.beat { elapsed += (end - event.beat) * 60 / event.bpm }
            if end == beat { return elapsed }
        }
        return elapsed
    }

    public func beat(atSeconds seconds: Double) throws -> Double {
        try validate()
        guard seconds.isFinite, seconds >= 0 else {
            throw MusicalTimeError.invalidPosition("Time must be finite and nonnegative.")
        }
        if let nativeClock {
            let beat = try nativeClock.nativeTick(atSeconds: seconds) / 480
            try validBeat(beat)
            return beat
        }
        var elapsed = 0.0
        for index in events.indices {
            let event = events[index]
            if index + 1 < events.count {
                let next = events[index + 1]
                let boundary = elapsed + (next.beat - event.beat) * 60 / event.bpm
                if seconds >= boundary { elapsed = boundary; continue }
            }
            let beat = event.beat + (seconds - elapsed) * event.bpm / 60
            try validBeat(beat)
            return beat
        }
        throw MusicalTimeError.invalidPosition("Time is outside the supported timeline.")
    }
}

public struct SignatureEvent: Codable, Equatable, Identifiable {
    public var id: UUID
    public var beat: Double
    public var numerator: Int
    public var denominator: Int

    public init(id: UUID = UUID(), beat: Double, numerator: Int, denominator: Int) {
        self.id = id; self.beat = beat; self.numerator = numerator; self.denominator = denominator
    }

    public var quarterNotesPerBar: Double { Double(numerator) * 4 / Double(denominator) }
}

/// One-based bars, denominator beats and sixteenths within that beat; zero-based
/// ticks within the sixteenth. Display rounding is nearest, half upward. This
/// app policy is distinct from the unverified native display-rounding rule.
public struct MusicalPosition: Codable, Equatable {
    public var bar: Int
    public var beat: Int
    public var sixteenth: Int
    public var tick: Int

    public init(bar: Int, beat: Int, sixteenth: Int = 1, tick: Int = 0) {
        self.bar = bar; self.beat = beat; self.sixteenth = sixteenth; self.tick = tick
    }

    public var formatted: String { "\(bar).\(String(format: "%02d", beat)).\(String(format: "%02d", sixteenth)).\(String(format: "%03d", tick))" }
}

public struct SignatureMap: Codable, Equatable {
    public var events: [SignatureEvent]

    public init(events: [SignatureEvent] = [SignatureEvent(beat: 0, numerator: 4, denominator: 4)]) {
        self.events = events
    }

    public func validate() throws {
        guard !events.isEmpty, events[0].beat == 0,
              Set(events.map(\.id)).count == events.count else {
            throw MusicalTimeError.invalidSignatureMap("A signature map needs a beat-zero event and unique identifiers.")
        }
        for index in events.indices {
            let event = events[index]
            guard event.beat.isFinite, event.beat >= 0, event.beat <= TempoMap.maximumBeat,
                  (1...64).contains(event.numerator), [1, 2, 4, 8, 16].contains(event.denominator) else {
                throw MusicalTimeError.invalidSignatureMap("Supported signatures have 1–64 beats and denominator 1, 2, 4, 8 or 16.")
            }
            if index > 0 {
                let previous = events[index - 1]
                let bars = (event.beat - previous.beat) / previous.quarterNotesPerBar
                guard event.beat > previous.beat, bars == bars.rounded(.towardZero) else {
                    throw MusicalTimeError.invalidSignatureMap("Signature changes must increase in position and fall on bar boundaries.")
                }
            }
        }
    }

    /// The default is a display scale: 480 ticks/quarter = 120/sixteenth.
    /// Accepted resolutions are multiples of four up to 96,000 ticks/quarter.
    public func position(atBeat beat: Double, ticksPerQuarter: Int = 480) throws -> MusicalPosition {
        try validate(); try validBeat(beat); try validResolution(ticksPerQuarter)
        let displayedBeat = (beat * Double(ticksPerQuarter)).rounded(.toNearestOrAwayFromZero) / Double(ticksPerQuarter)
        let index = segmentIndex(at: displayedBeat)
        let event = events[index]
        let barTicks = event.numerator * ticksPerQuarter * 4 / event.denominator
        let elapsedTicks = Int(((displayedBeat - event.beat) * Double(ticksPerQuarter)).rounded())
        let offsetInBar = elapsedTicks % barTicks
        let beatTicks = ticksPerQuarter * 4 / event.denominator
        let sixteenthTicks = ticksPerQuarter / 4
        return MusicalPosition(bar: firstBar(at: index) + elapsedTicks / barTicks,
                               beat: offsetInBar / beatTicks + 1,
                               sixteenth: (offsetInBar % beatTicks) / sixteenthTicks + 1,
                               tick: offsetInBar % sixteenthTicks)
    }

    public func beat(at position: MusicalPosition, ticksPerQuarter: Int = 480) throws -> Double {
        try validate(); try validResolution(ticksPerQuarter)
        guard position.bar >= 1, position.bar <= 4_000_000_001 else {
            throw MusicalTimeError.invalidPosition("Bar is outside the supported timeline.")
        }
        var index = 0
        for candidate in events.indices where firstBar(at: candidate) <= position.bar { index = candidate }
        let event = events[index]
        guard (1...event.numerator).contains(position.beat),
              (1...(16 / event.denominator)).contains(position.sixteenth),
              position.tick >= 0, position.tick < ticksPerQuarter / 4 else {
            throw MusicalTimeError.invalidPosition("Musical position fields do not fit the active signature and display resolution.")
        }
        let result = event.beat + Double(position.bar - firstBar(at: index)) * event.quarterNotesPerBar
            + Double(position.beat - 1) * 4 / Double(event.denominator)
            + Double(position.sixteenth - 1) / 4 + Double(position.tick) / Double(ticksPerQuarter)
        try validBeat(result)
        return result
    }

    fileprivate func segmentIndex(at beat: Double) -> Int {
        var result = 0
        for index in events.indices where events[index].beat <= beat { result = index }
        return result
    }

    private func firstBar(at index: Int) -> Int {
        var result = 1
        for previous in 0..<index {
            result += Int((events[previous + 1].beat - events[previous].beat) / events[previous].quarterNotesPerBar)
        }
        return result
    }
}

public enum GridSnap: Codable, Equatable {
    case bar
    case beat
    /// Uniform quarter-note spacing anchored at project beat zero. Swing,
    /// grooves and imported preset-binary meanings are not implemented.
    case quantize(Double)

    /// With no origin, snaps creation to the nearest grid. With an origin,
    /// quantizes the drag distance, retaining its original grid phase. Exact
    /// half-grid ties round away from zero (an explicit application policy).
    public func snappedBeat(_ proposedBeat: Double, signatures: SignatureMap = SignatureMap(),
                            relativeTo origin: Double? = nil) throws -> Double {
        try signatures.validate(); try validBeat(proposedBeat)
        let index = signatures.segmentIndex(at: proposedBeat)
        let event = signatures.events[index]
        let spacing: Double
        let anchor: Double
        switch self {
        case .bar: spacing = event.quarterNotesPerBar; anchor = event.beat
        case .beat: spacing = 4 / Double(event.denominator); anchor = event.beat
        case .quantize(let value):
            guard value.isFinite, value >= 1 / 38_400.0, value <= 1_000_000 else {
                throw MusicalTimeError.invalidPosition("Quantize spacing must be between 1/38400 and 1000000 quarter notes.")
            }
            spacing = value; anchor = 0
        }
        let result: Double
        if let origin {
            try validBeat(origin)
            guard signatures.segmentIndex(at: origin) == index else {
                throw MusicalTimeError.unsupportedRelativeSignatureChange
            }
            let steps = max(((proposedBeat - origin) / spacing).rounded(.toNearestOrAwayFromZero),
                            ceil(-origin / spacing))
            result = max(0, origin + steps * spacing)
            guard signatures.segmentIndex(at: result) == index else {
                throw MusicalTimeError.unsupportedRelativeSignatureChange
            }
        } else {
            result = anchor + ((proposedBeat - anchor) / spacing).rounded(.toNearestOrAwayFromZero) * spacing
        }
        try validBeat(result)
        return result
    }
}

private func validBeat(_ beat: Double) throws {
    guard beat.isFinite, beat >= 0, beat <= TempoMap.maximumBeat else {
        throw MusicalTimeError.invalidPosition("Quarter-note position must be between zero and one billion.")
    }
}

private func validResolution(_ resolution: Int) throws {
    guard resolution >= 4, resolution <= 96_000, resolution % 4 == 0 else {
        throw MusicalTimeError.invalidPosition("Display resolution must be a multiple of four, from 4 to 96000 ticks per quarter.")
    }
}
