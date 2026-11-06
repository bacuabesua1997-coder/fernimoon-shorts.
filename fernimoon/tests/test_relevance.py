"""Regression tests: historical video #9 used the wrong countries and objects."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fernimoon.config import PipelineError
from fernimoon.footage import collect_footage, select_footage
from fernimoon.relevance import target_location, visual_relevance
from test_pipeline import example_hit


class HistoricalRelevanceTests(unittest.TestCase):
    def test_vietnam_is_detected_from_topic(self):
        self.assertEqual(target_location("Vietnam Wars, 1969"), "vietnam")
        self.assertEqual(target_location("Japanese pagoda in Kyoto"), "japan")
        self.assertIsNone(target_location("Ocean animal facts"))

    def test_all_five_obvious_wandering_soul_mismatches_are_rejected(self):
        cases = (
            ("military helicopter flying",
             "helicopter, military, army, czech, fight, flying, sky, prague, transport"),
            ("ancient temple fog",
             "landscape, five story pagoda, buddhist temple, sunset, old capital kyoto, japan"),
            ("audio reel recorder player",
             "record, record player, vinyl, turntable, retro, spinning, disco, playing"),
            ("military helicopter night nightvision",
             "building, castle, japanese castle, osaka castle, crescent moon, night view"),
            ("night explosion gunfire battlefield",
             "shanghai, tall buildings, the bund, night view, city, lights, night, landscape"),
        )
        for query, tags in cases:
            with self.subTest(query=query):
                ok, score, reason = visual_relevance(query, tags, location="vietnam")
                self.assertFalse(ok, reason)
                self.assertEqual(score, 0)

    def test_plausible_footage_is_not_rejected(self):
        ok, score, reason = visual_relevance(
            "military helicopter flying", "helicopter, army, flying, vietnam, military",
            location="vietnam")
        self.assertTrue(ok, reason)
        self.assertGreater(score, 0)
        ok, _, _ = visual_relevance("foggy jungle trees sunset",
                                     "jungle, trees, water, waterfall",
                                     location="vietnam")
        self.assertTrue(ok)

    def test_geo_mismatch_is_not_required_for_basic_generic_selection(self):
        old = example_hit(tags="helicopter, czech, prague")
        self.assertIsNotNone(select_footage([old], set()))
        self.assertIsNone(select_footage([old], set(), query="military helicopter flying", location="vietnam"))

    def test_relevance_outweighs_portrait_crop(self):
        unrelated = example_hit(1, tags="shanghai, city, buildings, night view")
        unrelated["videos"]["medium"].update(width=1080, height=1920)
        relevant = example_hit(2, tags="vietnam, helicopter, army, military, flying")
        chosen = select_footage(
            [unrelated, relevant], set(), query="military helicopter flying", location="vietnam")
        self.assertEqual(chosen["id"], 2)
        self.assertEqual(chosen["authenticity"], "stock_illustration_not_verified_archive")
        self.assertIn("visual_review", chosen)

    @patch("fernimoon.footage.download_video")
    @patch("fernimoon.footage.search")
    def test_no_misleading_movie_is_downloaded_if_no_relevant_clip(self, search, download):
        search.return_value = [example_hit(tags="japanese castle, osaka, nighttime")]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PipelineError, "no context-relevant historical stock clip"):
                collect_footage(
                    [{"search_terms": ["military helicopter night nightvision"]}], "fake-key",
                    Path(tmp), Path(tmp) / "cache",
                    require_relevance=True,
                    historical_context="The Vietnam War")
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
