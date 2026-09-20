#!/usr/bin/env bash
set -e

APP_NAME="SafariMagicHub"
APP_BUNDLE="${APP_NAME}.app"
CONTENTS="${APP_BUNDLE}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"

echo "🔨 Building native macOS SwiftUI app: ${APP_NAME}..."

rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS}" "${RESOURCES}"

# Copy Info.plist and bundled resources
cp native-app/Info.plist "${CONTENTS}/Info.plist"
cp community_registry.json "${RESOURCES}/community_registry.json"

# Compile Swift sources using native swiftc
swiftc -O -parse-as-library -target arm64-apple-macos13.0 \
  -o "${MACOS}/${APP_NAME}" \
  native-app/Sources/*.swift \
  -framework SwiftUI -framework AppKit -lsqlite3

# Codesign ad-hoc for local execution
codesign --force --sign - "${APP_BUNDLE}"

echo "✓ Successfully built ${APP_BUNDLE}"

# Package zip into dist/ for distribution
mkdir -p dist
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "${APP_BUNDLE}" "dist/${APP_NAME}.zip"
echo "✓ Packaged release archive: dist/${APP_NAME}.zip"
