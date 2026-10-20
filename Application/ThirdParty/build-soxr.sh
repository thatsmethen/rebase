#!/bin/sh
# Build only the pinned PUBLIC source; never reads the installed Reference library.
set -eu
THIRD_PARTY=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_ROOT=$(dirname "$THIRD_PARTY")
BUILD_DIR=${REBASE_SOXR_BUILD_DIR:-"$APP_ROOT/.build-soxr"}
export BUILD_DIR THIRD_PARTY
python3 "$THIRD_PARTY/verify-soxr-source.py"
mkdir -p "$BUILD_DIR"
SDK=$(xcrun --sdk macosx --show-sdk-path)
CC=$(xcrun --find clang)
cmake -S "$THIRD_PARTY/soxr-0.1.3" -B "$BUILD_DIR/cmake" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER="$CC" \
    -DCMAKE_OSX_SYSROOT="$SDK" -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 \
    -DCMAKE_C_FLAGS="-fno-fast-math -ffp-contract=off" \
    -DCMAKE_C_FLAGS_RELEASE="-O3 -DNDEBUG" \
    -DCMAKE_INSTALL_PREFIX="$BUILD_DIR/install" \
    -DBUILD_SHARED_LIBS=ON -DBUILD_TESTS=OFF -DBUILD_EXAMPLES=OFF \
    -DWITH_OPENMP=OFF -DWITH_LSR_BINDINGS=OFF -DBUILD_LSR_TESTS=OFF \
    -DWITH_CR32=ON -DWITH_CR64=ON -DWITH_CR32S=OFF -DWITH_CR64S=OFF \
    -DWITH_VR32=OFF -DWITH_PFFFT=OFF -DWITH_AVFFT=OFF \
    -DWITH_HI_PREC_CLOCK=ON -DWITH_FLOAT_STD_PREC_CLOCK=OFF \
    -DWITH_DEV_TRACE=OFF -DWITH_DEV_GPROF=OFF \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "$BUILD_DIR/cmake" --parallel 2
cmake --install "$BUILD_DIR/cmake"
LIB="$BUILD_DIR/install/lib/libsoxr.0.1.2.dylib"
# This ABI version is upstream's 0.1.2; source/API version is 0.1.3.
install_name_tool -id '@rpath/libsoxr.0.dylib' "$LIB"
codesign --force --sign - "$LIB"
python3 "$THIRD_PARTY/record-soxr-build.py"
