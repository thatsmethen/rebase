#include "cpr_live_stereo_ring.h"
#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

_Static_assert(sizeof(float) == 4, "Requires four-byte sample storage");

typedef struct { uintptr_t first, last; } span;
static int make_span(const void *p, size_t bytes, size_t alignment, span *out) {
    uintptr_t first = (uintptr_t)p;
    if (!p || first % alignment || bytes > UINTPTR_MAX - first) return 0;
    *out = (span){first, first + bytes};
    return 1;
}
static int overlaps(span a, span b) {
    return a.first < b.last && b.first < a.last;
}
static int base_spans(rb_cpr_live_stereo_ring *s, span ranges[3]) {
    if (!make_span(s, sizeof(*s), _Alignof(rb_cpr_live_stereo_ring), &ranges[0]))
        return RB_CPR_LIVE_RING_INVALID;
    if (!make_span(s->left, 32768 * sizeof(float), _Alignof(float), &ranges[1]) ||
        !make_span(s->right, 32768 * sizeof(float), _Alignof(float), &ranges[2]))
        return RB_CPR_LIVE_RING_INVALID;
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < i; ++j)
            if (overlaps(ranges[i], ranges[j])) return RB_CPR_LIVE_RING_ALIAS;
    return RB_CPR_LIVE_RING_OK;
}
static int valid_state(rb_cpr_live_stereo_ring *s, span ranges[3]) {
    int error = base_spans(s, ranges);
    if (error) return error;
    if (s->write_index < 0 || s->write_index >= 32768 ||
        s->read_index < 0 || s->read_index >= 32768 ||
        s->submitted_frames < 0 || s->timeline_frames < 0)
        return RB_CPR_LIVE_RING_RANGE;
    return RB_CPR_LIVE_RING_OK;
}
static int available(const rb_cpr_live_stereo_ring *s) {
    return (s->write_index - s->read_index + 32768) % 32768;
}

int rb_cpr_live_ring_init(rb_cpr_live_stereo_ring *s, float *left, float *right) {
    span a, b, c;
    if (!make_span(s, sizeof(*s), _Alignof(rb_cpr_live_stereo_ring), &a) ||
        !make_span(left, 32768 * sizeof(float), _Alignof(float), &b) ||
        !make_span(right, 32768 * sizeof(float), _Alignof(float), &c))
        return RB_CPR_LIVE_RING_INVALID;
    if (overlaps(a,b) || overlaps(a,c) || overlaps(b,c)) return RB_CPR_LIVE_RING_ALIAS;
    *s = (rb_cpr_live_stereo_ring){left, right, 0, 0, 0, 0};
    return RB_CPR_LIVE_RING_OK;
}

int rb_cpr_live_ring_reset(rb_cpr_live_stereo_ring *s) {
    span ranges[3];
    int error = base_spans(s, ranges);
    if (error) return error;
    s->write_index = s->read_index = 0;
    s->submitted_frames = s->timeline_frames = 0;
    return RB_CPR_LIVE_RING_OK;
}

int rb_cpr_live_ring_write(rb_cpr_live_stereo_ring *s,
                          const float *input, int32_t frames) {
    span ranges[3], in;
    int error = valid_state(s, ranges);
    if (error) return error;
    if (frames < 0 || frames > 32768 ||
        s->submitted_frames > INT64_MAX - frames) return RB_CPR_LIVE_RING_RANGE;
    if (frames == 0) return RB_CPR_LIVE_RING_OK;
    if (!make_span(input, (size_t)frames * 2 * sizeof(float), _Alignof(float), &in))
        return RB_CPR_LIVE_RING_INVALID;
    for (int i = 0; i < 3; ++i)
        if (overlaps(in, ranges[i])) return RB_CPR_LIVE_RING_ALIAS;
    /* Native100384b70..c24 rechecks first-channel free space before each
       frame. This stronger call admission makes all checks succeed without
       relying on a concurrently advancing consumer or native sleep/retry. */
    if (frames > 32768 - available(s) - 16384 + 1)
        return RB_CPR_LIVE_RING_WOULD_BLOCK;
    int index = s->write_index;
    for (int i = 0; i < frames; ++i) {
        memcpy(s->left + index, input + 2 * i, sizeof(float));
        memcpy(s->right + index, input + 2 * i + 1, sizeof(float));
        index = (index + 1) % 32768;
    }
    s->write_index = index;
    s->submitted_frames += frames;
    return RB_CPR_LIVE_RING_OK;
}

int rb_cpr_live_ring_consume(rb_cpr_live_stereo_ring *s,
                            float *left, float *right,
                            int64_t start, int64_t end,
                            uint8_t stopped, uint8_t drain,
                            rb_cpr_live_ring_result *result) {
    span ranges[6];
    int error = valid_state(s, ranges);
    if (error) return error;
    if (stopped > 1 || drain > 1 || end < start ||
        (start < 0 && end > INT64_MAX + start)) return RB_CPR_LIVE_RING_RANGE;
    int64_t distance = end - start;
    if (distance > 32768) return RB_CPR_LIVE_RING_RANGE;
    int frames = (int)distance;
    if (!make_span(result, sizeof(*result), _Alignof(rb_cpr_live_ring_result), &ranges[3]))
        return RB_CPR_LIVE_RING_INVALID;
    int range_count = 4;
    if (frames) {
        if (!make_span(left, (size_t)frames * sizeof(float), _Alignof(float), &ranges[4]) ||
            !make_span(right, (size_t)frames * sizeof(float), _Alignof(float), &ranges[5]))
            return RB_CPR_LIVE_RING_INVALID;
        range_count = 6;
    }
    for (int i = 0; i < range_count; ++i)
        for (int j = 0; j < i; ++j)
            if (overlaps(ranges[i], ranges[j])) return RB_CPR_LIVE_RING_ALIAS;
    int queued = available(s);
    int advance = stopped || queued >= frames || drain;
    int copied = stopped ? 0 : (queued >= frames ? frames : (drain ? queued : 0));
    if (advance && s->timeline_frames > INT64_MAX - frames)
        return RB_CPR_LIVE_RING_RANGE;
    int index = s->read_index;
    /* Native1003847f0..83c and850..8c8 copy stereo planes independently;
       equal indices and equal channel populations are this bounded domain. */
    for (int i = 0; i < copied; ++i) {
        memcpy(left + i, s->left + index, sizeof(float));
        memcpy(right + i, s->right + index, sizeof(float));
        index = (index + 1) % 32768;
    }
    if (frames > copied) {
        memset(left + copied, 0, (size_t)(frames - copied) * sizeof(float));
        memset(right + copied, 0, (size_t)(frames - copied) * sizeof(float));
    }
    s->read_index = index;
    if (advance) s->timeline_frames += frames;
    *result = (rb_cpr_live_ring_result){copied, frames - copied, s->timeline_frames};
    return RB_CPR_LIVE_RING_OK;
}
