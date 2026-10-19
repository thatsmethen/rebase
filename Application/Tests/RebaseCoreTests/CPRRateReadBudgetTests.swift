import Darwin
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

/// Independent retained Fraction-oracle controls; no resampler or target runs.
struct CPRRateReadBudgetTests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private let evidence = "research/evidence/cpr-static/cpr-audio-events-001/rate-converter/"

    private struct Oracle: Decodable {
        struct Vector: Decodable {
            let source_f32_bits: String, output_f32_bits: String
            let requested: Int, mode: Int, first: Bool, available: Bool
            let padding: Int, total_budget: Int, initial_ceil: Int
            let returned_source_frames: Int, reverse_mapped_frames: Int, correction_decrements: Int
            let input_ratio_f64_bits: String, output_ratio_f64_bits: String, initial_product_f64_bits: String
            let differs_from_ceil_alone: Bool, differs_from_f32_ratio_initial: Bool
            let differs_from_unrounded_rational_initial: Bool
        }
        let budget_vectors: [Vector], controls: [Vector]
    }

    private func project(_ source: Float = 44100, _ output: Float = 48000, _ count: Int = 1024,
                         branch: CPRRateReadBudget.Branch = .withoutInitialAllowance) throws -> CPRRateReadBudget {
        try CPRRateReadBudget.project(sourceRateBits: source.bitPattern, outputRateBits: output.bitPattern,
            requestedFrames: count, branch: branch)
    }

    @Test func all240IndependentBudgetVectorsAndFourControlsMatchExactBits() throws {
        let pins = [
            "finding.json": "a78e11153ad11bbd925a915a4e5260af19ce28188073a78a59f26cc0fe109ada",
            "count_oracle.py": "f4973e1c259792aca92a3e30202ba75acde3e7a88ed58cbe024c396859bdd6d2",
            "analytical-count-controls.json": "5d9e87d6e0608e14808fc1142f3273c4cae3e96f9c41a84de63060e87d948c92"
        ]
        for (path, hash) in pins {
            #expect(try cprSHA256(Data(contentsOf: workspace.appendingPathComponent(evidence + path))) == hash)
        }
        let bytes = try Data(contentsOf: workspace.appendingPathComponent(evidence + "analytical-count-controls.json"))
        let oracle = try JSONDecoder().decode(Oracle.self, from: bytes)
        #expect(oracle.budget_vectors.count == 240 && oracle.controls.count == 4)
        #expect(oracle.budget_vectors.contains { $0.differs_from_ceil_alone })
        #expect(oracle.budget_vectors.contains { $0.differs_from_f32_ratio_initial })
        #expect(oracle.budget_vectors.contains { $0.differs_from_unrounded_rational_initial })
        for vector in oracle.budget_vectors + oracle.controls {
            let source = try #require(UInt32(vector.source_f32_bits, radix: 16))
            let output = try #require(UInt32(vector.output_f32_bits, radix: 16))
            // This chooses a conditional arithmetic branch. It does not
            // observe or certify backend availability in this process.
            let branch: CPRRateReadBudget.Branch = vector.mode == 2 && vector.first && vector.available
                ? .mode2InitialAllowance : .withoutInitialAllowance
            let value = try CPRRateReadBudget.project(sourceRateBits: source, outputRateBits: output,
                requestedFrames: vector.requested, branch: branch)
            #expect(value.sourceFrames == vector.returned_source_frames)
            #expect(value.allowanceFrames == vector.padding)
            #expect(value.adjustedOutputFrames == vector.total_budget)
            #expect(value.diagnostics.initialSourceCeiling == vector.initial_ceil)
            #expect(value.diagnostics.reverseMappedFrames == vector.reverse_mapped_frames)
            #expect(value.diagnostics.correctionDecrements == vector.correction_decrements)
            #expect(value.diagnostics.inputRatioBits == UInt64(vector.input_ratio_f64_bits, radix: 16))
            #expect(value.diagnostics.outputRatioBits == UInt64(vector.output_ratio_f64_bits, radix: 16))
            #expect(value.diagnostics.initialProductBits == UInt64(vector.initial_product_f64_bits, radix: 16))
            #expect(value.diagnostics.searchEvaluations <= 33)
        }
    }

    @Test func roundedDoubleRatioAndReverseCorrectionAreRequired() throws {
        let widened = try project(8000, 192000, 48000)
        #expect(widened.sourceFrames == 2000) // Float32 ratio would initially ceil to 2001.
        #expect(widened.diagnostics.inputRatioBits == 0x3fa5555555555555)
        let rounded = try project(48000, 44100, 147)
        #expect(rounded.sourceFrames == 161) // Exact rational arithmetic would ceil to 160.
        #expect(rounded.diagnostics.initialProductBits == 0x4064000000000001)
        let corrected = try project(44100, 48000, 2, branch: .mode2InitialAllowance)
        #expect(corrected.diagnostics.initialSourceCeiling == 3766)
        #expect(corrected.sourceFrames == 3765 && corrected.diagnostics.reverseMappedFrames == 4097)
        let zero = try project(48000, 96000, 1)
        #expect(zero.diagnostics.initialSourceCeiling == 1 && zero.sourceFrames == 0)
        #expect(zero.diagnostics.reverseMappedFrames == 0 && zero.diagnostics.correctionDecrements == 1)
    }

    @Test func conditionalAllowanceAndEqualRateShortcutAreDistinct() throws {
        let regular = try project(), initial = try project(branch: .mode2InitialAllowance)
        #expect(regular.sourceFrames == 941 && regular.allowanceFrames == 0)
        #expect(initial.allowanceFrames == 4096 && initial.adjustedOutputFrames == 5120)
        #expect(initial.sourceFrames == 4704)
        let down = try project(48000, 44100, 1024, branch: .mode2InitialAllowance)
        #expect(down.allowanceFrames == 2048)
        for count in [1, 1024, Int(Int32.max)] {
            for branch: CPRRateReadBudget.Branch in [.withoutInitialAllowance, .mode2InitialAllowance] {
                let equal = try project(44100, 44100, count, branch: branch)
                #expect(equal.sourceFrames == count && equal.adjustedOutputFrames == count)
                #expect(equal.allowanceFrames == 0 && equal.diagnostics.searchEvaluations == 0)
            }
        }
    }

    @Test func invalidRateBitsAndCountsRejectWithoutNarrowingOrNormalization() throws {
        let invalid: [UInt32] = [0, 0x80000000, 1, 0x007fffff, 0x80800000, 0xbf800000,
            0x7f800000, 0xff800000, 0x7fc00000, 0x7f800001]
        for bits in invalid {
            #expect(throws: CPRRateReadBudgetError.invalidInput) {
                try CPRRateReadBudget.project(sourceRateBits: bits, outputRateBits: Float(48000).bitPattern,
                    requestedFrames: 1, branch: .withoutInitialAllowance)
            }
            #expect(throws: CPRRateReadBudgetError.invalidInput) {
                try CPRRateReadBudget.project(sourceRateBits: Float(48000).bitPattern, outputRateBits: bits,
                    requestedFrames: 1, branch: .mode2InitialAllowance)
            }
        }
        for count in [Int.min, -1, 0, Int(Int32.max) + 1, Int.max] {
            #expect(throws: CPRRateReadBudgetError.invalidInput) { try project(44100, 48000, count) }
        }
        // Normal extreme rates with equal bits are valid identities, with no
        // arithmetic underflow or subnormal flushing involved.
        for bits: UInt32 in [0x00800000, 0x7f7fffff] {
            #expect(try CPRRateReadBudget.project(sourceRateBits: bits, outputRateBits: bits,
                requestedFrames: 7, branch: .mode2InitialAllowance).sourceFrames == 7)
        }
    }

    @Test func ratioAndEverySignedConversionBoundaryAreChecked() throws {
        #expect(try project(1, 100, 100).sourceFrames == 1)
        #expect(try project(100, 1, 1).sourceFrames == 100)
        for (source, output): (Float, Float) in [(1, 100.00001), (100.00001, 1),
            (.leastNormalMagnitude, .greatestFiniteMagnitude), (.greatestFiniteMagnitude, .leastNormalMagnitude)] {
            #expect(throws: CPRRateReadBudgetError.arithmeticRange) { try project(source, output, 1) }
        }
        let limit = Int(Int32.max)
        #expect(throws: CPRRateReadBudgetError.arithmeticRange) { try project(96000, 48000, limit) }
        #expect(throws: CPRRateReadBudgetError.arithmeticRange) {
            try project(48000, 96000, limit, branch: .mode2InitialAllowance)
        }
        // N fits, initial ceiling fits, but reverse FCVTZS would receive 2^31.
        #expect(throws: CPRRateReadBudgetError.arithmeticRange) { try project(48000, 96000, limit) }
        #expect(throws: CPRRateReadBudgetError.arithmeticRange) {
            try project(48000, 96000, limit - 4096, branch: .mode2InitialAllowance)
        }
        let atBoundary = try project(48000, 96000, limit - 4097, branch: .mode2InitialAllowance)
        #expect(atBoundary.adjustedOutputFrames == limit - 1)
        #expect(atBoundary.sourceFrames == (limit - 1) / 2)
        // A large initial failure is searched in bounded work, without making
        // the native's logical one-decrement observation an algorithmic limit.
        let corrected = try project(48000, 96000, limit - 2)
        #expect(corrected.sourceFrames == (limit - 3) / 2)
        #expect(corrected.diagnostics.correctionDecrements == 1)
        #expect(corrected.diagnostics.searchEvaluations <= 33)
        #expect(corrected.diagnostics.reverseMappedFrames == limit - 3)
    }

    @Test func nonNearestModesAreRejectedAndNotChangedIncludingEqualRatePath() throws {
        let saved = fegetround()
        defer { _ = fesetround(saved) }
        for mode in [FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO] {
            #expect(fesetround(mode) == 0)
            #expect(throws: CPRRateReadBudgetError.unsupportedRoundingMode) { try project() }
            #expect(throws: CPRRateReadBudgetError.unsupportedRoundingMode) { try project(44100, 44100, 1) }
            #expect(fegetround() == mode)
        }
    }

    @Test func kernelErrorsPreserveCallerOutputAndRejectUnknownBranch() throws {
        var value = rb_cpr_rate_budget()
        value.source_frames = 123; value.allowance_frames = 456
        value.adjusted_output_frames = 789; value.input_ratio_bits = 0x0123456789abcdef
        let sentinel = withUnsafeBytes(of: value) { Data($0) }
        let cases: [(UInt32, UInt32, Int32, Int32, Int)] = [
            (0, Float(48000).bitPattern, 1, 0, RB_CPR_RATE_BUDGET_INVALID),
            (Float(44100).bitPattern, Float(48000).bitPattern, 0, 0, RB_CPR_RATE_BUDGET_INVALID),
            (Float(44100).bitPattern, Float(48000).bitPattern, 1, 2, RB_CPR_RATE_BUDGET_INVALID),
            (Float(48000).bitPattern, Float(96000).bitPattern, .max, 0, RB_CPR_RATE_BUDGET_RANGE)
        ]
        for (source, output, count, branch, status) in cases {
            #expect(Int(rb_cpr_rate_read_budget(source, output, count, branch, &value)) == status)
            #expect(withUnsafeBytes(of: value) { Data($0) } == sentinel)
        }
        #expect(rb_cpr_rate_read_budget(Float(44100).bitPattern, Float(48000).bitPattern, 1, 0, nil)
            == RB_CPR_RATE_BUDGET_INVALID)
    }
}
