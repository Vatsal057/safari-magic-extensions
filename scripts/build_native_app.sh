#!/usr/bin/env bash
# Build the native macOS SwiftUI app (SafariMagicHub.app) from app/Sources.
#
# Produces a universal (arm64 + x86_64) binary when both slices can be built,
# otherwise falls back to the host architecture with a warning.
#
# Usage (from the repository root):
#   ./scripts/build_native_app.sh                    # universal if possible
#   ARCHS="arm64" ./scripts/build_native_app.sh       # host slice only (faster)
set -euo pipefail

# Paths below are relative to the repository root, not this script's directory.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

APP_NAME="SafariMagicHub"
APP_BUNDLE="${APP_NAME}.app"
CONTENTS="${APP_BUNDLE}/Contents"
MACOS_DIR="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"
BUILD_DIR="build"
DEPLOYMENT_TARGET="13.0"
ARCHS="${ARCHS:-arm64 x86_64}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: this app can only be built on macOS." >&2
  exit 1
fi

if ! command -v swiftc >/dev/null 2>&1; then
  echo "Error: swiftc not found. Install the Xcode command line tools:" >&2
  echo "  xcode-select --install" >&2
  exit 1
fi

SOURCES=(app/Sources/*.swift)
if [[ ! -e "${SOURCES[0]}" ]]; then
  echo "Error: no Swift sources found in app/Sources/." >&2
  exit 1
fi

echo "🔨 Building ${APP_NAME}..."

rm -rf "${APP_BUNDLE}" "${BUILD_DIR}"
mkdir -p "${MACOS_DIR}" "${RESOURCES}" "${BUILD_DIR}"

# Refresh the bundled catalog so the app has an offline fallback that matches
# the current packages.
python3 scripts/build_registry.py >/dev/null
cp app/Info.plist "${CONTENTS}/Info.plist"
cp web/community_registry.json "${RESOURCES}/community_registry.json"

# Compile one slice per architecture, then merge.
BUILT_SLICES=()
for arch in ${ARCHS}; do
  slice="${BUILD_DIR}/${APP_NAME}-${arch}"
  printf '   compiling %s slice... ' "${arch}"
  if swiftc -O -parse-as-library \
      -target "${arch}-apple-macos${DEPLOYMENT_TARGET}" \
      -o "${slice}" \
      "${SOURCES[@]}" \
      -framework SwiftUI -framework AppKit -lsqlite3 \
      >"${BUILD_DIR}/${arch}.log" 2>&1; then
    echo "ok"
    BUILT_SLICES+=("${slice}")
  else
    echo "failed (see ${BUILD_DIR}/${arch}.log)"
  fi
done

if [[ ${#BUILT_SLICES[@]} -eq 0 ]]; then
  echo "Error: every architecture failed to compile. Build log:" >&2
  cat "${BUILD_DIR}"/*.log >&2
  exit 1
fi

if [[ ${#BUILT_SLICES[@]} -eq 1 ]]; then
  echo "⚠️  Only one architecture built; the app will not be universal."
  cp "${BUILT_SLICES[0]}" "${MACOS_DIR}/${APP_NAME}"
else
  lipo -create -output "${MACOS_DIR}/${APP_NAME}" "${BUILT_SLICES[@]}"
fi

chmod +x "${MACOS_DIR}/${APP_NAME}"

# Prefer a real Developer ID / Apple Development identity; fall back to ad-hoc.
# Ad-hoc signed builds run locally but Gatekeeper will warn other users.
# `|| true` matters: with no identity installed (CI, fresh machines) grep
# exits 1, which would abort the script under `set -e`/`pipefail`.
SIGN_IDENTITY="$(
  security find-identity -v -p codesigning 2>/dev/null \
    | grep -E "Developer ID Application|Apple Development" \
    | head -n 1 \
    | awk -F '"' '{print $2}' || true
)"

if [[ -z "${SIGN_IDENTITY}" ]]; then
  SIGN_IDENTITY="-"
  echo "🔏 No signing identity found; using ad-hoc signature."
else
  echo "🔏 Signing with: ${SIGN_IDENTITY}"
fi

# --deep is deprecated; sign the nested binary first, then the bundle.
codesign --force --timestamp=none --sign "${SIGN_IDENTITY}" "${MACOS_DIR}/${APP_NAME}"
codesign --force --timestamp=none --sign "${SIGN_IDENTITY}" "${APP_BUNDLE}"
codesign --verify --strict "${APP_BUNDLE}"

rm -rf "${BUILD_DIR}"

echo "✓ Built ${APP_BUNDLE} ($(lipo -archs "${MACOS_DIR}/${APP_NAME}"))"
echo ""
echo "Run it with:  open ${APP_BUNDLE}"
echo "Note: grant Full Disk Access (System Settings > Privacy & Security)"
echo "      so the app can read Safari's extension database."
