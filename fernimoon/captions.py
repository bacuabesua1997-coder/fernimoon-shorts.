"""Burned-in ASS word highlights and an accompanying standard SRT file."""
from .speech import Word


def escape_ass(text: str) -> str:
    # Replace control syntax so model output cannot inject ASS overrides.
    return text.replace("\\", "／").replace("{", "（").replace("}", "）").replace("\n", " ").replace("\r", " ")


def ass_time(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def srt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def groups(words: list[Word]) -> list[list[Word]]:
    result: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and (len(current) == 4 or len(" ".join(w.text for w in current + [word])) > 30
                        or word.start - current[-1].end > 0.5):
            result.append(current)
            current = []
        current.append(word)
    if current:
        result.append(current)
    return result


def make_ass(words: list[Word], duration: float,
             sources: list[dict] | None = None,
             boundaries: list[float] | None = None) -> str:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,100,160,390,1
Style: Hook,DejaVu Sans,72,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,5,3,2,90,130,430,1
Style: Brand,DejaVu Sans,27,&H00FFFFFF,&H00FFFFFF,&H00202020,&H80000000,-1,0,0,0,100,100,2,0,1,2,1,8,80,80,190,1
Style: SourceLabel,DejaVu Sans,32,&H00FFFFFF,&H00FFFFFF,&H00202020,&H80000000,-1,0,0,0,100,100,2,0,1,3,1,8,90,90,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [f"Dialogue: 0,0:00:00.00,{ass_time(duration)},Brand,,0,0,0,,FERNIMOON STUDIO"]
    for group in groups(words):
        for index, word in enumerate(group):
            end = min(group[index + 1].start, word.end + 0.15) if index + 1 < len(group) else word.end
            if end <= word.start:
                continue
            parts = []
            for j, item in enumerate(group):
                color = r"{\c&H00E8FF&\fscx108\fscy108}" if j == index else r"{\c&HFFFFFF&\fscx100\fscy100}"
                parts.append(color + escape_ass(item.text))
            # Fade plus a moving word highlight; actual onsets come from the speech provider.
            text = r"{\fad(35,0)}" + " ".join(parts)
            style = "Hook" if word.start < min(duration, 3.0) else "Caption"
            lines.append(f"Dialogue: 1,{ass_time(word.start)},{ass_time(end)},{style},,0,0,0,,{text}")
    if sources is not None and boundaries is not None:
        for index, source in enumerate(sources):
            if source.get("kind") == "illustration":
                lines.append(f"Dialogue: 2,{ass_time(boundaries[index])},{ass_time(boundaries[index + 1])},"
                             "SourceLabel,,0,0,0,,ILLUSTRATION")
    return header + "\n".join(lines) + "\n"


def make_srt(words: list[Word]) -> str:
    return "\n\n".join(f"{i}\n{srt_time(g[0].start)} --> {srt_time(g[-1].end)}\n" + " ".join(w.text for w in g)
                       for i, g in enumerate(groups(words), 1)) + "\n"
