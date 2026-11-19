# Rep Counter — Spec (v0.3, matches the implementation)

## 1. Goal
A small web app: the user uploads a video, or gives a URL to one. The backend counts the squats (later, other reps) and returns the count with a per-rep timeline.

## 2. How I counted manually → algorithm
What I did by hand:
1. Download the video and read its duration (ffprobe).
2. Sample frames at a fixed rate (8 fps) and look at the body pose in each frame.
3. Classify each frame as **UP** (standing) or **DOWN** (bottom of squat).
4. Count each full **UP → DOWN → UP** cycle as one rep.

The automated version of this:

```
frames      = sample(video, fps=10–15)
for each frame:
    kp      = pose_estimator(frame)          # MediaPipe Pose: 33 landmarks
    if kp.visibility(hip,knee,ankle) < 0.5:  skip
    angle   = mean(knee_angle(L), knee_angle(R))   # hip-knee-ankle, degrees, 3D world landmarks
signal      = median_filter(angles, window=5)       # remove jitter

state = None; reps = []                         # wait for the first UP: no half reps
for t, a in signal:
    if state == UP   and a < DOWN_THRESHOLD (≈110°):  state = DOWN; start = t
    if state == DOWN and a > UP_THRESHOLD   (≈145°):  state = UP;   reps.append((start, t))
filter out reps shorter than MIN_REP_DURATION (≈0.4 s)
return len(reps), reps
```

Key points:
- **3D angles.** Use MediaPipe *world* landmarks (3D, in metres), not 2D image coordinates. On the sample video the person faces the camera: in 2D the knee only reached ~125°, so a squat was never detected. In 3D it goes from ~160° standing down to ~65°. In 3D a straight leg reads ~160°, not 180°, which is why UP is 145°.
- **Hysteresis.** Two separate thresholds keep noise around a single cut-off from creating fake reps.
- **Stance check.** The knee angle alone cannot tell a squat from a lunge: both reach ~66–70° at the bottom. So at the bottom of each rep we also look at the **hip asymmetry** = |hip angle L − hip angle R|, where the hip angle is shoulder–hip–knee in 3D. In a squat both hips flex together (asymmetry ~5°); in a lunge the front hip flexes and the back hip stays open (~60–75°). Measured on `squat_1.mp4` and `lunge_1.mp4`. An exercise declares `stance`: `symmetric` (squat) needs asymmetry < 30°, `split` (lunge) needs ≥ 30°, `None` (push-up) skips the check. The value is the median over ±2 samples around the bottom. Both sides are always used, with no visibility filter: in a side view the far leg is hidden, and the 3D model still gives a usable estimate for it. A rep that fails the check is not counted; it goes to `rejected` with a reason, so the UI can say "1 movement looked like a lunge, not a squat".
- *(Not implemented yet)* **Fallback signal.** If the knees are hidden, use hip height normalised by torso length.
- *(Not implemented yet)* **Shallow squats.** Optionally calibrate the thresholds per video from the min and max of the signal: DOWN = min + 30% of range, UP = max − 20% of range.

## 3. Architecture
```
Browser (HTML + JS, served by FastAPI)
   │  POST /api/count  (multipart form: file OR url, + exercise)
   ▼
FastAPI handler (synchronous, single request):
   download/validate → pose → counter → JSON result
```

### API
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/count` | multipart form: `exercise` (default `squat`) + exactly one of `file` / `url` | result (below); 400 bad video/URL; 422 bad input |
| GET | `/api/exercises` | – | `[{name, title}]` |
| GET | `/api/health` | – | `{status, llm_provider}` |
| GET | `/` | – | frontend page |

Result:
```json
{ "exercise": "squat", "count": 1, "duration_s": 3.07,
  "reps": [{"start_s": 1.13, "bottom_s": 1.47, "end_s": 2.2, "min_angle": 66.3, "hip_asym": 4.0}],
  "rejected": [],   // same shape as reps + "reason", e.g. "stance looks split (lunge-like), squat expected"
  "debug": {"fps_sampled": 15.0, "frames_sampled": 46, "frames_with_pose": 46,
            "thresholds": {"down": 110, "up": 145, "stance": "symmetric", "split_deg": 30},
            "angles": [{"t": 0.0, "a": 160.9, "h": 3.1}, ...]} }
