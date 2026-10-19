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
    private var meterGeneration: UInt64 = 0
    private var meterTapInstalled = false

    /// Linear left/right peaks from the latest delivered mixer tap buffer.
    /// These measure the engine mix, not the DAC or speakers. Values may exceed 1.
    public private(set) var outputPeaks: [Float] = [0, 0]

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

    public var isPlaying: Bool { running && currentTime < duration }

    public func configure(project: Project, projectRoot: URL) throws {
        stop()
        for player in players { engine.detach(player) }
        players.removeAll()
        playbackBuffers.removeAll()
        prepared = nil
        stoppedPosition = 0
        let next = try AudioPreparation.prepare(project, root: projectRoot)
        for _ in next.clips {
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
        guard let prepared else { throw RebaseCoreError.notConfigured }
        guard seconds.isFinite, seconds >= 0 else {
            throw RebaseCoreError.invalidProject("Playback position must be a nonnegative time.")
        }
        stop()
        startPosition = min(seconds, duration)
        stoppedPosition = startPosition
        guard startPosition < duration else { return }
        let sampleRate = prepared.format.sampleRate
        let fromFrame = Int64((startPosition * sampleRate).rounded())
        startPosition = Double(fromFrame) / sampleRate
        var scheduled: [(AVAudioPlayerNode, AVAudioPCMBuffer, TimeInterval)] = []
        for (clip, player) in zip(prepared.clips, players) {
            let clipEnd = clip.startFrame + Int64(clip.buffer.frameLength)
            guard clipEnd > fromFrame else { continue }
            let skip = max(0, fromFrame - clip.startFrame)
            let remaining = Int(clip.buffer.frameLength) - Int(skip)
            let playback: AVAudioPCMBuffer
            if skip == 0 {
                playback = clip.buffer
            } else {
                playback = try AudioPreparation.buffer(format: prepared.format, frames: remaining)
                for channel in 0..<2 {
                    playback.floatChannelData![channel].update(
                        from: clip.buffer.floatChannelData![channel].advanced(by: Int(skip)), count: remaining)
                }
            }
            let delay = Double(max(0, clip.startFrame - fromFrame)) / sampleRate
            scheduled.append((player, playback, delay))
        }
        engine.prepare()
        installMeterTap()
        do { try engine.start() }
        catch {
            removeMeterTap()
            throw error
        }
        // The lead-in allows every node to receive the same future-clock origin.
        startHostTime = mach_absolute_time() + AVAudioTime.hostTime(forSeconds: 0.08)
        for (player, buffer, delay) in scheduled {
            player.scheduleBuffer(buffer, at: nil, options: [])
            player.play(at: AVAudioTime(hostTime: startHostTime + AVAudioTime.hostTime(forSeconds: delay)))
            playbackBuffers.append(buffer)
        }
        running = true
        let wait = duration - startPosition + 0.08
        completionTask = Task { @MainActor [weak self] in
            do { try await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000)) }
            catch { return }
            guard let self, !Task.isCancelled else { return }
            self.stop()
            self.stoppedPosition = self.duration
        }
    }

    public func stop() {
        let position = currentTime
        completionTask?.cancel()
        completionTask = nil
        running = false
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
