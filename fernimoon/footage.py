"""Pixabay film search, 24-hour metadata cache and source attribution."""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode

from .config import PipelineError
from .http import MAX_VIDEO_BYTES, download_video, request_json, validate_video_url

SYNTHETIC = re.compile(r"\b(ai|cgi|animation|animated|render|rendered|3d|illustration|cartoon|synthetic)\b", re.I)


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


def search(query: str, api_key: str, cache: Path) -> list:
    params = {"q": query, "video_type": "film", "safesearch": "true", "order": "relevant", "per_page": 50}
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (digest + ".json")
    if path.exists() and 0 <= time.time() - path.stat().st_mtime < 86400:
        try:
            return json.loads(path.read_text())["hits"]
        except (OSError, KeyError, ValueError, TypeError):
            pass
    data = request_json("https://pixabay.com/api/videos/?" + urlencode({"key": api_key, **params}), service="Pixabay")
    if not isinstance(data.get("hits"), list):
        raise PipelineError("Pixabay: malformed video search response.")
    path.write_text(json.dumps({"hits": data["hits"]}), encoding="utf-8")
    return data["hits"]


def collect_footage(scenes: list[dict], api_key: str, work: Path, cache: Path) -> list[dict]:
    used: set[int] = set()
    sources = []
    for index, scene in enumerate(scenes):
        chosen = None
        for query in scene["search_terms"]:
            chosen = select_footage(search(query, api_key, cache), used)
            if chosen:
                chosen["search_query"] = query
                break
        if not chosen:
            raise PipelineError(f"Pixabay: no suitable real-film candidate for scene {index + 1}. Try a more filmable topic.")
        filename = f"footage-{index:02d}.mp4"
        download_video(chosen["url"], work / filename)
        used.add(chosen["id"])
        sources.append({**chosen, "scene": index + 1, "file": filename,
                        "license_url": "https://pixabay.com/service/license-summary/"})
        print(f"Footage {index + 1}/{len(scenes)} downloaded.", flush=True)
    return sources
