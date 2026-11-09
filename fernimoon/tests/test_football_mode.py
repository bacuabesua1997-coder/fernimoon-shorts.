import base64
import os
import tempfile
import unittest
from unittest.mock import patch

from fernimoon.captions import make_ass
from fernimoon.config import Config, PipelineError
from fernimoon.football_data import FootballAPI, build_football_context, is_major_competition
from fernimoon.speech import synthesize, Word


def league_item(league_id, name, country, year=2026):
    return {
        "league": {"id": league_id, "name": name, "type": "League"},
        "country": {"name": country},
        "seasons": [{"year": year, "current": True, "coverage": {"fixtures": {"events": True}}}],
    }


class FootballConfigurationTests(unittest.TestCase):
    @patch.dict(os.environ, {
        "GEMINI_API_KEY": "gemini",
        "PIXABAY_API_KEY": "pixabay",
        "ELEVENLABS_API_KEY": "eleven",
        "FOOTBALL_ELEVENLABS_VOICE_ID": "deep_male_voice",
        "FOOTBALL_API_KEY": "football_secret",
    }, clear=True)
    def test_football_mode_uses_dedicated_voice_and_api_key(self):
        config = Config.from_env(mode="football")
        self.assertEqual(config.mode, "football")
        self.assertEqual(config.voice_id, "deep_male_voice")
        self.assertNotIn("football_secret", repr(config))

    @patch.dict(os.environ, {
        "GEMINI_API_KEY": "gemini",
        "PIXABAY_API_KEY": "pixabay",
        "ELEVENLABS_API_KEY": "eleven",
        "FOOTBALL_ELEVENLABS_VOICE_ID": "deep_male_voice",
    }, clear=True)
    def test_football_mode_requires_football_api_key(self):
        with self.assertRaisesRegex(PipelineError, "FOOTBALL_API_KEY"):
            Config.from_env(mode="football")


