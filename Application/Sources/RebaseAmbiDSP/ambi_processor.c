#include "ambi_processor.h"
#include <fenv.h>
#include <float.h>
#include <limits.h>
#include <string.h>
#if defined(__x86_64__)
#include <xmmintrin.h>
#endif

#pragma STDC FENV_ACCESS ON
_Static_assert(CHAR_BIT == 8 && sizeof(float) == 4 && sizeof(double) == 8,
               "Requires binary32/binary64 storage");
_Static_assert(FLT_RADIX == 2 && FLT_MANT_DIG == 24 && DBL_MANT_DIG == 53 &&
               FLT_MIN_EXP == -125 && DBL_MIN_EXP == -1021,
               "Requires IEEE binary32/binary64");

/* Source offsets/bit checks are independently verified by test_processor.py.
 * Scatter indexes sources; gains index DESTINATIONS after the full scatter. */
static const uint32_t maps[2][16] = {
    {0,3,1,2,6,7,5,8,4,12,13,11,14,10,15,9},
    {0,2,3,1,8,6,4,5,7,15,13,11,9,10,12,14}
};
static const uint64_t gain64[2][16] = {
    {UINT64_C(0x3ff6a09e667f3bcd),UINT64_C(0x3ff0000000000000),UINT64_C(0x3ff0000000000000),UINT64_C(0x3ff0000000000000),
     UINT64_C(0x3ff0000000000000),UINT64_C(0x3febb67ae8584caa),UINT64_C(0x3febb67ae8584caa),UINT64_C(0x3febb67ae8584caa),
     UINT64_C(0x3febb67ae8584caa),UINT64_C(0x3ff0000000000000),UINT64_C(0x401314c3d92a9e91),UINT64_C(0x401314c3d92a9e91),
     UINT64_C(0x3fe7d9f4cf754635),UINT64_C(0x3fe7d9f4cf754635),UINT64_C(0x3ffc48c6001f0abf),UINT64_C(0x3ffc48c6001f0abf)},
    {UINT64_C(0x3fe6a09e667f3bcc),UINT64_C(0x3ff0000000000000),UINT64_C(0x3ff0000000000000),UINT64_C(0x3ff0000000000000),
     UINT64_C(0x3ff0000000000000),UINT64_C(0x3ff279a74590331d),UINT64_C(0x3ff279a74590331d),UINT64_C(0x3ff279a74590331d),
     UINT64_C(0x3ff279a74590331d),UINT64_C(0x3ff0000000000000),UINT64_C(0x3fcad5336963eefc),UINT64_C(0x3fcad5336963eefc),
     UINT64_C(0x3ff5775c544ff263),UINT64_C(0x3ff5775c544ff263),UINT64_C(0x3fe21a1851ff630a),UINT64_C(0x3fe21a1851ff630a)}
};
/* Exact nearest-even FCVT S,D results, not independently invented constants. */
static const uint32_t gain32[2][16] = {
    {0x3fb504f3,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f5db3d7,0x3f5db3d7,0x3f5db3d7,
     0x3f5db3d7,0x3f800000,0x4098a61f,0x4098a61f,0x3f3ecfa6,0x3f3ecfa6,0x3fe24630,0x3fe24630},
    {0x3f3504f3,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f93cd3a,0x3f93cd3a,0x3f93cd3a,
     0x3f93cd3a,0x3f800000,0x3e56a99b,0x3e56a99b,0x3fabbae3,0x3fabbae3,0x3f10d0c3,0x3f10d0c3}
};

static int config_valid(uint32_t n, uint32_t precision, size_t frames,
                        void *scratch, size_t bytes)
{
    if ((n != 4 && n != 9 && n != 16) ||
        (precision != 32 && precision != 64) || !frames || frames > INT32_MAX)
        return 0;
    const size_t width = precision / 8;
    if (frames > SIZE_MAX / n / width || !scratch ||
        (uintptr_t)scratch % width || bytes < frames * n * width ||
        (uintptr_t)scratch > UINTPTR_MAX - frames * n * width) return 0;
    return 1;
}

int ambip_init(ambip_state *state, uint32_t n, uint32_t precision,
               size_t frames, void *scratch, size_t bytes)
{
    if (!state || !config_valid(n, precision, frames, scratch, bytes))
        return AMBIP_CONFIGURATION;
    const ambip_state initialized = {AMBIP_ABI_VERSION,n,precision,0,0,0,frames,scratch,bytes};
    *state = initialized;
    return AMBIP_OK;
}

