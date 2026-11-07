# Isolated Creator Studio renderer

Build from the repository root with `docker build -f renderer/Dockerfile -t unexpected-creator-renderer:locked .`.

Pinned toolchain: Lemo-Opuscar `5c05490cc55dfb54f8f4c333f0f0e79cb6500564`; FFmpeg 7.1.5 source commit `3a0867c2bfda4a4d4309ca1a8cbdc6175e67f587`; Playwright 1.63.0; Three.js 0.170.0; Node 20; Python 3. The image builds FFmpeg with GPL and libx264 enabled; preserve the upstream licences if redistributing.

Input: a strict `manifest.json` plus original project files under `project/`, including `index.html` and `audio/mix.wav`. The page exposes `window.DUR`, `window.READY` and deterministic `window.render(t)`. Output profiles are 1080×1920 YouTube Shorts and TikTok.

The container uses a read-only input mount, writable output mount, `--network=none`, non-root UID 10001, dropped Linux capabilities, no-new-privileges and fixed memory/CPU/PID limits. It receives no API token, database URL, provider credential or Docker socket and never uploads or publishes media.

Outputs: `master.mp4`, `progress.json` and `result.json`. This one-shot worker is not a durable queue; the host coordinator owns job state, recovery and artifact storage. Docker access is not enabled in the live API.
