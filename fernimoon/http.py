"""Bounded HTTPS requests; raw HTTP exceptions can contain keys, so never log them."""
import http.client
import json
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from .config import PipelineError

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024
VIDEO_TIMEOUT = 30
MAX_RETRY_DELAY = 30


class VideoDownloadError(PipelineError):
    """Safe CDN diagnostics only; never store URLs, response bodies or raw exceptions."""

    def __init__(self, reason: str, host: str, attempts: int, *, status: int | None = None):
        self.status = status
        # These statuses can also mean removed/restricted content, not just expiration.
        self.refresh_url = status in (401, 403, 404, 410)
        super().__init__(f"Pixabay: footage download failed ({reason}; CDN {host}; attempts {attempts}).")


def retry_delay(header: str | None, attempt: int) -> float:
    """Respect Retry-After (seconds or HTTP date), bounded to keep Actions responsive."""
    fallback = 2 ** (attempt + 1)
    try:
        if not isinstance(header, str):
            return min(fallback, MAX_RETRY_DELAY)
        if header.strip().isdigit():
            seconds = int(header.strip())
        else:
            seconds = parsedate_to_datetime(header).timestamp() - time.time()
        return max(0, min(seconds, MAX_RETRY_DELAY))
    except (ValueError, TypeError, OverflowError):
        return min(fallback, MAX_RETRY_DELAY)


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
    try:
        parsed = urlparse(url)
        valid = (isinstance(url, str) and parsed.scheme == "https"
                 and parsed.hostname in ("cdn.pixabay.com", "videos.pixabay.com")
                 and not parsed.username and not parsed.password and parsed.port in (None, 443)
                 and parsed.path.lower().endswith(".mp4"))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise PipelineError("Pixabay: refused a video URL outside the approved MP4 CDN.")


class VideoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_video_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_video(url: str, destination: Path, *, retries: int = 2) -> None:
    """Restart transient downloads from byte zero; publish the file only on success.

    Source-policy and local filesystem failures remain fatal. Clip-specific CDN
    failures use VideoDownloadError so the caller can safely choose another film.
    """
    validate_video_url(url)
    host = urlparse(url).hostname  # Validated allowlist, never the path/query string.
    partial = destination.with_suffix(".part")
    opener = urllib.request.build_opener(VideoRedirectHandler())
    request = urllib.request.Request(url, headers={
        "User-Agent": "FERNIMOON-STUDIO/1.0", "Accept": "video/mp4,application/octet-stream;q=0.9",
    })
    for attempt in range(retries + 1):
        retryable = False
        status = None
        wait = retry_delay(None, attempt)
        try:
            with opener.open(request, timeout=VIDEO_TIMEOUT) as response:
                validate_video_url(response.geturl())
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type and content_type not in ("video/mp4", "application/octet-stream", "binary/octet-stream"):
                    raise VideoDownloadError("unexpected content type", host, attempt + 1)
                raw_length = response.headers.get("Content-Length", "")
                expected = int(raw_length) if raw_length.isdigit() else None
                if expected is not None and expected > MAX_VIDEO_BYTES:
                    raise VideoDownloadError("footage exceeds 150 MiB", host, attempt + 1)
                with partial.open("wb") as output:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_VIDEO_BYTES:
                            raise VideoDownloadError("footage exceeds 150 MiB", host, attempt + 1)
                        output.write(chunk)
                if total == 0 or (expected is not None and total != expected):
                    # A short read may return EOF without raising IncompleteRead.
                    raise http.client.IncompleteRead(b"")
            partial.replace(destination)
            return
        except urllib.error.HTTPError as exc:
            status = exc.code
            reason = f"HTTP {status}"
            retryable = status in (408, 429) or 500 <= status < 600
            wait = retry_delay(exc.headers.get("Retry-After") if exc.headers else None, attempt)
            exc.close()
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
            reason = "connection/timeout or incomplete response"
            retryable = True
        except OSError:
            # Disk errors must not exhaust the whole candidate list or conceal a full disk.
            raise PipelineError("Pixabay: local footage file could not be written.") from None
        finally:
            partial.unlink(missing_ok=True)
        if not retryable or attempt == retries:
            raise VideoDownloadError(reason, host, attempt + 1, status=status) from None
        print(f"Pixabay CDN {host}: {reason}; attempt {attempt + 1}/{retries + 1}; retrying in {wait:g}s.", flush=True)
        time.sleep(wait)
