#ifndef REBASE_CPR_TIMELINE_SELECTOR_H
#define REBASE_CPR_TIMELINE_SELECTOR_H
#include <stddef.h>
#include <stdint.h>

/* Bounded value reconstruction of 1001f96f8 and concrete end accessor
   101a17d08 (Cubase 15.0.30.287 arm64). -1 represents a null node index.
   Stable arrays stand in for the native list and non-mutating retain callbacks.
   Node0 is the list head when count>0; fresh traversal follows successors.
   A traversal exceeding count nodes fails instead of looping indefinitely.
   Coordinates must share a domain; this function does not convert units.
   The caller owns current_index: selecting does not advance it.
   Returns zero on success; validation failure leaves outputs untouched. */
int rb_cpr_timeline_select(const double *starts, const double *lengths,
                          const int64_t *successors, size_t count,
                          uint32_t generation, double query,
                          int64_t current_index, uint32_t cursor_generation,
                          int64_t *selected_index, uint32_t *updated_generation);
#endif
