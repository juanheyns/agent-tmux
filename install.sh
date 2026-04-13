#!/usr/bin/env bash
set -euo pipefail

PREFIX="${ATMUX_PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/lib/atmux"

# Check dependencies
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required"
  exit 1
fi

if ! command -v tmux &>/dev/null; then
  echo "Error: tmux is required. Run: brew install tmux"
  exit 1
fi

if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
  echo "Error: Python 3.10+ required"
  exit 1
fi

echo "Installing atmux..."
echo "  bin: $BIN_DIR/atmux"
echo "  lib: $LIB_DIR/"

mkdir -p "$BIN_DIR" "$LIB_DIR"

# Copy library files
cp -R src settings scripts .tmux.conf send stop "$LIB_DIR/"

# Ensure hooks are executable
chmod +x "$LIB_DIR"/scripts/hooks/*
chmod +x "$LIB_DIR"/send "$LIB_DIR"/stop

# Install main executable
cp atmux "$LIB_DIR/atmux"
chmod +x "$LIB_DIR/atmux"

# Create symlink
ln -sf "$LIB_DIR/atmux" "$BIN_DIR/atmux"

# Verify
if command -v atmux &>/dev/null; then
  echo ""
  echo "Installed. Run: atmux help"
else
  echo ""
  echo "Installed to $BIN_DIR/atmux"
  echo "Add $BIN_DIR to your PATH if not already:"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi
