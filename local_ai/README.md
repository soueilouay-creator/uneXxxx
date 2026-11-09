# uneXpected Local AI runtime

This directory is the local-only model bootstrap contract. It does not contain model weights.

## Safety model

- Normal generation is offline and must use `UNEXPECTED_AI_MODE=local_only`.
- The uneXpected local text adapter accepts only a literal loopback IP and bypasses inherited HTTP proxy variables.
- Cloud provider keys may remain in a host environment for unrelated purposes, but they are not loaded into the router in local-only mode. A conflicting external provider selection is rejected.
- Missing or unverified model weights remain unavailable; there is no remote fallback and no implicit download.
- Model downloads are explicit bootstrap actions. Planning is read-only; install requires a named model ID and `--allow-network`.
- Model weights are stored outside Git under `UNEXPECTED_MODEL_ROOT`.
- Internet is used only by a separate, explicit bootstrap operation. Do not run bootstrap while producing a video.

## First local language model

The registry now includes one pinned starter model: Qwen3-0.6B Q4_0 (429 MB, Apache-2.0). The exact file is locked to Hugging Face commit `a41486f827d17edd055fe6b3b0ba3f8d427c0519` and SHA-256 `da2572f16c06133561ce56accaa822216f2391ef4d37fba427801cd6736417d4`. Its conservative uneXpected profile requires at least 8 GB system RAM and 1 GB free disk; it does not require dedicated VRAM. Model card terms and source checksum are verified, but a model is not reported locally available until the downloaded file passes the local checksum check.

Review the hardware-aware plan before installation:
```bash
python -m unexpected_runtime.cli local-ai hardware
python -m unexpected_runtime.cli local-ai bootstrap
```

To download only that named, approved model, as a separate internet-enabled bootstrap action:
```bash
python -m unexpected_runtime.cli local-ai bootstrap --model qwen3-0.6b-q4 --allow-network
```

The installer uses immutable HTTPS revisions, checks the final redirect host, resumes interrupted transfers with HTTP Range, enforces file-size bounds, verifies SHA-256, and atomically places the file under `UNEXPECTED_MODEL_ROOT`. No other model is downloadable until its complete weight set, immutable source revision, SHA-256 and usage terms are reviewed and added to the registry. The llama.cpp runtime binary itself must still be installed separately for the computer's operating system and GPU backend.

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

The registry records code repository revisions separately from weight-file licences and checksums. Repository licences do not automatically apply to model weights, LoRAs, voices, music, fonts, textures or other assets. Qwen3-0.6B is the only model with a reviewed, immutable weight lock in this branch; it remains locally unavailable until its file has been downloaded and hashed. Every image, voice, music and video candidate remains disabled for installation until all required files and terms are individually verified.

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

Copy runtime_config.example.json to ~/.unexpected/local-ai/runtime_config.json and set only installed absolute executable paths, local working directories and loopback ports. The supervisor manages installed services but does not install runtimes or download weights. It checks process identity before signalling a process, strips provider keys and proxy credentials from child environments, and refuses public binds or unverified LLM models.

### Image, voice, music and video workflow configuration

Copy media_workflows.example.json to media_workflows.json. Add a task only after its local model weight files have passed the model registry's per-file SHA-256 and licence gates. Each configured task names:
- a matching verified model registry entry;
- one local ComfyUI workflow file and exact SHA-256;
- explicit node-class allowlist and prompt-input binding;
- minimum RAM, VRAM and free-disk requirements.

The initial image candidate is FLUX.1-schnell; Qwen3-TTS, ACE-Step and the local video candidates are also catalogued. They remain blocked: their complete weight-file locks, workflow graphs, runtime/node dependencies and target-hardware profiles are not yet verified. Do not mark them installable until every component is reviewed.

Run media preflight only after ComfyUI is running:

    UNEXPECTED_AI_MODE=local_only python -m unexpected_runtime.cli local-media preflight --probe-service

The Creator Team persists its six planning stages in Creator Studio. With UNEXPECTED_AI_MODE=local_only, the optional local media stage uses pinned ComfyUI graphs to generate per-scene images and videos, a narration WAV, and a music WAV. It writes a media_state.json record with the ComfyUI prompt ID before polling, so a stopped process can resume the same job. Completed assets are reused only when their prompt, workflow and file checksums still match.

The local editing stage assembles scene videos, narration, music and SRT captions with FFmpeg; then CreatorVideoQA inspects the encoded MP4. A passing planning package is not a passing video. The media stage reports blocked until all four task workflows, verified weights, hardware requirements and local service are ready.

**Network boundary:** ComfyUI's offline flag and partner-node disablement are necessary but are not a general OS firewall. During normal generation, run local AI services with outbound network blocked by the operating system or an isolated container. The renderer Docker worker independently uses --network=none. Never use online voice, music or video APIs as a fallback.
