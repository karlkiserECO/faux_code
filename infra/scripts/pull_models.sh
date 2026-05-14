#!/usr/bin/env bash
# Pull the default model set for a 16 GB Apple Silicon target.

set -euo pipefail

CHAT_MODEL="${CHAT_MODEL:-llama3.1:8b-instruct-q4_K_M}"
CODE_MODEL="${CODE_MODEL:-qwen2.5-coder:7b-instruct-q4_K_M}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "[pull_models] Ollama not installed. Run ./infra/scripts/install_ollama.sh first." >&2
  exit 1
fi

# Make sure the daemon is up. On macOS the cask installs an app; on Linux this is a service.
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "[pull_models] Ollama daemon not reachable at http://127.0.0.1:11434."
  echo "[pull_models] Start it (macOS: open Ollama.app or run 'ollama serve'; Linux: 'systemctl start ollama')."
  echo "[pull_models] Trying 'ollama serve' in background..."
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  sleep 3
fi

for M in "$CHAT_MODEL" "$CODE_MODEL" "$EMBED_MODEL"; do
  echo "[pull_models] Pulling $M..."
  ollama pull "$M" || echo "[pull_models] WARN: failed to pull $M (you can retry later)."
done

echo "[pull_models] Done. Installed models:"
ollama list || true
