# uneXpected Creator Studio — Long-form Story Film Profile

## Creative target

Primary deliverable: an original 30–45 minute YouTube romance/fantasy story film in 16:9 landscape. Target master is 1920×1080 H.264/AAC MP4 at 24 FPS, with a 1280×720 thumbnail and timed English subtitles. Build a separate vertical derivative only after the landscape master passes QA.

The owner's reference establishes genre and presentation conventions only: narrated paranormal romance/fantasy, dramatic emotional stakes, cinematic character imagery and long-form episode duration. All story worlds, titles, dialogue, characters, images, music and branding must be original or appropriately licensed.

## Render engines

- Opuscar remains the isolated code-rendering path for authored motion-led projects and short-form 9:16 renders.
- Story-film is an isolated FFmpeg composition path for supplied still illustrations, a narration WAV and an SRT file. It applies a slow landscape camera move, burns subtitles, normalizes the narration track, encodes the MP4 and extracts a thumbnail.
- The long-form worker accepts only the youtube_longform 1920×1080 profile. Its version-1 timeline JSON has 2–120 scenes. Every scene references a local scenes/*.png, .jpg, .jpeg or .webp asset and has a 2–180 second duration. Scene durations must cover the narration WAV within 1.5 seconds.
- project/audio/mix.wav, project/captions.srt and project/timeline.json must exist. No remote URL, arbitrary executable, network call or symlink is accepted in the render sandbox.
- Maximum input is 2,000 files and 100 MiB. The render container has no network, a read-only root, a non-root UID, resource limits and disposable writable output.

## Timeline example

A timeline is a JSON object with version 1 and a scenes array. Each scene includes scene_id, image, duration_seconds and optionally visual_prompt, narration and on_screen_text. Example:
- scene_id: moonlit-castle
- image: scenes/scene-01.png
- duration_seconds: 42
- visual_prompt: original moonlit castle above a misty pine forest
- narration: the opening narration for this shot
- on_screen_text: a short, mobile-legible phrase

## QA and packaging

Landscape masters must pass encoded-stream inspection, frame-rate validation, subtitle validation, black-frame inspection, audio loudness/peak checks and checksum validation. Still-image motion analysis is marked for human review rather than treating all intended holds as freezes; this does not waive black-frame, audio, caption or human continuity review. Narration sync, scene transitions, character consistency and emotional pacing still require human listening/viewing review.

Long-form metadata package generation accepts only a passing 1920×1080 16:9 master between 1,800 and 2,700 seconds (30–45 minutes), includes a thumbnail requirement and keeps upload/publication disabled. Shorts/TikTok packages remain a separate vertical profile; the long-form file must not be mislabeled as a vertical master.

## Explicit limitations

This renderer does not write the story, create the illustrations, synthesize narration, generate music or provision persistent cloud storage. Those are separate production integrations. An Opuscar or FFmpeg MP4 created in CI proves the renderer, not a complete live Creator Studio. A live deployment also needs a secure job queue/worker connection, durable artifact store, provider licensing/cost verification, project asset upload/retrieval and end-to-end playback/download checks.
