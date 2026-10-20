#include "cpr_timeline_selector.h"
#include <fenv.h>
#include <math.h>

#pragma STDC FENV_ACCESS ON

static int coordinate(double value) {
    return isfinite(value) && value >= 0 && (value == 0 || isnormal(value));
}

int rb_cpr_timeline_select(const double *starts, const double *lengths,
                          const int64_t *successors, size_t count,
                          uint32_t generation, double query,
                          int64_t current_index, uint32_t cursor_generation,
                          int64_t *selected_index, uint32_t *updated_generation) {
    if (!selected_index || !updated_generation || count > 4096 ||
        (count && (!starts || !lengths || !successors)) ||
        !coordinate(query) || fegetround() != FE_TONEAREST) return 1;
    if (generation == cursor_generation && current_index != -1 &&
        (current_index < 0 || (uint64_t)current_index >= count)) return 1;
    for (size_t i = 0; i < count; ++i) {
        if (!coordinate(starts[i]) || !coordinate(lengths[i]) ||
            successors[i] < -1 || (successors[i] >= 0 && (uint64_t)successors[i] >= count)) return 1;
        volatile double end = starts[i] + lengths[i];
        if (!coordinate(end)) return 1;
    }
    int64_t result = -1;
    uint32_t next_generation = cursor_generation;
    if (generation == cursor_generation && current_index != -1) {
        result = successors[current_index];
    } else {
        next_generation = generation;
        int64_t index = count ? 0 : -1;
        size_t visited = 0;
        while (index != -1) {
            if (visited++ == count) return 1; /* Reject a nonterminating cycle. */
            volatile double end = starts[index] + lengths[index];
            if (end >= query) { result = index; break; }
            index = successors[index];
        }
    }
    *selected_index = result;
    *updated_generation = next_generation;
    return 0;
}
