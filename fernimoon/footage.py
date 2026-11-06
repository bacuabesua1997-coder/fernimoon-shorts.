"""Pixabay film search, 24-hour metadata cache and source attribution."""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode

from .config import PipelineError
from .http import MAX_VIDEO_BYTES, VideoDownloadError, download_video, request_json, validate_video_url

SYNTHETIC = re.compile(r"\b(ai|cgi|animation|animated|render|rendered|3d|illustration|cartoon|synthetic)\b", re.I)
MAX_CANDIDATES_PER_QUERY = 3


def select_footage(hits: list, used: set[int]) -> dict | None:
    candidates = []
    for hit in hits:
        if not isinstance(hit, dict) or hit.get("type") != "film" or not isinstance(hit.get("id"), int):
            continue
        if hit["id"] in used or SYNTHETIC.search(hit.get("tags", "")):
            continue
        if hit.get("isAiGenerated") or hit.get("is_ai_generated") or hit.get("ai_generated"):
            continue
        if not isinstance(hit.get("duration"), (int, float)) or hit["duration"] < 3:
            continue
        variants = hit.get("videos", {})
        if not isinstance(variants, dict):
            continue
        for variant in variants.values():
            if not isinstance(variant, dict):
                continue
            width, height, size = (variant.get(k, 0) for k in ("width", "height", "size"))
            if not all(isinstance(v, (int, float)) for v in (width, height, size)):
                continue
            if min(width, height) < 720 or not 0 < size <= MAX_VIDEO_BYTES:
                continue
            try:
                validate_video_url(variant.get("url", ""))
            except (PipelineError, ValueError, TypeError):
                continue
            # Prefer portrait clips and enough resolution; avoid needlessly downloading 4K.
            score = abs(width / height - 9 / 16) * 10 + abs(height - 1920) / 1920
            candidates.append((score, hit, variant))
    if not candidates:
        return None
    _, hit, variant = min(candidates, key=lambda item: item[0])
    return {"id": hit["id"], "page_url": hit.get("pageURL", ""), "creator": hit.get("user", ""),
            "tags": hit.get("tags", ""), "url": variant["url"], "width": variant["width"],
            "height": variant["height"], "duration": hit["duration"], "type": "film"}


def search(query: str, api_key: str, cache: Path, *, force_refresh: bool = False) -> list:
    params = {"q": query, "video_type": "film", "safesearch": "true", "order": "relevant", "per_page": 50}
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (digest + ".json")
    if force_refresh:
        # A CDN URL can expire before the metadata cache's 24-hour TTL.
        # Invalidate first, so a failed refresh cannot leave a known-stale cache behind.
        path.unlink(missing_ok=True)
    if path.exists() and 0 <= time.time() - path.stat().st_mtime < 86400:
        try:
            hits = json.loads(path.read_text())["hits"]
            if isinstance(hits, list):
                return hits
        except (OSError, KeyError, ValueError, TypeError):
            pass
    data = request_json("https://pixabay.com/api/videos/?" + urlencode({"key": api_key, **params}), service="Pixabay")
    if not isinstance(data.get("hits"), list):
        raise PipelineError("Pixabay: malformed video search response.")
    path.write_text(json.dumps({"hits": data["hits"]}), encoding="utf-8")
    return data["hits"]


def collect_footage(scenes: list[dict], api_key: str, work: Path, cache: Path) -> list[dict]:
    used: set[int] = set()
    failed: set[int] = set()
    refreshed: set[str] = set()
    sources = []
    for index, scene in enumerate(scenes):
        chosen = None
        last_error = None
        filename = f"footage-{index:02d}.mp4"
        for query in scene["search_terms"]:
            hits = search(query, api_key, cache)
            for _ in range(MAX_CANDIDATES_PER_QUERY):
                candidate = select_footage(hits, used | failed)
                if not candidate:
                    break
                try:
                    download_video(candidate["url"], work / filename)
                    chosen = candidate
                except VideoDownloadError as exc:
                    last_error = exc
                    print(f"Scene {index + 1}, Pixabay clip {candidate['id']}: {exc}", flush=True)
                    if exc.refresh_url and query not in refreshed:
                        refreshed.add(query)
                        print(f"Scene {index + 1}: refreshing Pixabay URLs once; the clip may be expired or unavailable.", flush=True)
                        try:
                            hits = search(query, api_key, cache, force_refresh=True)
                        except PipelineError:
                            print("Pixabay URL refresh failed; trying other existing film candidates.", flush=True)
                        else:
                            # Same ID is allowed once more only if the API supplies a different,
                            # fully revalidated film URL. Otherwise switch to another clip.
                            fresh = select_footage([h for h in hits if isinstance(h, dict) and h.get("id") == candidate["id"]], used | failed)
                            if fresh and fresh["url"] != candidate["url"]:
                                try:
                                    download_video(fresh["url"], work / filename)
                                    chosen = fresh
                                except VideoDownloadError as refreshed_error:
                                    last_error = refreshed_error
                                    print(f"Scene {index + 1}, refreshed Pixabay clip {candidate['id']}: {refreshed_error}", flush=True)
                    if chosen is None:
                        failed.add(candidate["id"])
                        print(f"Scene {index + 1}: selecting another Pixabay film clip.", flush=True)
                if chosen:
                    chosen["search_query"] = query
                    break
            if chosen:
                break
        if not chosen:
            if last_error is not None:
                raise PipelineError(f"Pixabay: no downloadable real-film candidate for scene {index + 1} after bounded attempts. "
                                    f"Last CDN error: {last_error}") from None
            raise PipelineError(f"Pixabay: no suitable real-film candidate for scene {index + 1}. Try a more filmable topic.")
        used.add(chosen["id"])
        sources.append({**chosen, "scene": index + 1, "file": filename,
                        "license_url": "https://pixabay.com/service/license-summary/"})
        print(f"Footage {index + 1}/{len(scenes)} downloaded.", flush=True)
    return sources
