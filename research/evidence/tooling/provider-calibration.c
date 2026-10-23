#include <stdio.h>
#include <stdlib.h>

/* Authored solely to calibrate the local static-analysis provider. */
__attribute__((noinline)) int provider_calibration(int value) {
    if (value < 0) return -7;
    if (value > 100) return 100;
    return value * 3 + 1;
}

int main(int argc, char **argv) {
    int value = argc > 1 ? atoi(argv[1]) : 5;
    printf("provider-calibration:%d\n", provider_calibration(value));
    return 0;
}
