import Foundation
import RebaseTimingDSP

public enum CPRRateReadBudgetError: LocalizedError, Equatable {
    case invalidInput
    case unsupportedRoundingMode
    case arithmeticRange

    public var errorDescription: String? {
        switch self {
        case .invalidInput: return "The rate budget requires positive normal Float32 rates and a positive signed-32-bit request."
        case .unsupportedRoundingMode: return "The recovered rate budget requires round-to-nearest floating-point mode."
        case .arithmeticRange: return "The rate ratio or frame budget exceeds the supported arithmetic range."
        }
    }
}

/// Source-request counts from the bounded, static CPR-AUDIO-RATE-CONVERTER-001
/// contract. This does not resample audio, select a converter, detect backend
/// availability, or establish how many output samples a converter produces.
public struct CPRRateReadBudget: Equatable, Sendable {
    public enum Branch: Sendable {
        /// Mode 0/1, or a mode-2 call without the first/available conjunction.
        case withoutInitialAllowance
        /// Evaluate the conditional mode-2 first-call allowance. This value
        /// expresses an arithmetic assumption; it does not certify a backend.
        case mode2InitialAllowance
    }

    /// May be zero for a positive output request. Do not force a minimum of one.
    public let sourceFrames: Int
    public let allowanceFrames: Int
    public let adjustedOutputFrames: Int

    struct Diagnostics: Equatable, Sendable {
        let initialSourceCeiling: Int
        let reverseMappedFrames: Int
        let correctionDecrements: Int
        let searchEvaluations: Int
        let inputRatioBits: UInt64
        let outputRatioBits: UInt64
        let initialProductBits: UInt64
    }
    let diagnostics: Diagnostics

    /// Rates are exact stored Float32 bits, widened before division. The
    /// supported ratio Rout/Rin is [0.01,100]. Counts must fit each original
    /// signed-32-bit operation. All errors precede publication of a result.
    /// Equal rates return the request without an allowance in either branch.
    ///
    /// Caller responsibilities remain separate: select a valid branch, keep
    /// rates/state stable, validate source intervals and allocation byte
    /// capacities, and handle actual short reads, converter state and errors.
    public static func project(sourceRateBits: UInt32, outputRateBits: UInt32,
                               requestedFrames: Int, branch: Branch) throws -> CPRRateReadBudget {
        guard let requested = Int32(exactly: requestedFrames), requested > 0 else {
            throw CPRRateReadBudgetError.invalidInput
        }
        var raw = rb_cpr_rate_budget()
        let status = rb_cpr_rate_read_budget(sourceRateBits, outputRateBits, requested,
            branch == .mode2InitialAllowance ? 1 : 0, &raw)
        switch Int(status) {
        case RB_CPR_RATE_BUDGET_OK: break
        case RB_CPR_RATE_BUDGET_FP_ENVIRONMENT: throw CPRRateReadBudgetError.unsupportedRoundingMode
        case RB_CPR_RATE_BUDGET_RANGE: throw CPRRateReadBudgetError.arithmeticRange
        default: throw CPRRateReadBudgetError.invalidInput
        }
        return CPRRateReadBudget(sourceFrames: Int(raw.source_frames),
            allowanceFrames: Int(raw.allowance_frames), adjustedOutputFrames: Int(raw.adjusted_output_frames),
            diagnostics: Diagnostics(initialSourceCeiling: Int(raw.initial_source_ceiling),
                reverseMappedFrames: Int(raw.reverse_mapped_frames),
                correctionDecrements: Int(raw.correction_decrements),
                searchEvaluations: Int(raw.search_evaluations), inputRatioBits: raw.input_ratio_bits,
                outputRatioBits: raw.output_ratio_bits, initialProductBits: raw.initial_product_bits))
    }

    private init(sourceFrames: Int, allowanceFrames: Int, adjustedOutputFrames: Int,
                 diagnostics: Diagnostics) {
        self.sourceFrames = sourceFrames
        self.allowanceFrames = allowanceFrames
        self.adjustedOutputFrames = adjustedOutputFrames
        self.diagnostics = diagnostics
    }
}
