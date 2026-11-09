import unittest
from unittest.mock import patch

from fernimoon.config import PipelineError
from fernimoon.football_data import FootballAPI, build_football_context
from fernimoon.football_entities import resolve_team_entity, visual_query_for_scene
from fernimoon.football_news import _matches_topic
from fernimoon.relevance import visual_relevance
from fernimoon.football_script import enforce_team_topic_lock


class ManchesterUnitedTopicLockTests(unittest.TestCase):
    def test_manchester_united_aliases_resolve_to_one_canonical_entity(self):
        for topic in ("Manchester United", "Man Utd latest news", "MUFC transfer watch"):
            with self.subTest(topic=topic):
                entity = resolve_team_entity(topic)
                self.assertIsNotNone(entity)
                self.assertEqual(entity[0], "manchester united")

    def test_news_filter_rejects_unrelated_global_roundup_stories(self):
        manchester = {
            "title": "Manchester United assess their next transfer move",
            "summary": "The club is reviewing its squad options.",
        }
        barcelona = {
            "title": "Barcelona secure a dramatic win over Atletico Madrid",
            "summary": "The Spanish side remain in the title race.",
        }
        self.assertTrue(_matches_topic(manchester, "Manchester United"))
        self.assertFalse(_matches_topic(barcelona, "Manchester United"))

    def test_team_visual_queries_are_anchored_to_the_requested_club(self):
        terms = visual_query_for_scene(
            "Manchester United",
            ["football training ground", "fans inside stadium"],
            0,
        )
        self.assertEqual(len(terms), 2)
        self.assertTrue(all("manchester united" in term.lower() for term in terms))
        self.assertTrue(all("football" in term.lower() or "soccer" in term.lower() for term in terms))

    def test_generic_football_clip_is_rejected_without_club_or_venue_tags(self):
        accepted, _, reason = visual_relevance(
            "Manchester United football fans",
            "football, soccer, fans, stadium, players",
            required_phrases=("Manchester United", "Man Utd", "MUFC", "Old Trafford", "Carrington"),
        )
        self.assertFalse(accepted)
        self.assertIn("club identity", reason)

    def test_club_or_venue_specific_tags_are_accepted(self):
        accepted, _, _ = visual_relevance(
            "Manchester United Old Trafford football stadium",
            "Old Trafford, Manchester United, football stadium, England",
            required_phrases=("Manchester United", "Man Utd", "MUFC", "Old Trafford", "Carrington"),
        )
        self.assertTrue(accepted)

    @patch.object(FootballAPI, "current_major_leagues", return_value=[
        {"id": 39, "name": "Premier League", "season": 2026, "coverage": {}},
    ])
    @patch.object(FootballAPI, "fixtures", return_value=[
        {"fixture_id": 1, "timestamp": 1, "status": "FT",
         "league": {"id": 39, "name": "Premier League"},
         "home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
    ])
    def test_named_club_with_no_fixture_never_falls_back_to_other_matches(self, fixtures, leagues):
        with self.assertRaisesRegex(PipelineError, "No fixtures"):
            build_football_context("secret", "Manchester United", "2026-11-08")

    @patch.object(FootballAPI, "current_major_leagues", return_value=[
        {"id": 39, "name": "Premier League", "season": 2026, "coverage": {}},
    ])
    @patch.object(FootballAPI, "fixtures", return_value=[
        {"fixture_id": 1, "timestamp": 1, "status": "FT",
         "league": {"id": 39, "name": "Premier League"},
         "home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
    ])
    def test_named_club_can_return_empty_fixture_set_for_news_only_research(self, fixtures, leagues):
        context = build_football_context(
            "secret", "Manchester United", "2026-11-08", allow_empty=True
        )
        self.assertEqual(context["fixtures"], [])
        self.assertEqual(context["target_entity"], "manchester united")

    def test_generic_global_roundup_script_is_rejected_for_manchester_united_topic(self):
        script = {
            "title": "European Football Roundup",
            "scenes": [{
                "narration": "European football delivered massive drama across the continent tonight.",
                "fact_ids": ["mu-news"],
                "search_terms": ["football match", "soccer fans"],
            }],
        }
        facts = [{"id": "mu-news", "summary": "Manchester United are assessing their squad."}]
        with self.assertRaisesRegex(PipelineError, "title must explicitly identify"):
            enforce_team_topic_lock(script, "Manchester United", facts)

    def test_club_locked_script_gets_club_specific_visual_queries(self):
        script = {
            "title": "Manchester United's Defining Week",
            "scenes": [{
                "narration": "Manchester United face a defining week at Old Trafford.",
                "fact_ids": ["mu-news"],
                "search_terms": ["football training ground", "soccer supporters"],
            }],
        }
        facts = [{"id": "mu-news", "summary": "Manchester United are assessing their squad."}]
        result = enforce_team_topic_lock(script, "Manchester United", facts)
        self.assertEqual(result["target_entity"], "manchester united")
        self.assertTrue(all("manchester united" in term.lower()
                            for term in result["scenes"][0]["search_terms"]))

    def test_scene_cannot_cite_an_unrelated_club_story(self):
        script = {
            "title": "Manchester United's Defining Week",
            "scenes": [{
                "narration": "Manchester United face a defining week at Old Trafford.",
                "fact_ids": ["barca-news"],
                "search_terms": ["football training ground", "soccer supporters"],
            }],
        }
        facts = [{"id": "barca-news", "summary": "Barcelona beat Atletico Madrid."}]
        with self.assertRaisesRegex(PipelineError, "cites no evidence specifically"):
            enforce_team_topic_lock(script, "Manchester United", facts)


if __name__ == "__main__":
    unittest.main()
