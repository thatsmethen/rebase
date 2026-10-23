import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

struct MusicalRulerTests {
    @Test func fixedTempoProducesMusicalBarsRatherThanSecondLabels() throws {
        let project = Project(tempoMap: TempoMap(events: [TempoEvent(beat: 0, bpm: 96)]))
        let original = project
        let ticks = try MusicalRuler.ticks(project: project, duration: 7.5, pixelsPerSecond: 100)
        #expect(ticks.prefix(5).map(\.seconds) == [0, 0.625, 1.25, 1.875, 2.5])
        #expect(ticks.prefix(5).map(\.bar) == [true, false, false, false, true])
        #expect(ticks.prefix(5).map(\.label) == ["1", "1", "1", "1", "2"])
        #expect(ticks.filter(\.bar).map(\.seconds) == [0, 2.5, 5, 7.5])
        #expect(ticks.filter(\.bar).map(\.label) == ["1", "2", "3", "4"])
        #expect(project == original)
    }

    @Test func tempoAndSignatureChangesKeepContinuousBarNumbersAndUniqueBoundaries() throws {
        let project = Project(tempoMap: TempoMap(events: [TempoEvent(beat: 0, bpm: 120),
            TempoEvent(beat: 4, bpm: 60), TempoEvent(beat: 10, bpm: 180)]),
            signatureMap: SignatureMap(events: [SignatureEvent(beat: 0, numerator: 4, denominator: 4),
                SignatureEvent(beat: 8, numerator: 3, denominator: 4),
                SignatureEvent(beat: 14, numerator: 6, denominator: 8)]))
        let ticks = try MusicalRuler.ticks(project: project, duration: 10, pixelsPerSecond: 100)
        let expectedBeats: [Double] = (0...13).map { Double($0) } + [14, 14.5, 15, 15.5, 16]
        let expectedTimes = expectedBeats.map { beat -> Double in
            if beat <= 4 { return beat / 2 }
            if beat <= 10 { return 2 + beat - 4 }
            return 8 + (beat - 10) / 3
        }
        #expect(ticks.count == expectedTimes.count)
        for (tick, time) in zip(ticks, expectedTimes) { #expect(abs(tick.seconds - time) < 1e-12) }
        #expect(ticks.filter(\.bar).map(\.label) == ["1", "2", "3", "4", "5"])
        for (bar, time) in zip(ticks.filter(\.bar), [0, 2, 6, 25.0 / 3, 28.0 / 3]) {
            #expect(abs(bar.seconds - time) < 1e-12)
        }
        #expect(ticks.filter { $0.seconds == 6 }.count == 1)
        #expect(zip(ticks, ticks.dropFirst()).allSatisfy { $0.seconds < $1.seconds })
    }

    @Test func visibleEndpointIsIncludedEvenWhenAnotherSignatureComesLater() throws {
        var project = Project(signatureMap: SignatureMap(events: [SignatureEvent(beat: 0, numerator: 4, denominator: 4),
            SignatureEvent(beat: 8, numerator: 3, denominator: 4)]))
        let beforeChange = try MusicalRuler.ticks(project: project, duration: 2, pixelsPerSecond: 100)
        #expect(beforeChange.last?.seconds == 2 && beforeChange.last?.label == "2")
        project.signatureMap.events[1].beat = 4
        let atChange = try MusicalRuler.ticks(project: project, duration: 2, pixelsPerSecond: 100)
        #expect(atChange.filter { $0.seconds == 2 }.count == 1)
        #expect(atChange.last?.bar == true && atChange.last?.label == "2")
    }

    @Test func zoomChangesDensityWithoutChangingMusicalPositions() throws {
        let project = Project()
        let sparse = try MusicalRuler.ticks(project: project, duration: 12, pixelsPerSecond: 4)
        #expect(sparse.map(\.seconds) == [0, 4, 8, 12])
        #expect(sparse.map(\.label) == ["1", "3", "5", "7"] && sparse.allSatisfy(\.bar))
        let dense = try MusicalRuler.ticks(project: project, duration: 12, pixelsPerSecond: 420)
        #expect(dense.count == 25)
        #expect(sparse.allSatisfy { dense.contains($0) })
    }

    @Test func recoveredFixedAndJumpClocksKeepTheirOwnArithmetic() throws {
        let fixed = try NativeTempoClock(fixedBPMBits: Float(126.5).bitPattern,
            sourceSHA256: String(repeating: "a", count: 64), sourceObjectOffset: 100)
        var project = Project(tempoMap: TempoMap(events: [TempoEvent(beat: 0, bpm: fixed.fixedBPM)], nativeClock: fixed))
        let native = try MusicalRuler.ticks(project: project, duration: 2, pixelsPerSecond: 100)
        #expect(native[1].seconds.bitPattern == (try fixed.seconds(atNativeTick: 480)).bitPattern)
        #expect(native[1].seconds != 60 / 126.5)
        #expect(project.tempoMap.nativeClock == fixed)
        project.tempoMap.events[0].bpm = 125
        #expect(throws: (any Error).self) { try MusicalRuler.ticks(project: project, duration: 2, pixelsPerSecond: 100) }

        let records = [NativeTempoMapRecord(periodBits: Float(0.5).bitPattern, secondsBits: 0, tickBits: 0,
            kind: 0, sourceRecordOffset: 108),
            NativeTempoMapRecord(periodBits: Float(1).bitPattern, secondsBits: Double(2).bitPattern,
                tickBits: Double(1920).bitPattern, kind: 0, sourceRecordOffset: 130)]
        let clock = try NativeTempoClock(mapRecords: records, sourceSHA256: String(repeating: "b", count: 64), sourceObjectOffset: 100)
        project = Project(tempoMap: TempoMap(events: records.map { TempoEvent(beat: $0.beat, bpm: $0.displayBPM) }, nativeClock: clock))
        let jump = try MusicalRuler.ticks(project: project, duration: 4, pixelsPerSecond: 100)
        #expect(jump.map(\.seconds) == [0, 0.5, 1, 1.5, 2, 3, 4])
        #expect(jump.filter(\.bar).map(\.label) == ["1", "2"])
        #expect(project.tempoMap.nativeClock == clock)
    }

    @Test func invalidInputsAndUnsupportedMapsFailWithoutASecondsFallback() throws {
        for duration in [-1.0, 86_400.01, .nan, .infinity, -.infinity] {
            #expect(throws: (any Error).self) { try MusicalRuler.ticks(project: Project(), duration: duration, pixelsPerSecond: 100) }
        }
        for scale in [0.0, 3.99, 420.01, .nan, .infinity, -.infinity] {
            #expect(throws: (any Error).self) { try MusicalRuler.ticks(project: Project(), duration: 10, pixelsPerSecond: scale) }
        }
        let ramp = Project(tempoMap: TempoMap(events: [TempoEvent(beat: 0, bpm: 120), TempoEvent(beat: 4, bpm: 96, curve: .ramp)]))
        #expect(throws: MusicalTimeError.unsupportedRamp) { try MusicalRuler.ticks(project: ramp, duration: 10, pixelsPerSecond: 100) }
        let invalidSignature = Project(signatureMap: SignatureMap(events: [SignatureEvent(beat: 0, numerator: 4, denominator: 4),
            SignatureEvent(beat: 3, numerator: 3, denominator: 4)]))
        #expect(throws: (any Error).self) { try MusicalRuler.ticks(project: invalidSignature, duration: 10, pixelsPerSecond: 100) }
    }

    @Test func zeroExtentAndResourceLimitsAreExplicitAndBounded() throws {
        let origin = try MusicalRuler.ticks(project: Project(), duration: 0, pixelsPerSecond: 4)
        #expect(origin == [MusicalRulerTick(seconds: 0, bar: true, label: "1")])
        let full = try MusicalRuler.ticks(project: Project(), duration: 86_400, pixelsPerSecond: 420)
        #expect(full.count == 8_192 && full.last?.seconds == 4095.5)
        #expect(full.allSatisfy { $0.seconds.isFinite && (0...86_400).contains($0.seconds) })
        #expect(MusicalRuler.defaultDuration(for: Project()) == 30)
        let long = Project(tracks: [Track(name: "Long", clips: [Clip(mediaPath: "Media/control.wav", name: "Long", duration: 86_400)])])
        #expect(MusicalRuler.defaultDuration(for: long) == 86_400)
    }
}
