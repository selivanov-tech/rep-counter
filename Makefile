MODEL_URL = https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task

.PHONY: setup model run test docker-build docker-run

setup: model
	uv sync

model: models/pose_landmarker_full.task

models/pose_landmarker_full.task:
	mkdir -p models && curl -sSfL -o $@ $(MODEL_URL)

run: model
	uv run uvicorn app.main:app --reload --port 8000

test: model
	uv run pytest -q

docker-build:
	docker build -t rep-counter .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env rep-counter
