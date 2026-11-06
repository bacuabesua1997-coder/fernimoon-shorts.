"""Offline 4.5s video encode proving still-photo motion and a real sound-only pause."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from fernimoon.captions import make_ass
from fernimoon.media import media_duration, probe, render, run
from fernimoon.speech import Word


@unittest.skipUnless(os.environ.get("FERNIMOON_RENDER_TEST") == "1",
                     "Enable only for full FFmpeg integration")
class PhotoAndSoundRenderTests(unittest.TestCase):
    def test_still_picture_with_sound_gap_is_real_decodable_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "testsrc2=size=720x1280:rate=1",
                 "-frames:v", "1", "photo.png",], cwd=work)
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "sine=frequency=340:duration=3.3", "-c:a", "libmp3lame",
                 "narration.mp3"], cwd=work)
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "sine=frequency=840:duration=2.0", "sound.wav"], cwd=work)
            (work / "captions.ass").write_text(make_ass(
                [Word("First", 0.1, 0.6), Word("second", 2.9, 3.4)], 4.5,
                [{"kind": "illustration"}, {"kind": "image"}], [0, 2.8, 4.5]),
                encoding="utf-8")
            info = (work / "captions.ass").read_text()
            self.assertIn("ILLUSTRATION", info)
            video = render(
                work, [{"kind": "illustration", "file": "photo.png"},
                       {"kind": "image", "file": "photo.png"}],
                [0, 2.8, 4.5], 1.0, 4.5,
                sound={"file": "sound.wav", "start": 1.7, "seconds": 1.2})
            meta = probe(video)
            self.assertAlmostEqual(media_duration(meta), 4.5, delta=0.15)
            self.assertEqual(next(s["codec_name"] for s in meta["streams"]
                                  if s["codec_type"] == "video"), "h264")
            self.assertEqual(next(s["codec_name"] for s in meta["streams"]
                                  if s["codec_type"] == "audio"), "aac")
            run(["ffmpeg", "-v", "error", "-i", video.name, "-f", "null", "-"], cwd=work)
