#pragma once
#include "PlaybackCursor.hpp"

namespace rebase {
/* Owns transport in endpoint frames while projecting the stable source-frame
   ABI. Resampling phase is never restarted by seek: the caller indexes the
   same fully converted snapshot at the nearest endpoint frame (ties up). */
class RatePlaybackCursor {
public:
    int configure(uint64_t source_frames, uint32_t source_rate,
                  uint64_t endpoint_frames, uint32_t endpoint_rate);
    int play() { return endpoint_.play(); }
    int pause() { return endpoint_.pause(); }
    int stop();
    int seek(uint64_t source_frame);
    void fail(int result, int32_t hr) { endpoint_.fail(result, hr); }
    uint32_t next(uint32_t capacity) const { return endpoint_.next(capacity); }
    bool submitted(uint32_t frames) { return endpoint_.submitted(frames); }
    bool observe(uint64_t frames) { return endpoint_.observe(frames); }
    void peaks(float left, float right) { endpoint_.peaks(left, right); }
    bool playing() const { return endpoint_.playing(); }
    bool configured() const { return endpoint_.configured(); }
    uint64_t endpoint_index() const { return endpoint_.source_index(); }
    RBAudioStatus status() const;
    RBAudioRateInfo rate_info() const;
private:
    PlaybackCursor endpoint_;
    uint64_t source_frames_ = 0, source_base_ = 0, endpoint_base_ = 0;
    uint32_t source_rate_ = 0;
    uint64_t source_position(uint64_t endpoint_frame) const;
};
}
