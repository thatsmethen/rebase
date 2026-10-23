#include "cpr_track_overlap.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 && FLT_RADIX == 2,
               "IEEE binary64 required");

typedef struct Node {
    RBTrackOverlapRange value;
    struct Node *previous, *next;
} Node;
typedef struct {
    Node *head, *tail, *free;
    RBTrackOverlapRange *output;
    int32_t count, capacity;
    double watermark;
} State;

static int nearest_environment(void) {
    if (fegetround() != FE_TONEAREST) return 0;
#if defined(__aarch64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    return (fpcr & ((UINT64_C(1) << 24) | (UINT64_C(1) << 25) | 3)) == 0;
#else
    return 0;
#endif
}
static double from_bits(uint64_t bits) { double value; memcpy(&value, &bits, 8); return value; }
static int coordinate(double value) { return (value == 0.0 || isnormal(value)) && value >= 0.0 && value <= 86400.0; }
static int separated(double first, double second) {
    volatile double difference = first - second;
    return fabs(difference) >= from_bits(UINT64_C(0x3f1a36e2eb1c432d));
}
static void unlink_node(State *state, Node *node) {
    if (node->previous) node->previous->next = node->next; else state->head = node->next;
    if (node->next) node->next->previous = node->previous; else state->tail = node->previous;
    node->previous = node->next = NULL;
}
static void insert_after_equal_start(State *state, Node *node) {
    Node *previous = state->tail;
    while (previous && previous->value.start > node->value.start) previous = previous->previous;
    node->previous = previous;
    node->next = previous ? previous->next : state->head;
    if (node->next) node->next->previous = node; else state->tail = node;
    if (previous) previous->next = node; else state->head = node;
}
static void release_node(State *state, Node *node) {
    node->previous = NULL; node->next = state->free; state->free = node;
}
static int publish(State *state, const Node *node) {
    RBTrackOverlapRange value = node->value;
    if (value.start < state->watermark) value.start = state->watermark;
    if (state->watermark < value.end) state->watermark = value.end;
    volatile double length = value.end - value.start;
    if (length > 0.0) {
        if (state->count == state->capacity) return 0;
        state->output[state->count++] = value;
    }
    return 1;
}

int rb_cpr_track_overlap_normalize(const RBTrackOverlapRange *source, int32_t count,
    RBTrackOverlapRange *output, int32_t capacity, int32_t *outputCount) {
    if (!source || !output || !outputCount || count < 1 || count > RB_TRACK_OVERLAP_MAX_INPUTS ||
        capacity < 1 || capacity > RB_TRACK_OVERLAP_MAX_OUTPUTS) return RB_TRACK_OVERLAP_INVALID;
    if (!nearest_environment()) return RB_TRACK_OVERLAP_FP_ENVIRONMENT;
    for (int32_t i = 0; i < count; ++i) {
        const RBTrackOverlapRange *r = source + i;
        if (r->sourceIndex != i || r->ordinal < 0 || !coordinate(r->start) || !coordinate(r->end) ||
            !(r->start < r->end) || (i && source[i - 1].start > r->start)) return RB_TRACK_OVERLAP_INVALID;
        for (int32_t j = 0; j < i; ++j) if (source[j].ordinal == r->ordinal) return RB_TRACK_OVERLAP_INVALID;
    }
    Node *nodes = calloc((size_t)count + 1, sizeof(Node));
    RBTrackOverlapRange *result = calloc((size_t)capacity, sizeof(RBTrackOverlapRange));
    if (!nodes || !result) { free(nodes); free(result); return RB_TRACK_OVERLAP_ALLOCATION; }
    State state = { .head = nodes, .tail = nodes + count - 1, .free = nodes + count,
        .output = result, .count = 0, .capacity = capacity,
        .watermark = from_bits(UINT64_C(0xc14b774000000000)) };
    for (int32_t i = 0; i < count; ++i) {
        nodes[i].value = source[i];
        nodes[i].previous = i ? nodes + i - 1 : NULL;
        nodes[i].next = i + 1 < count ? nodes + i + 1 : NULL;
    }
    uint64_t visits = 0, limit = 4 * (uint64_t)count * (uint64_t)count + (uint64_t)count;
    int status = RB_TRACK_OVERLAP_OK;
    while (state.head) {
        Node *current = state.head;
        unlink_node(&state, current);
        Node *following = state.head;
        for (;;) {
            if (!following) {
                if (!publish(&state, current)) status = RB_TRACK_OVERLAP_LIMIT;
                break;
            }
            if (++visits > limit) { status = RB_TRACK_OVERLAP_LIMIT; break; }
            if (!(current->value.end >= following->value.start && separated(current->value.end, following->value.start))) {
                if (!publish(&state, current)) status = RB_TRACK_OVERLAP_LIMIT;
                break;
            }
            int currentWins = following->value.priority < current->value.priority ||
                (following->value.priority == current->value.priority && following->value.ordinal < current->value.ordinal);
            if (currentWins) {
                /* Keep this exact node identity before unlink/reinsertion. */
                Node *successor = following->next;
                unlink_node(&state, following);
                if (following->value.end >= current->value.end && separated(following->value.end, current->value.end)) {
                    following->value.start = current->value.end;
                    insert_after_equal_start(&state, following);
                } else release_node(&state, following);
                following = successor;
                continue;
            }
            if (current->value.end >= following->value.end && separated(current->value.end, following->value.end)) {
                Node *tail = state.free;
                if (!tail) { status = RB_TRACK_OVERLAP_LIMIT; break; }
                state.free = tail->next;
                tail->value = current->value;
                tail->value.start = following->value.end;
                insert_after_equal_start(&state, tail);
            }
            if (current->value.start < following->value.start && separated(current->value.start, following->value.start)) {
                current->value.end = following->value.start;
                if (!publish(&state, current)) status = RB_TRACK_OVERLAP_LIMIT;
            }
            break;
        }
        release_node(&state, current);
        if (status != RB_TRACK_OVERLAP_OK) break;
    }
    if (status == RB_TRACK_OVERLAP_OK) {
        memcpy(output, result, (size_t)state.count * sizeof(*output));
        *outputCount = state.count;
    }
    free(nodes); free(result);
    return status;
}
