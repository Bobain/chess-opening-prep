#!/bin/bash
# chess-self-coach installer
# Usage: curl -fsSL https://raw.githubusercontent.com/Bobain/chess-self-coach/main/install.sh | bash
set -euo pipefail

PACKAGE="chess-self-coach"

# --- OS detection ---

detect_platform() {
  OS="$(uname -s)"
  case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      echo "❌ Unsupported OS: $OS (macOS and Debian/Ubuntu supported)" && exit 1 ;;
  esac
}

# --- Stockfish ---

install_stockfish() {
  if command -v stockfish &>/dev/null; then
    echo "  ✓ Stockfish already installed ($(stockfish --help 2>&1 | head -1 || echo 'found'))"
    return
  fi

  echo "  Installing Stockfish..."
  case "$PLATFORM" in
    macos)
      if ! command -v brew &>/dev/null; then
        echo "  ❌ Homebrew is required to install Stockfish on macOS."
        echo "     Install it first: https://brew.sh"
        exit 1
      fi
      brew install stockfish
      ;;
    linux)
      if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y stockfish
      else
        echo "  ❌ apt-get not found. Install Stockfish manually:"
        echo "     https://stockfishchess.org/download/"
        exit 1
      fi
      ;;
  esac
  echo "  ✓ Stockfish installed"
}

# --- Python ---

install_python() {
  if command -v python3 &>/dev/null; then
    PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    echo "  ✓ Python $PYTHON_VERSION found"
    return
  fi

  echo "  Installing Python..."
  case "$PLATFORM" in
    macos) brew install python@3.12 ;;
    linux) sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv python3-pip ;;
  esac
  echo "  ✓ Python installed"
}

# --- pipx ---

install_pipx() {
  if command -v pipx &>/dev/null; then
    echo "  ✓ pipx already installed"
    return
  fi

  echo "  Installing pipx..."
  case "$PLATFORM" in
    macos) brew install pipx ;;
    linux)
      if command -v apt-get &>/dev/null; then
        sudo apt-get install -y pipx
      else
        python3 -m pip install --user pipx
      fi
      ;;
  esac
  pipx ensurepath 2>/dev/null || true
  echo "  ✓ pipx installed"
}

# --- Main ---

main() {
  echo ""
  echo "♟️  chess-self-coach installer"
  echo "─────────────────────────────"
  echo ""

  detect_platform
  echo "Platform: $PLATFORM ($(uname -m))"
  echo ""

  echo "Step 1/4: Stockfish"
  install_stockfish
  echo ""

  echo "Step 2/4: Python"
  install_python
  echo ""

  echo "Step 3/4: pipx"
  install_pipx
  echo ""

  echo "Step 4/4: $PACKAGE"
  if pipx list 2>/dev/null | grep -q "$PACKAGE"; then
    echo "  Upgrading $PACKAGE..."
    pipx upgrade "$PACKAGE"
  else
    echo "  Installing $PACKAGE from PyPI..."
    pipx install "$PACKAGE"
  fi
  echo "  ✓ $PACKAGE ready"
  echo ""

  echo "─────────────────────────────"
  echo "✓ Installation complete!"
  echo ""
  echo "Run the setup wizard:"
  echo "  chess-self-coach setup"
  echo ""
  echo "Update later with:"
  echo "  chess-self-coach update"
  echo ""
}

main "$@"