static int normalized(double value)
{
    uint64_t bits;
    memcpy(&bits, &value, sizeof bits);
    uint64_t magnitude = bits & UINT64_C(0x7fffffffffffffff);
    return magnitude <= UINT64_C(0x3ff0000000000000) &&
           (!(bits >> 63) || !magnitude);
}

static int parameters(ambip_state *next, const ambip_queue *queues,
                      size_t count, uint32_t *updates)
{
    if (count > 1024 || (count && !queues)) return AMBIP_PARAMETER;
    for (size_t i = 0; i < count; ++i) {
        const ambip_queue *q = queues + i;
        if (q->parameter_id != 1 && q->parameter_id != 2) continue;
        /* Empty recognized queues are deliberately rejected: native count-1
         * is not a defined safe empty-queue contract. Failed reads are ignored. */
        if (q->point_count <= 0) return AMBIP_PARAMETER;
        if (q->last_point_result != 0) continue;
        if (!q->points) return AMBIP_PARAMETER;
        double value = q->points[q->point_count - 1].value;
        if (!normalized(value)) return AMBIP_PARAMETER;
        if (q->parameter_id == 1) next->bypass = value > 0.5;
        else next->direction_table = value >= 0.5;
        ++*updates;
    }
    return AMBIP_OK;
}

static int arithmetic_environment(void)
{
    if (fegetround() != FE_TONEAREST) return 0;
#if defined(__aarch64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    /* Exact explicit candidate domain; no inference about target FPCR. */
    return fpcr == 0;
#elif defined(__x86_64__)
    /* Ignore sticky status flags; require default masks, nearest, no FTZ/DAZ. */
    return (_mm_getcsr() & ~0x3fu) == 0x1f80u;
#else
    return 0;
#endif
}

static int overlaps(uintptr_t a, size_t an, uintptr_t b, size_t bn)
{
    return a < b + bn && b < a + an;
}

static int audio_storage(const ambip_state *state, const ambip_input *in,
                         const ambip_output *out, size_t frames, int *stage)
{
    if (!out || in->channels != state->channels || out->channels != state->channels ||
        in->frame_capacity < frames || out->frame_capacity < frames || !in->planes || !out->planes)
        return AMBIP_SHAPE;
    const size_t n = state->channels, width = state->precision / 8, bytes = frames * width;
    const size_t scratch_size = n * state->maximum_frames * width;
    uintptr_t input[16], output[16];
    for (size_t i = 0; i < n; ++i) {
        input[i] = (uintptr_t)in->planes[i];
        output[i] = (uintptr_t)out->planes[i];
        if (!input[i] || !output[i] || input[i] % width || output[i] % width ||
            input[i] > UINTPTR_MAX - bytes || output[i] > UINTPTR_MAX - bytes)
            return AMBIP_SHAPE;
        if (overlaps(input[i],bytes,(uintptr_t)state->scratch,scratch_size) ||
            overlaps(output[i],bytes,(uintptr_t)state->scratch,scratch_size)) return AMBIP_OVERLAP;
        for (size_t j = 0; j < i; ++j)
            if (overlaps(input[i],bytes,input[j],bytes) || overlaps(output[i],bytes,output[j],bytes))
                return AMBIP_OVERLAP;
    }
    for (size_t i = 0; i < n; ++i)
        for (size_t j = 0; j < n; ++j)
            if (overlaps(input[i],bytes,output[j],bytes)) {
                if (i != j || input[i] != output[j]) return AMBIP_OVERLAP;
                *stage = 1;
            }
    return AMBIP_OK;
}

