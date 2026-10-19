#ifndef REBASE_NATIVE_TEMPO_H
#define REBASE_NATIVE_TEMPO_H

#include <stdint.h>

/* Recovered fixed-tempo arithmetic, limited to finite normal values or zero
   under round-to-nearest. No target code is included or executed. */
enum {
    RB_NATIVE_TEMPO_OK = 0,
    RB_NATIVE_TEMPO_INVALID = 1,
    RB_NATIVE_TEMPO_FP_ENVIRONMENT = 2,
    RB_NATIVE_TEMPO_UNREPRESENTABLE = 3
};
int rb_native_fixed_period(uint32_t bpm_bits, uint32_t *period_bits);
int rb_native_fixed_seconds(uint32_t bpm_bits, double tick, double *seconds);
int rb_native_fixed_ticks(uint32_t bpm_bits, double seconds, double *tick);

/* Detached jump-map arithmetic from CPR-MAP-CLOCK-001. These primitives do
   not establish which native list/cache is active and do not execute target
   code. Callers own source provenance, lifecycle and the display BPM domain.
   Conversion accepts 1/2 ordered points with first anchors +0, direct positive
   normal Float32 period bits, and finite normal-or-zero coordinates. Supplied
   later anchors are preserved. Query -0 is allowed. Errors do not write output.
   The limits match the application's 1e9-quarter-note/20-BPM upper timeline.
   A separate validator additionally requires exact native cache recurrence;
   import promotion must require that stronger canonical-state check. */
#define RB_NATIVE_MAP_MAX_TICKS 480000000000.0
#define RB_NATIVE_MAP_MAX_SECONDS 3000000000.0
typedef struct rb_native_jump_point {
    uint32_t period_bits;
    double seconds;
    double ticks;
} rb_native_jump_point;

int rb_native_map_validate(const rb_native_jump_point *points, uint32_t count);
int rb_native_map_seconds(const rb_native_jump_point *points, uint32_t count,
                          double tick, double *seconds);
int rb_native_map_ticks(const rb_native_jump_point *points, uint32_t count,
                       double seconds, double *tick);

#endif
