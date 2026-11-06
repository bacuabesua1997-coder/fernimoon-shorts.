"""Orchestrate script → real footage → timestamped voice → vertical MP4."""
import json
import tempfile
from pathlib import Path

from .captions import make_ass, make_srt
from .config import Config, validate_topic
from .footage import collect_footage
from .media import media_duration, preflight, probe, render, verify_output
from .script import generate_script
from .speech import retime, scene_boundaries, synthesize


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
    print("Finding real stock footage on Pixabay…", flush=True)
    sources = collect_footage(script["scenes"], config.pixabay_key, work, output / "pixabay-cache")
    write_json(work / "sources.json", sources)
    print("Creating timestamped English narration with ElevenLabs…", flush=True)
    original_words = synthesize(narration, config, work / "narration.mp3")
    audio_duration = media_duration(probe(work / "narration.mp3"))
    words, speed = retime(original_words, audio_duration, config.duration)
    boundaries = scene_boundaries(script["scenes"], words, config.duration)
    write_json(work / "timing.json", {"original_audio_duration": audio_duration, "tempo": speed,
                                   "scene_boundaries": boundaries, "words": [w.__dict__ for w in words]})
    (work / "captions.ass").write_text(make_ass(words, config.duration), encoding="utf-8")
    (work / "captions.srt").write_text(make_srt(words), encoding="utf-8")
    video = render(work, sources, boundaries, speed, config.duration)
    metadata = verify_output(video, config.duration)
    write_json(work / "manifest.json", {"channel": "FERNIMOON STUDIO", "topic": topic, **metadata,
                                     "gemini_model": config.gemini_model, "voice_id": config.voice_id,
                                     "elevenlabs_model": config.elevenlabs_model,
                                     "story_style": config.story_style,
                                     "footage_policy": "Pixabay film only; no image or video generation"})
    (work / "upload.txt").write_text(script["title"] + "\n\n" + script["description"] + "\n", encoding="utf-8")
    # Only a complete, validated video is copied to the downloadable delivery directory.
    delivery = work / "delivery"
    delivery.mkdir()
    for name in (video.name, "captions.srt", "captions.ass", "script.json", "sources.json", "timing.json", "manifest.json", "upload.txt"):
        (work / name).replace(delivery / name)
    print(f"Finished: {delivery / video.name}", flush=True)
    return delivery
