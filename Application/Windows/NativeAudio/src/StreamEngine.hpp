#pragma once
#include "RateConversion.hpp"
#include "rebase_windows_audio.h"
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <memory>
#include <thread>
#include <vector>

namespace rebase {
// Checked duration arithmetic, independent of the bounded storage capacity.
bool rate_frame_bound(uint64_t frames, uint32_t from, uint32_t to, uint64_t &result);
bool rate_frame_floor(uint64_t frames, uint32_t from, uint32_t to, uint64_t &result);
int validate_stream_descriptor(const RBAudioStreamDescriptor &descriptor);
class StreamEngine {
    class Ring {
        std::vector<float> samples_;
        uint32_t capacity_;
        std::atomic<uint64_t> read_{0}, write_{0};
        std::atomic<uint32_t> peak_{0};
    public:
        explicit Ring(uint32_t capacity, const ConversionServices *services);
        uint32_t size() const;
        uint32_t capacity() const { return capacity_; }
        uint32_t peak() const { return peak_.load(); }
        uint32_t append(const float *input, uint32_t frames);
        uint32_t take(float *output, uint32_t frames);
    } source_, endpoint_;
    const RBAudioStreamDescriptor descriptor_;
    const uint32_t endpoint_rate_, device_buffer_, prime_;
    const uint64_t upper_;
    const ConversionServices *services_;
    std::mutex submission_, wake_mutex_;
    std::condition_variable wake_;
    std::thread producer_;
    uint64_t sequence_ = 0; // submission_ owns protocol admission.
    std::atomic<bool> stop_{false}, started_{false}, eof_{false}, final_{false}, primed_{false};
    std::atomic<uint32_t> phase_{RB_AUDIO_PRIMING};
    std::atomic<int32_t> result_{RB_AUDIO_OK}, hresult_{0};
    std::atomic<uint64_t> accepted_{0}, consumed_{0}, produced_{0}, submitted_{0}, position_{0}, total_{0};
    std::atomic<float> left_{0}, right_{0};
    void run() noexcept;
    void wait_for_work();
    bool flush(const float *samples, uint32_t count);
    void update_prime();
public:
    StreamEngine(const RBAudioStreamDescriptor &, uint32_t endpoint_rate, uint32_t device_buffer,
                 const ConversionServices *services = nullptr);
    ~StreamEngine();
    StreamEngine(const StreamEngine &) = delete;
    StreamEngine &operator=(const StreamEngine &) = delete;
    int start();
    int submit(uint64_t generation, uint64_t sequence, uint64_t start, const float *, uint32_t frames);
    int finish(uint64_t generation, uint64_t next_sequence, uint64_t committed);
    int play();
    int pause();
    void stop_producer();
    void cancel(); // Caller has first successfully stopped/reset the device.
    void fail(int result, int32_t hresult = 0);
    bool playing() const;
    // Device thread only. No allocation, conversion, IPC, or capacity waits.
    int available(uint32_t requested, uint32_t &actual);
    int consume(float *destination, uint32_t frames);
    void submitted(uint32_t frames);
    bool observe(uint64_t endpoint_frames);
    RBAudioStreamStatus status() const;
    uint64_t generation() const { return descriptor_.generation; }
};
// Creates and starts privately; failure leaves output ownership unchanged.
int create_stream_engine(const RBAudioStreamDescriptor &, uint32_t rate, uint32_t buffer,
                         std::shared_ptr<StreamEngine> &output, const ConversionServices *services = nullptr);
// Device-control seam used by WASAPI and deterministic fault controls. A failed
// Stop/Reset is a fault, never cancellation success; a retry may complete the
// barrier. These callbacks run only on the native control thread.
struct StreamDeviceResult { int result; int32_t hresult; };
using StreamDeviceAction = StreamDeviceResult (*)(void *) noexcept;
int cancel_stream_device(StreamEngine &, void *, StreamDeviceAction stop, StreamDeviceAction reset);
}

