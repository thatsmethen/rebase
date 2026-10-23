#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <audioclient.h>
#include <mmdeviceapi.h>
#include <ks.h>
#include <ksmedia.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <new>
#include <thread>
#include <vector>
#include <utility>
#include "PlaybackCursor.hpp"

namespace {
template<class T> class Com {
    T *value_ = nullptr;
public:
    Com() = default;
    Com(const Com &) = delete;
    Com &operator=(const Com &) = delete;
    ~Com() { reset(); }
    void reset() { if (value_) value_->Release(); value_ = nullptr; }
    T **put() { reset(); return &value_; }
    T *operator->() const { return value_; }
    explicit operator bool() const { return value_ != nullptr; }
};
struct TaskMemory { void operator()(WAVEFORMATEX *p) const { CoTaskMemFree(p); } };
enum class Operation { Format, Source, Play, Pause, Stop, Seek, Status, Quit };
struct Command {
    Operation operation;
    uint64_t frame = 0;
    uint32_t rate = 0;
    std::vector<float> *samples = nullptr;
    RBAudioDeviceFormat format{};
    RBAudioStatus status{};
    int result = RB_AUDIO_INTERNAL;
};
bool float_stereo(const WAVEFORMATEX *format) {
    if (format->nChannels != 2 || format->wBitsPerSample != 32 || format->nBlockAlign != 8) return false;
    if (format->wFormatTag == WAVE_FORMAT_IEEE_FLOAT) return true;
    if (format->wFormatTag != WAVE_FORMAT_EXTENSIBLE || format->cbSize < 22) return false;
    const auto *extended = reinterpret_cast<const WAVEFORMATEXTENSIBLE *>(format);
    return extended->Samples.wValidBitsPerSample == 32 &&
        IsEqualGUID(extended->SubFormat, KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) &&
        (extended->dwChannelMask == 0 || extended->dwChannelMask == (SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT));
}
}

struct RBAudio {
    std::mutex calls, queue;
    Command *pending = nullptr;
    HANDLE command_event = nullptr, audio_event = nullptr, completed_event = nullptr;
    HANDLE ready_event = nullptr, exited_event = nullptr;
    std::thread thread;
    std::atomic<bool> running{false};
    HRESULT startup = E_FAIL;
    // The following fields are owned exclusively by the worker thread.
    Com<IAudioClient> client;
    Com<IAudioRenderClient> render;
    Com<IAudioClock> clock;
    std::vector<float> samples;
    rebase::PlaybackCursor cursor;
    UINT32 capacity = 0;
    UINT64 frequency = 0;
    bool clock_approximate = false;

