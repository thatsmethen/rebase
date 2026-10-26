#include "StreamEngine.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <stdexcept>

namespace rebase {
static_assert(std::atomic<uint64_t>::is_always_lock_free && std::atomic<uint32_t>::is_always_lock_free &&
              std::atomic<float>::is_always_lock_free && std::atomic<bool>::is_always_lock_free,
              "The native device path requires lock-free counters");
namespace {
bool rate_map(uint64_t frames, uint32_t from, uint32_t to, bool ceil, uint64_t &result) {
    if (!from || !to) return false;
    const uint64_t whole = frames / from, remainder = frames % from;
    if (whole > UINT64_MAX / to) return false;
    const uint64_t partial = (remainder * to + (ceil ? from - 1 : 0)) / from;
    const uint64_t base = whole * to;
    if (base > UINT64_MAX - partial) return false;
    result = base + partial; return true;
}
uint64_t upper_for(const RBAudioStreamDescriptor &d, uint32_t rate) {
    uint64_t upper = 0;
    if (validate_stream_descriptor(d) || rate < 8000 || rate > 192000 ||
        !rate_frame_bound(d.source_frames, d.source_rate, rate, upper)) throw std::invalid_argument("stream bounds");
    return upper;
}
uint32_t prime_for(const RBAudioStreamDescriptor &d, uint32_t buffer) {
    const uint64_t prime = d.prime_endpoint_frames ? d.prime_endpoint_frames : std::max<uint64_t>(4096, uint64_t(buffer) * 2);
    if (!buffer || prime < buffer || prime > d.endpoint_queue_frames) throw std::invalid_argument("stream priming");
    return static_cast<uint32_t>(prime);
}
struct Destroy { void (*function)(soxr_t); void operator()(soxr *p) const { if (p) function(p); } };
}
bool rate_frame_bound(uint64_t f, uint32_t from, uint32_t to, uint64_t &out) { return rate_map(f, from, to, true, out); }
bool rate_frame_floor(uint64_t f, uint32_t from, uint32_t to, uint64_t &out) { return rate_map(f, from, to, false, out); }
int validate_stream_descriptor(const RBAudioStreamDescriptor &d) {
    if (d.abi_version != 1 || d.channels != 2 || d.reserved || !d.generation || !d.source_frames ||
        d.source_rate < 8000 || d.source_rate > 192000 || !d.max_block_frames || d.max_block_frames > 65536 ||
        d.source_queue_frames < 4096 || d.source_queue_frames > 262144 ||
        d.endpoint_queue_frames < 4096 || d.endpoint_queue_frames > 262144 ||
        d.max_block_frames > d.source_queue_frames || d.prime_endpoint_frames > d.endpoint_queue_frames)
        return RB_AUDIO_ARGUMENT;
    return RB_AUDIO_OK;
}
StreamEngine::Ring::Ring(uint32_t capacity, const ConversionServices *services)
    : samples_(services && services->allocate ? services->allocate(static_cast<size_t>(capacity) * 2) : std::vector<float>(static_cast<size_t>(capacity) * 2)), capacity_(capacity) {
    if (samples_.size() != static_cast<size_t>(capacity) * 2) throw std::bad_alloc();
}
uint32_t StreamEngine::Ring::size() const {
    const uint64_t read = read_.load(std::memory_order_acquire);
    const uint64_t write = write_.load(std::memory_order_acquire);
    // Concurrent diagnostic readers can observe advancement between loads;
    // clamp their snapshot. The actual SPSC owners never overrun capacity.
    return static_cast<uint32_t>(std::min<uint64_t>(write - read, capacity_));
}
uint32_t StreamEngine::Ring::append(const float *input, uint32_t frames) {
    const uint64_t write = write_.load(std::memory_order_relaxed), read = read_.load(std::memory_order_acquire);
    frames = std::min(frames, capacity_ - static_cast<uint32_t>(write - read));
    const uint32_t index = static_cast<uint32_t>(write % capacity_);
    const uint32_t first = std::min(frames, capacity_ - index);
    std::memcpy(samples_.data() + size_t(index) * 2, input, size_t(first) * 8);
    if (frames > first) std::memcpy(samples_.data(), input + size_t(first) * 2, size_t(frames - first) * 8);
    write_.store(write + frames, std::memory_order_release);
    const uint32_t used = static_cast<uint32_t>(write + frames - read);
    peak_.store(std::max(peak_.load(std::memory_order_relaxed), used));
    return frames;
}
uint32_t StreamEngine::Ring::take(float *output, uint32_t frames) {
    const uint64_t read = read_.load(std::memory_order_relaxed), write = write_.load(std::memory_order_acquire);
    frames = std::min<uint32_t>(frames, static_cast<uint32_t>(write - read));
    const uint32_t index = static_cast<uint32_t>(read % capacity_);
    const uint32_t first = std::min(frames, capacity_ - index);
    std::memcpy(output, samples_.data() + size_t(index) * 2, size_t(first) * 8);
    if (frames > first) std::memcpy(output + size_t(first) * 2, samples_.data(), size_t(frames - first) * 8);
    read_.store(read + frames, std::memory_order_release);
    return frames;
}
StreamEngine::StreamEngine(const RBAudioStreamDescriptor &d, uint32_t rate, uint32_t buffer, const ConversionServices *services)
    : source_(validate_stream_descriptor(d) ? throw std::invalid_argument("descriptor") : d.source_queue_frames, services),
      endpoint_(d.endpoint_queue_frames, services), descriptor_(d), endpoint_rate_(rate), device_buffer_(buffer),
      prime_(prime_for(d, buffer)), upper_(upper_for(d, rate)), services_(services) {}
StreamEngine::~StreamEngine() { stop_producer(); }
int StreamEngine::start() {
    if (producer_.joinable()) return RB_AUDIO_STATE;
    producer_ = std::thread([this] { run(); });
    std::unique_lock<std::mutex> lock(wake_mutex_);
    while (!started_.load()) wake_.wait_for(lock, std::chrono::milliseconds(1));
    return result_.load();
}
void StreamEngine::wait_for_source(uint32_t frames) {
    // Notifications must satisfy the actual awaited work condition. A
    // stop-only predicate would ignore submitted input until the timeout.
    // The bounded fallback covers a notification racing the wait without
    // requiring the audio consumer to take this mutex.
    std::unique_lock<std::mutex> lock(wake_mutex_);
    wake_.wait_for(lock, std::chrono::milliseconds(1), [this, frames] {
        return stop_.load() || (frames ? source_.size() >= frames : eof_.load(std::memory_order_acquire));
    });
}
void StreamEngine::wait_for_endpoint() {
    std::unique_lock<std::mutex> lock(wake_mutex_);
    wake_.wait_for(lock, std::chrono::milliseconds(1), [this] {
        return stop_.load() || endpoint_.size() < endpoint_.capacity();
    });
}
int StreamEngine::submit(uint64_t generation, uint64_t sequence, uint64_t start, const float *samples, uint32_t frames) {
    std::lock_guard<std::mutex> lock(submission_);
    if (generation != descriptor_.generation) return RB_AUDIO_STALE;
    if (stop_.load() || eof_.load()) return RB_AUDIO_STATE;
    if (!samples || !frames || frames > descriptor_.max_block_frames) return RB_AUDIO_ARGUMENT;
    if (sequence != sequence_ || start != accepted_.load() || frames > descriptor_.source_frames - accepted_.load()) return RB_AUDIO_PROTOCOL;
    for (size_t i = 0; i < size_t(frames) * 2; ++i) {
        uint32_t bits; std::memcpy(&bits, samples + i, sizeof(bits));
        if ((bits & 0x7f800000u) == 0x7f800000u) return RB_AUDIO_ARGUMENT;
    }
    if (source_.capacity() - source_.size() < frames) return RB_AUDIO_BACKPRESSURE;
    if (sequence_ == UINT64_MAX) return RB_AUDIO_PROTOCOL;
    accepted_.fetch_add(frames);
    if (source_.append(samples, frames) != frames) { fail(RB_AUDIO_INTERNAL); return RB_AUDIO_INTERNAL; }
    ++sequence_; wake_.notify_one(); return RB_AUDIO_OK;
}
int StreamEngine::finish(uint64_t generation, uint64_t sequence, uint64_t committed) {
    std::lock_guard<std::mutex> lock(submission_);
    if (generation != descriptor_.generation) return RB_AUDIO_STALE;
    if (stop_.load() || eof_.load()) return RB_AUDIO_STATE;
    if (sequence != sequence_ || committed != accepted_.load() || committed != descriptor_.source_frames) return RB_AUDIO_PROTOCOL;
    eof_.store(true, std::memory_order_release); wake_.notify_one(); return RB_AUDIO_OK;
}
void StreamEngine::fail(int result, int32_t hr) {
    int32_t expected = RB_AUDIO_OK;
    if (result_.compare_exchange_strong(expected, result)) hresult_.store(hr);
    phase_.store(RB_AUDIO_FAULT); left_.store(0); right_.store(0); stop_.store(true); wake_.notify_one();
}
void StreamEngine::stop_producer() {
    { std::lock_guard<std::mutex> lock(submission_); stop_.store(true); }
    wake_.notify_one(); if (producer_.joinable()) producer_.join();
}
void StreamEngine::cancel() { stop_producer(); result_.store(RB_AUDIO_OK); hresult_.store(0); left_.store(0); right_.store(0); phase_.store(RB_AUDIO_CANCELLED); }
void StreamEngine::update_prime() {
    if (endpoint_.size() >= prime_ || (final_.load(std::memory_order_acquire) && total_.load() > 0)) {
        primed_.store(true); uint32_t expected = RB_AUDIO_PRIMING;
        phase_.compare_exchange_strong(expected, RB_AUDIO_READY);
    }
}
bool StreamEngine::flush(const float *samples, uint32_t count) {
    uint32_t offset = 0;
    while (offset < count && !stop_.load()) {
        const uint32_t added = endpoint_.append(samples + size_t(offset) * 2, count - offset);
        offset += added; update_prime();
        if (!added) wait_for_endpoint();
    }
    return offset == count;
}
void StreamEngine::run() noexcept {
    try {
        const bool converted = descriptor_.source_rate != endpoint_rate_;
        auto create = services_ ? services_->create : soxr_create;
        auto process = services_ ? services_->process : soxr_process;
        auto destroy = services_ ? services_->destroy : soxr_delete;
        if (!create || !process || !destroy) { fail(RB_AUDIO_ARGUMENT); started_.store(true); wake_.notify_all(); return; }
        std::unique_ptr<soxr, Destroy> converter(nullptr, Destroy{destroy});
        if (converted) {
            if (!conversion_environment_valid()) { fail(RB_AUDIO_ENVIRONMENT); started_.store(true); wake_.notify_all(); return; }
            const auto io = soxr_io_spec(SOXR_FLOAT32_I, SOXR_FLOAT32_I);
            const auto quality = soxr_quality_spec(SOXR_VHQ | SOXR_LINEAR_PHASE, 0);
            const auto runtime = soxr_runtime_spec(1);
            soxr_error_t error = nullptr;
            converter.reset(create(descriptor_.source_rate, endpoint_rate_, 2, &error, &io, &quality, &runtime));
            if (!converter || error) { fail(RB_AUDIO_CONVERSION); started_.store(true); wake_.notify_all(); return; }
        }
        started_.store(true); wake_.notify_all();
        std::array<float, 8192> input{}, output{};
        uint32_t retained = 0;
        while (!stop_.load()) {
            // Refill the sliding input window after partial consumption. This
            // exactly matches the snapshot oracle's next min(4096, remaining)
            // call, regardless of transport chunks or ring wrap boundaries.
            const uint32_t wanted = static_cast<uint32_t>(std::min<uint64_t>(4096, descriptor_.source_frames - consumed_.load()));
            retained += source_.take(input.data() + size_t(retained) * 2, wanted - retained);
            if (retained < wanted || (!wanted && !eof_.load(std::memory_order_acquire))) { wait_for_source(wanted - retained); continue; }
            size_t used = 0, made = 0;
            const size_t capacity = static_cast<size_t>(std::min<uint64_t>(4096, upper_ - produced_.load()));
            if (!converted) {
                used = wanted; made = wanted;
                if (made) std::memcpy(output.data(), input.data(), made * 8);
            } else {
                const auto error = process(converter.get(), wanted ? input.data() : nullptr, wanted, &used,
                                           output.data(), capacity ? capacity : 1, &made);
                if (error || used > wanted || made > (capacity ? capacity : 1) || (!capacity && made)) { fail(RB_AUDIO_CONVERSION); break; }
                for (size_t i = 0; i < made * 2; ++i) if (!std::isfinite(output[i])) { fail(RB_AUDIO_CONVERSION); break; }
                if (stop_.load()) break;
            }
            consumed_.fetch_add(used); produced_.fetch_add(made);
            if (used < retained) std::memmove(input.data(), input.data() + used * 2, (retained - used) * 8);
            retained -= static_cast<uint32_t>(used);
            if (!flush(output.data(), static_cast<uint32_t>(made))) break;
            if (!wanted && !made) {
                if (!produced_.load()) { fail(RB_AUDIO_RATE_EMPTY); break; }
                total_.store(produced_.load()); final_.store(true, std::memory_order_release); update_prime();
                uint32_t expected = RB_AUDIO_PLAYING; phase_.compare_exchange_strong(expected, RB_AUDIO_DRAINING);
                break;
            }
            if (!used && !made) { fail(RB_AUDIO_CONVERSION); break; }
        }
    } catch (const std::bad_alloc &) { fail(RB_AUDIO_MEMORY); }
      catch (...) { fail(RB_AUDIO_CONVERSION); }
    started_.store(true); wake_.notify_all();
}
bool StreamEngine::playing() const { const auto p = phase_.load(); return p == RB_AUDIO_PLAYING || p == RB_AUDIO_DRAINING; }
int StreamEngine::play() {
    if (playing()) return RB_AUDIO_OK;
    const auto p = phase_.load();
    if (!primed_.load() || (p != RB_AUDIO_READY && p != RB_AUDIO_PAUSED)) return RB_AUDIO_STATE;
    uint32_t expected = p;
    return phase_.compare_exchange_strong(expected, final_.load() ? RB_AUDIO_DRAINING : RB_AUDIO_PLAYING) ? RB_AUDIO_OK : RB_AUDIO_STATE;
}
int StreamEngine::pause() {
    uint32_t expected = phase_.load();
    for (;;) {
        if (expected == RB_AUDIO_PAUSED || expected == RB_AUDIO_FINISHED) return RB_AUDIO_OK;
        if (expected != RB_AUDIO_PLAYING && expected != RB_AUDIO_DRAINING) return RB_AUDIO_STATE;
        // Final drain may advance PLAYING to DRAINING concurrently with this
        // already-frozen device pause. Retry that benign producer transition.
        if (phase_.compare_exchange_weak(expected, RB_AUDIO_PAUSED)) {
            left_.store(0); right_.store(0); return RB_AUDIO_OK;
        }
    }
}
int StreamEngine::available(uint32_t requested, uint32_t &actual) {
    if (!playing()) return RB_AUDIO_STATE;
    const bool final = final_.load(std::memory_order_acquire);
    const uint32_t queued = endpoint_.size();
    if (requested > queued && !final) { fail(RB_AUDIO_UNDERRUN); return RB_AUDIO_UNDERRUN; }
    actual = std::min(requested, queued); return RB_AUDIO_OK;
}
int StreamEngine::consume(float *destination, uint32_t frames) {
    if (!destination || frames > endpoint_.size()) return RB_AUDIO_ARGUMENT;
    if (endpoint_.take(destination, frames) != frames) { fail(RB_AUDIO_INTERNAL); return RB_AUDIO_INTERNAL; }
    float left = 0, right = 0;
    for (uint32_t i = 0; i < frames; ++i) { left = std::max(left, std::fabs(destination[size_t(i) * 2])); right = std::max(right, std::fabs(destination[size_t(i) * 2 + 1])); }
    left_.store(left); right_.store(right); wake_.notify_one(); return RB_AUDIO_OK;
}
void StreamEngine::submitted(uint32_t frames) { submitted_.fetch_add(frames); }
bool StreamEngine::observe(uint64_t frames) {
    if (!playing()) return false;
    const bool final = final_.load(std::memory_order_acquire);
    const uint64_t sent = submitted_.load(), previous = position_.load();
    if (frames < previous || (frames > sent && !(final && sent == total_.load()))) { fail(RB_AUDIO_UNDERRUN); return false; }
    const uint64_t position = std::min(frames, sent); position_.store(position);
    if (final && position == total_.load() && sent == total_.load()) {
        uint32_t expected = phase_.load();
        return (expected == RB_AUDIO_PLAYING || expected == RB_AUDIO_DRAINING) && phase_.compare_exchange_strong(expected, RB_AUDIO_FINISHED);
    }
    return false;
}
RBAudioStreamStatus StreamEngine::status() const {
    RBAudioStreamStatus s{};
    s.abi_version = 1; s.phase = phase_.load(); s.source_rate = descriptor_.source_rate; s.endpoint_rate = endpoint_rate_;
    s.generation = descriptor_.generation; s.source_frames = descriptor_.source_frames;
    // Read release-published completion flags before the monotonic counters
    // they certify. A concurrent final drain must not yield final=true beside
    // an earlier partial count in the same public status snapshot.
    s.endpoint_total_final = final_.load(std::memory_order_acquire) ? 1 : 0;
    s.source_eof = eof_.load(std::memory_order_acquire) ? 1 : 0;
    s.endpoint_position = position_.load(); s.endpoint_submitted = submitted_.load(); s.endpoint_produced = produced_.load();
    s.source_consumed = consumed_.load(); s.source_accepted = accepted_.load();
    s.endpoint_total = s.endpoint_total_final ? total_.load() : 0;
    uint64_t mapped = 0;
    if (!rate_frame_floor(s.endpoint_position, endpoint_rate_, descriptor_.source_rate, mapped)) mapped = descriptor_.source_frames;
    s.source_position = s.phase == RB_AUDIO_FINISHED ? descriptor_.source_frames : std::min(std::min(mapped, s.source_consumed), descriptor_.source_frames - 1);
    s.source_queued = source_.size(); s.endpoint_queued = endpoint_.size(); s.source_capacity = source_.capacity(); s.endpoint_capacity = endpoint_.capacity();
    s.source_peak = source_.peak(); s.endpoint_peak = endpoint_.peak(); s.primed = primed_.load() ? 1 : 0;
    s.converted = descriptor_.source_rate == endpoint_rate_ ? 0 : 1;
    s.result = result_.load(); s.hresult = hresult_.load(); s.peak_left = left_.load(); s.peak_right = right_.load();
    s.endpoint_buffer_frames = device_buffer_; s.soxr_recipe = s.converted ? 6 : 0; return s;
}

int create_stream_engine(const RBAudioStreamDescriptor &descriptor, uint32_t rate, uint32_t buffer,
                         std::shared_ptr<StreamEngine> &output, const ConversionServices *services) {
    try {
        auto next = std::make_shared<StreamEngine>(descriptor, rate, buffer, services);
        const int result = next->start();
        if (result) { next->stop_producer(); return result; }
        output = std::move(next); return RB_AUDIO_OK;
    } catch (const std::bad_alloc &) { return RB_AUDIO_MEMORY; }
      catch (const std::invalid_argument &) { return RB_AUDIO_ARGUMENT; }
      catch (...) { return RB_AUDIO_INTERNAL; }
}
int cancel_stream_device(StreamEngine &engine, void *context, StreamDeviceAction stop, StreamDeviceAction reset) {
    if (!stop || !reset) return RB_AUDIO_ARGUMENT;
    if (engine.status().phase == RB_AUDIO_CANCELLED) return RB_AUDIO_OK;
    for (auto action : {stop, reset}) {
        const auto result = action(context);
        if (result.result != RB_AUDIO_OK) {
            engine.fail(result.result, result.hresult); engine.stop_producer(); return result.result;
        }
    }
    engine.cancel(); return RB_AUDIO_OK;
}
}
