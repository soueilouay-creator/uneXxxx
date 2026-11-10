#!/usr/bin/env bash
set -euo pipefail
: "${COMFYUI_HOME:?Set COMFYUI_HOME to the local ComfyUI checkout}"
: "${COMFYUI_PYTHON:?Set COMFYUI_PYTHON to its local Python executable}"
if [[ ! -f "$COMFYUI_HOME/main.py" ]]; then
  echo "ComfyUI main.py was not found at COMFYUI_HOME." >&2
  exit 2
fi
if [[ ! -x "$COMFYUI_PYTHON" ]]; then
  echo "ComfyUI Python executable is missing or not executable." >&2
  exit 2
fi
cd "$COMFYUI_HOME"
exec "$COMFYUI_PYTHON" main.py --listen 127.0.0.1 --port 8188 --offline --disable-partner-nodes
