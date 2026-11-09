import os
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
from unittest.mock import patch
from xml.sax.saxutils import escape

from fernimoon.config import PipelineError
from fernimoon.football_news import (
    DEFAULT_ALLOWED_DOMAINS,
    _parse_feed,
    _matches_topic,
    collect_football_news,
    configured_feeds,
)


BBC = "https://feeds.bbci.co.uk/sport/football/rss.xml"
GUARDIAN = "https://www.theguardian.com/football/rss"


def rss(feed_title, link, title, description, date=None):
    date = date or format_datetime(datetime.now(timezone.utc))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<rss version='2.0'><channel>"
        f"<title>{escape(feed_title)}</title><item>"
        f"<title>{escape(title)}</title><link>{escape(link)}</link>"
        f"<description>{escape(description)}</description>"
        f"<pubDate>{escape(date)}</pubDate>"
        "</item></channel></rss>"
    ).encode("utf-8")


class FootballNewsParsingTests(unittest.TestCase):
    def test_parses_rss_and_strips_markup_from_excerpt(self):
        payload = rss(
            "BBC Sport", "https://www.bbc.co.uk/sport/football/123",
            "Manchester United transfer update",
            "<p>United are reported to be tracking a striker.</p>",
        )
        articles = _parse_feed(payload, BBC, set(DEFAULT_ALLOWED_DOMAINS))
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["publisher"], "BBC Sport")
        self.assertEqual(articles[0]["summary"], "United are reported to be tracking a striker.")
        self.assertTrue(articles[0]["id"].startswith("news-"))
        self.assertIn("T", articles[0]["published_at"])

    def test_rejects_article_links_outside_allowlisted_publishers(self):
        payload = rss(
            "BBC Sport", "https://evil.example/article",
            "Manchester United transfer update", "A transfer report.",
        )
        self.assertEqual(_parse_feed(payload, BBC, set(DEFAULT_ALLOWED_DOMAINS)), [])

    @patch.dict(os.environ, {}, clear=True)
    def test_named_club_adds_its_official_rss_feed(self):
        feeds = configured_feeds("Manchester United")
        self.assertIn("https://www.manutd.com/Feeds/NewsSecondRSSFeed", feeds)
        self.assertIn(BBC, feeds)

    def test_official_club_feed_scopes_articles_even_without_club_name_in_headline(self):
        official = "https://www.manutd.com/Feeds/NewsSecondRSSFeed"
        payload = rss(
            "Manchester United",
            "https://www.manutd.com/en/news/2026/11/09/example",
            "Carrick explains Maguire change",
            "The manager has explained his latest selection decision.",
        )
        article = _parse_feed(payload, official, set(DEFAULT_ALLOWED_DOMAINS))[0]
        self.assertEqual(article["team_entity"], "manchester united")
        self.assertTrue(_matches_topic(article, "Manchester United"))

    @patch.dict(os.environ, {"FOOTBALL_NEWS_FEEDS": BBC}, clear=True)
    @patch("fernimoon.football_news._fetch_feed")
    def test_breaking_news_includes_current_club_updates(self, fetch):
        fetch.return_value = rss(
            "Manchester United",
            "https://www.manutd.com/en/news/2026/11/09/example",
            "Carrick explains Maguire change",
            "Manchester United head coach Michael Carrick explains his latest team decision.",
        )
        result = collect_football_news("Manchester United", "breaking_news")
        self.assertEqual(result["selected_count"], 1)
        self.assertIn("Carrick explains", result["articles"][0]["title"])

    @patch.dict(os.environ, {"FOOTBALL_NEWS_FEEDS": BBC}, clear=True)
    @patch("fernimoon.football_news._fetch_feed")
    def test_filters_by_team_alias_and_transfer_format(self, fetch):
        fetch.return_value = rss(
            "BBC Sport", "https://www.bbc.co.uk/sport/football/123",
            "Man Utd open transfer talks for a striker",
            "Manchester United are reported to be monitoring a forward.",
        )
        result = collect_football_news("Manchester United", "transfer_watch")
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["articles"][0]["publisher"], "BBC Sport")
        self.assertEqual(result["articles"][0]["source_type"], "publisher_rss")

    @patch.dict(os.environ, {"FOOTBALL_NEWS_FEEDS": BBC + ";" + GUARDIAN}, clear=True)
    @patch("fernimoon.football_news._fetch_feed")
    def test_similar_headlines_are_marked_as_discovery_corroboration(self, fetch):
        title = "Manchester United open talks over new striker signing"
        fetch.side_effect = [
            rss("BBC Sport", "https://www.bbc.co.uk/sport/football/123", title, "Report one."),
            rss("The Guardian", "https://www.theguardian.com/football/2026/nov/08/123", title, "Report two."),
        ]
        result = collect_football_news("football", "transfer_watch")
        self.assertEqual(result["selected_count"], 2)
        self.assertEqual({item["publisher_count"] for item in result["articles"]}, {2})
        self.assertTrue(all(item["related_source_ids"] for item in result["articles"]))

    @patch.dict(os.environ, {"FOOTBALL_NEWS_FEEDS": "https://evil.example/rss.xml"}, clear=True)
    def test_rejects_unapproved_feed_domain(self):
        with self.assertRaisesRegex(PipelineError, "approved publisher domain"):
            configured_feeds()

    @patch.dict(os.environ, {"FOOTBALL_NEWS_FEEDS": BBC}, clear=True)
    @patch("fernimoon.football_news._fetch_feed")
    def test_category_filter_does_not_mistake_match_reports_for_transfer_news(self, fetch):
        fetch.return_value = rss(
            "BBC Sport", "https://www.bbc.co.uk/sport/football/456",
            "Manchester United win a dramatic league match",
            "A late goal decided the match.",
        )
        result = collect_football_news("Manchester United", "transfer_watch")
        self.assertEqual(result["selected_count"], 0)


if __name__ == "__main__":
    unittest.main()
