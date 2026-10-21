import Foundation
import RebaseTimingDSP
import RebaseSoXR

/// Fixed-rate reconstruction of an accessor over an immutable stereo source.
/// The supplied source format and output rate are explicit context. A saved
/// WAV's format alone does not prove the format of Reference's selected backend.
/// This implements accessor calls, not a FIFO, timeline scheduler or device.
final class CPRNativeAudioAccessor {
    enum SourceFormat { case float32, pcm24 }
    enum Converter { case mode1, mode2 }
    struct Read {
        let samples: [Float]
        let requestedOutputFrames: Int
        let budgetSourceFrames: Int
        let actualSourceFrames: Int
        let firstCall: Bool
        let terminal: Bool
        var returnedOutputFrames: Int { samples.count / 2 }
    }

    let sourceRate: Float
    let outputRate: Float
    private let source: [Float]
    private let sourceFormat: SourceFormat
    private let converter: Converter
    private let mode2BudgetAvailable: Bool
    private var mode1Handle: OpaquePointer?
    private var mode2Handle: OpaquePointer?
    private(set) var sourcePosition: Int64 = 0
    private(set) var firstConvertedRead = true
    private(set) var terminalSeen = false
    private(set) var failed = false
    private(set) var gain: Float

    init(source: [Float], sourceRate: Double, outputRate: Double,
         sourceFormat: SourceFormat = .float32, converter: Converter = .mode2,
         mode2BudgetAvailable: Bool = true, gain: Float = 1) throws {
        var probe = RBAccessorSeek()
        guard sourceRate.isFinite, outputRate.isFinite,
              Double(Float(sourceRate)) == sourceRate, Double(Float(outputRate)) == outputRate,
              rb_cpr_accessor_seek(Float(sourceRate).bitPattern, Float(outputRate).bitPattern,
                                   0, &probe) == 0,
              !source.isEmpty, source.count % 2 == 0, source.count <= 32_000_000,
              Self.supportsGain(gain, pcm24EqualRate: sourceFormat == .pcm24 && sourceRate == outputRate) else {
            throw Self.unsupported
        }
        for value in source {
            guard value.isFinite, value == 0 || value.isNormal else { throw Self.unsupported }
            if sourceFormat == .pcm24 {
                let integer = Double(value) * 8_388_608
                // A packed signed integer zero decodes to +0. Accepting -0
                // here could feed a history-sensitive filter an impossible
                // PCM24 decode, even though the numerical value compares equal.
                guard (-8_388_608...8_388_607).contains(integer), integer.rounded() == integer,
                      value != 0 || value.bitPattern == 0 else {
                    throw Self.unsupported
                }
            }
        }
        self.source = source
        self.sourceRate = Float(sourceRate); self.outputRate = Float(outputRate)
        self.sourceFormat = sourceFormat; self.converter = converter
        self.mode2BudgetAvailable = mode2BudgetAvailable
        self.gain = gain
    }

    deinit {
        if let mode1Handle { rb_native_mode1_destroy(mode1Handle) }
        if let mode2Handle { rb_native_mode2_destroy(mode2Handle) }
    }

    /// The native setter changes only the gain field. The next read copies it
    /// into the retained converter; neither history nor the first flag resets.
    func setGain(_ value: Float) throws {
        guard !failed, !terminalSeen,
              Self.supportsGain(value, pcm24EqualRate: sourceFormat == .pcm24 && sourceRate == outputRate)
        else { throw Self.unsupported }
        gain = value
    }

    private static func supportsGain(_ value: Float, pcm24EqualRate: Bool) -> Bool {
        guard value.isFinite, value == 0 || value.isNormal else { return false }
        // Equal-rate PCM24 fast paths fold gain into either 2^-23 or 2^-31.
        // In this domain both scales stay normal and their power-of-two
        // rearrangement is exact. Smaller nonzero gains need the actual native
        // scalar/SIMD selection; do not silently pick one of those paths.
        return !pcm24EqualRate || value == 0 || abs(value) >= 0x1p-95
    }

    /// Native Float32 ratio, separately widened for both frame conversions.
    /// Seeking retains the existing converter and first-read flag. The returned
    /// output coordinate can differ from the requested coordinate.
    @discardableResult
    func seek(to outputFrame: Int64) throws -> Int64 {
        guard !failed, !terminalSeen else { throw Self.unsupported }
        var result = RBAccessorSeek()
        guard rb_cpr_accessor_seek(sourceRate.bitPattern, outputRate.bitPattern,
                                   outputFrame, &result) == 0,
              result.sourceFrame <= Int64(source.count / 2) else { throw Self.unsupported }
        sourcePosition = result.sourceFrame
        return result.returnedOutputFrame
    }

