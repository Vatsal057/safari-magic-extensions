#!/usr/bin/env bash
# Build SafariMagicHub.app and package it for distribution.
#
# Produces, in dist/:
#   SafariMagicHub-<version>.dmg   drag-to-Applications installer (for everyone)
#   SafariMagicHub-<version>.zip   plain archive (for scripted installs)
#   SHA256SUMS.txt
#
# Usage (from the repository root):
#   ./scripts/package_release.sh            # version read from app/Info.plist
#   VERSION=1.2.0 ./scripts/package_release.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

APP_NAME="SafariMagicHub"
APP_BUNDLE="${APP_NAME}.app"
DIST_DIR="dist"
VOL_NAME="Safari Magic Hub"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: packaging requires macOS." >&2
  exit 1
fi

VERSION="${VERSION:-$(
  /usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" app/Info.plist 2>/dev/null \
    || echo "0.0.0"
)}"

echo "📦 Packaging ${APP_NAME} ${VERSION}"

./scripts/build_native_app.sh

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

# --- Plain zip (ditto preserves the signature and resource forks) -------------
ZIP_PATH="${DIST_DIR}/${APP_NAME}-${VERSION}.zip"
ditto -c -k --sequesterRsrc --keepParent "${APP_BUNDLE}" "${ZIP_PATH}"
echo "   built $(basename "${ZIP_PATH}")"

# --- DMG ---------------------------------------------------------------------
# A staging folder holds the app plus an /Applications symlink, so the window
# shows the familiar "drag this onto that" layout.
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

cp -R "${APP_BUNDLE}" "${STAGE}/"
ln -s /Applications "${STAGE}/Applications"

# Plain-text first-run instructions. The app is signed with a development
# certificate rather than notarized, so Gatekeeper warns on first launch.
cat > "${STAGE}/READ ME FIRST.txt" <<'TXT'
Safari Magic Hub — first run
============================

1. Drag "SafariMagicHub" onto the "Applications" folder in this window.

2. Open your Applications folder, then RIGHT-CLICK SafariMagicHub and choose
   "Open". Click "Open" again when macOS asks.

   This extra step is only needed the first time. macOS shows the warning
   because this app is not notarized by Apple, which requires a paid Apple
   Developer account. After the first launch it opens normally.

3. The app needs permission to read Safari's extension list. Go to:

       System Settings > Privacy & Security > Full Disk Access

   Turn on SafariMagicHub, then reopen the app.

4. Open the "Community Hub" tab and click Install on anything you like.
   Safari restarts to pick up the new extension.

You do not need Python or the Terminal for any of this.

Questions, or something not working?
https://github.com/Vatsal057/safari-magic-extensions/issues
TXT

DMG_PATH="${DIST_DIR}/${APP_NAME}-${VERSION}.dmg"
# hdiutil prints a deprecation notice on recent macOS but still works, and is
# available far more widely than its `diskutil image` replacement.
hdiutil create \
  -volname "${VOL_NAME}" \
  -srcfolder "${STAGE}" \
  -ov \
  -fs HFS+ \
  -format UDZO \
  "${DMG_PATH}" 2>&1 >/dev/null | grep -v 'is deprecated' || true
echo "   built $(basename "${DMG_PATH}")"

# --- Checksums ---------------------------------------------------------------
( cd "${DIST_DIR}" && shasum -a 256 ./*.dmg ./*.zip > SHA256SUMS.txt )

echo ""
echo "✓ Release artifacts in ${DIST_DIR}/"
ls -lh "${DIST_DIR}" | tail -n +2 | awk '{printf "   %-42s %s\n", $9, $5}'
echo ""
cat "${DIST_DIR}/SHA256SUMS.txt" | sed 's/^/   /'
