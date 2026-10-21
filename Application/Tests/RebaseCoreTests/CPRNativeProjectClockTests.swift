import AVFoundation
import Foundation
import Testing
@testable import RebaseCore

/// Independent integer-index controls for the explicit project-clock ordinary
/// reader context. These do not infer a hosted Reference clock from CPR metadata,
/// execute the target, or use the production planner to construct expectations.
@Suite(.serialized)
struct CPRNativeProjectClockTests {
    private func rejected(_ work: () throws -> Void) -> Bool {
        do { try work(); return false } catch { return true }
    }

    private func samples(_ frames: Int, seed: Int = 19) -> [Float] {
        // Exact binary fractions, distinct channels and deliberately irregular
        // adjacent values expose resampling, index scaling and channel swaps.
        (0..<frames * 2).map { Float(($0 * 73 + seed) % 8191 - 4095) / 8192 }
    }

    private func bits(_ buffer: AVAudioPCMBuffer) -> [UInt32] {
        let planes = buffer.floatChannelData!
        return (0..<Int(buffer.frameLength) * 2).map { planes[$0 % 2][$0 / 2].bitPattern }
    }

    private func read(_ stream: CPRNativeTimelineStream, from: Int64 = 0,
                      block: Int) throws -> [UInt32] {
        let cursor = try stream.cursor(from: from)
        var result: [UInt32] = []
        while let output = try cursor.nextBuffer(maximumFrames: block) {
            #expect(output.frameLength > 0 && output.frameLength <= block)
            #expect(output.format.sampleRate == stream.format.sampleRate)
            result.append(contentsOf: bits(output))
        }
        #expect(cursor.deliveredFrames == stream.frameCount && cursor.isAtEnd)
        #expect(try cursor.nextBuffer(maximumFrames: block) == nil)
        return result
    }

    @Test func DifferentClockRatesCopyRawFramesInBothDirections() throws {
        let input = samples(36_000)
        for (sourceRate, timelineRate) in [(44_100.0, 48_000.0), (48_000.0, 44_100.0)] {
            // Quarter-second coordinates are binary exact; both clock rates
            // are divisible by four. Native integer rounding cannot be near a
            // half-frame tie here. Crucially, offset is in the reader's clock.
            let start = Int(timelineRate) / 4
            let count = Int(timelineRate) / 4
            let offset = Int(timelineRate) / 4
            let stream = try CPRNativeTimelineStream(sampleRate: timelineRate, segments: [
                .init(start: 0.25, length: 0.25, offset: 0.25,
                      samples: input, gain: 1, sourceRate: sourceRate)
            ])
            let expected = [UInt32](repeating: 0, count: start * 2)
                + input[(offset * 2)..<((offset + count) * 2)].map(\.bitPattern)
            #expect(stream.frameCount == Int64(start + count))
            #expect(stream.format.sampleRate == timelineRate)
            #expect(offset != Int(sourceRate) / 4)
            #expect(input[offset * 2].bitPattern != input[(Int(sourceRate) / 4) * 2].bitPattern)
            for block in [17, 4096, 65_536] {
                #expect(try read(stream, block: block) == expected)
            }
            // The source duration remains 0.25 s in the descriptor, but the
            // amount of file time consumed changes with the supplied clock.
            #expect(Double(count) / sourceRate != 0.25)
        }
    }

