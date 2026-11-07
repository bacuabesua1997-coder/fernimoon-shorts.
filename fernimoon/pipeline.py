"""Orchestrate script → real footage → timestamped voice → vertical MP4."""
import json
import tempfile
from pathlib import Path

from .captions import make_ass, make_srt
from .config import Config, PipelineError, validate_topic
from .media_sources import select_researched_media
from .research import research_topic
from .sound import find_sound, retime_with_sound
from .media import media_duration, preflight, probe, render, verify_output
from .script import generate_script
from .speech import scene_boundaries, synthesize


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_short(topic: str, config: Config, output: Path) -> Path:
    topic = validate_topic(topic)
    preflight()
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="short-", dir=output)).resolve()
    print("SOURCE-FIRST: researching event-specific licensed video and photos…", flush=True)
    research = research_topic(topic, work)
    write_json(work / "research.json", research)
    print("Writing English script with Gemini using only researched sources…", flush=True)
    script = generate_script(topic, config, research)
    write_json(work / "script.json", script)
    narration = " ".join(s["narration"] for s in script["scenes"])
    sources = select_researched_media(script["scenes"], research, work)
    write_json(work / "sources.json", sources)
    print("Checking for a licensed sound that deserves a narration pause…", flush=True)
    sound = find_sound(script["scenes"], work)
    print("Creating timestamped English narration with ElevenLabs…", flush=True)
    original_words = synthesize(narration, config, work / "narration.mp3")
    audio_duration = media_duration(probe(work / "narration.mp3"))
    try:
        words, speed, sound = retime_with_sound(
            script["scenes"], original_words, audio_duration, config.duration, sound)
    except PipelineError as exc:
        if sound is None or "safe inter-scene gap" not in str(exc):
            raise
        # Do not cut through spoken words; omit the sound and the pause.
        print("No safe speech gap at cue position; omitting sound moment.", flush=True)
        words, speed, sound = retime_with_sound(
            script["scenes"], original_words, audio_duration, config.duration, None)
    boundaries = scene_boundaries(script["scenes"], words, config.duration)
    write_json(work / "timing.json", {"original_audio_duration": audio_duration, "tempo": speed,
                                   "scene_boundaries": boundaries, "sound_moment": sound and {
                                       "start": sound["start"], "seconds": sound["seconds"],
                                       "after_scene": sound["after_scene"]},
                                   "words": [w.__dict__ for w in words]})
    (work / "captions.ass").write_text(
        make_ass(words, config.duration, sources, boundaries), encoding="utf-8")
    (work / "captions.srt").write_text(make_srt(words), encoding="utf-8")
    video = render(work, sources, boundaries, speed, config.duration, sound=sound)
    metadata = verify_output(video, config.duration)
    write_json(work / "manifest.json", {"channel": "FERNIMOON STUDIO", "topic": topic, **metadata,
                                     "gemini_model": config.gemini_model, "voice_id": config.voice_id,
                                     "elevenlabs_model": config.elevenlabs_model,
                                     "story_style": config.story_style,
                                     "footage_policy": "SOURCE FIRST: Wikimedia event-specific photo/film or clearly labeled illustration; no generic stock fallback",
                                     "research_source_count": len(research["sources"]),
                                     "subject_type": research.get("subject_type", "documentary_candidate"),
                                     "sound_used": bool(sound), "sound_source": sound and {
                                         "source": sound["source"], "title": sound["title"],
                                         "page_url": sound["page_url"], "license": sound["license"]}})
    credits = ["", "VISUAL SOURCES (stock footage is not original-event archival footage):"]
    for i, source in enumerate(sources, 1):
        origin = source.get("source", "Unknown")
        status = ("illustration" if source.get("kind") == "illustration"
                  else "stock footage" if origin == "Pixabay" else "historic media candidate")
        credits.append(f"{i}. {status} | {origin} | {source.get('title', source.get('page_url', ''))} | "
                       f"{source.get('creator', '')} | {source.get('license', source.get('license_url', ''))} | "
                       f"{source.get('page_url', '')}")
    if research.get("subject_type") == "urban_legend_unverified":
        credits.append("")
        credits.append("EDITORIAL DISCLOSURE: All visuals are ORIGINAL DRAMATIZATIONS of an "
                       "unverified urban legend; no footage depicts an authenticated encounter.")
        credits.append("FOLKLORE BACKGROUND (not proof of supernatural events):")
        for ref in research.get("fact_references", []):
            credits.append(f"- {ref['title']}: {ref['url']}")
    if sound:
        credits.append("Sound moment: " + " | ".join(str(sound.get(x, "")) for x in
                       ("title", "creator", "license", "page_url")))
    (work / "upload.txt").write_text(
        script["title"] + "\n\n" + script["description"] + "\n\n" +
        "\n".join(credits) + "\n", encoding="utf-8")
    # Only a complete, validated video is copied to the downloadable delivery directory.
    delivery = work / "delivery"
    delivery.mkdir()
    if sound:
        write_json(work / "sound_source.json", {k: sound.get(k) for k in (
            "title", "page_url", "creator", "license", "license_url",
            "source_query", "seconds", "after_scene", "start")})
    files = [video.name, "captions.srt", "captions.ass", "script.json", "sources.json",
             "research.json", "timing.json", "manifest.json", "upload.txt"]
    if sound:
        files.append("sound_source.json")
    for name in files:
        (work / name).replace(delivery / name)
    print(f"Finished: {delivery / video.name}", flush=True)
    return delivery
