"""FFmpeg runs without a shell, with fixed filenames and bounded CPU/memory usage."""
import json
import math
import shutil
import subprocess
from pathlib import Path

from .config import PipelineError


def run(command: list[str], cwd: Path | None = None, timeout: int = 600) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        raise PipelineError(f"Missing executable: {command[0]}. Install FFmpeg and ffprobe.") from None
    except subprocess.TimeoutExpired:
        raise PipelineError(f"{command[0]} exceeded its time limit.") from None
    if result.returncode:
        # These commands operate only on local files and never receive API keys or remote URLs.
        raise PipelineError(f"{command[0]} failed: {result.stderr[-2000:]}")
    return result.stdout


def preflight() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            raise PipelineError(f"Install {binary} before running the pipeline.")
    filters = run(["ffmpeg", "-hide_banner", "-filters"])
    if " ass " not in filters or " loudnorm " not in filters or " atempo " not in filters:
        raise PipelineError("FFmpeg needs libass, loudnorm and atempo filters.")


def probe(path: Path) -> dict:
    try:
        return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))
    except ValueError:
        raise PipelineError("ffprobe returned invalid metadata.") from None


def media_duration(metadata: dict) -> float:
    try:
        value = float(metadata["format"]["duration"])
        if not math.isfinite(value) or value <= 0:
            raise ValueError()
        return value
    except (KeyError, TypeError, ValueError):
        raise PipelineError("Media has no valid duration.") from None


def verify_output(path: Path, target: float) -> dict:
    data = probe(path)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    duration = media_duration(data)
    actual_video = (video.get("width"), video.get("height"), video.get("codec_name"), video.get("pix_fmt"))
    if actual_video != (1080, 1920, "h264", "yuv420p"):
        raise PipelineError(
            "Rendered video failed the 1080×1920 H.264 compatibility check. "
            f"Actual width={actual_video[0]}, height={actual_video[1]}, "
            f"codec={actual_video[2]}, pixel_format={actual_video[3]}.")
    if audio.get("codec_name") != "aac" or not 35 <= duration <= 45.15 or abs(duration - target) > 0.15:
        raise PipelineError("Rendered video failed the audio/duration check.")
    try:
        if abs(float(audio["duration"]) - target) > 0.05 or abs(float(video["duration"]) - target) > 0.05:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise PipelineError("Rendered audio/video streams do not cover the complete timeline.") from None
    return {"width": 1080, "height": 1920, "duration": duration, "video_codec": "h264", "audio_codec": "aac"}


def render(work: Path, sources: list[dict], boundaries: list[float], speed: float, target: float,
           sound: dict | None = None) -> Path:
    # Quantize all shared scene boundaries onto the same 30 fps timeline to prevent cumulative drift.
    frames = [round(t * 30) for t in boundaries]
    segments = []
    for index, source in enumerate(sources):
        source_path = work / source["file"]
        meta = probe(source_path)
        stream = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})
        if not stream or min(stream.get("width", 0), stream.get("height", 0)) < 540:
            raise PipelineError(f"Media scene {index + 1} lacks an adequate visual stream.")
        kind = source.get("kind", "video")
        segment = f"segment-{index:02d}.mp4"
        base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-threads", "2", "-filter_threads", "1"]
        if kind in ("image", "illustration"):
            # An archival still receives gentle camera motion; it remains a labeled photo/illustration.
            base += ["-loop", "1", "-framerate", "30", "-i", source["file"]]
            visual_filter = ("scale=1080:1920:force_original_aspect_ratio=increase,"
                             "crop=1080:1920,setsar=1,"
                             "zoompan=z='min(zoom+0.00020,1.06)':"
                             "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                             "d=1:s=1080x1920:fps=30")
        elif kind == "video":
            if (stream.get("disposition", {}).get("attached_pic") or media_duration(meta) < 1):
                raise PipelineError(f"Media scene {index + 1} is not a usable moving clip.")
            base += ["-stream_loop", "-1", "-i", source["file"]]
            visual_filter = ("scale=1080:1920:force_original_aspect_ratio=increase,"
                             "crop=1080:1920,setsar=1,fps=30,setpts=PTS-STARTPTS")
        else:
            raise PipelineError(f"Media scene {index + 1} has an unsupported visual kind.")
        base += ["-an", "-map", "0:v:0", "-vf", visual_filter,
                 "-frames:v", str(frames[index + 1] - frames[index]),
                 "-c:v", "libx264", "-threads", "2", "-preset", "veryfast",
                 "-crf", "21", "-pix_fmt", "yuv420p", segment]
        run(base, cwd=work)
        segments.append(segment)
        print(f"Rendered scene {index + 1}/{len(sources)}.", flush=True)
    (work / "concat.txt").write_text("".join(f"file '{name}'\n" for name in segments), encoding="utf-8")
    output = work / "FERNIMOON-STUDIO.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-threads", "2", "-filter_threads", "1", "-f", "concat", "-safe", "1",
               "-i", "concat.txt", "-i", "narration.mp3"]
    if sound:
        active = target - sound["seconds"]
        cut_at = sound["start"]
        fade_out = max(0, sound["seconds"] - 0.12)
        command += ["-i", sound["file"]]
        # The real sound plays alone between two intact sections of narration.
        # All narration timestamps, captions and scene boundaries shift identically.
        filters = (
            f"[1:a]atempo={speed:.10f},aresample=48000,"
            f"aformat=channel_layouts=stereo,atrim=duration={active},"
            f"asetpts=PTS-STARTPTS,asplit=2[v0][v1];"
            f"[v0]atrim=duration={cut_at:.6f},asetpts=PTS-STARTPTS[a0];"
            f"[v1]atrim=start={cut_at:.6f},asetpts=PTS-STARTPTS[a1];"
            f"[2:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"atrim=duration={sound['seconds']:.6f},asetpts=PTS-STARTPTS,"
            f"volume=0.65,afade=t=in:st=0:d=0.08,"
            f"afade=t=out:st={fade_out:.6f}:d=0.12[fx];"
            f"[a0][fx][a1]concat=n=3:v=0:a=1,"
            f"loudnorm=I=-16:TP=-1.5:LRA=11,apad,"
            f"atrim=duration={target}[aud]")
        command += ["-filter_complex", filters, "-map", "0:v:0", "-map", "[aud]"]
    else:
        command += ["-map", "0:v:0", "-map", "1:a:0", "-af",
                    f"atempo={speed:.10f},loudnorm=I=-16:TP=-1.5:LRA=11,"
                    f"aresample=48000,apad,atrim=duration={target}"]
    command += ["-vf", "fps=30,scale=1080:1920:flags=lanczos,setsar=1,"
                "tpad=stop_mode=clone:stop_duration=1,ass=captions.ass",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", "2",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-t", str(target), "-movflags", "+faststart",
                "-metadata", "title=FERNIMOON STUDIO", output.name]
    run(command, cwd=work)
    return output
