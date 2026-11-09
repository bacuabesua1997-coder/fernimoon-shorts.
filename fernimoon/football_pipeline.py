"""Football Mode production path: live/global match data → English voiceover → licensed B-roll."""
import json
import tempfile
from pathlib import Path

from .captions import make_ass, make_srt
from .commons import find_and_download
from .config import Config, PipelineError, validate_topic
from .football_entities import resolve_team_entity
from .football_research import build_football_research
from .football_script import generate_football_script
from .footage import collect_footage
from .media import media_duration, preflight, probe, render, verify_output
from .sound import find_sound, retime_with_sound
from .speech import scene_boundaries, synthesize


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")




def collect_football_visuals(scenes: list[dict], api_key: str, work: Path,
                             cache: Path, required_phrases: list[str] | None = None) -> list[dict]:
    """Prefer real CC0/PD Commons media, then identity-matched Pixabay stock."""
    used_commons: set[str] = set()
    used_pixabay: set[int] = set()
    results = []
    for index, scene in enumerate(scenes):
        media = find_and_download(
            scene["search_terms"],
            "real",
            work,
            index,
            used_commons,
            required_phrases=required_phrases,
        )
        if media:
            media["priority_tier"] = 1
        else:
            fallback = collect_footage(
                [scene],
                api_key,
                work,
                cache,
                require_relevance=True,
                used_ids=used_pixabay,
                scene_offset=index,
                required_phrases=required_phrases,
            )
            media = fallback[0]
            media["priority_tier"] = 2
        media["scene"] = index + 1
        results.append(media)
        print(
            f"Football visual {index + 1}/{len(scenes)}: "
            f"{media.get('source')} ({media.get('kind')}, priority {media['priority_tier']}).",
            flush=True,
        )
    return results


