import Foundation
import Testing
import RebaseCore

/// Synthetic arithmetic/validation tests. They establish this application's
/// contract; no Reference runtime equivalence or file compatibility is claimed.
struct MusicalTimeTests {
    private func rejects(_ operation: () throws -> Void, sourceLocation: SourceLocation = #_sourceLocation) {
        do { try operation(); Issue.record("Expected a typed musical-time rejection", sourceLocation: sourceLocation) }
        catch is MusicalTimeError { }
        catch { Issue.record(error, sourceLocation: sourceLocation) }
    }

    private var variedTempo: TempoMap {
        TempoMap(events: [TempoEvent(beat: 0, bpm: 120), TempoEvent(beat: 4, bpm: 60), TempoEvent(beat: 10, bpm: 180)])
    }

    private var variedSignature: SignatureMap {
        SignatureMap(events: [SignatureEvent(beat: 0, numerator: 4, denominator: 4),
                              SignatureEvent(beat: 8, numerator: 3, denominator: 4),
                              SignatureEvent(beat: 14, numerator: 6, denominator: 8)])
    }

    @Test func tempoIntegratesKnownDurationsAndIsContinuousAtChanges() throws {
        let map = variedTempo
        for (beat, seconds) in [(0.0, 0.0), (2, 1), (4, 2), (7, 5), (10, 8), (13, 9)] {
            #expect(try map.seconds(atBeat: beat) == seconds)
            #expect(try map.beat(atSeconds: seconds) == beat)
        }
        let epsilon = 1 / 960.0
        #expect(abs(try map.seconds(atBeat: 4 - epsilon) - (2 - epsilon / 2)) < 1e-12)
        #expect(abs(try map.seconds(atBeat: 4 + epsilon) - (2 + epsilon)) < 1e-12)
    }

    @Test func tempoInverseAcrossManySegmentsAndBothDirections() throws {
        let map = TempoMap(events: [TempoEvent(beat: 0, bpm: 137), TempoEvent(beat: 3.25, bpm: 20),
                                   TempoEvent(beat: 40.5, bpm: 400), TempoEvent(beat: 90, bpm: 79)])
        var lastSeconds = -1.0
        for index in 0...400 {
            let beat = Double(index) / 3
            let seconds = try map.seconds(atBeat: beat)
            #expect(seconds > lastSeconds)
            #expect(abs(try map.beat(atSeconds: seconds) - beat) < 1e-10)
            lastSeconds = seconds
        }
        for seconds in [0.0, 0.001, 2, 10, 30, 100, 200] {
            #expect(abs(try map.seconds(atBeat: map.beat(atSeconds: seconds)) - seconds) < 1e-10)
        }
    }

