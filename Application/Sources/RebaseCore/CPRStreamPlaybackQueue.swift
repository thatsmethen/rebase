import AVFoundation
import Foundation

/// Application scheduling policy, not a reconstruction of Reference's threads.
/// A serial producer owns the cursor and a bounded set of scheduled buffers.
/// Player callbacks only enqueue work here. After synchronous priming, refill
/// and lifecycle reporting never run on the render callback or main actor.
final class CPRStreamPlaybackQueue {
    typealias Producer = () throws -> AVAudioPCMBuffer?
    typealias Scheduler = (AVAudioPCMBuffer, @escaping () -> Void) -> Void
    typealias Completion = (Result<Void, Error>) -> Void

    private enum Phase { case ready, running, terminal }
    private let queue = DispatchQueue(label: "org.rebase.rebase.source-event-producer",
                                      qos: .userInitiated)
    private let isolationKey = DispatchSpecificKey<UInt8>()
    private let depth: Int
    private let schedule: Scheduler
    private var nextBuffer: Producer?
    private var completion: Completion?
    private var phase = Phase.ready
    private var pending: [UUID: AVAudioPCMBuffer] = [:]

    init(nextBuffer: @escaping Producer, schedule: @escaping Scheduler,
         completion: @escaping Completion, depth: Int = 4) {
        precondition(depth > 0 && depth <= 64)
        self.nextBuffer = nextBuffer
        self.schedule = schedule
        self.completion = completion
        self.depth = depth
        queue.setSpecific(key: isolationKey, value: 1)
    }

    /// Prime before starting the player. A failed prime schedules no buffers.
    /// Dispatch sync may run this initial work on the caller's physical thread;
    /// it is serialized with the worker, and does not overlap live playback.
    func start() throws {
        try withQueue {
            guard phase == .ready else {
                throw RebaseCoreError.invalidProject("This source playback queue has already been used.")
            }
            do {
                var initial: [AVAudioPCMBuffer] = []
                for _ in 0..<depth {
                    guard let buffer = try produce() else { break }
                    initial.append(buffer)
                }
                phase = .running
                for buffer in initial { enqueue(buffer) }
                finishIfDrained()
            } catch {
                phase = .terminal
                nextBuffer = nil
                completion = nil
                pending.removeAll()
                throw error
            }
        }
    }

    /// A scheduling barrier: after this returns no callback can schedule more
    /// buffers. The owner can then stop/detach the player without racing refill.
    /// The host must not stop the player from its render/completion callback.
    /// Cancelling from our terminal notification is safe and does not resync.
    func cancel() {
        withQueue {
            phase = .terminal
            nextBuffer = nil
            completion = nil
            pending.removeAll()
        }
    }

    private func withQueue<T>(_ body: () throws -> T) rethrows -> T {
        if DispatchQueue.getSpecific(key: isolationKey) != nil { return try body() }
        return try queue.sync(execute: body)
    }

    private func produce() throws -> AVAudioPCMBuffer? {
        guard let nextBuffer else { return nil }
        guard let buffer = try nextBuffer() else {
            self.nextBuffer = nil
            return nil
        }
        guard buffer.frameLength > 0 else {
            throw RebaseCoreError.unsupportedAudio("The source converter returned an empty playback buffer.")
        }
        return buffer
    }

    private func enqueue(_ buffer: AVAudioPCMBuffer) {
        guard phase == .running else { return }
        let id = UUID()
        pending[id] = buffer
        schedule(buffer) { [weak self] in
            // Returning from the AVAudioPlayerNode callback before conversion
            // also avoids calling stop while inside its completion callback.
            self?.queue.async { [weak self] in self?.consumed(id) }
        }
    }

    private func consumed(_ id: UUID) {
        guard phase == .running, pending.removeValue(forKey: id) != nil else { return }
        do {
            while pending.count < depth, nextBuffer != nil {
                guard let buffer = try produce() else { break }
                enqueue(buffer)
            }
            finishIfDrained()
        } catch {
            finish(.failure(error))
        }
    }

    private func finishIfDrained() {
        if pending.isEmpty && nextBuffer == nil { finish(.success(())) }
    }

    private func finish(_ result: Result<Void, Error>) {
        guard phase == .running else { return }
        phase = .terminal
        nextBuffer = nil
        let notify = completion
        completion = nil
        // Already scheduled audio remains owned until the host stops the
        // player or this queue is released; no further refill follows failure.
        notify?(result)
    }
}
