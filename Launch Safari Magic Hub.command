#!/usr/bin/env bash
# Double-clickable launcher for SafariMagicHub.app.
# Build the app first with ./scripts/build_native_app.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
APP="${DIR}/SafariMagicHub.app"

if [[ ! -d "${APP}" ]]; then
  echo "Safari Magic Hub is not built yet."
  echo ""
  echo "Build it by running this in Terminal:"
  echo "  cd \"${DIR}\" && ./scripts/build_native_app.sh"
  echo ""
  read -r -p "Press Return to close this window..."
  exit 1
fi

# Use `open` so macOS activates the bundle properly (dock icon, document
# handling, and the .magicext file association all depend on this).
open "${APP}"

# Close the Terminal window this launcher opened.
osascript -e 'tell application "Terminal" to close (every window whose name contains "Launch Safari Magic Hub")' >/dev/null 2>&1 &
exit 0
