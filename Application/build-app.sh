#!/bin/sh
set -eu
cd "$(dirname "$0")"
ICON="$PWD/Assets/Rebase.icns"
if [ ! -s "$ICON" ]; then
    printf 'Missing application icon: %s\n' "$ICON" >&2
    exit 1
fi
sh ThirdParty/build-soxr.sh
build_swift_release() {
    swift build -c release \
        --cache-path "$PWD/.build/cache" --config-path "$PWD/.build/config" \
        --security-path "$PWD/.build/security" --disable-netrc --disable-keychain \
        -Xswiftc -file-prefix-map -Xswiftc "$PWD=/rebase/Application" \
        -Xswiftc -debug-prefix-map -Xswiftc "$PWD=/rebase/Application" \
        -Xswiftc -file-compilation-dir -Xswiftc /rebase/Application \
        -Xcc "-ffile-prefix-map=$PWD=/rebase/Application" \
        -Xcc "-fdebug-prefix-map=$PWD=/rebase/Application" \
        -Xcc "-fmacro-prefix-map=$PWD=/rebase/Application" \
        -Xcc -fdebug-compilation-dir=/rebase/Application "$@"
}
build_swift_release
BIN_DIR=$(build_swift_release --show-bin-path)
APP="$PWD/dist/Rebase.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Frameworks"
cp "$BIN_DIR/Rebase" "$APP/Contents/MacOS/Rebase"
cp "$ICON" "$APP/Contents/Resources/Rebase.icns"
install_name_tool -delete_rpath "$PWD/.build-soxr/install/lib" "$APP/Contents/MacOS/Rebase"
python3 - "$APP/Contents/MacOS/Rebase" <<'PY'
import re
import subprocess
import sys
executable = sys.argv[1]
commands = subprocess.check_output(["otool", "-l", executable], text=True)
for path in re.findall(r"cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset", commands):
    if path.startswith("/") and not path.startswith(("/usr/lib/", "/System/Library/")):
        subprocess.run(["install_name_tool", "-delete_rpath", path, executable], check=True)
        print("Removed development rpath:", path)
PY
cp .build-soxr/install/lib/libsoxr.0.1.2.dylib "$APP/Contents/Frameworks/libsoxr.0.dylib"
codesign --force --sign - "$APP/Contents/Frameworks/libsoxr.0.dylib"
NOTICES=$(mktemp "$APP/Contents/Resources/.ThirdPartyNotices.XXXXXX")
trap 'rm -f "$NOTICES"' EXIT
cat .build/checkouts/ZIPFoundation/LICENSE ThirdParty/SOXR-NOTICES.txt > "$NOTICES"
chmod 644 "$NOTICES"
mv -f "$NOTICES" "$APP/Contents/Resources/ThirdPartyNotices.txt"
rm -rf "$APP/Contents/Resources/ThirdParty"
cp -R ThirdParty "$APP/Contents/Resources/ThirdParty"
python3 export-build-manifest.py .build-soxr/build-manifest.json \
    "$APP/Contents/Resources/ThirdParty/soxr-build-manifest.json"
cp -Rf "$BIN_DIR/ZIPFoundation_ZIPFoundation.bundle" "$APP/Contents/Resources/"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Rebase</string>
<key>CFBundleDisplayName</key><string>Rebase</string>
<key>CFBundleIdentifier</key><string>org.rebaseproject.Rebase</string>
<key>CFBundleVersion</key><string>21</string>
<key>CFBundleShortVersionString</key><string>0.21.0</string>
<key>CFBundleExecutable</key><string>Rebase</string>
<key>CFBundleIconFile</key><string>Rebase.icns</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSPrincipalClass</key><string>NSApplication</string>
<key>CFBundleDocumentTypes</key><array><dict>
<key>CFBundleTypeName</key><string>Rebase Project</string>
<key>CFBundleTypeExtensions</key><array><string>rebaseproj</string></array>
<key>CFBundleTypeRole</key><string>Editor</string>
<key>LSTypeIsPackage</key><true/>
</dict></array>
</dict></plist>
PLIST
strip -S "$APP/Contents/MacOS/Rebase"
python3 release-support.py clean "$APP"
python3 release-support.py audit "$APP"
codesign --force --sign - "$APP"
codesign --verify --strict --deep "$APP"
printf 'Built %s\n' "$APP"