    ~RBAudio() {
        if (thread.joinable()) {
            if (running.load()) { Command quit{Operation::Quit}; submit(quit); }
            // A failed submit already joins before releasing its stack command.
            if (thread.joinable()) thread.join();
        }
        for (HANDLE handle : {command_event, audio_event, completed_event, ready_event, exited_event})
            if (handle) CloseHandle(handle);
    }
    bool start_worker() {
        command_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        audio_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        completed_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        ready_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        exited_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (!command_event || !audio_event || !completed_event || !ready_event || !exited_event) return false;
        thread = std::thread([this] { work(); });
        HANDLE events[] = {ready_event, exited_event};
        return WaitForMultipleObjects(2, events, FALSE, INFINITE) == WAIT_OBJECT_0 && SUCCEEDED(startup);
    }
    int submit(Command &command) {
        std::lock_guard<std::mutex> call_lock(calls);
        if (!running.load()) return RB_AUDIO_INTERNAL;
        if (!ResetEvent(completed_event)) { quiesce_worker(); return RB_AUDIO_INTERNAL; }
        { std::lock_guard<std::mutex> queue_lock(queue); pending = &command; }
        if (!SetEvent(command_event)) {
            quiesce_worker();
            return RB_AUDIO_INTERNAL;
        }
        HANDLE events[] = {completed_event, exited_event};
        DWORD result = WaitForMultipleObjects(2, events, FALSE, INFINITE);
        if (result == WAIT_OBJECT_0) return command.result;
        // Even WAIT_FAILED must not release this stack command or the source
        // vector while a worker could still be using either of them.
        quiesce_worker();
        return RB_AUDIO_INTERNAL;
    }
    void quiesce_worker() {
        // Caller holds calls, never queue. Destruction is exclusive by API
        // contract. Joining may wait for an in-flight OS/driver call; returning
        // while the command has borrowed caller storage is not safe.
        running.store(false);
        SetEvent(command_event);
        if (thread.joinable()) thread.join();
        std::lock_guard<std::mutex> queue_lock(queue);
        pending = nullptr;
    }
    void close_device() {
        if (client) client->Stop();
        clock.reset(); render.reset(); client.reset();
        capacity = 0; frequency = 0; clock_approximate = false;
        ResetEvent(audio_event);
    }
    int failure(int result, HRESULT hr) {
        cursor.fail(result, static_cast<int32_t>(hr));
        close_device();
        return result;
    }
    int endpoint(Com<IMMDevice> &device, HRESULT &hr) {
        Com<IMMDeviceEnumerator> enumerator;
        hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
            __uuidof(IMMDeviceEnumerator), reinterpret_cast<void **>(enumerator.put()));
        if (FAILED(hr)) return RB_AUDIO_DEVICE;
        hr = enumerator->GetDefaultAudioEndpoint(eRender, eMultimedia, device.put());
        if (FAILED(hr)) return hr == HRESULT_FROM_WIN32(ERROR_NOT_FOUND) ? RB_AUDIO_NO_ENDPOINT : RB_AUDIO_DEVICE;
        return RB_AUDIO_OK;
    }
    int activate(Com<IAudioClient> &target, RBAudioDeviceFormat &format, HRESULT &hr) {
        Com<IMMDevice> device;
        int result = endpoint(device, hr);
        if (result) return result;
        hr = device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, reinterpret_cast<void **>(target.put()));
        if (FAILED(hr)) return RB_AUDIO_DEVICE;
        WAVEFORMATEX *raw = nullptr;
        hr = target->GetMixFormat(&raw);
        std::unique_ptr<WAVEFORMATEX, TaskMemory> mix(raw);
        if (FAILED(hr) || !mix) return RB_AUDIO_DEVICE;
        format = {mix->nSamplesPerSec, mix->nChannels, float_stereo(mix.get()) ? 1u : 0u};
        return RB_AUDIO_OK;
    }
    int open_device(uint32_t rate) {
        HRESULT hr;
        RBAudioDeviceFormat format{};
        int result = activate(client, format, hr);
        if (result) return failure(result, hr);
        if (!format.float32 || format.channels != 2 || format.sample_rate != rate)
            return failure(RB_AUDIO_FORMAT, AUDCLNT_E_UNSUPPORTED_FORMAT);
        WAVEFORMATEX requested{};
        requested.wFormatTag = WAVE_FORMAT_IEEE_FLOAT;
        requested.nChannels = 2; requested.nSamplesPerSec = rate;
        requested.wBitsPerSample = 32; requested.nBlockAlign = 8;
        requested.nAvgBytesPerSec = rate * 8;
        WAVEFORMATEX *raw = nullptr;
        hr = client->IsFormatSupported(AUDCLNT_SHAREMODE_SHARED, &requested, &raw);
        std::unique_ptr<WAVEFORMATEX, TaskMemory> closest(raw);
        if (hr != S_OK) return failure(RB_AUDIO_FORMAT, FAILED(hr) ? hr : AUDCLNT_E_UNSUPPORTED_FORMAT);
        // No AUTOCONVERTPCM/SRC_DEFAULT_QUALITY: source/device adaptation is
        // an explicit upstream responsibility. Shared-mode Windows effects
        // may still process this stream; no bit-exact DAC claim is made.
        hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_NOPERSIST,
            0, 0, &requested, nullptr);
        if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
        hr = client->SetEventHandle(audio_event);
        if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
        hr = client->GetBufferSize(&capacity);
        if (FAILED(hr) || !capacity) return failure(RB_AUDIO_DEVICE, FAILED(hr) ? hr : E_UNEXPECTED);
        hr = client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void **>(render.put()));
        if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
        hr = client->GetService(__uuidof(IAudioClock), reinterpret_cast<void **>(clock.put()));
        if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
        hr = clock->GetFrequency(&frequency);
        if (FAILED(hr) || !frequency || frequency > std::numeric_limits<uint64_t>::max() / rate)
            return failure(RB_AUDIO_DEVICE, FAILED(hr) ? hr : E_UNEXPECTED);
        return RB_AUDIO_OK;
    }
    int refresh_clock() {
        if (!cursor.playing()) return RB_AUDIO_OK;
        UINT64 ticks = 0;
        HRESULT hr = clock->GetPosition(&ticks, nullptr);
        if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
        clock_approximate = hr == S_FALSE;
        auto status = cursor.status();
        // Integer quotient/remainder avoids multiplying an unbounded clock.
        uint64_t seconds = ticks / frequency;
        uint64_t frames = seconds > status.total_frames / status.sample_rate + 1
            ? status.total_frames + 1
            : seconds * status.sample_rate + ((ticks % frequency) * status.sample_rate) / frequency;
        bool finished = cursor.observe(frames);
        if (cursor.status().phase == RB_AUDIO_FAULT)
            return failure(cursor.status().result, 0); // Clock outran submitted data.
        if (finished) {
            hr = client->Stop();
            if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
        }
        return RB_AUDIO_OK;
    }
    int fill() {
        UINT32 padding = 0;
        HRESULT hr = client->GetCurrentPadding(&padding);
        if (FAILED(hr) || padding > capacity) return failure(RB_AUDIO_DEVICE, FAILED(hr) ? hr : E_UNEXPECTED);
        UINT32 available = capacity - padding;
        UINT32 actual = cursor.next(available);
        if (!actual) return RB_AUDIO_OK;
        BYTE *destination = nullptr;
        hr = render->GetBuffer(available, &destination);
        if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
        const float *source = samples.data() + cursor.source_index() * 2;
        // This is the only audio-data path: bounded copies/peak scans, no
        // allocation, IPC, source reads, or caller/managed callbacks.
        std::memcpy(destination, source, static_cast<size_t>(actual) * 2 * sizeof(float));
        if (actual < available)
            std::memset(destination + static_cast<size_t>(actual) * 8, 0, static_cast<size_t>(available - actual) * 8);
        float left = 0, right = 0;
        for (UINT32 i = 0; i < actual; ++i) {
            left = std::max(left, std::fabs(source[2 * i]));
            right = std::max(right, std::fabs(source[2 * i + 1]));
        }
        hr = render->ReleaseBuffer(available, 0);
        if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
        if (!cursor.submitted(actual)) return failure(RB_AUDIO_INTERNAL, E_UNEXPECTED);
        cursor.peaks(left, right);
        return RB_AUDIO_OK;
    }
    int dispatch(Command &command) {
        HRESULT hr;
        switch (command.operation) {
        case Operation::Format: {
            if (cursor.playing()) return RB_AUDIO_STATE;
            Com<IAudioClient> temporary;
            return activate(temporary, command.format, hr);
        }
        case Operation::Source: {
            close_device(); samples.clear();
            int result = open_device(command.rate);
            if (result) return result;
            samples = std::move(*command.samples);
            return cursor.configure(command.frame, command.rate);
        }
        case Operation::Play: {
            if (cursor.playing()) return RB_AUDIO_OK;
            if (!client || (cursor.status().phase != RB_AUDIO_READY && cursor.status().phase != RB_AUDIO_PAUSED)) return RB_AUDIO_STATE;
            bool resumed = cursor.status().phase == RB_AUDIO_PAUSED;
            int result = cursor.play();
            if (result) return result;
            if (!resumed && (result = fill()) != RB_AUDIO_OK) return result;
            hr = client->Start();
            return FAILED(hr) ? failure(RB_AUDIO_DEVICE, hr) : RB_AUDIO_OK;
        }
        case Operation::Pause: {
            if (cursor.status().phase == RB_AUDIO_PAUSED) return RB_AUDIO_OK;
            if (!cursor.playing()) return RB_AUDIO_STATE;
            // Freeze first, then read the frozen clock; queued samples remain.
            hr = client->Stop();
            if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
            int result = refresh_clock();
            if (result) return result;
            return cursor.status().phase == RB_AUDIO_FINISHED ? RB_AUDIO_OK : cursor.pause();
        }
        case Operation::Stop: {
            if (!cursor.configured() || !client) return RB_AUDIO_STATE;
            hr = client->Stop();
            if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
            hr = client->Reset();
            if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
            ResetEvent(audio_event);
            return cursor.stop();
        }
        case Operation::Seek: {
            if (!cursor.configured() || !client) return RB_AUDIO_STATE;
            if (command.frame > cursor.status().total_frames) return RB_AUDIO_ARGUMENT;
            bool resumed = cursor.playing();
            hr = client->Stop();
            if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
            hr = client->Reset();
            if (FAILED(hr)) return failure(RB_AUDIO_DEVICE, hr);
            ResetEvent(audio_event);
            int result = cursor.seek(command.frame);
            if (result || !resumed || !cursor.playing()) return result;
            if ((result = fill()) != RB_AUDIO_OK) return result;
            hr = client->Start();
            return FAILED(hr) ? failure(RB_AUDIO_DEVICE, hr) : RB_AUDIO_OK;
        }
        case Operation::Status:
            refresh_clock(); // A runtime failure is observable in the returned status.
            command.status = cursor.status();
            command.status.endpoint_buffer_frames = capacity;
            command.status.clock_reading_approximate = clock_approximate ? 1 : 0;
            return RB_AUDIO_OK;
        case Operation::Quit:
            close_device(); samples.clear(); return RB_AUDIO_OK;
        }
        return RB_AUDIO_INTERNAL;
    }
    void work() noexcept {
        startup = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        const bool com_initialized = SUCCEEDED(startup);
        if (com_initialized) running.store(true);
        SetEvent(ready_event);
        try {
            while (running.load()) {
                HANDLE events[] = {command_event, audio_event};
                DWORD event = WaitForMultipleObjects(2, events, FALSE, cursor.playing() ? 5000 : INFINITE);
                if (event == WAIT_OBJECT_0) {
                    Command *command;
                    { std::lock_guard<std::mutex> lock(queue); command = pending; pending = nullptr; }
                    if (!command) continue;
                    try { command->result = dispatch(*command); }
                    catch (const std::bad_alloc &) { command->result = failure(RB_AUDIO_MEMORY, E_OUTOFMEMORY); }
                    catch (...) { command->result = failure(RB_AUDIO_INTERNAL, E_FAIL); }
                    const bool quit = command->operation == Operation::Quit;
                    SetEvent(completed_event);
                    if (quit) break;
                    // Service a signalled device event even under sustained UI
                    // command traffic; command priority must not starve output.
                    if (cursor.playing() && WaitForSingleObject(audio_event, 0) == WAIT_OBJECT_0 &&
                        refresh_clock() == RB_AUDIO_OK && cursor.playing()) fill();
                } else if (event == WAIT_OBJECT_0 + 1) {
                    if (cursor.playing() && refresh_clock() == RB_AUDIO_OK && cursor.playing()) fill();
                } else {
                    failure(RB_AUDIO_DEVICE, HRESULT_FROM_WIN32(event == WAIT_TIMEOUT ? ERROR_TIMEOUT : GetLastError()));
                    if (event != WAIT_TIMEOUT) break;
                }
            }
        } catch (...) { failure(RB_AUDIO_INTERNAL, E_FAIL); }
        close_device();
        if (com_initialized) CoUninitialize();
        running.store(false);
        SetEvent(exited_event);
    }
};

