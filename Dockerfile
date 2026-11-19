FROM python:3.14-slim

# ffmpeg: ffprobe validation; libegl1/libgles2/libgl1: required by mediapipe at import time
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libegl1 libgles2 libgl1 curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.0 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

RUN mkdir -p models && curl -sSfL -o models/pose_landmarker_full.task \
    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task

COPY app ./app
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
