#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"

echo "==> Installing AGY Session Manager (agym) from: $SCRIPT_DIR"

# 1. Check prerequisites
for cmd in python3 tmux; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' is required but not installed." >&2
    exit 1
  fi
done

if ! command -v agy >/dev/null 2>&1; then
  echo "Warning: 'agy' was not found in PATH. Make sure Antigravity CLI is installed." >&2
fi

# 2. Create / update isolated virtualenv
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
  echo "==> Creating Python virtual environment..."
  python3 -m venv "$SCRIPT_DIR/.venv"
fi

echo "==> Installing Python dependencies..."
"$SCRIPT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$SCRIPT_DIR/.venv/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

# 3. Set executable permissions
chmod +x "$SCRIPT_DIR/agym" "$SCRIPT_DIR/double_left.sh" "$SCRIPT_DIR/tui.py" "$SCRIPT_DIR/install.sh"

# 4. Symlink agym into ~/.local/bin
mkdir -p "$BIN_DIR"
ln -sf "$SCRIPT_DIR/agym" "$BIN_DIR/agym"

echo ""
echo "Installed successfully!"
echo "  Executable: $BIN_DIR/agym -> $SCRIPT_DIR/agym"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo ""
  echo "Note: $BIN_DIR is not in your PATH. Add this to your ~/.bashrc or ~/.zshrc:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
echo ""
echo "Run 'agym' to launch AGY Session Manager."
