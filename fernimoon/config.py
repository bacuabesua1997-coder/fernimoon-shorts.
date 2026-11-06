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

    @classmethod
    def from_env(cls, duration: int = 40) -> "Config":
        names = ("GEMINI_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID")
        values = {name: os.environ.get(name, "").strip() for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise PipelineError("Missing GitHub Secrets / environment variables: " + ", ".join(missing))
        if not 35 <= duration <= 45:
            raise PipelineError("Duration must be between 35 and 45 seconds.")
        voice = values["ELEVENLABS_VOICE_ID"]
        gemini = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
        eleven = os.environ.get("ELEVENLABS_MODEL", "").strip() or "eleven_multilingual_v2"
        for label, value in (("voice ID", voice), ("Gemini model", gemini), ("ElevenLabs model", eleven)):
            if not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", value):
                raise PipelineError(f"Invalid {label}; use an ID, not a URL.")
        return cls(values[names[0]], values[names[1]], values[names[2]], voice, gemini, eleven, duration)


def validate_topic(topic: str) -> str:
    topic = " ".join(topic.split())
    if not 3 <= len(topic) <= 300:
        raise PipelineError("Topic must contain 3–300 characters.")
    return topic
