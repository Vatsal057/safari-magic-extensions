#!/usr/bin/env bash
# Safari Magic Extension CLI installer.
#
# Usage:
#   ./install-cli.sh              # install from main
#   REF=v1.2.0 ./install-cli.sh   # install a tagged release
set -euo pipefail

REPO="${REPO:-Vatsal057/safari-magic-extensions}"
REF="${REF:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
TARGET="$INSTALL_DIR/safari-magic-ext"
SOURCE_URL="https://raw.githubusercontent.com/${REPO}/${REF}/safari-magic-ext.py"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: Safari Magic Extensions only runs on macOS." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but was not found on PATH." >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"

TMP_FILE="$(mktemp "${TMPDIR:-/tmp}/safari-magic-ext.XXXXXX")"
cleanup() { rm -f "$TMP_FILE"; }
trap cleanup EXIT

echo "🪄 Downloading safari-magic-ext (${REPO}@${REF})..."
# --fail so an HTML error page is never written over the real script.
if ! curl --fail --silent --show-error --location "$SOURCE_URL" -o "$TMP_FILE"; then
  echo "Error: download failed from $SOURCE_URL" >&2
  exit 1
fi

# Sanity-check what we downloaded before making it executable.
if [[ ! -s "$TMP_FILE" ]]; then
  echo "Error: downloaded file is empty." >&2
  exit 1
fi

if ! head -n 1 "$TMP_FILE" | grep -q '^#!/usr/bin/env python3'; then
  echo "Error: downloaded file does not look like the CLI (bad shebang)." >&2
  exit 1
fi

if ! python3 -m py_compile "$TMP_FILE" 2>/dev/null; then
  echo "Error: downloaded file is not valid Python. Refusing to install." >&2
  exit 1
fi
rm -rf "$(dirname "$TMP_FILE")/__pycache__"

# py_compile only checks syntax. Actually execute the tool so an incompatible
# interpreter is caught here rather than the first time the user runs it.
if ! VERSION_OUTPUT="$(python3 "$TMP_FILE" --version 2>&1)"; then
  echo "Error: the CLI does not run with this Python:" >&2
  echo "  $(python3 -V 2>&1)  ($(command -v python3))" >&2
  echo "$VERSION_OUTPUT" | tail -3 | sed 's/^/  /' >&2
  echo "" >&2
  echo "No Python? Use the Mac app instead, no Python required:" >&2
  echo "  https://github.com/${REPO}/releases/latest" >&2
  exit 1
fi

echo "📦 Installing to $TARGET..."
install -m 0755 "$TMP_FILE" "$TARGET"

echo "✓ Installed ${VERSION_OUTPUT}"

if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
  echo ""
  echo "Notice: add $INSTALL_DIR to your PATH to run it from anywhere:"
  echo "  echo 'export PATH=\"${INSTALL_DIR}:\$PATH\"' >> ~/.zshrc"
  echo "  source ~/.zshrc"
fi