static int sample_domain(const ambip_input *in, size_t frames, uint32_t precision,
                         int conversion)
{
    for (size_t c = 0; c < in->channels; ++c)
        for (size_t f = 0; f < frames; ++f) {
            uint64_t magnitude;
            if (precision == 32) {
                uint32_t bits;
                memcpy(&bits, (const float *)in->planes[c] + f, sizeof bits);
                magnitude = bits & UINT32_C(0x7fffffff);
                if (magnitude >= UINT32_C(0x7f800000)) return AMBIP_SAMPLE_DOMAIN;
                if (conversion && magnitude && (magnitude < UINT32_C(0x02000000) ||
                    magnitude > UINT32_C(0x7dffffff))) return AMBIP_SAMPLE_DOMAIN;
            } else {
                uint64_t bits;
                memcpy(&bits, (const double *)in->planes[c] + f, sizeof bits);
                magnitude = bits & UINT64_C(0x7fffffffffffffff);
                if (magnitude >= UINT64_C(0x7ff0000000000000)) return AMBIP_SAMPLE_DOMAIN;
                if (conversion && magnitude && (magnitude < UINT64_C(0x0040000000000000) ||
                    magnitude > UINT64_C(0x7fbfffffffffffff))) return AMBIP_SAMPLE_DOMAIN;
            }
            if ((in->silence_flags & (UINT64_C(1) << c)) && magnitude)
                return AMBIP_INVALID_SILENCE;
        }
    return AMBIP_OK;
}

static int process(ambip_state *state, const ambip_input *in, ambip_output *out,
                   size_t frames, const ambip_queue *queues, size_t count,
                   ambip_report *report, uint32_t precision)
{
    if (!state || !report || state->abi_version != AMBIP_ABI_VERSION ||
        state->reserved || state->direction_table > 1 || state->bypass > 1 ||
        state->precision != precision || !config_valid(state->channels,state->precision,
          state->maximum_frames,state->scratch,state->scratch_bytes)) return AMBIP_CONFIGURATION;
    if (frames > state->maximum_frames) return AMBIP_SHAPE;
    ambip_state next = *state;
    ambip_report result = {AMBIP_NO_AUDIO,0,0};
    int error = parameters(&next, queues, count, &result.successful_parameter_updates);
    if (error) return error;
    if (!frames || !in || !in->channels) {
        *state = next; *report = result;
        return AMBIP_OK;
    }
    int stage = 0;
    error = audio_storage(state, in, out, frames, &stage);
    if (error) return error;
    int conversion = !next.bypass && !in->silence_flags;
    if (conversion && !arithmetic_environment()) return AMBIP_FP_ENVIRONMENT;
    error = sample_domain(in, frames, precision, conversion);
    if (error) return error;
    size_t n = state->channels, width = precision / 8, bytes = frames * width;
    if (next.bypass) {
        for (size_t c = 0; c < n; ++c)
            if (in->planes[c] != out->planes[c]) memcpy(out->planes[c], in->planes[c], bytes);
        result.disposition = AMBIP_BYPASS_COPIED;
    } else if (in->silence_flags) {
        result.disposition = AMBIP_SILENCE_SKIPPED;
    } else {
        const void *sources[16];
        for (size_t c = 0; c < n; ++c) {
            sources[c] = in->planes[c];
            if (stage) {
                void *plane = (unsigned char *)state->scratch + c * state->maximum_frames * width;
                memcpy(plane, in->planes[c], bytes);
                sources[c] = plane;
            }
        }
        for (size_t c = 0; c < n; ++c)
            memcpy(out->planes[maps[next.direction_table][c]], sources[c], bytes);
        for (size_t c = 0; c < n; ++c) {
            if (precision == 32) {
                float gain; memcpy(&gain, &gain32[next.direction_table][c], sizeof gain);
                float *samples = out->planes[c];
                for (size_t f = 0; f < frames; ++f) samples[f] *= gain;
            } else {
                double gain; memcpy(&gain, &gain64[next.direction_table][c], sizeof gain);
                double *samples = out->planes[c];
                for (size_t f = 0; f < frames; ++f) samples[f] *= gain;
            }
        }
        result.disposition = AMBIP_CONVERTED;
        result.staged_all_inputs = stage;
    }
    out->silence_flags = in->silence_flags;
    *state = next; *report = result;
    return AMBIP_OK;
}

int ambip_process_f32(ambip_state *s, const ambip_input *i, ambip_output *o,
                      size_t f, const ambip_queue *q, size_t n, ambip_report *r)
{ return process(s,i,o,f,q,n,r,32); }
int ambip_process_f64(ambip_state *s, const ambip_input *i, ambip_output *o,
                      size_t f, const ambip_queue *q, size_t n, ambip_report *r)
{ return process(s,i,o,f,q,n,r,64); }
