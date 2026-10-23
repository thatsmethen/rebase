import Foundation
import AVFoundation
import Darwin

/// Playback schedules one player node per audible clip on a shared host clock.
/// Call configure again after project edits; configure and stop cancel playback.
@MainActor
public final class AudioTransportEngine {
    private let engine = AVAudioEngine()
    private var players: [AVAudioPlayerNode] = []
    private var prepared: PreparedProject?
    private var playbackBuffers: [AVAudioPCMBuffer] = []
    private var startHostTime: UInt64 = 0
    private var startPosition: TimeInterval = 0
    private var stoppedPosition: TimeInterval = 0
    private var running = false
    private var completionTask: Task<Void, Never>?
    private var playbackGeneration: UInt64 = 0
    private var pendingPlayers = 0
    private var timelineElapsed = false
    private var streamQueue: CPRStreamPlaybackQueue?
    private var meterGeneration: UInt64 = 0
    private var meterTapInstalled = false

    /// Linear left/right peaks from the latest delivered mixer tap buffer.
    /// These measure the engine mix, not the DAC or speakers. Values may exceed 1.
    public private(set) var outputPeaks: [Float] = [0, 0]
    public private(set) var playbackFailure: String?

    public init() {}

    public var duration: TimeInterval {
        guard let prepared else { return 0 }
        return Double(prepared.frameCount) / prepared.format.sampleRate
    }

    public var currentTime: TimeInterval {
        guard running else { return stoppedPosition }
        let now = mach_absolute_time()
        let elapsed = now > startHostTime ? AVAudioTime.seconds(forHostTime: now - startHostTime) : 0
        return min(duration, startPosition + elapsed)
    }

    public var isPlaying: Bool { running && engine.isRunning }

    public func configure(project: Project, projectRoot: URL) throws {
        clearConfiguration()
        let next = try AudioPreparation.prepare(project, root: projectRoot)
        install(next)
    }

    /// Explicitly audition the selected source event or its complete supported
    /// track. Fresh source proof and all media hashes are checked each time.
    @discardableResult
    public func configureCPRSourceEvent(eventID: UUID, project: Project, projectRoot: URL,
                                       mode: CPRSourceEventPlaybackMode = .sourceRate) throws -> CPRSourceEventPlaybackInfo {
        clearConfiguration()
        let next = try CPRSourceEventPlayback.prepare(eventID: eventID, project: project, root: projectRoot, mode: mode)
        install(next.audio)
        return next.info
    }

    private func clearConfiguration() {
        stop()
        for player in players { engine.detach(player) }
        players.removeAll()
        playbackBuffers.removeAll()
        prepared = nil
        stoppedPosition = 0
        playbackFailure = nil
    }

    private func install(_ next: PreparedProject) {
        let count = next.sourceEventStream == nil && next.nativeTimelineStream == nil ? next.clips.count : 1
        for _ in 0..<count {
            let player = AVAudioPlayerNode()
            engine.attach(player)
            engine.connect(player, to: engine.mainMixerNode, format: next.format)
            player.volume = 1
            players.append(player)
        }
        engine.mainMixerNode.outputVolume = 1
        prepared = next
    }

