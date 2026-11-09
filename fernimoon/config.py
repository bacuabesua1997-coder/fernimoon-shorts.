"""Configuration shared by the CLI and GitHub Actions. Never serialize secrets."""
import os
import re
from dataclasses import dataclass, field


class PipelineError(Exception):
    """An actionable error whose message is safe to display in Actions logs."""


@dataclass(frozen=True)
class Config:
    gemini_key: str = field(repr=False)
    pixabay_key: str = field(repr=False)
    elevenlabs_key: str = field(repr=False)
    voice_id: str
    gemini_model: str = "gemini-2.5-flash"
    elevenlabs_model: str = "eleven_multilingual_v2"
    duration: int = 40
    story_style: str = "mystery"
    football_api_key: str = field(default="", repr=False)
    mode: str = "documentary"
    football_format: str = "auto"

    @classmethod
    def from_env(cls, duration: int = 60, mode: str | None = None,
                 football_format: str | None = None) -> "Config":
        selected_mode = (mode or os.environ.get("FERNIMOON_MODE", "documentary")).strip().lower()
        if selected_mode not in ("documentary", "football"):
            raise PipelineError("FERNIMOON_MODE must be documentary or football.")
        voice_name = "FOOTBALL_ELEVENLABS_VOICE_ID" if selected_mode == "football" else "ELEVENLABS_VOICE_ID"
        required = ["GEMINI_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_API_KEY", voice_name]
        if selected_mode == "football":
            required.append("FOOTBALL_API_KEY")
        values = {name: os.environ.get(name, "").strip() for name in required}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise PipelineError("Missing GitHub Secrets / environment variables: " + ", ".join(missing))
        if duration not in (30, 45, 60, 75, 90):
            raise PipelineError("Duration must be one of 30, 45, 60, 75 or 90 seconds.")
        voice = values[voice_name]
        gemini = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
        eleven = os.environ.get("ELEVENLABS_MODEL", "").strip() or "eleven_multilingual_v2"
        style = os.environ.get("SHORTS_STYLE", "mystery").strip().lower() or "mystery"
        if style not in ("mystery", "history", "science"):
            raise PipelineError("SHORTS_STYLE must be mystery, history or science.")
        selected_format = (football_format or os.environ.get("FOOTBALL_FORMAT", "auto")).strip().lower()
        if selected_format not in {
            "auto", "global_roundup", "breaking_news", "transfer_watch", "match_preview",
            "match_recap", "tactical_analysis", "player_spotlight", "club_business",
            "drama", "academy", "history_facts",
        }:
            raise PipelineError("FOOTBALL_FORMAT is not a supported editorial format.")
        for label, value in (("voice ID", voice), ("Gemini model", gemini), ("ElevenLabs model", eleven)):
            if not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", value):
                raise PipelineError(f"Invalid {label}; use an ID, not a URL.")
        return cls(
            gemini_key=values["GEMINI_API_KEY"],
            pixabay_key=values["PIXABAY_API_KEY"],
            elevenlabs_key=values["ELEVENLABS_API_KEY"],
            voice_id=voice,
            gemini_model=gemini,
            elevenlabs_model=eleven,
            duration=duration,
            story_style=style,
            football_api_key=values.get("FOOTBALL_API_KEY", ""),
            mode=selected_mode,
            football_format=selected_format,
        )


def validate_topic(topic: str) -> str:
    topic = " ".join(topic.split())
    if not 3 <= len(topic) <= 300:
        raise PipelineError("Topic must contain 3–300 characters.")
    return topic
