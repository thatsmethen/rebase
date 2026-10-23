#include <fenv.h>
int review_nearest(void){return FE_TONEAREST;}
int review_upward(void){return FE_UPWARD;}
int review_downward(void){return FE_DOWNWARD;}
int review_zero(void){return FE_TOWARDZERO;}