    public func play(from seconds: TimeInterval = 0) throws {
        stop()
        playbackFailure = nil
        guard let prepared else { throw RebaseCoreError.notConfigured }
        guard seconds.isFinite, seconds >= 0 else {
            throw RebaseCoreError.invalidProject("Playback position must be a nonnegative time.")
        }
        let sampleRate = prepared.format.sampleRate
        let schedule = try AudioPlaybackSchedule.make(prepared, from: seconds)
        startPosition = Double(schedule.startFrame) / sampleRate
        stoppedPosition = startPosition
        guard schedule.startFrame < prepared.frameCount else { return }
        var scheduled: [(AVAudioPlayerNode, AVAudioPCMBuffer, TimeInterval)] = []
        let generation = playbackGeneration
        let producer: CPRStreamPlaybackQueue.Producer?
        if let stream = prepared.nativeTimelineStream {
            let cursor = try stream.cursor(from: schedule.startFrame)
            producer = { try cursor.nextBuffer() }
        } else if let stream = prepared.sourceEventStream {
            let cursor = try stream.cursor(from: schedule.startFrame)
            producer = { try cursor.nextBuffer() }
        } else {
            producer = nil
        }
        if let producer {
            let player = players[0]
            let queue = CPRStreamPlaybackQueue(nextBuffer: producer,
                schedule: { buffer, consumed in
                    player.scheduleBuffer(buffer, at: nil, options: [],
                        completionCallbackType: .dataPlayedBack) { _ in consumed() }
                }, completion: { [weak self] result in
                    DispatchQueue.main.async { [weak self] in
                        guard let self, self.running, self.playbackGeneration == generation else { return }
                        switch result {
                        case .success:
                            self.pendingPlayers -= 1
                            self.finishPlaybackIfReady()
                        case .failure(let error):
                            self.playbackFailure = error.localizedDescription
                            self.stop()
                        }
                    }
                })
            streamQueue = queue
            do { try queue.start() }
            catch {
                stop()
                throw error
            }
        }
        for span in schedule.spans {
            let playback = try AudioPlaybackSchedule.buffer(for: span, in: prepared)
            scheduled.append((players[span.clipIndex], playback, Double(span.delayFrames) / sampleRate))
        }
        engine.prepare()
        installMeterTap()
        do { try engine.start() }
        catch {
            stop()
            throw error
        }
        // The lead-in allows every node to receive the same future-clock origin.
        startHostTime = mach_absolute_time() + AVAudioTime.hostTime(forSeconds: 0.08)
        pendingPlayers = scheduled.count + (streamQueue == nil ? 0 : 1)
        timelineElapsed = false
        running = true
        if streamQueue != nil {
            players[0].play(at: AVAudioTime(hostTime: startHostTime))
        }
        for (player, buffer, delay) in scheduled {
            player.scheduleBuffer(buffer, at: nil, options: [], completionCallbackType: .dataPlayedBack) { [weak self] _ in
                // Stopping from a player callback can deadlock. Return first;
                // stale callbacks from cancelled schedules cannot finish a new run.
                DispatchQueue.main.async { [weak self] in
                    guard let self, self.running, self.playbackGeneration == generation else { return }
                    self.pendingPlayers -= 1
                    self.finishPlaybackIfReady()
                }
            }
            player.play(at: AVAudioTime(hostTime: startHostTime + AVAudioTime.hostTime(forSeconds: delay)))
            playbackBuffers.append(buffer)
        }
        let wait = duration - startPosition + 0.08
        completionTask = Task { @MainActor [weak self] in
            do { try await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000)) }
            catch { return }
            guard let self, !Task.isCancelled, self.playbackGeneration == generation else { return }
            self.timelineElapsed = true
            self.finishPlaybackIfReady()
        }
    }

    private func finishPlaybackIfReady() {
        // Preserve silent project tails and wait for delivered player callbacks;
        // elapsed wall time alone must not cut off downstream audio.
        guard running, timelineElapsed, pendingPlayers == 0 else { return }
        stop()
        stoppedPosition = duration
    }

    public func stop() {
        let position = currentTime
        playbackGeneration &+= 1
        completionTask?.cancel()
        completionTask = nil
        running = false
        pendingPlayers = 0
        timelineElapsed = false
        streamQueue?.cancel()
        streamQueue = nil
        for player in players { player.stop() }
        engine.stop()
        removeMeterTap()
        playbackBuffers.removeAll()
        stoppedPosition = position
    }

    private func installMeterTap() {
        meterGeneration &+= 1
        let generation = meterGeneration
        engine.mainMixerNode.installTap(onBus: 0, bufferSize: 1024, format: nil) { [weak self] buffer, _ in
            guard let channels = buffer.floatChannelData else { return }
            let count = Int(buffer.frameLength)
            let channelCount = Int(buffer.format.channelCount)
            let interleaved = buffer.format.isInterleaved
            var peaks: [Float] = [0, 0]
            for channel in 0..<min(2, channelCount) {
                let samples = channels[interleaved ? 0 : channel]
                let stride = interleaved ? channelCount : 1
                let offset = interleaved ? channel : 0
                for frame in 0..<count {
                    let magnitude = abs(samples[frame * stride + offset])
                    if magnitude > peaks[channel] { peaks[channel] = magnitude }
                }
            }
            let measured = peaks
            // Never access actor state from the render callback. A generation
            // rejects already-enqueued results after stop or a new playback run.
            DispatchQueue.main.async { [weak self] in
                guard let self, self.running, self.meterGeneration == generation else { return }
                self.outputPeaks = measured
            }
        }
        meterTapInstalled = true
    }

    private func removeMeterTap() {
        meterGeneration &+= 1
        if meterTapInstalled {
            engine.mainMixerNode.removeTap(onBus: 0)
            meterTapInstalled = false
        }
        outputPeaks = [0, 0]
    }
}
