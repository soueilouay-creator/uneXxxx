# Third-party notices

## awesome-llm-apps

- Repository: https://github.com/Shubhamsaboo/awesome-llm-apps
- Source revision referenced by the v6→v7 crosswalk: 6c16b23f1bacd0fdf240bb5141ef45e59e82c306
- Declared upstream license: Apache License 2.0
- License text: third_party/licenses/awesome-llm-apps/LICENSE
- Adapted material: workflow discovery/crosswalk metadata and procedural summaries preserved with individual source paths/URLs in MIGRATION_CROSSWALK_V6_TO_V7.json and web/assets/workflow-catalog.json.
- No upstream application code is bundled as an executable dependency.

Other repositories in docs/OPEN_SOURCE_ADAPTATION_REGISTER.md are architecture references only. Their code, branding, UI assets and media are not copied into this repository.


## Lemo Opuscar isolated rendering worker

- **Lemo Opuscar source:** MIT, pinned to commit 5c05490cc55dfb54f8f4c333f0f0e79cb6500564. The upstream LICENSE is retained inside the renderer image at /opt/lemo-opuscar/LICENSE.
- **Playwright:** playwright-core 1.63.0, Apache-2.0. Browser binaries come from the matching Microsoft Playwright v1.63.0-noble base image; retain the base-image notices.
- **Three.js:** 0.170.0, MIT.
- **FFmpeg:** signed release tag n7.1.5, resolved commit 3a0867c2bfda4a4d4309ca1a8cbdc6175e67f587. The worker compiles it with GPL and libx264 enabled; this build is GPL. Retain the matching FFmpeg source and build configuration when redistributing.
- **x264:** Ubuntu libx264-dev package, GPL. Preserve the package licence notices on redistribution.
- **Opuscar demo films/posters and voice tracks:** not bundled in the smoke project. They carry independent per-asset licence/attribution conditions and are not covered automatically by the Opuscar code licence. Every later media asset needs its own provenance and licence record.