```

### Validation and safety
- Size limit: 100 MB. Duration limit: 5 min. Allowed types: mp4/mov/webm, checked with ffprobe rather than the file extension.
- URL downloads: only http and https. Block private and loopback IPs to prevent SSRF. Stream the download with a size cap and a timeout.
- Delete temp files after the request (in `finally`).
- Run the CPU-heavy work in a threadpool (`def` endpoint or `run_in_threadpool`) so the event loop isn't blocked.

### Frontend
One page with two tabs, **Upload file** and **From URL**. Plain HTML/JS, no build step, in `app/static/index.html`. Submitting shows a "Counting…" state until the response arrives, then the page shows the big count number, a list of reps with timestamps, and a video player that seeks to a rep when you click it.

## 4. Stack
Python 3.14 (uv), FastAPI, uvicorn, `mediapipe` 1.2.x (Tasks API, `PoseLandmarker` + the `pose_landmarker_full.task` model file), `opencv-python-headless`, `numpy`, `httpx`, `pydantic-settings`, ffmpeg (ffprobe). System libs that mediapipe needs: `libegl1 libgles2 libgl1`. Ships with a Dockerfile. Tests use pytest with the sample video (expected count = 1) plus synthetic angle-signal tests for the counter.

## 5. Out of scope for MVP
Auth, persistence in a DB, multiple people in a frame, real-time webcam.

## 6. Decisions
- **Engine:** pose estimation (MediaPipe) with an angle state machine. No LLM calls.
- **Exercises:** pluggable. Each exercise is a config entry, for example:
  ```python
  EXERCISES = {
    "squat":  {"joints": ("hip","knee","ankle"),       "down": 110, "up": 145, "min_rep_s": 0.4, "stance": "symmetric"},  # verified
    "pushup": {"joints": ("shoulder","elbow","wrist"), "down": 90,  "up": 145, "min_rep_s": 0.4},                          # unverified
    "lunge":  {"joints": ("hip","knee","ankle"),       "down": 105, "up": 145, "min_rep_s": 0.5, "combine": "min", "stance": "split"},  # one video
  }
  ```
  The counter is generic: config → angle signal → hysteresis FSM. The frontend shows an exercise dropdown fed by `GET /api/exercises`.
- **Deploy:** one Docker container. No queue, workers or job store: the request is processed synchronously and returns the result. With the 5 min / 100 MB limits, processing takes seconds to tens of seconds, which is fine for v1.

## 7. LLM port
This follows the BrainPort pattern from `aria-english-coach`: a Protocol port, adapters behind it, a factory that picks one from `Settings`, and typed errors. The first iteration is deliberately thin.

```python
# llm/port.py
@dataclass(frozen=True)
class LlmMessage:  role: Literal["system", "user", "assistant"]; content: str
@dataclass(frozen=True)
class LlmUsage:    tokens_in: int | None; tokens_out: int | None; latency_ms: int; cost_usd: float | None = None
@dataclass(frozen=True)
class LlmResult:   text: str; usage: LlmUsage

class LlmError(Exception):          # timeout, non-zero exit, unparsable output
    def __init__(self, msg, *, status: int | None = None, body: str | None = None): ...

class LlmPort(Protocol):
    async def complete(self, messages: list[LlmMessage], *, max_tokens: int = 512,
                       json_mode: bool = False) -> LlmResult: ...
```

Adapters for v1:
- **`OfflineLlm`** is the default. It raises `LlmError("llm disabled")` or returns a stub, so tests and CI need no CLI and no keys.
- **`ClaudeCliLlm`** runs `claude -p --output-format json [--model X]` through `asyncio.create_subprocess_exec`. There's no shell, and the prompt goes in on stdin.
  - All messages are flattened into one prompt; system text is passed via `--append-system-prompt`.
  - Usage is parsed from the CLI's JSON output.
  - A timeout kills the process, and a non-zero exit raises `LlmError` carrying stderr.
  - The binary path and extra args come from settings, so another local CLI can be plugged in the same way.

Composition (`llm/factory.py`):
```python
def build_llm(s: Settings) -> LlmPort:
    match s.llm_provider:
        case "offline":    return OfflineLlm()
        case "claude_cli": return ClaudeCliLlm(bin=s.llm_cli_bin, model=s.llm_model,
                                               timeout_s=s.llm_timeout_s, extra_args=s.llm_cli_args)
```
It's wired once at startup (`app.state.llm`) and handed to handlers through `Depends(get_llm)`, so tests can override it with `app.dependency_overrides`. Later adapters, such as the Anthropic API or an OpenAI-compatible provider, slot into the same `match`. A `FallbackLlm(primary, offline)` wrapper can come later too.

Settings (`settings.py`, `.env`):
```
LLM_PROVIDER=offline        # offline | claude_cli
LLM_MODEL=                  # empty = CLI default
LLM_CLI_BIN=claude
LLM_CLI_ARGS=               # extra flags, space-separated
LLM_TIMEOUT_S=60
```
Docker: the `claude` CLI isn't in the image. `claude_cli` is meant for running locally, not in a container, for v1.

**v1 decision:** the port is built and wired (`app.state.llm`, `get_llm` in `app/main.py`), but no feature uses it yet. Candidate first uses: form feedback from the rep timeline, or a second opinion when pose confidence is low.

## 8. Project layout
```
app/
  main.py          # FastAPI routes + static, lifespan builds the LLM
  service.py       # use case: video -> count result (no HTTP)
  ingest.py        # upload/URL download, SSRF guard, ffprobe validation
  pose.py          # MediaPipe → per-frame 3D joint angle
  counter.py       # angle calc, smoothing, FSM (pure, unit-tested)
  exercises.py     # config registry
  settings.py      # pydantic-settings, reads .env
  llm/
    port.py        # LlmPort protocol + DTOs + LlmError
    cli.py         # ClaudeCliLlm: local `claude -p` subprocess
    offline.py     # OfflineLlm: no-op/deterministic, default for tests/CI
    factory.py     # build_llm(settings) -> LlmPort
  static/index.html
tests/             # test_counter (synthetic), test_llm (fake CLI), test_api (real sample video)
  data/squat_1.mp4 # sample: 1 squat, 3 s
models/            # pose model, downloaded by `make model` (gitignored)
docs/              # spec + progress/handover
Dockerfile, Makefile, .env.example
```
