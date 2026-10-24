#include "PlaybackCursor.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>

namespace rebase {
bool valid_snapshot(const float *samples, uint64_t frames, uint32_t rate) {
    if (!samples || frames == 0 || frames > 32000000 || rate < 8000 || rate > 192000) return false;
    // Classify without floating arithmetic: even signaling NaNs must be
    // rejected safely before qualifying a caller's floating-point traps.
    for (uint64_t i = 0; i < frames * 2; ++i) {
        uint32_t bits; std::memcpy(&bits, samples + i, sizeof(bits));
        if ((bits & 0x7f800000u) == 0x7f800000u) return false;
    }
    return true;
}
int PlaybackCursor::configure(uint64_t frames, uint32_t rate) {
    if (!frames || frames > 32000000 || rate < 8000 || rate > 192000) return RB_AUDIO_ARGUMENT;
    uint64_t generation = value_.generation + 1;
    value_ = {1, RB_AUDIO_READY, rate, 0, frames, 0, 0, generation, 0, 0, RB_AUDIO_OK, 0, 0, 0};
    base_ = 0;
    return RB_AUDIO_OK;
}
int PlaybackCursor::play() {
    if (value_.phase == RB_AUDIO_PLAYING) return RB_AUDIO_OK;
    if (value_.phase != RB_AUDIO_READY && value_.phase != RB_AUDIO_PAUSED) return RB_AUDIO_STATE;
    if (value_.position_frames == value_.total_frames) { value_.phase = RB_AUDIO_FINISHED; return RB_AUDIO_STATE; }
    value_.phase = RB_AUDIO_PLAYING;
    return RB_AUDIO_OK;
}
int PlaybackCursor::pause() {
    if (value_.phase == RB_AUDIO_PAUSED) return RB_AUDIO_OK;
    if (!playing()) return RB_AUDIO_STATE;
    value_.phase = RB_AUDIO_PAUSED;
    peaks(0, 0);
    return RB_AUDIO_OK;
}
int PlaybackCursor::stop() {
    if (!configured()) return RB_AUDIO_STATE;
    ++value_.generation;
    value_.phase = RB_AUDIO_READY;
    value_.position_frames = value_.submitted_frames = base_ = 0;
    peaks(0, 0);
    return RB_AUDIO_OK;
}
int PlaybackCursor::seek(uint64_t frame) {
    if (!configured()) return RB_AUDIO_STATE;
    if (frame > value_.total_frames) return RB_AUDIO_ARGUMENT;
    const bool resume = playing();
    ++value_.generation;
    base_ = value_.position_frames = value_.submitted_frames = frame;
    value_.phase = frame == value_.total_frames ? RB_AUDIO_FINISHED : (resume ? RB_AUDIO_PLAYING : RB_AUDIO_READY);
    peaks(0, 0);
    return RB_AUDIO_OK;
}
void PlaybackCursor::fail(int result, int32_t hresult) {
    ++value_.generation;
    value_.phase = RB_AUDIO_FAULT;
    value_.result = result; value_.hresult = hresult;
    peaks(0, 0);
}
uint32_t PlaybackCursor::next(uint32_t capacity) const {
    if (!configured() || value_.phase == RB_AUDIO_FINISHED) return 0;
    return static_cast<uint32_t>(std::min<uint64_t>(capacity, value_.total_frames - value_.submitted_frames));
}
bool PlaybackCursor::submitted(uint32_t frames) {
    if (!configured() || frames > next(frames)) return false;
    value_.submitted_frames += frames;
    return true;
}
bool PlaybackCursor::observe(uint64_t device_frames) {
    if (!playing()) return false;
    const uint64_t available = value_.submitted_frames - base_;
    if (device_frames > available && value_.submitted_frames < value_.total_frames) {
        fail(RB_AUDIO_UNDERRUN, 0); return false;
    }
    const uint64_t position = base_ + std::min(device_frames, available);
    // A stale clock observation never moves the visible cursor backwards.
    value_.position_frames = std::max(value_.position_frames, position);
    if (value_.position_frames == value_.total_frames && value_.submitted_frames == value_.total_frames) {
        value_.phase = RB_AUDIO_FINISHED; peaks(0, 0); return true;
    }
    return false;
}
void PlaybackCursor::peaks(float left, float right) {
    value_.submitted_peak_left = left; value_.submitted_peak_right = right;
}
}