def create_football_short(topic: str, config: Config, output: Path,
                          match_date: str | None = None,
                          editorial_format: str | None = None) -> Path:
    if config.mode != "football":
        raise PipelineError("Football pipeline requires FERNIMOON_MODE=football.")
    topic = validate_topic(topic)
    preflight()
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="football-", dir=output)).resolve()

    editorial_format = editorial_format or config.football_format
    print("FOOTBALL MODE: researching publisher news and global match data…", flush=True)
    context = build_football_research(
        config.football_api_key, topic, match_date, editorial_format=editorial_format
    )
    _write_json(work / "football_context.json", context)

    print(f"Writing an evidence-linked English football script ({editorial_format})…", flush=True)
    script = generate_football_script(topic, config, context, editorial_format=editorial_format)
    resolved_entity = resolve_team_entity(topic)
    if resolved_entity:
        canonical, _entity_data = resolved_entity
        print(
            f"Named-club visual lock enabled: {canonical}. "
            "Generic football stock without club/venue identity will be rejected.",
            flush=True,
        )
    _write_json(work / "script.json", script)
    narration = " ".join(scene["narration"] for scene in script["scenes"])

    print("Finding licensed, relevant football stock footage (not match highlights)…", flush=True)
    required_visual_phrases = context.get("visual_entity_phrases") or None
    sources = collect_football_visuals(
        script["scenes"], config.pixabay_key, work, output / "pixabay-cache",
        required_phrases=required_visual_phrases,
    )
    _write_json(work / "sources.json", sources)

    print("Checking for a suitably licensed stadium sound moment…", flush=True)
    sound = find_sound(script["scenes"], work)
    print("Creating English sports narration with the configured male ElevenLabs voice…", flush=True)
    original_words = synthesize(narration, config, work / "narration.mp3")
    audio_duration = media_duration(probe(work / "narration.mp3"))
    try:
        words, speed, sound = retime_with_sound(
            script["scenes"], original_words, audio_duration, config.duration, sound)
    except PipelineError as exc:
        if sound is None or "safe inter-scene gap" not in str(exc):
            raise
        print("No safe speech gap for the sound moment; omitting it.", flush=True)
        words, speed, sound = retime_with_sound(
            script["scenes"], original_words, audio_duration, config.duration, None)

    boundaries = scene_boundaries(script["scenes"], words, config.duration)
    _write_json(work / "timing.json", {
        "original_audio_duration": audio_duration,
        "tempo": speed,
        "scene_boundaries": boundaries,
        "sound_moment": sound and {"start": sound["start"], "seconds": sound["seconds"],
                                   "after_scene": sound["after_scene"]},
        "words": [word.__dict__ for word in words],
    })
    (work / "captions.ass").write_text(
        make_ass(words, config.duration, sources, boundaries, football_mode=True), encoding="utf-8")
    (work / "captions.srt").write_text(make_srt(words), encoding="utf-8")

    video = render(work, sources, boundaries, speed, config.duration, sound=sound)
    metadata = verify_output(video, config.duration)
    _write_json(work / "manifest.json", {
        "channel": "FERNIMOON STUDIO",
        "mode": "football",
        "topic": topic,
        "editorial_format": editorial_format,
        "target_entity": context.get("target_entity"),
        "visual_entity_phrases": required_visual_phrases or [],
        "news_count": len(context.get("news") or []),
        "fact_count": len(context.get("fact_index") or []),
        "visual_source_count": len(sources),
        "commons_media_count": sum(1 for source in sources if source.get("source") == "Wikimedia Commons"),
        "pixabay_stock_count": sum(1 for source in sources if source.get("source") == "Pixabay"),
        "visual_audit": [{
            "scene": source.get("scene"),
            "source": source.get("source"),
            "kind": source.get("kind"),
            "search_query": source.get("search_query"),
            "tags": source.get("tags"),
            "title": source.get("title"),
            "page_url": source.get("page_url"),
            "license": source.get("license"),
            "visual_review": source.get("visual_review"),
        } for source in sources],
        "scene_fact_map": [{
            "scene": index + 1,
            "fact_ids": scene.get("fact_ids", []),
        } for index, scene in enumerate(script["scenes"])],
        **metadata,
        "gemini_model": config.gemini_model,
        "voice_id": config.voice_id,
        "voice_profile": "male_low_register_sports_commentary",
        "elevenlabs_model": config.elevenlabs_model,
        "football_provider": context["provider"],
        "football_retrieved_at": context["retrieved_at"],
        "competition_count": len(context["competitions"]),
        "fixture_count": len(context["fixtures"]),
        "visual_policy": (
            "Prefer club-identity-matched CC0/Public Domain Wikimedia real photos/videos; otherwise use "
            "club-identity-matched licensed Pixabay illustrative B-roll. No generic football fallback. "
            "Never represented as actual match highlights."
        ),
        "sound_used": bool(sound),
    })

    credits = [
        "",
        "FOOTBALL DATA:",
        f"Provider: {context['provider']}",
        f"Retrieved: {context['retrieved_at']}",
        f"Match date: {context['match_date']}",
        "Scores and match facts are provider data; coverage and update latency vary by competition.",
        "",
        "NEWS SOURCES (publisher reports are attributed, not automatically confirmed):",
    ]
    for article in context.get("news") or []:
        credits.append(
            f"{article.get('publisher', 'Publisher')} | {article.get('published_at', 'date not supplied')} | "
            f"{article.get('title', '')} | {article.get('url', '')}"
        )
    credits.extend([
        "",
        "VISUAL SOURCES:",
        "Wikimedia Commons CC0/Public Domain media is preferred; Pixabay clips are illustrative B-roll, "
        "not footage of the specific fixture.",
    ])
    for index, source in enumerate(sources, 1):
        credits.append(
            f"{index}. {source.get('source', 'Unknown source')} | {source.get('kind', 'media')} | "
            f"{source.get('title') or source.get('tags', '')} | {source.get('page_url', '')} | "
            f"{source.get('creator', '')} | {source.get('license') or 'Pixabay license'} | "
            f"{source.get('license_url', '')}"
        )
    if sound:
        credits.append("Sound moment: " + " | ".join(str(sound.get(key, "")) for key in
                       ("title", "creator", "license", "page_url")))
    credits.extend([
        "",
        "FACT REFERENCES USED BY THE SCRIPT:",
    ])
    for fact in context.get("fact_index") or []:
        credits.append(
            f"{fact.get('id')} | {fact.get('kind')} | {fact.get('publisher', 'API-Football')} | "
            f"{fact.get('summary', '')} | {fact.get('url', '')}"
        )
    (work / "upload.txt").write_text(
        script["title"] + "\n\n" + script["description"] + "\n\n" +
        "\n".join(credits) + "\n", encoding="utf-8")

    delivery = work / "delivery"
    delivery.mkdir()
    if sound:
        _write_json(work / "sound_source.json", {key: sound.get(key) for key in (
            "title", "page_url", "creator", "license", "license_url",
            "source_query", "seconds", "after_scene", "start")})
    files = [
        video.name, "captions.srt", "captions.ass", "script.json", "sources.json",
        "football_context.json", "timing.json", "manifest.json", "upload.txt",
    ]
    if sound:
        files.append("sound_source.json")
    for name in files:
        (work / name).replace(delivery / name)
    print(f"Finished: {delivery / video.name}", flush=True)
    return delivery
