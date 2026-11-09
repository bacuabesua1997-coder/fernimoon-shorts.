import unittest
from unittest.mock import patch

from fernimoon.config import Config, PipelineError
from fernimoon.football_research import build_football_research
from fernimoon.script import validate_script


def evidence_script(scene_word_counts):
    scenes = []
    for index, count in enumerate(scene_word_counts):
        words = [f"word{index}{i}" for i in range(count)]
        scenes.append({
            "narration": " ".join(words),
            "search_terms": ["football stadium", "soccer supporters"],
            "fact_ids": ["news-approved"],
        })
    return {
        "title": "A sourced football story",
        "description": "A sourced football story. #Football #Shorts",
        "scenes": scenes,
    }


class LongFormShortValidationTests(unittest.TestCase):
    def test_ninety_second_script_accepts_ten_scenes_and_preserves_fact_ids(self):
        script = evidence_script([8, 22, 22, 22, 22, 22, 22, 22, 22, 12])
        result = validate_script(script, 90, approved_fact_ids={"news-approved"})
        self.assertEqual(len(result["scenes"]), 10)
        self.assertEqual(result["scenes"][0]["fact_ids"], ["news-approved"])
        self.assertEqual(sum(len(scene["narration"].split()) for scene in result["scenes"]), 196)

    def test_thirty_second_script_accepts_five_scenes(self):
        script = evidence_script([8, 15, 15, 15, 10])
        result = validate_script(script, 30, approved_fact_ids={"news-approved"})
        self.assertEqual(len(result["scenes"]), 5)

    def test_rejects_fact_ids_not_present_in_the_research_pack(self):
        script = evidence_script([8, 15, 15, 15, 10])
        script["scenes"][2]["fact_ids"] = ["invented-source"]
        with self.assertRaisesRegex(PipelineError, "verified fact index"):
            validate_script(script, 30, approved_fact_ids={"news-approved"})

    def test_short_duration_cannot_use_ten_scenes(self):
        script = evidence_script([8, 8, 8, 8, 8, 8, 8, 8, 8, 8])
        with self.assertRaisesRegex(PipelineError, "expected 5–7 scenes"):
            validate_script(script, 30, approved_fact_ids={"news-approved"})


class FootballResearchTests(unittest.TestCase):
    @patch("fernimoon.football_research.collect_football_news")
    @patch("fernimoon.football_research.build_football_context")
    def test_news_and_match_records_are_assembled_into_a_fact_index(self, match_data, news_data):
        match_data.return_value = {
            "provider": "API-Football",
            "retrieved_at": "2026-11-08T12:00:00+07:00",
            "timezone": "Asia/Ho_Chi_Minh",
            "match_date": "2026-11-08",
            "competitions": [],
            "fixtures": [{
                "fixture_id": 123,
                "home": {"name": "Manchester United"},
                "away": {"name": "Chelsea"},
                "league": {"name": "Premier League"},
                "status": "FT",
                "date": "2026-11-08T19:00:00+07:00",
                "score": {"home": 2, "away": 1},
                "events": [{"elapsed": 90, "team": "Manchester United", "type": "Goal",
                            "detail": "Normal Goal", "player": "Example Player", "assist": None}],
            }],
            "editorial_note": "Provider facts.",
        }
        news_data.return_value = {
            "provider": "curated RSS",
            "retrieved_at": "2026-11-08T05:00:00+00:00",
            "feed_count": 4,
            "successful_article_count": 1,
            "selected_count": 1,
            "articles": [{
                "id": "news-approved", "title": "Manchester United report",
                "summary": "An attributed publisher report.", "publisher": "BBC Sport",
                "published_at": "2026-11-08T04:00:00+00:00",
                "url": "https://www.bbc.co.uk/sport/football/123",
                "publisher_count": 1,
            }],
            "feed_errors": [],
        }
        result = build_football_research("secret", "Manchester United", "2026-11-08", "auto")
        ids = {fact["id"] for fact in result["fact_index"]}
        self.assertIn("news-approved", ids)
        self.assertIn("fixture-123", ids)
        fixture_fact = next(fact for fact in result["fact_index"] if fact["id"] == "fixture-123")
        self.assertIn("events", fixture_fact)
        self.assertEqual(result["news"][0]["publisher"], "BBC Sport")
        self.assertEqual(result["editorial_format"], "auto")
        self.assertTrue(match_data.call_args.kwargs["allow_empty"])

    @patch("fernimoon.football_research.collect_football_news", return_value={
        "provider": "curated RSS", "retrieved_at": "now", "feed_count": 4,
        "successful_article_count": 0, "selected_count": 0, "articles": [],
        "feed_errors": ["feed unavailable"],
    })
    @patch("fernimoon.football_research.build_football_context", return_value={
        "provider": "API-Football", "retrieved_at": "now", "timezone": "UTC",
        "match_date": "today", "competitions": [], "fixtures": [], "editorial_note": "",
    })
    def test_transfer_format_stops_if_no_publisher_material_exists(self, match_data, news_data):
        with self.assertRaisesRegex(PipelineError, "no verified RSS material"):
            build_football_research("secret", "Manchester United", None, "transfer_watch")


if __name__ == "__main__":
    unittest.main()
