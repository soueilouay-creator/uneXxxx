# uneXpected Local AI runtime

This directory is the local-only model bootstrap contract. It does not contain model weights.

## Safety model

- Normal generation is offline and must use `UNEXPECTED_AI_MODE=local_only`.
- The uneXpected local text adapter accepts only a literal loopback IP and bypasses inherited HTTP proxy variables.
- Cloud provider keys may remain in a host environment for unrelated purposes, but they are not loaded into the router in local-only mode. A conflicting external provider selection is rejected.
- Missing or unverified model weights remain unavailable; there is no remote fallback and no automatic download.
- Model weights are stored outside Git under `UNEXPECTED_MODEL_ROOT`.
- Internet is used only by a separate, explicit bootstrap operation. Do not run bootstrap while producing a video.

## First local language model

Install/build the pinned llama.cpp runtime for the computer's operating system and GPU backend, then obtain a compatible GGUF instruct model through its own reviewed model card. Verify its licence, commercial-use terms, weight-file SHA-256 and machine memory before loading it.

Start the local server (example):

```bash
LLAMA_SERVER_BIN=/path/to/llama-server \
UNEXPECTED_LOCAL_MODEL_PATH=/path/to/models/instruct.gguf \
UNEXPECTED_LOCAL_MODEL=uneXpected-local \
./local_ai/start-llama-server.sh
```

In a separate shell, run uneXpected with:

```bash
UNEXPECTED_AI_MODE=local_only \
UNEXPECTED_LOCAL_BASE_URL=http://127.0.0.1:8080/v1 \
UNEXPECTED_LOCAL_MODEL=uneXpected-local \
python -m unexpected_runtime.http_api
```

The router does not fall back if this local service is stopped or unavailable.

## ComfyUI

Install ComfyUI in a dedicated local environment. Launch with `--listen 127.0.0.1 --port 8188 --offline --disable-partner-nodes`. Do not install unreviewed custom nodes. Workflow JSON may reference only local nodes and cached, licence-reviewed weights.

## Model registry states

`discovered → reviewed → download-approved → cached → verified`

The registry records code repository revisions separately from weight-file licences and checksums. Repository licences do not automatically apply to model weights, LoRAs, voices, music, fonts, textures or other assets. No entry in the initial registry is marked verified because no exact local weight file has yet been selected and hashed.

## Inspection

```bash
python -m unexpected_runtime.local_ai status --model-root ./models
python -m unexpected_runtime.local_ai preflight --model-root ./models
```

Inspection is read-only. It detects platform, CPU count, RAM where available, free disk space, common runtime executables and model-file availability. It does not download files, call web endpoints or start processes. Hardware-specific video-model choice is deferred to the local machine's measured capability report.
