"""Getting a video onto local disk (upload or URL) and validating it with ffprobe."""

import ipaddress
import json
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urljoin, urlparse

import httpx

ALLOWED_FORMATS = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "webm", "matroska"}
MAX_REDIRECTS = 3
CHUNK = 1024 * 1024


class IngestError(ValueError):
    """User-facing problem with the input video (maps to HTTP 4xx)."""


def new_workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="repcount-"))


def cleanup(workdir: Path) -> None:
    shutil.rmtree(workdir, ignore_errors=True)


def save_upload(src: BinaryIO, dest: Path, max_bytes: int) -> Path:
    total = 0
    with dest.open("wb") as out:
        while chunk := src.read(CHUNK):
            total += len(chunk)
            if total > max_bytes:
                raise IngestError(f"file is larger than {max_bytes // (1024 * 1024)} MB")
            out.write(chunk)
    if total == 0:
        raise IngestError("empty file")
    return dest


def check_url_safe(url: str) -> None:
    """Only public http(s) hosts: blocks SSRF to localhost / private networks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise IngestError("only http(s) URLs are allowed")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or None,
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise IngestError(f"cannot resolve host {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise IngestError("URL points to a non-public address")


def download(url: str, dest: Path, max_bytes: int, timeout_s: float) -> Path:
    """Stream the URL to disk with a size cap; every redirect hop is re-checked."""
    with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            check_url_safe(url)
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code != 200:
                    raise IngestError(f"download failed: HTTP {resp.status_code}")
                declared = int(resp.headers.get("content-length") or 0)
                if declared > max_bytes:
                    raise IngestError(f"file is larger than {max_bytes // (1024 * 1024)} MB")
                total = 0
                with dest.open("wb") as out:
                    for chunk in resp.iter_bytes(CHUNK):
                        total += len(chunk)
                        if total > max_bytes:
                            raise IngestError(
                                f"file is larger than {max_bytes // (1024 * 1024)} MB")
                        out.write(chunk)
                return dest
        raise IngestError("too many redirects")


def probe(path: Path, max_duration_s: float) -> float:
    """Validate by content (not extension). Returns the duration in seconds."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=format_name,duration:stream=codec_type", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
        info = json.loads(out)
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise IngestError("not a readable video file") from exc
    fmt = info.get("format", {})
    if not set(fmt.get("format_name", "").split(",")) & ALLOWED_FORMATS:
        raise IngestError("unsupported format (use mp4, mov or webm)")
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise IngestError("file has no video stream")
    duration = float(fmt.get("duration") or 0)
    if duration <= 0:
        raise IngestError("cannot read video duration")
    if duration > max_duration_s:
        raise IngestError(f"video is longer than {int(max_duration_s)} s")
    return duration
