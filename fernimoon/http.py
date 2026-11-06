"""Bounded HTTPS requests; raw HTTP exceptions can contain keys, so never log them."""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .config import PipelineError

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024


def request_json(url: str, *, service: str, headers: dict | None = None,
                 body: dict | None = None, retries: int = 2) -> dict:
    """Retry only rate limits, server failures and transport errors, with a fixed cap."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": "FERNIMOON-STUDIO/1.0", "Content-Type": "application/json", **(headers or {})
    })
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                raise PipelineError(f"{service}: response exceeded the size limit.")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Expected an object")
            return result
        except urllib.error.HTTPError as exc:
            retry = exc.code == 429 or 500 <= exc.code < 600
            if retry and attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            hint = " Check the API key and provider access." if exc.code in (401, 403) else ""
            if exc.code == 429:
                hint = " Check quota or retry later."
            raise PipelineError(f"{service}: HTTP {exc.code}.{hint}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            raise PipelineError(f"{service}: connection failed or timed out; retry later.") from None
        except (ValueError, UnicodeError):
            raise PipelineError(f"{service}: malformed JSON response.") from None
    raise AssertionError("Unreachable")


def validate_video_url(url: str) -> None:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in ("cdn.pixabay.com", "videos.pixabay.com")
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not parsed.path.lower().endswith(".mp4")):
        raise PipelineError("Pixabay: refused a video URL outside the approved MP4 CDN.")


class VideoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_video_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_video(url: str, destination: Path) -> None:
    validate_video_url(url)
    partial = destination.with_suffix(".part")
    try:
        opener = urllib.request.build_opener(VideoRedirectHandler())
        with opener.open(url, timeout=120) as response, partial.open("wb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise PipelineError("Pixabay: footage download exceeds 150 MiB.")
                output.write(chunk)
        if total == 0:
            raise PipelineError("Pixabay: empty footage download.")
        partial.replace(destination)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise PipelineError("Pixabay: footage download failed; retry later.") from None
    finally:
        partial.unlink(missing_ok=True)
