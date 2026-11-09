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

## Local ComfyUI launch

Install ComfyUI and its reviewed model/node dependencies in a dedicated local environment during bootstrap. Then launch it offline:

- Linux/macOS: `COMFYUI_HOME=/path/to/ComfyUI COMFYUI_PYTHON=/path/to/python ./local_ai/start-comfyui.sh`
- Windows PowerShell: set `COMFYUI_HOME` and `COMFYUI_PYTHON`, then run `./local_ai/start-comfyui.ps1`.

The launch scripts bind only to `127.0.0.1`, turn on ComfyUI offline mode, and disable optional partner/API nodes. They do not download missing models or custom nodes.


## Hardware-aware supervisor and media stages

Use these commands from the repository root:

    python -m unexpected_runtime.cli local-ai hardware
    python -m unexpected_runtime.cli local-ai preflight
    python -m unexpected_runtime.cli local-ai status
    python -m unexpected_runtime.cli local-ai start --service llm
    python -m unexpected_runtime.cli local-ai start --service comfyui
    python -m unexpected_runtime.cli local-ai stop

Copy runtime_config.example.json to ~/.unexpected/local-ai/runtime_config.json and set only installed absolute executable paths, local working directories and loopback ports. The supervisor does not install or download weights. It checks process identity before signalling a process, strips provider keys and proxy credentials from child environments, and refuses public binds or unverified LLM models.

### Image, voice, music and video workflow configuration

Copy media_workflows.example.json to media_workflows.json. Add a task only after its local model weight files have passed the model registry's per-file SHA-256 and licence gates. Each configured task names:
- a matching verified model registry entry;
- one local ComfyUI workflow file and exact SHA-256;
- explicit node-class allowlist and prompt-input binding;
- minimum RAM, VRAM and free-disk requirements.

The initial image candidate is FLUX.1-schnell. Its upstream weight licence is a candidate for Apache-2.0, but no exact weight bundle or checksum is installed; it remains discovered and unavailable until reviewed. Qwen3-TTS, ACE-Step and the local video candidates are equally gated. Do not mark a model verified until the exact full weight set and terms are checked.

Run media preflight only after ComfyUI is running:

    UNEXPECTED_AI_MODE=local_only python -m unexpected_runtime.cli local-media preflight --probe-service

The Creator Team persists its six planning stages in Creator Studio. With UNEXPECTED_AI_MODE=local_only, the optional local media stage uses pinned ComfyUI graphs to generate per-scene images and videos, a narration WAV, and a music WAV. It writes a media_state.json record with the ComfyUI prompt ID before polling, so a stopped process can resume the same job. Completed assets are reused only when their prompt, workflow and file checksums still match.

The local editing stage assembles scene videos, narration, music and SRT captions with FFmpeg; then CreatorVideoQA inspects the encoded MP4. A passing planning package is not a passing video. The media stage reports blocked until all four task workflows, verified weights, hardware requirements and local service are ready.

**Network boundary:** ComfyUI's offline flag and partner-node disablement are necessary but are not a general OS firewall. During normal generation, run local AI services with outbound network blocked by the operating system or an isolated container. The renderer Docker worker independently uses --network=none. Never use online voice, music or video APIs as a fallback.
