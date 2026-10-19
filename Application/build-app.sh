#!/bin/sh
set -eu
cd "$(dirname "$0")"
cmp ../candidate/ambiconverter_processor/ambi_processor.c Sources/RebaseAmbiDSP/ambi_processor.c
cmp ../candidate/ambiconverter_processor/ambi_processor.h Sources/RebaseAmbiDSP/include/ambi_processor.h
swift build -c release
BIN_DIR=$(swift build -c release --show-bin-path)
APP="$PWD/dist/Rebase.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN_DIR/Rebase" "$APP/Contents/MacOS/Rebase"
cp -f .build/checkouts/ZIPFoundation/LICENSE "$APP/Contents/Resources/ThirdPartyNotices.txt"
cp -Rf "$BIN_DIR/ZIPFoundation_ZIPFoundation.bundle" "$APP/Contents/Resources/"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Rebase</string>
<key>CFBundleDisplayName</key><string>Rebase</string>
<key>CFBundleIdentifier</key><string>org.rebase.rebase</string>
<key>CFBundleVersion</key><string>7</string>
<key>CFBundleShortVersionString</key><string>0.7.0</string>
<key>CFBundleExecutable</key><string>Rebase</string>
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
codesign --force --sign - "$APP"
codesign --verify --strict "$APP"
printf 'Built %s\n' "$APP"
