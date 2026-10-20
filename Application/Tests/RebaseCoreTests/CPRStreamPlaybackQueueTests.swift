import AVFoundation
import Foundation
import Testing
@testable import RebaseCore

/// Application host-queue controls. Expectations come from explicit supplied
/// buffers/callback order, not a reconstructed Reference thread or timing model.
@Suite(.serialized)
struct CPRStreamPlaybackQueueTests {
    private enum Injected: Error { case producer }

    private final class State: @unchecked Sendable {
        let condition = NSCondition()
        var produced = 0
        var scheduled: [Int] = []
        var callbacks: [() -> Void] = []
        var results: [Bool] = []
        var ranOnMain = false
        var producerDepth = 0
        var maxProducerDepth = 0
        var scheduleDepth = 0
        var maxScheduleDepth = 0

        @discardableResult
        func locked<T>(_ body: () -> T) -> T {
            condition.lock(); defer { condition.unlock() }
            let result = body(); condition.broadcast(); return result
        }

        func wait(_ predicate: () -> Bool, seconds: TimeInterval = 5) -> Bool {
            condition.lock(); defer { condition.unlock() }
            let deadline = Date(timeIntervalSinceNow: seconds)
            while !predicate() {
                if !condition.wait(until: deadline) { return predicate() }
            }
            return true
        }

        func callback(_ index: Int) -> (() -> Void)? {
            locked { callbacks.indices.contains(index) ? callbacks[index] : nil }
        }

        func note(_ result: Result<Void, Error>) {
            locked {
                if case .success = result { results.append(true) }
                else { results.append(false) }
                ranOnMain = ranOnMain || Thread.isMainThread
            }
        }
    }

    private func buffer(_ identity: Int, frames: Int = 32) throws -> AVAudioPCMBuffer {
        let format = try #require(AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 2))
        let result = try #require(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)))
        result.frameLength = AVAudioFrameCount(frames)
        for frame in 0..<frames {
            result.floatChannelData![0][frame] = Float(identity + 1) / 256
            result.floatChannelData![1][frame] = -Float(identity + 1) / 512
        }
        return result
    }

    private func identity(_ buffer: AVAudioPCMBuffer) -> Int {
        Int(buffer.floatChannelData![0][0] * 256) - 1
    }

    private func fakeQueue(_ state: State, count: Int, depth: Int = 4,
                           failureAt: Int? = nil) -> CPRStreamPlaybackQueue {
        CPRStreamPlaybackQueue(nextBuffer: {
            let index = state.locked {
                state.ranOnMain = state.ranOnMain || Thread.isMainThread
                let index = state.produced
                state.produced += 1
                return index
            }
            if index == failureAt { throw Injected.producer }
            return index < count ? try buffer(index) : nil
        }, schedule: { value, callback in
            state.locked {
                state.scheduled.append(identity(value))
                state.callbacks.append(callback)
                state.ranOnMain = state.ranOnMain || Thread.isMainThread
            }
        }, completion: { state.note($0) }, depth: depth)
    }

    @Test func PrimeIsAtomicAndEmptySourceCompletesOnce() throws {
        let failed = State()
        let bad = fakeQueue(failed, count: 10, failureAt: 2)
        #expect(throws: Injected.self) { try bad.start() }
        #expect(failed.locked { failed.produced == 3 && failed.scheduled.isEmpty && failed.results.isEmpty })
        #expect(throws: RebaseCoreError.self) { try bad.start() }
        bad.cancel()

        let empty = State()
        let queue = fakeQueue(empty, count: 0)
        try queue.start()
        #expect(empty.locked { empty.produced == 1 && empty.scheduled.isEmpty && empty.results == [true] })
        #expect(throws: RebaseCoreError.self) { try queue.start() }
        queue.cancel()
        #expect(empty.locked { empty.results == [true] })
    }

