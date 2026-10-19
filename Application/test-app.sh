#!/bin/sh
set -eu
cd "$(dirname "$0")"
DEVELOPER_ROOT=$(xcode-select -p)
case "$DEVELOPER_ROOT" in
    */CommandLineTools)
        swift test --scratch-path .build-tests --disable-xctest --enable-swift-testing \
            -Xswiftc -F -Xswiftc "$DEVELOPER_ROOT/Library/Developer/Frameworks" \
            -Xswiftc -Xfrontend -Xswiftc -disable-cross-import-overlays \
            -Xswiftc -plugin-path -Xswiftc "$DEVELOPER_ROOT/usr/lib/swift/host/plugins/testing" \
            -Xlinker -rpath -Xlinker "$DEVELOPER_ROOT/Library/Developer/Frameworks" "$@"
        ;;
    *) swift test --scratch-path .build-tests "$@" ;;
esac
