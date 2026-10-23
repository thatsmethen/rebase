#pragma once
#include "rebase_windows_audio.h"
#include <cstdint>

namespace rebase {
/* Single-owner value model. The WASAPI worker serializes access. This is not
   the recovered CPR ring and must not be shared concurrently. */
class PlaybackCursor {
public:
    int configure(uint64_t frames, uint32_t rate);
    int play();
    int pause();
    int stop();
    int seek(uint64_t frame);
    void fail(int result, int32_t hresult);
    uint32_t next(uint32_t capacity) const;
    bool submitted(uint32_t frames);
    bool observe(uint64_t device_frames);
    void peaks(float left, float right);
    RBAudioStatus status() const { return value_; }
    uint64_t source_index() const { return value_.submitted_frames; }
    bool playing() const { return value_.phase == RB_AUDIO_PLAYING; }
    bool configured() const { return value_.phase != RB_AUDIO_EMPTY && value_.phase != RB_AUDIO_FAULT; }
private:
    RBAudioStatus value_{1, RB_AUDIO_EMPTY, 0, 0, 0, 0, 0, 0, 0, 0, RB_AUDIO_OK, 0, 0, 0};
    uint64_t base_ = 0;
};
bool valid_snapshot(const float *samples, uint64_t frames, uint32_t rate);
}
