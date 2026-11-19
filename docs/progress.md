# Progress & Handover

Read this first when continuing in a new session. The full design is in [spec.md](spec.md).

## Goal
A FastAPI web app that counts exercise reps (squats first) in a video. The user either uploads a file or gives a URL. The counter is pose estimation plus an angle state machine. The app also has a pluggable LLM port (`.env` switches between `offline` and the local `claude` CLI) for future features.

The owner is Sergey: a backend dev who is learning Go, Postgres, DDD and K8s and knows PHP well. He prefers simple v1s and no over-engineering.

## Status: v1 implemented, tests green

| Area | State |
|---|---|
| Counter (`app/counter.py`) | Done. Median smoothing plus a hysteresis FSM that waits for the first UP, then a **stance check** (`check_stance`) at the bottom of each rep. Unit-tested on synthetic signals. |
| Pose (`app/pose.py`) | Done. MediaPipe Tasks `PoseLandmarker` in VIDEO mode, **3D world landmarks**, visibility ≥ 0.5, mean or min of the left/right sides. |
| Exercises (`app/exercises.py`) | squat (**verified**), lunge (**checked on one video**, see below), pushup (**thresholds unverified**). |
| Ingest (`app/ingest.py`) | Done. Upload with a size cap; URL download with an SSRF guard that re-checks every redirect hop, a size cap and a timeout; ffprobe validation. |
| API (`app/main.py`) | Done. `POST /api/count` (sync `def`, so it runs in a threadpool), `GET /api/exercises`, `GET /api/health`, `GET /`. |
| Frontend (`app/static/index.html`) | Done. Upload/URL tabs, exercise dropdown, count, a clickable rep list that seeks the video. Checked in headless Chromium. |
| LLM port (`app/llm/`) | Done. `LlmPort`, `OfflineLlm` (default), `ClaudeCliLlm`, `build_llm` factory, wired via lifespan and `get_llm`. **Not used by any feature yet** (by decision). |
| Tests | 39 passing (`make test`): counter + stance check, LLM with a fake CLI script, API end to end on `tests/data/squat_1.mp4` and `tests/data/lunge_1.mp4`: the right exercise counts 1, the wrong one counts 0 with 1 `rejected`. |
| Docker | **Built and checked** on 2026-11-19 (macOS, Docker 29.5, arm64 image, 1.64 GB). In the container: `/api/health` ok, `/` 200, `POST /api/count` on `squat_1.mp4` → count = 1, ~2.4 s. The URL path also works in the container: the sample URL below → count = 1, ~2.6 s. The sample URL is byte-identical to `tests/data/squat_1.mp4` (same sha256), so it is **not** a second test video. No changes to the Dockerfile were needed. Not built for amd64 yet. |

Verified manually: the sample URL
`https://cdn.kinestex.com/uploads%2F2047b732-0206-4bb9-9e15-e92fddaabefb_jz73VFlUyZ9nyd64OjRb.mp4`
→ `count: 1`, rep at 1.13 s → bottom 1.47 s → 2.2 s, min knee angle 66°, ~2 s of processing.

Lunge check (2026-11-19): `tests/data/lunge_1.mp4` = `https://cdn.kinestex.com/uploads/Lunges_Aygul.mp4` (6.5 s, 1228×1920, side view, alternating legs). It is a **looped demo clip**: it starts at the bottom of a rep (end half), has one full lunge (~2.3 → 3.2 bottom → 4.2 s, min knee angle 66°), and ends at the bottom of the next rep (start half). Ground truth checked frame by frame = 1 full rep; the counter gives 1. Notes from the angle signal (`combine=min`):
- standing reads ~172–175°, the bottom ~66°; DOWN=105 has a big margin;
- the walking step before and after each lunge dips the signal to ~145–148°, right at UP=145. This is harmless now (the FSM is already UP there), but a higher UP threshold (≥150) would make the step look like the end of a rep; keep UP ≤ 145 for lunges;
- the rep ends at 4.2 s on a 146° value, just above UP=145; the clear stand (~166°) comes at 4.4 s;
- before the stance check, the squat config also gave 1 on this clip (and the lunge config gave 1 on `squat_1.mp4`): the knee angle is ~66–70° at the bottom in both. Fixed on 2026-11-19, see below.

Stance check (2026-11-19, bug: "lunge video counts as squat"): at the bottom of each rep we take the **hip asymmetry** |hip angle L − hip angle R| (shoulder–hip–knee, 3D, both sides, no visibility filter), median over ±2 samples. Squat needs < 30°, lunge ≥ 30°, push-up has no check (`Exercise.stance`, `STANCE_SPLIT_DEG` in `app/exercises.py`). Measured: `squat_1` 7°, `lunge_1` ~57°. A failed rep is not counted and goes to `rejected` with a `reason`; the UI shows it under the video. Per-frame values are in `debug.angles[].h`. Risk: the 30° cut is based on two videos only; a side-view squat and a wide (sumo) squat still need checking.

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
- `make docker-run` uses `--env-file .env`, so it fails if `.env` does not exist. Copy `.env.example` first, or run `docker run --rm -p 8000:8000 rep-counter`.
- Tests also pass on macOS (Apple Silicon) with Homebrew ffmpeg; the Linux EGL/GL libs are only needed in Linux/Docker.

## Next steps (suggested, not committed)
1. ~~Build and run the Docker image~~ — done 2026-11-19, works as is.
2. Collect 3–5 more videos (also to re-check the 30° stance cut) (side view, several reps, push-ups, lunges); add them as tests and tune the thresholds. Done so far: one lunge video (above). Still needed: push-ups (no video at all), a squat with several reps, a side-view squat, a lunge clip with several reps. Candidate open videos on Wikimedia Commons (CC BY / CC BY-SA / public domain) were listed on 2026-11-19 but **not downloaded**: e.g. "Squat - exercise demonstration video.webm", "Kettlebell crush grip push-up.webm", "Interval Push-ups.webm", "Strength Training Circuit- Forward Lunge.webm". CC BY/BY-SA files need an attribution file (`tests/data/SOURCES.md`) if committed.
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
make up        # build + run in Docker in background, UI at http://localhost:8011 (PORT=… to change)
make logs      # follow container logs
make down      # stop and remove the container
```
For `LLM_PROVIDER=claude_cli`, copy `.env.example` to `.env` and set the provider. The `claude` CLI must be on PATH and logged in.

## Handover prompt for a new session
> Continue work on `rep-counter`. Read `docs/progress.md` and `docs/spec.md` first, then run `make setup && make test`. Next task: <pick from "Next steps">.
