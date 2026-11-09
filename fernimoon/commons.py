"""License-aware Wikimedia Commons media lookup: real footage/images before illustration.

Wikimedia metadata is user-supplied; returned records are candidate historical
media, never independently authenticated archival evidence. No API key needed.
"""
import html
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, urlencode

from .config import PipelineError
from .http import request_json
from .relevance import target_location, visual_relevance

API = "https://commons.wikimedia.org/w/api.php"
MAX_ASSET_BYTES = 45 * 1024 * 1024
REAL_MIMES = {
    "image/jpeg": ("image", ".jpg"), "image/png": ("image", ".png"),
    "video/webm": ("video", ".webm"), "video/ogg": ("video", ".ogv"),
    "video/mp4": ("video", ".mp4"),
}
SOUND_MIMES = {
    "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/wav": ".wav",
    "audio/x-wav": ".wav", "audio/flac": ".flac",
}
ART_WORDS = re.compile(r"\b(drawing|illustration|painting|lithograph|engraving|"
                       r"diagram|cartoon|sketch|poster|artwork|digital art|"
                       r"artist impression|reconstruction)\b", re.I)
AI_WORDS = re.compile(r"\b(ai generated|generative ai|stable diffusion|midjourney|"
                      r"dall.e|synthetic image)\b", re.I)
LICENSES = {"cc0", "cc0 1.0", "public domain", "pd", "pd-us", "pd-old", "pd-usgov"}


def plain(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())[:500]


def metadata(item: dict, key: str) -> str:
    raw = item.get("extmetadata", {}).get(key, {})
    return plain(raw.get("value", "")) if isinstance(raw, dict) else ""


def allowed_license(info: dict) -> str | None:
    raw = metadata(info, "LicenseShortName").lower().strip()
    if raw in LICENSES or raw.startswith("public domain") or raw.startswith("cc0 "):
        return metadata(info, "LicenseShortName")
    return None


def search_commons(query: str, *, limit: int = 15) -> list[dict]:
    if not isinstance(query, str) or not 2 <= len(query) <= 100:
        return []
    params = {
        "action": "query", "format": "json", "formatversion": 2,
        "generator": "search", "gsrsearch": query, "gsrnamespace": 6,
        "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1280,
        "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|ImageDescription|DateTimeOriginal"
    }
    result = request_json(API + "?" + urlencode(params), service="Wikimedia Commons", retries=1)
    pages = result.get("query", {}).get("pages", [])
    return pages if isinstance(pages, list) else []


