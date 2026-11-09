"""Football Mode production path: live/global match data → English voiceover → licensed B-roll."""
import json
import tempfile
from pathlib import Path

from .captions import make_ass, make_srt
from .config import Config, PipelineError, validate_topic
from .football_research import build_football_research
from .football_script import generate_football_script
from .footage import collect_footage
from .media import media_duration, preflight, probe, render, verify_output
from .sound import find_sound, retime_with_sound
from .speech import scene_boundaries, synthesize


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    _write_json(work / "script.json", script)
    narration = " ".join(scene["narration"] for scene in script["scenes"])

    print("Finding licensed, relevant football stock footage (not match highlights)…", flush=True)
    required_visual_phrases = context.get("visual_entity_phrases") or None
    sources = collect_footage(
        script["scenes"], config.pixabay_key, work, output / "pixabay-cache",
        require_relevance=True,
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
            "Club-identity-matched licensed illustrative stock footage only; no generic football fallback. "
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
        "Pixabay stock footage is illustrative B-roll, not footage of the specific fixture.",
    ])
    for index, source in enumerate(sources, 1):
        credits.append(
            f"{index}. Pixabay stock footage | {source.get('page_url', '')} | "
            f"{source.get('creator', '')} | {source.get('license_url', '')}"
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