    @Test @MainActor func RefillAndDrainContinueWhileMainActorIsBlocked() throws {
        let state = State()
        let queue = fakeQueue(state, count: 19)
        try queue.start()
        #expect(state.locked { state.produced == 4 && state.scheduled == [0, 1, 2, 3] })
        // DispatchQueue.sync may perform the initial prime on the caller's
        // physical thread. The guarantee under test is independent refill,
        // scheduling and completion after the synchronous prime has returned.
        state.locked { state.ranOnMain = false }
        let finished = DispatchSemaphore(value: 0)
        let driverOK = State()
        DispatchQueue.global().async {
            var ok = true
            for index in 0..<19 {
                if !state.wait({ state.callbacks.count > index }) { ok = false; break }
                state.callback(index)?()
                // A duplicate must neither release another buffer nor refill twice.
                state.callback(index)?()
                let expectedScheduled = min(19, index + 5)
                if !state.wait({ state.scheduled.count >= expectedScheduled }) { ok = false; break }
                if !state.locked({ state.scheduled.count == expectedScheduled }) { ok = false; break }
            }
            ok = state.wait({ !state.results.isEmpty }) && ok
            driverOK.locked { driverOK.results = [ok] }
            finished.signal()
        }
        // Deliberately do not service the main actor during all 19 deliveries.
        #expect(finished.wait(timeout: .now() + 10) == .success)
        #expect(driverOK.locked { driverOK.results == [true] })
        #expect(state.locked {
            state.scheduled == Array(0..<19) && state.produced == 20 &&
            state.results == [true] && !state.ranOnMain
        })
        queue.cancel()
    }

    @Test func SynchronousSchedulerCallbacksAreDeferredAndNotRecursive() throws {
        let state = State()
        let queue = CPRStreamPlaybackQueue(nextBuffer: {
            let index = state.locked {
                state.producerDepth += 1
                state.maxProducerDepth = max(state.maxProducerDepth, state.producerDepth)
                let value = state.produced; state.produced += 1
                return value
            }
            defer { state.locked { state.producerDepth -= 1 } }
            return index < 100 ? try buffer(index) : nil
        }, schedule: { value, callback in
            state.locked {
                state.scheduleDepth += 1
                state.maxScheduleDepth = max(state.maxScheduleDepth, state.scheduleDepth)
                state.scheduled.append(identity(value))
            }
            callback(); callback()
            state.locked { state.scheduleDepth -= 1 }
        }, completion: { state.note($0) })
        try queue.start()
        #expect(state.wait { !state.results.isEmpty })
        #expect(state.locked {
            state.results == [true] && state.scheduled == Array(0..<100) &&
            state.produced == 101 && state.maxProducerDepth == 1 && state.maxScheduleDepth == 1
        })
        queue.cancel()
    }

    @Test func CancelWaitsForInFlightProductionAndRejectsAllLateCallbacks() throws {
        let state = State()
        let entered = DispatchSemaphore(value: 0), release = DispatchSemaphore(value: 0)
        let cancelled = DispatchSemaphore(value: 0)
        let queue = CPRStreamPlaybackQueue(nextBuffer: {
            let index = state.locked { let i = state.produced; state.produced += 1; return i }
            if index == 4 {
                entered.signal()
                guard release.wait(timeout: .now() + 5) == .success else { throw Injected.producer }
            }
            return try buffer(index)
        }, schedule: { value, callback in
            state.locked { state.scheduled.append(identity(value)); state.callbacks.append(callback) }
        }, completion: { state.note($0) })
        try queue.start()
        state.callback(0)?()
        #expect(entered.wait(timeout: .now() + 5) == .success)
        DispatchQueue.global().async { queue.cancel(); cancelled.signal() }
        #expect(cancelled.wait(timeout: .now() + 0.05) == .timedOut)
        release.signal()
        #expect(cancelled.wait(timeout: .now() + 5) == .success)
        let before = state.locked { (state.produced, state.scheduled.count, state.callbacks) }
        for callback in before.2 { callback(); callback() }
        // A synchronous barrier waits behind every just-enqueued callback.
        queue.cancel()
        #expect(state.locked {
            state.produced == before.0 && state.scheduled.count == before.1 && state.results.isEmpty
        })
        #expect(throws: RebaseCoreError.self) { try queue.start() }
    }

    @Test func RefillFailureNotifiesOnceAndRetainsUnplayedBuffersUntilCancel() throws {
        let state = State()
        weak var retained: AVAudioPCMBuffer?
        let queue = CPRStreamPlaybackQueue(nextBuffer: {
            let index = state.locked { let i = state.produced; state.produced += 1; return i }
            if index == 4 { throw Injected.producer }
            return try buffer(index)
        }, schedule: { value, callback in
            if identity(value) == 3 { retained = value }
            state.locked { state.scheduled.append(identity(value)); state.callbacks.append(callback) }
        }, completion: { state.note($0) })
        try queue.start()
        state.callback(0)?()
        #expect(state.wait { !state.results.isEmpty })
        #expect(state.locked { state.results == [false] && state.produced == 5 && state.scheduled == [0, 1, 2, 3] })
        #expect(retained != nil)
        for callback in state.locked({ state.callbacks }) { callback(); callback() }
        queue.cancel()
        #expect(retained == nil)
        #expect(state.locked { state.results == [false] && state.produced == 5 })
    }

    @Test func CancelFromCompletionDoesNotDeadlockAndOldCallbacksCannotAffectRestart() throws {
        let first = State(), second = State()
        var firstQueue: CPRStreamPlaybackQueue?
        firstQueue = CPRStreamPlaybackQueue(nextBuffer: { nil }, schedule: { _, _ in
            Issue.record("Empty queue unexpectedly scheduled audio")
        }, completion: { result in firstQueue?.cancel(); first.note(result) })
        try firstQueue!.start()
        #expect(first.locked { first.results == [true] })
        firstQueue = nil

        let old = fakeQueue(first, count: 100)
        try old.start()
        let callbacks = first.locked { first.callbacks }
        old.cancel()
        let fresh = fakeQueue(second, count: 2)
        try fresh.start()
        for callback in callbacks { callback() }
        old.cancel()
        #expect(second.locked { second.scheduled == [0, 1] && second.results.isEmpty })
        second.callback(1)?() // Reverse completion order is also valid.
        second.callback(0)?()
        #expect(second.wait { !second.results.isEmpty })
        #expect(second.locked { second.results == [true] && second.produced == 3 })
        fresh.cancel()
    }

    @Test func EmptyBufferIsRejectedDuringPrimeWithoutScheduling() throws {
        let empty = try buffer(0)
        empty.frameLength = 0
        let state = State()
        let queue = CPRStreamPlaybackQueue(nextBuffer: { empty }, schedule: { _, _ in
            state.locked { state.scheduled.append(0) }
        }, completion: { state.note($0) })
        #expect(throws: RebaseCoreError.self) { try queue.start() }
        #expect(state.locked { state.scheduled.isEmpty && state.results.isEmpty })
        queue.cancel()
    }

    @Test @MainActor func OfflinePlayerReceivesMoreThanFourBuffersWhileMainActorIsBlocked() throws {
        let complete = DispatchSemaphore(value: 0)
        let state = State()
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let blocks = 15, frames = 512
                let format = try #require(AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 2))
                let engine = AVAudioEngine(), player = AVAudioPlayerNode()
                engine.attach(player); engine.connect(player, to: engine.mainMixerNode, format: format)
                player.volume = 1; engine.mainMixerNode.outputVolume = 1
                try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: 128)
                let queue = CPRStreamPlaybackQueue(nextBuffer: {
                    let index = state.locked {
                        state.ranOnMain = state.ranOnMain || Thread.isMainThread
                        let i = state.produced; state.produced += 1; return i
                    }
                    return index < blocks ? try buffer(index, frames: frames) : nil
                }, schedule: { value, callback in
                    player.scheduleBuffer(value, at: nil, options: [], completionCallbackType: .dataRendered) { _ in callback() }
                    state.locked {
                        state.scheduled.append(identity(value))
                        state.ranOnMain = state.ranOnMain || Thread.isMainThread
                    }
                }, completion: { state.note($0) })
                defer { queue.cancel(); player.stop(); engine.stop(); engine.disableManualRenderingMode() }
                try queue.start(); try engine.start(); player.play()
                let output = try #require(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 128))
                var position = 0, retries = 0
                while position < blocks * frames + 257 {
                    let block = position / frames
                    if position % frames == 0 && block < blocks {
                        try #require(state.wait { state.scheduled.count >= min(blocks, block + 2) })
                    }
                    let count = AVAudioFrameCount(min(128, blocks * frames + 257 - position))
                    let status = try engine.renderOffline(count, to: output)
                    if status == .cannotDoInCurrentContext && retries < 32 { retries += 1; continue }
                    try #require(status == .success && output.frameLength == count)
                    var matches = true
                    for offset in 0..<Int(count) {
                        let at = position + offset
                        for channel in 0..<2 {
                            let expected: Float = at < blocks * frames ?
                                (channel == 0 ? Float(at / frames + 1) / 256 : -Float(at / frames + 1) / 512) : 0
                            if output.floatChannelData![channel][offset].bitPattern != expected.bitPattern { matches = false }
                        }
                    }
                    try #require(matches)
                    position += Int(count)
                }
                try #require(state.wait { !state.results.isEmpty })
                #expect(state.locked {
                    state.scheduled == Array(0..<blocks) && state.produced == blocks + 1 &&
                    state.results == [true] && !state.ranOnMain
                })
            } catch { Issue.record("Offline producer check failed: \(error)") }
            complete.signal()
        }
        #expect(complete.wait(timeout: .now() + 20) == .success)
    }
}