    /// Returns the actual native-shaped count. A caller requiring a full
    /// timeline read must reject a short count; it must not invent padding or
    /// borrow subsequent output to conceal a context/rate mismatch.
    func read(requestedFrames: Int) throws -> Read {
        guard !failed, !terminalSeen, (1...65_536).contains(requestedFrames) else {
            throw Self.unsupported
        }
        let converting = sourceRate != outputRate
        let first = firstConvertedRead
        var budget = requestedFrames
        if converting {
            var result = rb_cpr_rate_budget()
            guard rb_cpr_rate_read_budget(sourceRate.bitPattern, outputRate.bitPattern,
                Int32(requestedFrames), first && mode2BudgetAvailable ? 1 : 0, &result) == 0,
                result.source_frames <= 65_408 else { throw Self.unsupported }
            budget = Int(result.source_frames)
            // Cleared even when the native count helper returns zero. Seeking
            // does not restore it. This is distinct from backend availability.
            firstConvertedRead = false
        } else if sourceFormat == .pcm24 || gain != 1 {
            firstConvertedRead = false
        }
        if budget == 0 {
            return Read(samples: [], requestedOutputFrames: requestedFrames, budgetSourceFrames: 0,
                        actualSourceFrames: 0, firstCall: first, terminal: false)
        }
        let available = source.count / 2 - Int(sourcePosition)
        let actual = min(available, budget)
        let terminal = converting && actual == available && first && actual < budget
        let start = Int(sourcePosition) * 2
        var values = Array(source[start..<(start + actual * 2)])
        do {
            // The generic native converter applies destination-format gain
            // before upsampling, and after source-format downsampling. A gain
            // change therefore enters retained filter history only on the up
            // path. Equal-rate fast paths agree in the admitted gain domain.
            if sourceRate <= outputRate { try applyGain(to: &values) }
            if converting {
                // Existing kernels deliberately exclude continuation after a
                // terminal call. Native mode1 has no done guard; mode2 additionally
                // depends on its backend's EOF lifecycle. Never reset to hide this.
                values = try process(values, terminal: terminal)
                if sourceFormat == .pcm24 && sourceRate > outputRate && !values.isEmpty {
                    guard rb_cpr_accessor_pcm24_roundtrip(&values, values.count) == 0 else {
                        throw Self.unsupported
                    }
                }
            }
            if sourceRate > outputRate { try applyGain(to: &values) }
        } catch {
            // A backend may already have changed state. No retry of a
            // partially processed conversion is promised by this wrapper.
            failed = true
            throw error
        }
        sourcePosition += Int64(actual)
        terminalSeen = terminal
        return Read(samples: values, requestedOutputFrames: requestedFrames,
                    budgetSourceFrames: budget, actualSourceFrames: actual,
                    firstCall: first, terminal: terminal)
    }

    private func applyGain(to values: inout [Float]) throws {
        guard gain != 1, !values.isEmpty else { return }
        guard rb_cpr_accessor_gain_f32(&values, values.count, gain.bitPattern) == 0 else {
            throw Self.unsupported
        }
    }

    private func process(_ input: [Float], terminal: Bool) throws -> [Float] {
        let frames = input.count / 2
        let final: UInt32 = terminal ? 1 : 0
        var count = 0, produced = 0
        if converter == .mode1 {
            if mode1Handle == nil {
                guard rb_native_mode1_create(Double(sourceRate), Double(outputRate), 2,
                                              &mode1Handle) == 0 else { throw Self.unsupported }
            }
            guard rb_native_mode1_count(mode1Handle, frames, final, &count) == 0 else {
                throw Self.unsupported
            }
        } else {
            if mode2Handle == nil {
                guard rb_native_mode2_create(Double(sourceRate), Double(outputRate), 2,
                    rb_public_soxr_backend(), &mode2Handle) == 0 else { throw Self.unsupported }
            }
            guard rb_native_mode2_count(mode2Handle, frames, final, &count) == 0 else {
                throw Self.unsupported
            }
        }
        var output = [Float](repeating: 0, count: max(2, count * 2))
        let status = input.withUnsafeBufferPointer { source in
            output.withUnsafeMutableBufferPointer { destination in
                let pointer = frames == 0 ? nil : source.baseAddress
                if converter == .mode1 {
                    return rb_native_mode1_process(mode1Handle, pointer, frames,
                        destination.baseAddress, count, final, &produced)
                }
                return rb_native_mode2_process(mode2Handle, pointer, frames,
                    destination.baseAddress, count, final, &produced)
            }
        }
        guard status == 0, produced == count else { throw Self.unsupported }
        output.removeLast(output.count - count * 2)
        return output
    }

    private static var unsupported: RebaseCoreError {
        .unsupportedAudio("The native accessor call exceeds its verified rate, source, frame, floating-point or retained-state domain.")
    }
}
