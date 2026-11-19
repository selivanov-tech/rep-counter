from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.exercises import EXERCISES
from app.ingest import IngestError, cleanup, download, new_workdir, save_upload
from app.llm.factory import build_llm
from app.llm.port import LlmPort
from app.service import count_video
from app.settings import Settings, get_settings

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.llm = build_llm(get_settings())
    yield


app = FastAPI(title="Rep Counter", lifespan=lifespan)


def get_llm(request: Request) -> LlmPort:
    return request.app.state.llm


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict:
    return {"status": "ok", "llm_provider": settings.llm_provider}


@app.get("/api/exercises")
def exercises() -> list[dict]:
    return [{"name": e.name, "title": e.title} for e in EXERCISES.values()]


# Sync `def`: FastAPI runs it in a threadpool, so CPU-heavy pose work
# does not block the event loop.
@app.post("/api/count")
def count(
    settings: Annotated[Settings, Depends(get_settings)],
    exercise: Annotated[str, Form()] = "squat",
    url: Annotated[str | None, Form()] = None,
    file: UploadFile | None = None,
) -> dict:
    ex = EXERCISES.get(exercise)
    if ex is None:
        raise HTTPException(422, f"unknown exercise: {exercise}")
    has_file = file is not None and bool(file.filename)
    if has_file == bool(url and url.strip()):
        raise HTTPException(422, "provide exactly one of: file, url")

    workdir = new_workdir()
    try:
        dest = workdir / "input"
        if has_file:
            save_upload(file.file, dest, settings.max_upload_bytes)
        else:
            download(url.strip(), dest, settings.max_upload_bytes,
                     settings.download_timeout_s)
        return count_video(dest, ex, settings)
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        cleanup(workdir)
