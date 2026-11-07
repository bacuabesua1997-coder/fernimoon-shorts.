"""Failures caught by auditing FERNIMOON #13 and #14.

All tests are local/offline: no Pixabay, Gemini, ElevenLabs or Wikimedia calls.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fernimoon.commons import pick_media
from fernimoon.config import PipelineError
from fernimoon.media_sources import select_researched_media
from fernimoon.pipeline import create_short
from fernimoon.research import relevance_to_event, research_topic
from fernimoon.script import validate_script
from test_authentic_media import page
from test_pipeline import config, example_script


def tacoma_page():
    return page(
        title="File:Tacoma Narrows Bridge destruction.ogv",
        mime="application/ogg", width=640, height=480,
        tags="Original footage of Tacoma Narrows Bridge destruction, 7 November 1940")


class EventGroundingTests(unittest.TestCase):
    def test_tacoma_original_film_is_supported_at_historical_resolution(self):
        film = pick_media([tacoma_page()], "Tacoma Narrows Bridge", kind="real")
        self.assertIsNotNone(film)
        self.assertEqual(film["kind"], "video")
        self.assertEqual(film["extension"], ".ogv")
        self.assertTrue(relevance_to_event("The Tacoma Narrows Bridge Collapse of 1940", film)[0])

    def test_rejects_modern_tacoma_or_generic_bridges(self):
        modern = {"title": "File:2024 Tacoma Narrows bridge drone.webm",
                  "source_description": "Modern bridge flyover in 2024",
                  "kind": "video"}
        foreign = {"title": "File:Clifton Suspension Bridge England.jpg",
                   "source_description": "Beautiful bridge over a river",
                   "kind": "image"}
        for bad in (modern, foreign):
            self.assertFalse(relevance_to_event("The Tacoma Narrows Bridge Collapse of 1940", bad)[0])

    @patch("fernimoon.research.download_media")
    @patch("fernimoon.research.search_commons")
    def test_true_event_film_is_selected_before_gemini(self, search, download):
        search.return_value = [tacoma_page()]
        with tempfile.TemporaryDirectory() as tmp:
            found = research_topic("The Tacoma Narrows Bridge Collapse of 1940", Path(tmp))
        self.assertGreaterEqual(len(found["sources"]), 1)
        self.assertEqual(found["sources"][0]["kind"], "video")
        self.assertEqual(found["sources"][0]["id"], "R1")
        self.assertIn("Tacoma Narrows", found["sources"][0]["title"])
        self.assertTrue(download.called)

    @patch("fernimoon.research.search_commons", return_value=[])
    def test_black_eyed_children_without_authentic_media_fails_closed(self, search):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PipelineError, "SOURCE QUALITY GATE"):
                research_topic("Black-Eyed Children urban legend", Path(tmp))

    @patch("fernimoon.pipeline.synthesize")
    @patch("fernimoon.pipeline.generate_script")
    @patch("fernimoon.pipeline.preflight")
    @patch("fernimoon.pipeline.research_topic",
           side_effect=PipelineError("SOURCE QUALITY GATE: no matching media"))
    def test_no_source_does_not_charge_tts_or_script(self, research, preflight, gemini, tts):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PipelineError, "SOURCE QUALITY GATE"):
                create_short("Black-Eyed Children urban legend", config(), Path(tmp))
        gemini.assert_not_called()
        tts.assert_not_called()

    def test_gemini_cannot_use_unresearched_clip(self):
        script = example_script()
        for scene in script["scenes"]:
            scene["source_id"] = "R1"
        good = validate_script(script, 40, {"R1"})
        self.assertTrue(all(s["source_id"] == "R1" for s in good["scenes"]))
        script["scenes"][2]["source_id"] = "FAKE"
        with self.assertRaisesRegex(PipelineError, "source_id"):
            validate_script(script, 40, {"R1"})

    @patch("fernimoon.media_sources.probe",
           return_value={"format": {"duration": "150.0"}})
    def test_same_original_film_can_supply_multiple_different_moments(self, probe):
        scenes = [{"source_id": "R1"}] * 6
        research = {"sources": [{"id": "R1", "kind": "video",
                                 "title": "Tacoma Narrows Bridge destruction",
                                 "file": "research-00.ogv", "source": "Wikimedia Commons"}]}
        with tempfile.TemporaryDirectory() as tmp:
            sources = select_researched_media(scenes, research, Path(tmp))
        self.assertEqual(len(sources), 6)
        self.assertEqual(len({s["file"] for s in sources}), 1)
        start_points = [s["start_at"] for s in sources]
        self.assertEqual(start_points[0], 0)
        self.assertTrue(all(b > a for a, b in zip(start_points, start_points[1:])))

if __name__ == "__main__":
    unittest.main()
