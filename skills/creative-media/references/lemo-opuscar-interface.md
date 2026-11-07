# Lemo Opuscar — uneXpected adapter reference

**Status:** Reviewed source reference; not yet installed or executable in the uneXpected runtime.  
**Upstream:** https://github.com/lemomo-ai/lemo-opuscar  
**Pinned revision:** `5c05490cc55dfb54f8f4c333f0f0e79cb6500564`  
**Upstream package version:** `0.1.0`  
**Root source licence:** MIT (Copyright 2026 LemoLab).

## What this engine is

Lemo Opuscar is a code-based filmmaking engine: it supplies a catalogue of 66 film styles and a reproducible toolchain for drawing frames, composing audio, timing subtitles and assembling a finished film. It is not a hosted video-generation API or an autonomous creator. A capable, verified uneXpected model route must still direct the project and author a validated source bundle.

The upstream README says its styles were tuned for Claude Opus 5.5 and cautions that other models may reproduce them less reliably. uneXpected must benchmark its selected provider on original sample briefs before treating a style as production-ready.

## Production pipeline

The upstream technique guide describes a timeline as the source of truth:
1. A deterministic web page exposes a frame renderer such as `window.render(t)`.
2. Headless Chromium renders frames at the requested frame rate.
3. Voice is generated per narration line when an approved local or authorized voice engine is available.
4. Speech checks can establish word timing for subtitles.
5. Music stems and procedural sound effects follow the same timeline.
6. FFmpeg mixes, normalizes and muxes the assets into the final film.

Prefer original code-drawn visuals and locally available, properly licensed audio where quality is sufficient. An online TTS service, optional voice model, instrument pack, GPU, remote asset download or model call may introduce network use, storage requirements, licence duties or cost. None is assumed free.

## Runtime requirements recorded upstream

- Node.js 20 or later.
- FFmpeg 7 or later; upstream warns older 6.x versions can under-report audio duration for its loudness/mux checks.
- Python 3.11 or later (or uv).
- Playwright/Chromium and Three.js for rendering.
- Optional voice, music, instrument, HDRI and style-specific dependencies are installed only when a selected project requires them.

These prerequisites are a build target, not evidence that the current uneXpected API container or Render service has them. Install and execute the engine only in the dedicated isolated renderer introduced by the Creator Studio implementation.

## uneXpected integration boundary

- Pin every build to the commit above; never consume floating upstream `main`.
- Keep upstream-owned source distinct from uneXpected adapters. Preserve the MIT notice and source provenance.
- The upstream README advertises an MIT / CC BY 4.0 mix. The root MIT licence does not automatically cover every font, sample library, HDRI, texture, model, style-specific tool or demo asset. Check and record each selected asset's actual licence, attribution and permitted use.
- Do not copy demo films' stories, characters, scenes, music, artwork or other protected expression. Create original treatments and project-specific assets.
- The control plane sends only a bounded, validated one-job bundle to the renderer. Never pass bearer tokens, provider keys, database URLs, approval credentials or host environment variables.
- The renderer must be non-root, network-disabled by default, resource-limited, read-only except for its per-job output directory, and isolated from the host filesystem.
- If an isolated renderer is unavailable, keep the render job recoverable and report `renderer_unavailable`. Never execute generated code inside the authenticated API process.

## Reference sources

- [Pinned README](https://github.com/lemomo-ai/lemo-opuscar/blob/5c05490cc55dfb54f8f4c333f0f0e79cb6500564/README.md)
- [Pinned technical guide](https://github.com/lemomo-ai/lemo-opuscar/blob/5c05490cc55dfb54f8f4c333f0f0e79cb6500564/TECHNIQUE.md)
- [Pinned director guide](https://github.com/lemomo-ai/lemo-opuscar/blob/5c05490cc55dfb54f8f4c333f0f0e79cb6500564/DIRECTOR.md)
- [Pinned package manifest](https://github.com/lemomo-ai/lemo-opuscar/blob/5c05490cc55dfb54f8f4c333f0f0e79cb6500564/package.json)
- [Pinned root MIT licence](https://github.com/lemomo-ai/lemo-opuscar/blob/5c05490cc55dfb54f8f4c333f0f0e79cb6500564/LICENSE)
