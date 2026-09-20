#!/usr/bin/env bash
# Render a real screenshot of each extension's new-tab page.
#
# Every .magicext is self-contained HTML, so the honest thumbnail is a picture
# of what the extension actually looks like, rather than hand-picked art that may not
# match. Output goes to web/assets/thumbnails/<slug>.png, which
# build_registry.py picks up automatically unless a curated art_image overrides it.
#
# Usage (from the repository root):
#   ./scripts/generate_thumbnails.sh
#   BROWSER="/path/to/Chrome" ./scripts/generate_thumbnails.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PACKAGES_DIR="web/packages"
OUT_DIR="web/assets/thumbnails"
WIDTH=1280
HEIGHT=800
# Animated pages (rAF loops) never let the browser exit on its own, so each
# render is capped: the screenshot is written well before this fires.
RENDER_TIMEOUT=20
SETTLE_MS=3500

# Find a Chromium-family browser; any of them renders identically for this.
find_browser() {
  if [[ -n "${BROWSER:-}" ]]; then echo "$BROWSER"; return; fi
  local candidates=(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    "/usr/bin/google-chrome"
    "/usr/bin/google-chrome-stable"
    "/usr/bin/chromium-browser"
    "/usr/bin/chromium"
  )
  for c in "${candidates[@]}"; do
    [[ -x "$c" ]] && { echo "$c"; return; }
  done
  return 1
}

BROWSER_BIN="$(find_browser || true)"
if [[ -z "$BROWSER_BIN" ]]; then
  echo "Error: no Chromium-based browser found. Set BROWSER=/path/to/Chrome." >&2
  exit 1
fi
echo "Using: $BROWSER_BIN"

slug_of() { python3 -c "import re,sys; print(re.sub(r'[^a-z0-9]+','-',sys.argv[1].lower()).strip('-') or 'extension')" "$1"; }

# Run the browser but never block on it: animated pages keep the process alive
# after the screenshot lands, so we poll for the file and then kill it.
render() {
  local url="$1" out="$2" profile
  profile="$(mktemp -d)"
  "$BROWSER_BIN" --headless=new --disable-gpu --no-sandbox --mute-audio \
    --hide-scrollbars --force-color-profile=srgb \
    --user-data-dir="$profile" \
    --virtual-time-budget="$SETTLE_MS" \
    --window-size="${WIDTH},${HEIGHT}" \
    --screenshot="$out" "$url" >/dev/null 2>&1 &
  local pid=$!

  local waited=0
  while (( waited < RENDER_TIMEOUT )); do
    if [[ -f "$out" ]] && ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1; (( waited++ ))
  done
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  rm -rf "$profile"
  [[ -f "$out" ]]
}

mkdir -p "$OUT_DIR"
shopt -s nullglob
packages=("$PACKAGES_DIR"/*.magicext)
if (( ${#packages[@]} == 0 )); then
  echo "No packages in $PACKAGES_DIR."; exit 0
fi

echo "Rendering ${#packages[@]} thumbnail(s) at ${WIDTH}x${HEIGHT}..."
failed=0
for pkg in "${packages[@]}"; do
  name="$(unzip -p "$pkg" magic.json | python3 -c "import json,sys; print(json.load(sys.stdin).get('name',''))")"
  entry="$(unzip -p "$pkg" manifest.json | python3 -c "import json,sys; print(json.load(sys.stdin).get('browser_url_overrides',{}).get('newtab','index.html'))" 2>/dev/null || echo index.html)"
  slug="$(slug_of "$name")"

  work="$(mktemp -d)"
  unzip -q "$pkg" -d "$work"
  raw="$work/_shot.png"
  out="$OUT_DIR/$slug.png"

  printf '  %-24s ' "$slug"
  if render "file://$work/$entry" "$raw"; then
    # Downscale to a consistent gallery width and strip metadata if tool available, or copy
    if command -v sips >/dev/null 2>&1; then
      sips -Z 640 "$raw" --out "$out" >/dev/null 2>&1
    elif command -v convert >/dev/null 2>&1; then
      convert "$raw" -resize 640x "$out" >/dev/null 2>&1
    elif python3 -c "import PIL" 2>/dev/null; then
      python3 -c "from PIL import Image; img = Image.open('$raw'); img.thumbnail((640, 400)); img.save('$out')"
    else
      cp "$raw" "$out"
    fi
    echo "ok  ($(du -h "$out" | cut -f1))"
  else
    echo "FAILED to render"
    failed=$((failed + 1))
  fi
  rm -rf "$work"
done

echo ""
if (( failed > 0 )); then
  echo "⚠️  $failed thumbnail(s) failed; those extensions fall back to curated art or the default."
else
  echo "✓ All thumbnails written to $OUT_DIR/"
fi
echo "Run 'python3 scripts/build_registry.py' to pick them up."