    @Test func tempoRejectsUnsupportedRampsAndInvalidMapsWithoutSorting() throws {
        rejects { try TempoMap(events: []).validate() }
        rejects { try TempoMap(events: [TempoEvent(beat: 1, bpm: 120)]).validate() }
        for bpm in [0, 19, 401, Double.nan, .infinity] {
            rejects { try TempoMap(events: [TempoEvent(beat: 0, bpm: bpm)]).validate() }
        }
        let first = TempoEvent(beat: 0, bpm: 120)
        for events in [[first, TempoEvent(beat: 0, bpm: 80)],
                       [first, TempoEvent(beat: 8, bpm: 80), TempoEvent(beat: 4, bpm: 90)],
                       [first, TempoEvent(id: first.id, beat: 4, bpm: 80)]] {
            rejects { try TempoMap(events: events).validate() }
        }
        do {
            try TempoMap(events: [first, TempoEvent(beat: 4, bpm: 80, curve: .ramp)]).validate()
            Issue.record("Ramp should remain explicitly unsupported")
        } catch { #expect(error as? MusicalTimeError == .unsupportedRamp) }
    }

    @Test func conversionRejectsNegativeNonfiniteAndUnrepresentableCoordinates() throws {
        for value in [-1.0, .nan, .infinity, -.infinity, Double.greatestFiniteMagnitude] {
            rejects { _ = try TempoMap().seconds(atBeat: value) }
            rejects { _ = try TempoMap().beat(atSeconds: value) }
            rejects { _ = try SignatureMap().position(atBeat: value) }
            rejects { _ = try GridSnap.beat.snappedBeat(value) }
        }
        #expect(try TempoMap().seconds(atBeat: TempoMap.maximumBeat) == 500_000_000)
        #expect(try TempoMap().beat(atSeconds: 500_000_000) == TempoMap.maximumBeat)
        rejects { _ = try TempoMap().beat(atSeconds: 500_000_001) }
    }

    @Test func rulerChangesMeterWithoutResettingBarNumbers() throws {
        let map = variedSignature
        let cases: [(Double, MusicalPosition)] = [
            (0, MusicalPosition(bar: 1, beat: 1)),
            (7, MusicalPosition(bar: 2, beat: 4)),
            (8, MusicalPosition(bar: 3, beat: 1)),
            (13, MusicalPosition(bar: 4, beat: 3)),
            (14, MusicalPosition(bar: 5, beat: 1)),
            (15.25, MusicalPosition(bar: 5, beat: 3, sixteenth: 2)),
            (16.5, MusicalPosition(bar: 5, beat: 6)),
            (17, MusicalPosition(bar: 6, beat: 1))
        ]
        for (beat, position) in cases {
            #expect(try map.position(atBeat: beat) == position)
            #expect(try map.beat(at: position) == beat)
        }
    }

    @Test func displayTicksAreConfigurableAndRoundWithBoundaryCarry() throws {
        let map = SignatureMap()
        #expect(try map.position(atBeat: 3.75625).formatted == "1.04.04.003")
        #expect(try map.position(atBeat: 3.75625, ticksPerQuarter: 960).tick == 6)
        #expect(try map.position(atBeat: 4 - 0.4 / 480) == MusicalPosition(bar: 2, beat: 1))
        #expect(try variedSignature.position(atBeat: 14 - 0.4 / 480) == MusicalPosition(bar: 5, beat: 1))
        for tick in stride(from: 0, through: 9600, by: 37) {
            let beat = Double(tick) / 480
            let position = try variedSignature.position(atBeat: beat)
            #expect(abs(try variedSignature.beat(at: position) - beat) < 1e-12)
        }
    }

    @Test func signaturesRejectNonBarChangesAndInvalidRulerFields() throws {
        let first = SignatureEvent(beat: 0, numerator: 4, denominator: 4)
        for events in [[], [SignatureEvent(beat: 4, numerator: 4, denominator: 4)],
                       [first, SignatureEvent(beat: 6, numerator: 3, denominator: 4)],
                       [first, SignatureEvent(beat: 0, numerator: 3, denominator: 4)],
                       [first, SignatureEvent(id: first.id, beat: 8, numerator: 3, denominator: 4)],
                       [SignatureEvent(beat: 0, numerator: 0, denominator: 4)],
                       [SignatureEvent(beat: 0, numerator: 4, denominator: 32)]] {
            rejects { try SignatureMap(events: events).validate() }
        }
        for position in [MusicalPosition(bar: 0, beat: 1), MusicalPosition(bar: Int.max, beat: 1),
                         MusicalPosition(bar: 3, beat: 4), MusicalPosition(bar: 5, beat: 1, sixteenth: 3),
                         MusicalPosition(bar: 1, beat: 1, tick: 120), MusicalPosition(bar: 1, beat: 0)] {
            rejects { _ = try variedSignature.beat(at: position) }
        }
        for resolution in [0, 3, 5, Int.max] {
            rejects { _ = try SignatureMap().position(atBeat: 0, ticksPerQuarter: resolution) }
        }
    }

    @Test func ordinaryAndRelativeSnapHaveDifferentCreationDragResults() throws {
        // Documented Reference example: 3.04.01 -> 4.04.01 under relative bar snap.
        #expect(try GridSnap.bar.snappedBeat(15.1, relativeTo: 11) == 15)
        #expect(try GridSnap.bar.snappedBeat(15.1) == 16)
        #expect(try GridSnap.beat.snappedBeat(1.1, relativeTo: 0.35) == 1.35)
        #expect(try GridSnap.beat.snappedBeat(1.1) == 1)
        #expect(abs(try GridSnap.quantize(0.25).snappedBeat(1.11, relativeTo: 0.07) - 1.07) < 1e-12)
        #expect(try GridSnap.quantize(0.25).snappedBeat(1.11) == 1)
        // Clamping retains the first available phase, rather than shifting it to zero.
        #expect(abs(try GridSnap.beat.snappedBeat(0, relativeTo: 0.8) - 0.8) < 1e-12)
    }

    @Test func signatureAwareGridUsesDenominatorBeatsAndRejectsUnknownCrossing() throws {
        #expect(try GridSnap.bar.snappedBeat(15.6, signatures: variedSignature) == 17)
        #expect(try GridSnap.beat.snappedBeat(15.3, signatures: variedSignature) == 15.5)
        #expect(try GridSnap.bar.snappedBeat(13.9, signatures: variedSignature) == 14)
        rejects { _ = try GridSnap.bar.snappedBeat(14.2, signatures: variedSignature, relativeTo: 13) }
        rejects { _ = try GridSnap.bar.snappedBeat(13.9, signatures: variedSignature, relativeTo: 11.5) }
        for spacing in [0, -1, .nan, .infinity, 1e-100] {
            rejects { _ = try GridSnap.quantize(spacing).snappedBeat(3) }
        }
    }

    @Test func musicalModelsCodableRoundTripAndDecodedInvalidStateStillRejects() throws {
        let tempo = variedTempo
        #expect(try JSONDecoder().decode(TempoMap.self, from: JSONEncoder().encode(tempo)) == tempo)
        let signature = variedSignature
        #expect(try JSONDecoder().decode(SignatureMap.self, from: JSONEncoder().encode(signature)) == signature)
        let grid = GridSnap.quantize(0.25)
        #expect(try JSONDecoder().decode(GridSnap.self, from: JSONEncoder().encode(grid)) == grid)
        var invalid = tempo
        invalid.events[1].beat = -2
        let decoded = try JSONDecoder().decode(TempoMap.self, from: JSONEncoder().encode(invalid))
        rejects { _ = try decoded.seconds(atBeat: 8) }
    }
}
