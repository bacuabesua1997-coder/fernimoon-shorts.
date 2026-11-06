"""Optional real-world sound moment: reserve time only when licensed audio exists."""
from pathlib import Path

from .commons import find_and_download
from .config import PipelineError
from .media import media_duration, probe
from .speech import Word, retime


def find_sound(scenes: list[dict], work: Path) -> dict | None:
    for i, scene in enumerate(scenes):
        requested = scene.get("sound_cue")
        if not requested:
            continue
        asset = find_and_download([requested["query"]], "sound", work, i, set())
        if not asset:
            print("No licensed sound matched; narration will continue without a pause.", flush=True)
            return None
        try:
            info = probe(work / asset["file"])
            if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
                raise PipelineError("Sound media contains no audio stream.")
            if media_duration(info) < requested["seconds"] + 0.2:
                raise PipelineError("Sound effect shorter than requested pause.")
        except PipelineError:
            print("Sound file could not be validated; narration continues normally.", flush=True)
            return None
        return {**asset, "after_scene": i, "seconds": requested["seconds"],
                "source_query": requested["query"]}
    return None


def retime_with_sound(scenes: list[dict], words: list[Word],
                      source_duration: float, target: float, sound: dict | None):
    if sound is None:
        shifted, speed = retime(words, source_duration, target)
        return shifted, speed, None

    seconds = float(sound["seconds"])
    active_duration = target - seconds
    shifted, speed = retime(words, source_duration, active_duration)
    cutoff_index = sum(len(s["narration"].split()) for s in scenes[:sound["after_scene"] + 1])
    if cutoff_index < 1 or cutoff_index >= len(shifted):
        raise PipelineError("Sound moment must follow a nonfinal scene.")
    previous, next_word = shifted[cutoff_index - 1], shifted[cutoff_index]
    # Leave the original inter-scene gap intact; cut narration between words.
    if next_word.start - previous.end < 0.04:
        raise PipelineError("Narration has no safe inter-scene gap for a sound moment.")
    cut_at = (previous.end + next_word.start) / 2
    updated = [word if i < cutoff_index
               else Word(word.text, word.start + seconds, word.end + seconds)
               for i, word in enumerate(shifted)]
    if updated[-1].end > target + 0.01:
        raise PipelineError("Sound moment extends beyond video duration.")
    moment = {**sound, "start": cut_at}
    return updated, speed, moment
