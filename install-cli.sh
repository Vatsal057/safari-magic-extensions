#!/usr/bin/env bash
# Safari Magic Extension CLI Installer
set -e

INSTALL_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"

echo "🪄 Installing safari-magic-ext CLI to $INSTALL_DIR..."
curl -sSL "https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/safari-magic-ext.py" -o "$INSTALL_DIR/safari-magic-ext"
chmod +x "$INSTALL_DIR/safari-magic-ext"

echo "✓ Successfully installed safari-magic-ext!"

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "Notice: Add ~/.local/bin to your PATH to run it anywhere:"
    echo '  echo '\''export PATH="$HOME/.local/bin:$PATH"'\'' >> ~/.zshrc'
    echo "  source ~/.zshrc"
fi
