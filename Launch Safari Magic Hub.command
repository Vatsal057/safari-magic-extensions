#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
"${DIR}/SafariMagicHub.app/Contents/MacOS/SafariMagicHub" >/dev/null 2>&1 &
osascript -e 'tell application "Terminal" to close (every window whose name contains "Launch Safari Magic Hub")' >/dev/null 2>&1 &
exit 0
