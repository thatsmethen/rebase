#include "RateConversion.hpp"
#include "PlaybackCursor.hpp"
#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstring>
#include <memory>
#include <new>
#if defined(_M_X64) || defined(__x86_64__)
#include <xmmintrin.h>
#if defined(_MSC_VER)
#include <float.h>
#endif
#endif

namespace rebase {
bool conversion_environment_valid() {
    if (std::fegetround() != FE_TONEAREST) return false;
#if defined(_M_X64) || defined(__x86_64__)
    // Conversion can raise inexact/underflow even for finite input. Require
    // masked traps as well as nearest rounding and preserved denormals.
    const unsigned mxcsr = _mm_getcsr();
    if ((mxcsr & ((1u << 6) | (3u << 13) | (1u << 15))) != 0 || (mxcsr & 0x1f80) != 0x1f80)
        return false;
#if defined(_MSC_VER)
    unsigned control = 0;
    return _controlfp_s(&control, 0, 0) == 0 && (control & _MCW_EM) == _MCW_EM;
#else
    unsigned short control;
    __asm__ volatile("fnstcw %0" : "=m"(control));
    return (control & 0x3f) == 0x3f && (control & 0xc00) == 0;
#endif
#elif defined(__aarch64__) && !defined(_MSC_VER)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    return (fpcr & ((3ull << 22) | (1ull << 24) | (31ull << 8) | (1ull << 15))) == 0;
#else
    return false; // Unqualified architecture, never silently weaker semantics.
#endif
}
namespace {
std::vector<float> allocate_samples(size_t count) { return std::vector<float>(count); }
const ConversionServices standard{soxr_create, soxr_process, soxr_delete, allocate_samples};
struct Destroy {
    void (*function)(soxr_t);
    void operator()(soxr *value) const { if (value) function(value); }
};
}
int convert_snapshot(const float *input, uint64_t frames, uint32_t source_rate,
                     uint32_t endpoint_rate, std::vector<float> &output,
                     const ConversionServices *provided) {
    if (!valid_snapshot(input, frames, source_rate) || endpoint_rate < 8000 || endpoint_rate > 192000)
        return RB_AUDIO_ARGUMENT;
    const auto &service = provided ? *provided : standard;
    if (!service.create || !service.process || !service.destroy || !service.allocate)
        return RB_AUDIO_ARGUMENT;
    const uint64_t upper_frames = (frames * endpoint_rate + source_rate - 1) / source_rate;
    if (upper_frames > 32000000) return RB_AUDIO_CAPACITY;
    try {
        // Identity does not invoke floating point arithmetic or SoXR. Preserve
        // even signed-zero/subnormal bit patterns and bypass FP qualification.
        if (source_rate == endpoint_rate) {
            auto next = service.allocate(static_cast<size_t>(frames) * 2);
            if (next.size() != frames * 2) return RB_AUDIO_CONVERSION;
            std::memcpy(next.data(), input, next.size() * sizeof(float));
            output.swap(next); return RB_AUDIO_OK;
        }
        if (!conversion_environment_valid()) return RB_AUDIO_ENVIRONMENT;
        auto next = service.allocate(static_cast<size_t>(upper_frames) * 2);
        if (next.size() != upper_frames * 2) return RB_AUDIO_CONVERSION;
        const auto io = soxr_io_spec(SOXR_FLOAT32_I, SOXR_FLOAT32_I);
        const auto quality = soxr_quality_spec(SOXR_VHQ | SOXR_LINEAR_PHASE, 0);
        const auto runtime = soxr_runtime_spec(1);
        soxr_error_t error = nullptr;
        std::unique_ptr<soxr, Destroy> converter(service.create(source_rate, endpoint_rate, 2,
            &error, &io, &quality, &runtime), Destroy{service.destroy});
        if (!converter || error) return RB_AUDIO_CONVERSION;
        uint64_t consumed = 0, produced = 0;
        float overflow[2]{};
        for (;;) {
            const size_t input_count = static_cast<size_t>(std::min<uint64_t>(4096, frames - consumed));
            const size_t capacity = static_cast<size_t>(std::min<uint64_t>(4096, upper_frames - produced));
            size_t used = 0, made = 0;
            // A spare single-frame sink verifies actual EOF even if the bounded
            // destination is full; any extra output is an error, not truncation.
            float *destination = capacity ? next.data() + produced * 2 : overflow;
            error = service.process(converter.get(), input_count ? input + consumed * 2 : nullptr,
                input_count, &used, destination, capacity ? capacity : 1, &made);
            if (error || used > input_count || made > (capacity ? capacity : 1) || (!capacity && made))
                return RB_AUDIO_CONVERSION;
            for (size_t i = 0; i < made * 2; ++i)
                if (!std::isfinite(destination[i])) return RB_AUDIO_CONVERSION;
            consumed += used; produced += made;
            if (!input_count && !made) break; // Only NULL input establishes EOF.
            if (!used && !made) return RB_AUDIO_CONVERSION;
        }
        if (consumed != frames) return RB_AUDIO_CONVERSION;
        if (!produced) return RB_AUDIO_RATE_EMPTY;
        next.resize(static_cast<size_t>(produced) * 2); // Shrinks without a second PCM allocation.
        output.swap(next);
        return RB_AUDIO_OK;
    } catch (const std::bad_alloc &) { return RB_AUDIO_MEMORY; }
    catch (...) { return RB_AUDIO_CONVERSION; }
}
}
