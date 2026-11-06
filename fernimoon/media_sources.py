"""Prefer Commons historical video/photos, then relevant real stock, then illustrations."""
from pathlib import Path

from .commons import find_and_download
from .config import Config, PipelineError
from .footage import collect_footage


def collect_priority_media(scenes: list[dict], config: Config, work: Path,
                           cache: Path, context: str) -> list[dict]:
    used_commons: set[str] = set()
    used_pixabay: set[int] = set()
    results = []
    for index, scene in enumerate(scenes):
        archival_queries = scene.get("archive_queries") or scene["search_terms"]
        media = find_and_download(archival_queries, "real", work, index,
                                  used_commons, context if config.story_style == "history" else "")
        if media:
            media["priority_tier"] = 1
        if media is None:
            try:
                stock = collect_footage(
                    [scene], config.pixabay_key, work, cache, require_relevance=True,
                    historical_context=context if config.story_style == "history" else "",
                    used_ids=used_pixabay, scene_offset=index)
                media = stock[0]
                media["priority_tier"] = 2
            except PipelineError as exc:
                # Provider outages, licence/URL policy failures and write errors are NOT
                # evidence that real footage is unavailable; fail rather than misleading.
                if "no suitable real-film candidate" not in str(exc) and \
                        "no context-relevant historical stock clip" not in str(exc):
                    raise
        if media is None:
            art_queries = [(q + " historical illustration")[:100] for q in archival_queries[:2]]
            media = find_and_download(art_queries, "illustration", work, index,
                                      used_commons, context if config.story_style == "history" else "")
            if media:
                media["priority_tier"] = 3
        if media is None:
            raise PipelineError(
                f"No licensed, context-matching real video/photo or illustration for scene {index + 1}. "
                "Try a better documented topic or provide media with verified reuse rights.")
        results.append(media)
        print(f"Media {index + 1}/{len(scenes)}: {media['source']} ({media['kind']}, priority {media['priority_tier']}).", flush=True)
    return results
