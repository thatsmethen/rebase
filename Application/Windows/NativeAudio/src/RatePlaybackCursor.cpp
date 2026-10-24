#include "RatePlaybackCursor.hpp"
#include <algorithm>

namespace rebase {
int RatePlaybackCursor::configure(uint64_t frames, uint32_t rate,
                                  uint64_t output_frames, uint32_t output_rate) {
    if (!frames || frames > 32000000 || rate < 8000 || rate > 192000)
        return RB_AUDIO_ARGUMENT;
    const int result = endpoint_.configure(output_frames, output_rate);
    if (result) return result;
    source_frames_ = frames; source_rate_ = rate;
    source_base_ = endpoint_base_ = 0;
    return RB_AUDIO_OK;
}
int RatePlaybackCursor::stop() {
    const int result = endpoint_.stop();
    if (!result) source_base_ = endpoint_base_ = 0;
    return result;
}
int RatePlaybackCursor::seek(uint64_t frame) {
    if (!configured()) return RB_AUDIO_STATE;
    if (frame > source_frames_) return RB_AUDIO_ARGUMENT;
    const auto endpoint = endpoint_.status();
    // All products are bounded by 32M * 192k, well within UInt64.
    const uint64_t mapped = frame == source_frames_ ? endpoint.total_frames :
        std::min(endpoint.total_frames,
                 (frame * endpoint.sample_rate + source_rate_ / 2) / source_rate_);
    const int result = endpoint_.seek(mapped);
    if (!result) { source_base_ = frame; endpoint_base_ = mapped; }
    return result;
}
uint64_t RatePlaybackCursor::source_position(uint64_t frame) const {
    const auto endpoint = endpoint_.status();
    if (!source_rate_ || !endpoint.sample_rate) return 0;
    if (frame >= endpoint.total_frames) return source_frames_;
    const uint64_t elapsed = frame >= endpoint_base_ ? frame - endpoint_base_ : 0;
    return std::min(source_frames_, source_base_ + elapsed * source_rate_ / endpoint.sample_rate);
}
RBAudioStatus RatePlaybackCursor::status() const {
    auto value = endpoint_.status();
    value.sample_rate = source_rate_;
    value.total_frames = source_frames_;
    value.position_frames = source_position(value.position_frames);
    value.submitted_frames = source_position(value.submitted_frames);
    return value;
}
RBAudioRateInfo RatePlaybackCursor::rate_info() const {
    const auto value = endpoint_.status();
    const uint32_t converted = source_rate_ && source_rate_ != value.sample_rate ? 1u : 0u;
    return {1, source_rate_, value.sample_rate, converted, source_frames_, value.total_frames,
            value.position_frames, value.submitted_frames, converted ? 6u : 0u, 0};
}
}
