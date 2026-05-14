#!/usr/bin/env bash
# Install Ollama on macOS / Linux if not already present.

set -euo pipefail

if command -v ollama >/dev/null 2>&1; then
  echo "[install_ollama] Ollama already installed: $(ollama --version 2>/dev/null || true)"
  exit 0
fi

OS="$(uname -s)"

case "$OS" in
  Darwin)
    echo "[install_ollama] Installing Ollama via Homebrew (macOS)..."
    if ! command -v brew >/dev/null 2>&1; then
      echo "[install_ollama] Homebrew not found. Install from https://brew.sh and re-run." >&2
      exit 1
    fi
    brew install --cask ollama
    ;;
  Linux)
    echo "[install_ollama] Installing Ollama via official script (Linux)..."
    curl -fsSL https://ollama.com/install.sh | sh
    ;;
  *)
    echo "[install_ollama] Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

echo "[install_ollama] Done. Start Ollama with: ollama serve  (or launch the app on macOS)"