class FootballCompetitionTests(unittest.TestCase):
    def test_global_competition_registry_checks_country_for_ambiguous_league_names(self):
        self.assertTrue(is_major_competition({"name": "Premier League"}, {"name": "England"}))
        self.assertFalse(is_major_competition({"name": "Premier League"}, {"name": "Wales"}))
        self.assertTrue(is_major_competition({"name": "Serie A"}, {"name": "Italy"}))
        self.assertTrue(is_major_competition({"name": "Serie A"}, {"name": "Brazil"}))
        self.assertTrue(is_major_competition({"name": "UEFA Champions League"}, {"name": "World"}))
        self.assertTrue(is_major_competition({"name": "UEFA Women's Champions League"}, {"name": "World"}))
        self.assertTrue(is_major_competition({"name": "Women's Super League"}, {"name": "England"}))
        self.assertTrue(is_major_competition({"name": "FIFA Women's World Cup"}, {"name": "World"}))

    @patch("fernimoon.football_data.request_json")
    def test_current_major_leagues_are_resolved_from_provider_not_hardcoded_ids(self, request):
        request.return_value = {"response": [
            league_item(39, "Premier League", "England"),
            league_item(140, "La Liga", "Spain"),
            league_item(999, "Local Cup", "Nowhere"),
        ], "errors": {}}
        result = FootballAPI("secret").current_major_leagues()
        self.assertEqual([item["id"] for item in result], [39, 140])
        self.assertEqual(result[0]["season"], 2026)
        self.assertIn("/leagues?current=true", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["headers"]["x-apisports-key"], "secret")

    @patch("fernimoon.football_data.request_json")
    def test_fixture_payload_is_normalized_without_inventing_scorers(self, request):
        request.return_value = {"response": [{
            "fixture": {"id": 123, "date": "2026-11-08T19:00:00+07:00", "timestamp": 1,
                        "status": {"short": "FT", "long": "Match Finished", "elapsed": 90}},
            "league": {"id": 39, "name": "Premier League", "country": "England",
                       "season": 2026, "round": "Regular Season - 12"},
            "teams": {"home": {"id": 1, "name": "Arsenal"},
                      "away": {"id": 2, "name": "Chelsea"}},
            "goals": {"home": 2, "away": 1},
            "score": {"halftime": {"home": 1, "away": 0}},
        }], "errors": {}}
        fixture = FootballAPI("secret").fixtures(match_date="2026-11-08")[0]
        self.assertEqual(fixture["fixture_id"], 123)
        self.assertEqual(fixture["home"]["name"], "Arsenal")
        self.assertEqual(fixture["score"], {"home": 2, "away": 1})
        self.assertEqual(fixture["status"], "FT")
        self.assertEqual(fixture["source"], "API-Football")
        self.assertNotIn("scorers", fixture)
        self.assertIn("date=2026-11-08", request.call_args.args[0])

    def test_context_filters_a_named_competition_and_preserves_retrieval_provenance(self):
        leagues = [
            {"id": 39, "name": "Premier League", "season": 2026},
            {"id": 140, "name": "La Liga", "season": 2026},
        ]
        fixtures = [
            {"fixture_id": 1, "timestamp": 2, "status": "FT",
             "league": {"id": 39, "name": "Premier League"},
             "home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
            {"fixture_id": 2, "timestamp": 1, "status": "FT",
             "league": {"id": 140, "name": "La Liga"},
             "home": {"name": "Barcelona"}, "away": {"name": "Real Madrid"}},
        ]
        with patch.object(FootballAPI, "current_major_leagues", return_value=leagues), \
             patch.object(FootballAPI, "fixtures", return_value=fixtures):
            context = build_football_context("secret", "Premier League roundup", "2026-11-08")
        self.assertEqual([item["fixture_id"] for item in context["fixtures"]], [1])
        self.assertEqual(context["provider"], "API-Football")
        self.assertTrue(context["retrieved_at"])
        self.assertEqual(context["match_date"], "2026-11-08")

    def test_named_club_with_no_fixture_does_not_fall_back_to_global_matches(self):
        leagues = [{"id": 39, "name": "Premier League", "season": 2026}]
        fixtures = [
            {"fixture_id": 10, "timestamp": 1, "status": "FT",
             "league": {"id": 39, "name": "Premier League"},
             "home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
            {"fixture_id": 11, "timestamp": 2, "status": "FT",
             "league": {"id": 140, "name": "La Liga"},
             "home": {"name": "Barcelona"}, "away": {"name": "Real Madrid"}},
        ]
        with patch.object(FootballAPI, "current_major_leagues", return_value=leagues), patch.object(FootballAPI, "fixtures", return_value=fixtures):
            context = build_football_context(
                "secret", "Manchester United", "2026-11-08", allow_empty=True
            )
        self.assertEqual(context["fixtures"], [])
        self.assertEqual(context["competitions"], [])


class FootballPresentationTests(unittest.TestCase):
    def test_ass_has_no_persistent_channel_watermark(self):
        ass = make_ass([Word("Goal!", 0.1, 0.8)], 40)
        self.assertNotIn("FERNIMOON STUDIO", ass)
        self.assertNotIn("Style: Brand", ass)

    def test_football_stock_visuals_are_disclosed_per_scene_not_branded(self):
        ass = make_ass(
            [Word("Football", 0.1, 0.8)],
            40,
            [{"source": "Pixabay", "kind": "video"}],
            [0, 40],
            football_mode=True,
        )
        self.assertIn("ILLUSTRATIVE STOCK FOOTAGE", ass)
        self.assertNotIn("FERNIMOON STUDIO", ass)

    @patch("fernimoon.speech.request_json")
    def test_football_tts_uses_dedicated_voice_settings(self, request):
        narration = "Hello world"
        request.return_value = {
            "alignment": {
                "characters": list(narration),
                "character_start_times_seconds": [i * 0.05 for i in range(len(narration))],
                "character_end_times_seconds": [(i + 1) * 0.05 for i in range(len(narration))],
            },
            "audio_base64": base64.b64encode(b"x" * 200).decode(),
        }
        config = Config("gemini", "pixabay", "eleven", "deep_male_voice",
                        football_api_key="football", mode="football")
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            synthesize(narration, config, Path(tmp) / "voice.mp3")
        body = request.call_args.kwargs["body"]
        self.assertEqual(body["voice_settings"]["stability"], 0.42)
        self.assertEqual(body["voice_settings"]["similarity_boost"], 0.80)
        self.assertEqual(body["voice_settings"]["style"], 0.35)
        self.assertIn("/deep_male_voice/", request.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
