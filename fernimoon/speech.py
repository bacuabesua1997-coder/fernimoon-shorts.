"""One ElevenLabs request supplies natural narration and character-level timestamps."""
import base64
import binascii
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config, PipelineError
from .http import request_json


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


def alignment_words(alignment: dict, narration: str) -> list[Word]:
    try:
        chars = alignment["characters"]
        starts = alignment["character_start_times_seconds"]
        ends = alignment["character_end_times_seconds"]
        if not (isinstance(chars, list) and isinstance(starts, list) and isinstance(ends, list)
                and len(chars) == len(starts) == len(ends) > 0
                and all(isinstance(c, str) and len(c) == 1 for c in chars)):
            raise ValueError()
        text = "".join(chars)
        if " ".join(text.split()) != " ".join(narration.split()):
            raise ValueError()
        previous = 0.0
        for start, end in zip(starts, ends):
            if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                    or not math.isfinite(start) or not math.isfinite(end)
                    or not 0 <= start <= end <= 120 or start < previous):
                raise ValueError()
            previous = start
        words = [Word(m.group(), starts[m.start()], max(ends[m.start():m.end()]))
                 for m in re.finditer(r"\S+", text)]
        if not words or any(w.end <= w.start for w in words):
            raise ValueError()
        return words
    except (KeyError, TypeError, ValueError):
        raise PipelineError("ElevenLabs: missing, mismatched or invalid timestamps; refusing unsynchronized captions.") from None


def synthesize(narration: str, config: Config, destination: Path) -> list[Word]:
    # Do not automatically repeat a paid TTS request after an ambiguous network failure.
    result = request_json(
        f"https://api.elevenlabs.io/v1/text-to-speech/{config.voice_id}/with-timestamps?output_format=mp3_44100_128",
        service="ElevenLabs", headers={"xi-api-key": config.elevenlabs_key}, retries=0,
        body={"text": narration, "model_id": config.elevenlabs_model, "language_code": "en",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "use_speaker_boost": True}},
    )
    words = alignment_words(result.get("alignment", {}), narration)
    try:
        audio = base64.b64decode(result["audio_base64"], validate=True)
        if len(audio) < 100:
            raise ValueError()
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise PipelineError("ElevenLabs: invalid audio response.") from None
    destination.write_bytes(audio)
    return words


def retime(words: list[Word], audio_duration: float, target: float) -> tuple[list[Word], float]:
    if not math.isfinite(audio_duration) or audio_duration <= 0:
        raise PipelineError("ElevenLabs: invalid narration duration.")
    if not math.isfinite(target) or target <= 0:
        raise PipelineError("Invalid video duration.")
    if any(w.end > audio_duration + 0.08 for w in words):
        raise PipelineError("ElevenLabs: timestamps extend past the narration audio.")
    # Shorter voice tracks are common even with a validated word count. Never
    # slow a voice beyond 20%; preserve the words and let FFmpeg pad the tail
    # with silence while keeping the video and subtitle timeline intact.
    speed = max(0.8, audio_duration / target)
    if speed > 1.2:
        raise PipelineError("Narration is too long for natural pacing (maximum 20% speed-up). "
                            "Regenerate a shorter script; no speech was truncated.")
    return [Word(w.text, w.start / speed, min(w.end / speed, target)) for w in words], speed


def scene_boundaries(scenes: list[dict], words: list[Word], duration: float) -> list[float]:
    counts = [len(scene["narration"].split()) for scene in scenes]
    if sum(counts) != len(words):
        raise PipelineError("Scene text does not match narration alignment.")
    result = [0.0]
    offset = 0
    for count in counts[:-1]:
        offset += count
        result.append(words[offset].start)
    result.append(duration)
    if any(b - a < 0.5 for a, b in zip(result, result[1:])):
        raise PipelineError("Invalid scene timing.")
    return result