def pick_media(pages: list[dict], query: str, *, kind: str, context: str = "",
               used_titles: set[str] | None = None,
               required_phrases: tuple[str, ...] | list[str] | None = None) -> dict | None:
    used_titles = used_titles or set()
    location = target_location(context) if context else None
    ranked = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        title = page.get("title", "")
        if not isinstance(title, str) or title in used_titles:
            continue
        info_list = page.get("imageinfo", [])
        if not isinstance(info_list, list) or not info_list or not isinstance(info_list[0], dict):
            continue
        info = info_list[0]
        license_name = allowed_license(info)
        if not license_name:
            continue
        mime = info.get("mime", "")
        # Historical .ogv files are routinely served as application/ogg,
        # not video/ogg (e.g. the public-domain 1940 Tacoma bridge film).
        if mime in ("application/ogg", "application/x-ogg") and title.casefold().endswith(".ogv"):
            mime = "video/ogg"
        if kind == "sound":
            if mime not in SOUND_MIMES or info.get("size", MAX_ASSET_BYTES + 1) > MAX_ASSET_BYTES:
                continue
        elif mime not in REAL_MIMES:
            continue
        elif mime.startswith("video/"):
            # Old archival film is often 640x480 or 320x240; upscale in
            # FFmpeg instead of replacing it with an unrelated HD stock clip.
            if info.get("size", MAX_ASSET_BYTES + 1) > MAX_ASSET_BYTES or min(
                    info.get("width", 0), info.get("height", 0)) < 240:
                continue
        elif min(info.get("width", 0), info.get("height", 0)) < 540:
            continue
        description = metadata(info, "ImageDescription")
        description_for_matching = (title.removeprefix("File:") + " " + description)[:700]
        if AI_WORDS.search(description_for_matching):
            continue
        is_art = bool(ART_WORDS.search(description_for_matching))
        if kind == "illustration" and not is_art:
            continue
        if kind in ("real", "sound") and is_art:
            continue
        if kind == "sound":
            requested = set(re.findall(r"[a-z]{4,}", query.lower())) - {"sound", "audio", "effect", "recording"}
            found = set(re.findall(r"[a-z]{4,}", description_for_matching.lower()))
            if not requested & found:
                continue
            score = len(requested & found) * 10
        else:
            accepted, score, _ = visual_relevance(
                query, description_for_matching, location=location,
                required_phrases=required_phrases,
            )
            if not accepted:
                continue
        if kind == "illustration" and mime.startswith("video/"):
            continue
        url = info.get("thumburl") if mime.startswith("image/") else info.get("url")
        if not url:
            url = info.get("url")
        try:
            validate_media_url(url)
        except PipelineError:
            continue
        target_type, extension = REAL_MIMES.get(mime, ("sound", SOUND_MIMES.get(mime, "")))
        ranked.append((score, {
            "kind": "illustration" if kind == "illustration" else target_type,
            "extension": extension, "url": url, "title": title,
            "source": "Wikimedia Commons", "page_url": info.get("descriptionurl", ""),
            "creator": metadata(info, "Artist"), "license": license_name,
            "license_url": metadata(info, "LicenseUrl"),
            "source_date": metadata(info, "DateTimeOriginal"),
            "source_description": description[:300],
            "authenticity": ("illustration_not_documentary" if kind == "illustration"
                             else "candidate_original_media_not_independently_verified"),
            "visual_review": "Keyword and location metadata match; manual verification required"
        }))
    return max(ranked, key=lambda x: x[0])[1] if ranked else None


def validate_media_url(url: str):
    try:
        u = urlparse(url)
        valid = isinstance(url, str) and u.scheme == "https" and u.hostname == "upload.wikimedia.org" \
            and not u.username and not u.password and u.port in (None, 443) \
            and u.path.startswith("/wikipedia/commons/")
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise PipelineError("Commons: media URL outside approved Wikimedia uploads host.")


class MediaRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_media_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_media(url: str, path: Path):
    validate_media_url(url)
    opener = urllib.request.build_opener(MediaRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "FERNIMOON-STUDIO/2.0 (video research)", 
                                                   "Accept": "image/*,video/*,audio/*"})
    partial = path.with_suffix(path.suffix + ".part")
    try:
        with opener.open(request, timeout=30) as response:
            validate_media_url(response.geturl())
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > MAX_ASSET_BYTES:
                raise PipelineError("Commons: candidate media exceeds 45 MiB.")
            total = 0
            with partial.open("wb") as dest:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_ASSET_BYTES:
                        raise PipelineError("Commons: candidate media exceeds 45 MiB.")
                    dest.write(chunk)
            if total < 512:
                raise PipelineError("Commons: media too small or empty.")
        partial.replace(path)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise PipelineError("Commons: media unavailable or timed out.") from None
    except OSError:
        raise PipelineError("Commons: could not write downloaded media.") from None
    finally:
        partial.unlink(missing_ok=True)


def find_and_download(queries: list[str], kind: str, work: Path, index: int,
                      used_titles: set[str], context: str = "",
                      required_phrases: tuple[str, ...] | list[str] | None = None) -> dict | None:
    for query in queries[:2]:
        try:
            pages = search_commons(query)
        except PipelineError:
            continue
        for _ in range(3):
            asset = pick_media(
                pages, query, kind=kind, context=context, used_titles=used_titles,
                required_phrases=required_phrases,
            )
            if asset is None:
                break
            used_titles.add(asset["title"])
            filename = (f"sound-{index:02d}" if kind == "sound" else f"footage-{index:02d}") + asset["extension"]
            try:
                download_media(asset["url"], work / filename)
            except PipelineError:
                continue
            asset["file"] = filename
            asset["search_query"] = query
            asset["scene"] = index + 1
            return asset
    return None
