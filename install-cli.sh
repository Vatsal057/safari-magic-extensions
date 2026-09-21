#!/usr/bin/env bash
# Safari Magic Extension CLI installer.
#
# Usage:
#   ./install-cli.sh              # install only, update PATH
#   REF=v1.2.0 ./install-cli.sh   # install a tagged release
#
# Pass-through usage (run a command immediately after installing):
#   curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash -s -- install nightlife-in-the-wild
#   curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash -s -- submit
set -euo pipefail

REPO="${REPO:-Vatsal057/safari-magic-extensions}"
REF="${REF:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
TARGET="$INSTALL_DIR/safari-magic-ext"
SOURCE_URL="https://raw.githubusercontent.com/${REPO}/${REF}/safari-magic-ext.py?v=$(date +%s)"

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
  echo "Please install Python 3.9+ or run: xcode-select --install" >&2
  exit 1
fi

echo "📦 Installing to $TARGET..."
install -m 0755 "$TMP_FILE" "$TARGET"

echo "✓ Installed ${VERSION_OUTPUT}"

# Auto-configure PATH in ~/.zshrc if needed.
SHELL_RC="$HOME/.zshrc"
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
  EXPORT_LINE="export PATH=\"${INSTALL_DIR}:\$PATH\""
  if ! grep -qF "$EXPORT_LINE" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# Added by safari-magic-ext installer" >> "$SHELL_RC"
    echo "$EXPORT_LINE" >> "$SHELL_RC"
    echo ""
    echo "✓ Added $INSTALL_DIR to PATH in $SHELL_RC"
  fi
  # Make it available in the current shell session immediately.
  export PATH="${INSTALL_DIR}:$PATH"
fi

# If arguments were passed (e.g. `bash -s -- install nightlife`), run them now.
# This means the single curl | bash one-liner fully installs AND runs the command.
if [[ $# -gt 0 ]]; then
  echo ""
  echo "Running: safari-magic-ext $*"
  echo ""
  # When run via `curl | bash`, stdin is the pipe. Reconnect it to the terminal
  # so that interactive prompts (like the extension picker) work properly.
  if [[ -t 1 ]] && [[ -e /dev/tty ]]; then
    exec < /dev/tty
  fi
  exec python3 "$TARGET" "$@"
fi
