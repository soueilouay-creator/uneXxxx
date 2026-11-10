#!/usr/bin/env bash
set -euo pipefail
: "${LLAMA_SERVER_BIN:?Set LLAMA_SERVER_BIN to the local llama-server executable}"
: "${UNEXPECTED_LOCAL_MODEL_PATH:?Set UNEXPECTED_LOCAL_MODEL_PATH to a reviewed local GGUF file}"
: "${UNEXPECTED_LOCAL_MODEL:?Set UNEXPECTED_LOCAL_MODEL to the local model alias}"
if [[ ! -x "$LLAMA_SERVER_BIN" ]]; then
  echo "llama-server executable is missing or not executable." >&2
  exit 2
fi
if [[ ! -f "$UNEXPECTED_LOCAL_MODEL_PATH" || -L "$UNEXPECTED_LOCAL_MODEL_PATH" ]]; then
  echo "Local model file is missing or is a symbolic link." >&2
  exit 2
fi
exec "$LLAMA_SERVER_BIN" --model "$UNEXPECTED_LOCAL_MODEL_PATH" --alias "$UNEXPECTED_LOCAL_MODEL" --host 127.0.0.1 --port 8080