    @Test func MixedSourceRatesGapsAndGainUseOneTimelineIndexSpace() throws {
        let rate = 8192.0
        let rows: [(start: Int, count: Int, offset: Int, gain: Float, rate: Double, input: [Float])] = [
            (3, 513, 7, 0.5, 44_100, samples(530, seed: 11)),
            (521, 257, 5, 2, 192_000, samples(275, seed: 71)),
            (778, 1027, 13, 1, 8000, samples(1050, seed: 917))
        ]
        let stream = try CPRNativeTimelineStream(sampleRate: rate, segments: rows.map { row in
            .init(start: Double(row.start) / rate, length: Double(row.count) / rate,
                  offset: Double(row.offset) / rate, samples: row.input,
                  gain: row.gain, sourceRate: row.rate)
        })
        var expected = [UInt32](repeating: 0, count: 1805 * 2)
        for row in rows {
            for frame in 0..<row.count {
                for channel in 0..<2 {
                    // Power-of-two gains are exact for every authored sample.
                    expected[(row.start + frame) * 2 + channel]
                        = (row.input[(row.offset + frame) * 2 + channel] * row.gain).bitPattern
                }
            }
        }
        for block in [1, 19, 257, 4096] {
            #expect(try read(stream, block: block) == expected)
        }
        // Includes prefix, gaps, touching boundary, exact prior end and EOF.
        for seek in [0, 2, 3, 515, 516, 520, 521, 777, 778, 1804, 1805] {
            #expect(try read(stream, from: Int64(seek), block: 31)
                    == Array(expected.dropFirst(seek * 2)))
        }
    }

    @Test func LongReadSeeksAndCallerMutationPreserveVerifiedSnapshot() throws {
        let rate = 32_768.0, length = 16_387, start = 5, offset = 11
        var input = samples(length + offset + 9)
        let saved = input
        let stream = try CPRNativeTimelineStream(sampleRate: rate, segments: [
            .init(start: Double(start) / rate, length: Double(length) / rate,
                  offset: Double(offset) / rate, samples: input, gain: 1, sourceRate: 48_000)
        ])
        input[0] = 999
        input[offset * 2] = -999
        let expected = [UInt32](repeating: 0, count: start * 2)
            + saved[(offset * 2)..<((offset + length) * 2)].map(\.bitPattern)
        for block in [257, 8192, 65_536] {
            #expect(try read(stream, block: block) == expected)
        }
        for seek in [4, 5, 8191, 8192, 8193, 16384, start + length - 1, start + length] {
            #expect(try read(stream, from: Int64(seek), block: 8191)
                    == Array(expected.dropFirst(seek * 2)))
        }
        let cursor = try stream.cursor(from: 0)
        let exposed = try #require(try cursor.nextBuffer(maximumFrames: 8192))
        exposed.floatChannelData![0][6] = 777
        #expect(try read(stream, block: 65_536) == expected)
        #expect(input != saved)
    }

    @Test func CompleteCapacityIsCheckedBeforeAnyPlaybackAndNeverPadded() throws {
        let input = samples(100)
        for sourceRate in [8000.0, 44_100.0, 192_000.0] {
            let exact = CPRNativeTimelineStream.Segment(start: 3 / 8192, length: 99 / 8192,
                offset: 1 / 8192, samples: input, gain: 1, sourceRate: sourceRate)
            let stream = try CPRNativeTimelineStream(sampleRate: 8192, segments: [exact])
            let expected = [UInt32](repeating: 0, count: 6) + input.dropFirst(2).map(\.bitPattern)
            #expect(try read(stream, block: 7) == expected)
            for (length, offset) in [(100.0, 1.0), (99, 2), (1, 100), (1, 101)] {
                #expect(rejected {
                    _ = try CPRNativeTimelineStream(sampleRate: 8192, segments: [
                        .init(start: 0, length: length / 8192, offset: offset / 8192,
                              samples: input, gain: 1, sourceRate: sourceRate)
                    ])
                })
            }
        }
        // A quarter-second 44.1k source really has only 11,025 frames. Merely
        // supplying a 48k timeline does not grant it 12,000 source frames.
        #expect(rejected {
            _ = try CPRNativeTimelineStream(sampleRate: 48_000, segments: [
                .init(start: 0, length: 0.25, offset: 0,
                      samples: samples(11_025), gain: 1, sourceRate: 44_100)
            ])
        })
    }

    @Test func InvalidSourceClockCannotBeHiddenByValidTimelineClock() throws {
        let input = samples(16)
        for sourceRate in [Double.nan, .infinity, -.infinity, -0.0, -1, 7999, 8192.5, 192001] {
            #expect(rejected {
                _ = try CPRNativeTimelineStream(sampleRate: 48_000, segments: [
                    .init(start: 0, length: 8 / 48_000, offset: 0,
                          samples: input, gain: 1, sourceRate: sourceRate)
                ])
            })
        }
        // Validate the entire descriptor collection before publishing a stream.
        #expect(rejected {
            _ = try CPRNativeTimelineStream(sampleRate: 48_000, segments: [
                .init(start: 0, length: 8 / 48_000, offset: 0,
                      samples: input, gain: 1, sourceRate: 44_100),
                .init(start: 8 / 48_000, length: 8 / 48_000, offset: 0,
                      samples: input, gain: 1, sourceRate: .nan)
            ])
        })
    }

    @Test func RawSignedZerosAndFailedRequestLeaveCursorUnchanged() throws {
        let values: [UInt32] = [0x80000000, 0, 0x3f000001, 0xbf000003,
                                0x3e800001, 0xbe800005, 0, 0x80000000]
        let stream = try CPRNativeTimelineStream(sampleRate: 8192, segments: [
            .init(start: 1 / 8192, length: 4 / 8192, offset: 0,
                  samples: values.map { Float(bitPattern: $0) }, gain: 1, sourceRate: 192_000)
        ])
        let cursor = try stream.cursor(from: 0)
        for block in [0, -1, 65_537] {
            #expect(rejected { _ = try cursor.nextBuffer(maximumFrames: block) })
            #expect(cursor.deliveredFrames == 0 && !cursor.isAtEnd)
        }
        let output = try #require(try cursor.nextBuffer(maximumFrames: 5))
        #expect(bits(output) == [0, 0] + values)
        #expect(cursor.isAtEnd && cursor.deliveredFrames == 5)
        #expect(try cursor.nextBuffer(maximumFrames: 5) == nil)
        #expect(rejected { _ = try stream.cursor(from: -1) })
        #expect(rejected { _ = try stream.cursor(from: 6) })
    }
}
