# Public SoXR build and replacement

Rebase dynamically links an independently built public SoX Resampler Library
0.1.3. It does not load Reference's bundled library. The complete unchanged source
is in `soxr-0.1.3`, from commit
`945b592b70470e29f917f4de89b4281fbbd540c0` of
<https://github.com/chirlu/soxr>. The upstream project is
<https://sourceforge.net/projects/soxr/>. `soxr-source-manifest.json` records
the download identity and every source file or symlink.

The public library is LGPL 2.1 or later. `soxr-0.1.3/LICENCE` and
`soxr-0.1.3/COPYING.LGPL` contain its notice and complete license.
The FFT notices remain in their original files and are also reproduced in
`SOXR-NOTICES.txt`. The source tree contains optional code not compiled by this
configuration; its licenses remain present as well. The original source has
not been modified. Rebase's bridge and native-wrapper reconstruction are
separate application files.

Build on an arm64 Mac with Xcode Command Line Tools, CMake and Python 3:

```sh
sh Application/ThirdParty/build-soxr.sh
```

This uses Apple Clang, the selected macOS SDK and a macOS 14 minimum. It enables
scalar CR32 and CR64, disables SIMD, OpenMP, variable-rate support, libav FFT,
PFFFT and the libsamplerate interface, and uses `-O3 -fno-fast-math
-ffp-contract=off`. High-precision clock support is enabled. Compiler, SDK,
source hashes, configured options, compile commands and binary identity are
recorded in `.build-soxr/build-manifest.json`. These are our reproducible
configuration choices; the proprietary build's configuration and output
equivalence are unknown.

The callback bridge creates Float32 interleaved streams with quality recipe 6
(VHQ), flags 0 and runtime 0. It reports actual library input/output counts.
It does not implement the separate native wrapper's padding, carry or EOF
policy itself. No implicit fallback is provided.

The application bundle contains this entire directory at
`Contents/Resources/ThirdParty`, including corresponding library source and
build scripts. Its replaceable library is
`Contents/Frameworks/libsoxr.0.dylib`, with install name
`@rpath/libsoxr.0.dylib`. The upstream ABI version is 0.1.2 even though the
source/API version is 0.1.3. The application executable uses its bundled
Frameworks rpath; the development build-directory rpath is removed during
packaging.

To modify or replace the library, copy the bundled ThirdParty directory to a
writable location, change the source if desired, and run:

```sh
REBASE_SOXR_ALLOW_MODIFIED_SOURCE=1 \
REBASE_SOXR_BUILD_DIR="$PWD/rebuilt-soxr" sh ThirdParty/build-soxr.sh
cp rebuilt-soxr/install/lib/libsoxr.0.1.2.dylib \
  /path/to/Rebase.app/Contents/Frameworks/libsoxr.0.dylib
codesign --force --sign - /path/to/Rebase.app/Contents/Frameworks/libsoxr.0.dylib
codesign --force --sign - /path/to/Rebase.app
```

Keep the public ABI compatible. The explicit modified-source option bypasses
the pinned-source check and records the actual source hashes in the resulting
build manifest. The original application acceptance hashes will no longer
describe a modified build. Modification/replacement and reverse engineering
for debugging such modifications are permitted under the library license.
