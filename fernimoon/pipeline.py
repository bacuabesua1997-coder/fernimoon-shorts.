"""Orchestrate script → real footage → timestamped voice → vertical MP4."""
import json
import tempfile
from pathlib import Path

from .captions import make_ass, make_srt
from .config import Config, PipelineError, validate_topic
from .media_sources import collect_priority_media
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
    print("Writing English script with Gemini…", flush=True)
    script = generate_script(topic, config)
    write_json(work / "script.json", script)
    narration = " ".join(s["narration"] for s in script["scenes"])
    print("Finding real photos or video before illustrative stock footage…", flush=True)
    context = topic + " " + " ".join(scene["narration"] for scene in script["scenes"])
    sources = collect_priority_media(script["scenes"], config, work,
                                     output / "pixabay-cache", context)
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
    (work / "captions.ass").write_text(make_ass(words, config.duration), encoding="utf-8")
    (work / "captions.srt").write_text(make_srt(words), encoding="utf-8")
    video = render(work, sources, boundaries, speed, config.duration, sound=sound)
    metadata = verify_output(video, config.duration)
    write_json(work / "manifest.json", {"channel": "FERNIMOON STUDIO", "topic": topic, **metadata,
                                     "gemini_model": config.gemini_model, "voice_id": config.voice_id,
                                     "elevenlabs_model": config.elevenlabs_model,
                                     "story_style": config.story_style,
                                     "footage_policy": "licensed Wikimedia real media, contextual Pixabay film, then Wikimedia illustration",
                                     "sound_used": bool(sound), "sound_source": sound and {
                                         "source": sound["source"], "title": sound["title"],
                                         "page_url": sound["page_url"], "license": sound["license"]}})
    (work / "upload.txt").write_text(script["title"] + "\n\n" + script["description"] + "\n", encoding="utf-8")
    # Only a complete, validated video is copied to the downloadable delivery directory.
    delivery = work / "delivery"
    delivery.mkdir()
    if sound:
        write_json(work / "sound_source.json", {k: sound.get(k) for k in (
            "title", "page_url", "creator", "license", "license_url",
            "source_query", "seconds", "after_scene", "start")})
    files = [video.name, "captions.srt", "captions.ass", "script.json", "sources.json",
             "timing.json", "manifest.json", "upload.txt"]
    if sound:
        files.append("sound_source.json")
    for name in files:
        (work / name).replace(delivery / name)
    print(f"Finished: {delivery / video.name}", flush=True)
    return delivery