extern "C" {
int32_t rb_audio_create(RBAudio **output) {
    if (!output) return RB_AUDIO_ARGUMENT;
    try {
        std::unique_ptr<RBAudio> audio(new RBAudio());
        if (!audio->start_worker()) return RB_AUDIO_INTERNAL;
        *output = audio.release(); return RB_AUDIO_OK;
    } catch (const std::bad_alloc &) { return RB_AUDIO_MEMORY; }
    catch (...) { return RB_AUDIO_INTERNAL; }
}
void rb_audio_destroy(RBAudio *audio) { delete audio; }
int32_t rb_audio_default_format(RBAudio *audio, RBAudioDeviceFormat *output) {
    if (!audio || !output) return RB_AUDIO_ARGUMENT;
    try { Command command{Operation::Format}; int result = audio->submit(command); if (!result) *output = command.format; return result; }
    catch (...) { return RB_AUDIO_INTERNAL; }
}
int32_t rb_audio_set_source(RBAudio *audio, const float *samples, uint64_t frames, uint32_t rate) {
    if (!audio || !rebase::valid_snapshot(samples, frames, rate)) return RB_AUDIO_ARGUMENT;
    try {
        std::vector<float> snapshot(samples, samples + frames * 2);
        Command command{Operation::Source}; command.frame = frames; command.rate = rate; command.samples = &snapshot;
        return audio->submit(command);
    } catch (const std::bad_alloc &) { return RB_AUDIO_MEMORY; }
    catch (...) { return RB_AUDIO_INTERNAL; }
}
static int32_t simple(RBAudio *audio, Operation operation, uint64_t frame = 0) {
    if (!audio) return RB_AUDIO_ARGUMENT;
    try { Command command{operation}; command.frame = frame; return audio->submit(command); }
    catch (...) { return RB_AUDIO_INTERNAL; }
}
int32_t rb_audio_play(RBAudio *audio) { return simple(audio, Operation::Play); }
int32_t rb_audio_pause(RBAudio *audio) { return simple(audio, Operation::Pause); }
int32_t rb_audio_stop(RBAudio *audio) { return simple(audio, Operation::Stop); }
int32_t rb_audio_seek(RBAudio *audio, uint64_t frame) { return simple(audio, Operation::Seek, frame); }
int32_t rb_audio_status(RBAudio *audio, RBAudioStatus *output) {
    if (!audio || !output) return RB_AUDIO_ARGUMENT;
    try { Command command{Operation::Status}; int result = audio->submit(command); if (!result) *output = command.status; return result; }
    catch (...) { return RB_AUDIO_INTERNAL; }
}
}
