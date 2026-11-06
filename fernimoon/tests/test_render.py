"""Offline integration: actual 1080x1920/40-second encode, no providers or paid calls.

The moving test pattern and tone are test fixtures only, never production footage.
Enable with FERNIMOON_RENDER_TEST=1 (also enabled by the test workflow).
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fernimoon.media import run, verify_output
from fernimoon.pipeline import create_short
from fernimoon.speech import Word
from test_pipeline import config, example_script


@unittest.skipUnless(os.environ.get("FERNIMOON_RENDER_TEST") == "1", "Set FERNIMOON_RENDER_TEST=1 for the full FFmpeg smoke test")
class RenderIntegrationTests(unittest.TestCase):
    def test_complete_pipeline_creates_verified_mp4_captions_and_sources(self):
        with tempfile.TemporaryDirectory(prefix="fernimoon-test-") as directory:
            root = Path(directory)
            # Real video stream with visible motion; not a production asset or an AI image.
            fixture = root / "fixture.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30",
                 "-t", "1", "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", str(fixture)])

            def fake_footage(scenes, config, work, cache, context):
                sources = []
                for index, _ in enumerate(scenes):
                    filename = f"footage-{index:02d}.mp4"
                    shutil.copyfile(fixture, work / filename)
                    sources.append({"file": filename, "type": "film", "scene": index + 1, "id": index})
                return sources

            def fake_voice(narration, cfg, destination):
                run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=40",
                     "-c:a", "libmp3lame", "-b:a", "128k", str(destination)])
                tokens = narration.split()
                step = 38 / len(tokens)
                return [Word(text, 0.5 + i * step, 0.5 + (i + 0.8) * step) for i, text in enumerate(tokens)]

            with patch("fernimoon.pipeline.generate_script", return_value=example_script()), \
                    patch("fernimoon.pipeline.collect_priority_media", side_effect=fake_footage), \
                    patch("fernimoon.pipeline.find_sound", return_value=None), \
                    patch("fernimoon.pipeline.synthesize", side_effect=fake_voice):
                delivery = create_short("Ocean life", config(), root / "output")
            self.assertEqual(verify_output(delivery / "FERNIMOON-STUDIO.mp4", 40)["height"], 1920)
            self.assertEqual(len(list(delivery.iterdir())), 8)
            timing = json.loads((delivery / "timing.json").read_text())
            self.assertEqual(len(timing["scene_boundaries"]), 7)
            self.assertLess(timing["words"][-1]["end"], 40)
            self.assertIn("FERNIMOON STUDIO", (delivery / "captions.ass").read_text())
            self.assertNotIn("secret-", "".join(p.read_text() for p in delivery.iterdir() if p.suffix != ".mp4"))
            # Optional local copy for visual inspection. CI leaves test media in its temporary directory.
            preview = os.environ.get("FERNIMOON_TEST_PREVIEW")
            if preview:
                shutil.copyfile(delivery / "FERNIMOON-STUDIO.mp4", preview)


if __name__ == "__main__":
    unittest.main()
