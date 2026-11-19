# Progress & Handover

Read this first when continuing in a new session. The full design is in [spec.md](spec.md).

## Goal
A FastAPI web app that counts exercise reps (squats first) in a video. The user either uploads a file or gives a URL. The counter is pose estimation plus an angle state machine. The app also has a pluggable LLM port (`.env` switches between `offline` and the local `claude` CLI) for future features.

The owner is Sergey: a backend dev who is learning Go, Postgres, DDD and K8s and knows PHP well. He prefers simple v1s and no over-engineering.

## Status: v1 implemented, tests green

| Area | State |
|---|---|
| Counter (`app/counter.py`) | Done. Median smoothing plus a hysteresis FSM that waits for the first UP. Unit-tested on synthetic signals. |
| Pose (`app/pose.py`) | Done. MediaPipe Tasks `PoseLandmarker` in VIDEO mode, **3D world landmarks**, visibility ≥ 0.5, mean or min of the left/right sides. |
| Exercises (`app/exercises.py`) | squat (**verified**), pushup and lunge (**thresholds unverified**). |
| Ingest (`app/ingest.py`) | Done. Upload with a size cap; URL download with an SSRF guard that re-checks every redirect hop, a size cap and a timeout; ffprobe validation. |
| API (`app/main.py`) | Done. `POST /api/count` (sync `def`, so it runs in a threadpool), `GET /api/exercises`, `GET /api/health`, `GET /`. |
| Frontend (`app/static/index.html`) | Done. Upload/URL tabs, exercise dropdown, count, a clickable rep list that seeks the video. Checked in headless Chromium. |
| LLM port (`app/llm/`) | Done. `LlmPort`, `OfflineLlm` (default), `ClaudeCliLlm`, `build_llm` factory, wired via lifespan and `get_llm`. **Not used by any feature yet** (by decision). |
| Tests | 30 passing (`make test`): counter, LLM with a fake CLI script, API end to end on `tests/data/squat_1.mp4` (count = 1). |
| Docker | `Dockerfile` written but **never built**: the dev container had no Docker daemon. Build it and run it once to check. |

Verified manually: the sample URL
`https://cdn.kinestex.com/uploads%2F2047b732-0206-4bb9-9e15-e92fddaabefb_jz73VFlUyZ9nyd64OjRb.mp4`
→ `count: 1`, rep at 1.13 s → bottom 1.47 s → 2.2 s, min knee angle 66°, ~2 s of processing.

## Key decisions (and why)
1. **Pose estimation, not an LLM, for counting.** Free, local, deterministic.
2. **Synchronous request, no queue or workers.** The owner judged a queue to be over-engineering for v1. The 100 MB / 5 min limits keep requests within tens of seconds.
3. **Pluggable exercises** as config entries (joints plus down/up thresholds plus min rep duration).
4. **3D world landmarks instead of 2D.** In 2D, a front-facing squat on the sample only reached ~125°, so nothing was counted. In 3D the knee goes from ~160° standing to ~65° at the bottom. Because a straight leg reads ~160°, the UP threshold is 145°.
5. **LLM port modelled on `BrainPort`** from `selivanov-tech/aria-english-coach` (`apps/api/app/contexts/learning/{application/ports/brain.py, infrastructure/brain/factory.py}`). It's a Protocol, adapters, a factory driven by settings, and an error type carrying status and body.
6. **Python 3.14.** mediapipe 1.2.3 installs and runs on it. mediapipe 1.x has no `mp.solutions`; only the Tasks API plus a `.task` model file.
7. **One form endpoint** for both upload and URL (multipart form fields), instead of separate JSON and multipart bodies.

## Gotchas
- mediapipe needs `libegl1 libgles2 libgl1` at import time; it fails with `OSError: libEGL...` without them.
- Model file: `make model` downloads `models/pose_landmarker_full.task` (~9 MB, gitignored).
- `PoseLandmarker` in VIDEO mode needs increasing timestamps, so one instance is created per request (it isn't shared across threads).
- `ClaudeCliLlm` ignores `max_tokens` because the CLI has no flag for it.

## Next steps (suggested, not committed)
1. Build and run the Docker image; fix whatever breaks.
2. Collect 3–5 more videos (side view, several reps, push-ups, lunges); add them as tests and tune the thresholds.
3. Per-video threshold calibration (spec §2), for shallow reps and different camera angles.
4. Fallback signal from hip height when the knees aren't visible.
5. First LLM feature, e.g. short form feedback from `reps` + `debug.angles` via `Depends(get_llm)`.
6. An angle-over-time chart in the UI (the data is already in `debug.angles`).
7. Optionally trim `debug.angles` from the response, or put it behind a `?debug=1` flag.

## How to run
```
make setup     # uv sync + download model
make test
make run       # http://localhost:8000
```
For `LLM_PROVIDER=claude_cli`, copy `.env.example` to `.env` and set the provider. The `claude` CLI must be on PATH and logged in.

## Handover prompt for a new session
> Continue work on `rep-counter`. Read `docs/progress.md` and `docs/spec.md` first, then run `make setup && make test`. Next task: <pick from "Next steps">.
