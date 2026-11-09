"""Curated RSS discovery for global football news.

Only HTTPS feeds and article links on explicitly allowlisted publisher domains are
accepted. Feed descriptions are short source excerpts; Gemini must cite their IDs
and may not turn rumours into confirmed facts.
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from hashlib import sha256
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
import json
import os
import re
import socket
import time
import xml.etree.ElementTree as ET

from .config import PipelineError

MAX_FEED_BYTES = 2 * 1024 * 1024
FEED_TIMEOUT = 15
MAX_FEEDS = 12
MAX_ITEMS_PER_FEED = 30
MAX_ARTICLES = 40

DEFAULT_FEEDS = (
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.theguardian.com/football/rss",
    "https://www.espn.com/espn/rss/soccer/news",
    "https://www.skysports.com/rss/12040",
)
DEFAULT_ALLOWED_DOMAINS = (
    "bbc.co.uk", "bbc.com", "theguardian.com", "espn.com", "skysports.com",
    "manutd.com", "premierleague.com", "uefa.com", "fifa.com",
    "fifa.org", "the-afc.com", "concacaf.com", "cafonline.com",
    "bundesliga.com", "laliga.com", "legaseriea.it", "ligue1.com",
    "mlssoccer.com", "cbf.com.br", "thefa.com", "fifa.com",
)

CATEGORY_TERMS = {
    "breaking_news": ("breaking", "announces", "confirmed", "official", "sacked", "appointed"),
    "transfer_watch": ("transfer", "signing", "signs", "bid", "loan", "deal", "contract",
                       "interest", "move", "agreed", "release clause", "free agent"),
    "drama": ("controversy", "row", "clash", "feud", "crisis", "fallout", "anger",
              "dispute", "booed", "backlash", "investigation"),
    "club_business": ("takeover", "ownership", "ineos", "investment", "finance", "revenue",
                      "stadium", "board", "debt", "shareholder", "profit"),
    "academy": ("academy", "youth", "under-21", "under 21", "under-18", "under 18",
                "youngster", "teenager", "prospect", "wonderkid", "graduate"),
    "player_spotlight": ("player", "career", "record", "milestone", "captain", "striker",
                         "midfielder", "defender", "goalkeeper", "form"),
    "history_facts": ("history", "historic", "anniversary", "legend", "record",
                      "classic", "decade", "years ago", "first ever"),
}

TEAM_ALIASES = {
    "manchester united": ("manchester united", "man united", "man utd", "mufc"),
    "manchester city": ("manchester city", "man city", "mcfc"),
    "tottenham": ("tottenham", "spurs"),
    "newcastle united": ("newcastle united", "newcastle"),
    "west ham": ("west ham united", "west ham"),
    "nottingham forest": ("nottingham forest", "nottm forest"),
    "real madrid": ("real madrid",),
    "atletico madrid": ("atletico madrid", "atletico"),
    "barcelona": ("barcelona", "barca"),
    "bayern munich": ("bayern munich", "bayern"),
    "borussia dortmund": ("borussia dortmund", "dortmund"),
    "paris saint germain": ("paris saint germain", "paris saint-germain", "psg"),
    "inter milan": ("inter milan", "internazionale", "inter"),
    "ac milan": ("ac milan", "milan"),
    "juventus": ("juventus", "juve"),
    "bayer leverkusen": ("bayer leverkusen", "leverkusen"),
    "rb leipzig": ("rb leipzig", "leipzig"),
    "ajax": ("ajax",),
    "benfica": ("benfica",),
    "porto": ("porto",),
    "sporting cp": ("sporting cp", "sporting lisbon"),
    "al nassr": ("al nassr",),
    "al hilal": ("al hilal",),
    "inter miami": ("inter miami",),
    "flamengo": ("flamengo",),
    "boca juniors": ("boca juniors",),
    "river plate": ("river plate",),
}

GENERIC_TOPIC_TERMS = {
    "football", "soccer", "global", "world", "roundup", "news", "latest",
    "breaking", "transfer", "transfers", "rumours", "rumors", "match",
    "today", "weekly", "daily", "all", "international",
}


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(data.strip())


def _plain_text(value: str, limit: int = 1800) -> str:
    parser = _TextOnly()
    try:
        parser.feed(value or "")
        parser.close()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value or ""))[:limit].strip()
    return re.sub(r"\s+", " ", " ".join(parser.parts))[:limit].strip()


def _domain_allowed(host: str, allowed: set[str]) -> bool:
    host = (host or "").lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in allowed)


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, allowed: set[str]):
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or not _domain_allowed(parsed.hostname or "", self.allowed):
            raise PipelineError("Football News: blocked a redirect outside the publisher allowlist.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _allowed_domains() -> set[str]:
    configured = os.environ.get("FOOTBALL_NEWS_ALLOWED_DOMAINS", "").strip()
    domains = set(DEFAULT_ALLOWED_DOMAINS)
    if configured:
        domains.update(x.strip().lower().lstrip(".") for x in configured.split(";") if x.strip())
    if any(not re.fullmatch(r"[a-z0-9.-]{3,253}", item) or ".." in item for item in domains):
        raise PipelineError("Football News: invalid publisher allowlist.")
    return domains


def configured_feeds() -> list[str]:
    raw = os.environ.get("FOOTBALL_NEWS_FEEDS", "").strip()
    feeds = [item.strip() for item in raw.split(";") if item.strip()] if raw else list(DEFAULT_FEEDS)
    if not 1 <= len(feeds) <= MAX_FEEDS:
        raise PipelineError(f"Football News: configure between 1 and {MAX_FEEDS} RSS feeds.")
    allowed = _allowed_domains()
    for feed in feeds:
        parsed = urlparse(feed)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.query or parsed.fragment
                or not _domain_allowed(parsed.hostname, allowed)):
            raise PipelineError("Football News: feed URL must be HTTPS on an approved publisher domain.")
    return feeds


def _fetch_feed(url: str, allowed: set[str]) -> bytes:
    request = Request(url, headers={
        "User-Agent": "FERNIMOON-STUDIO/2.0 (+football-news-rss)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9",
    })
    opener = build_opener(_SafeRedirect(allowed))
    try:
        with opener.open(request, timeout=FEED_TIMEOUT) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or not _domain_allowed(final.hostname or "", allowed):
                raise PipelineError("Football News: feed redirected outside the publisher allowlist.")
            payload = response.read(MAX_FEED_BYTES + 1)
        if len(payload) > MAX_FEED_BYTES:
            raise PipelineError("Football News: feed exceeded the two-megabyte size limit.")
        return payload
    except PipelineError:
        raise
    except Exception:
        raise PipelineError("Football News: publisher feed unavailable; retry later.") from None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1].lower()


def _child_text(node, names: set[str]) -> str:
    for child in list(node):
        if _local_name(child.tag) in names:
            if child.text:
                return child.text.strip()
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def _published(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())


def _topic_aliases(topic: str) -> list[str]:
    folded = _normalize(topic)
    for canonical, aliases in TEAM_ALIASES.items():
        if canonical in folded or any(alias in folded for alias in aliases):
            return list(aliases)
    meaningful = [word for word in folded.split() if word not in GENERIC_TOPIC_TERMS]
    return [" ".join(meaningful)] if meaningful else []


def _matches_topic(article: dict, topic: str) -> bool:
    aliases = _topic_aliases(topic)
    if not aliases:
        return True
    text = _normalize(article["title"] + " " + article["summary"])
    return any(_normalize(alias) in text for alias in aliases)


def _matches_format(article: dict, editorial_format: str) -> bool:
    terms = CATEGORY_TERMS.get(editorial_format)
    if not terms:
        return True
    text = (article["title"] + " " + article["summary"]).lower()
    return any(term in text for term in terms)


def _article_id(url: str, title: str) -> str:
    return "news-" + sha256((url or title).encode("utf-8")).hexdigest()[:14]


def _parse_feed(payload: bytes, feed_url: str, allowed: set[str]) -> list[dict]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise PipelineError("Football News: publisher returned malformed RSS or Atom XML.") from None
    host = urlparse(feed_url).hostname or ""
    feed_title = ""
    for node in root.iter():
        if _local_name(node.tag) in {"channel", "feed"}:
            feed_title = _child_text(node, {"title"})
            break
    items = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    result = []
    for node in items[:MAX_ITEMS_PER_FEED]:
        title = _child_text(node, {"title"})
        link = _child_text(node, {"link", "guid", "id"})
        if link and not link.startswith("https://"):
            link = ""
        parsed = urlparse(link)
        if not title or not link or parsed.scheme != "https" or not _domain_allowed(parsed.hostname or "", allowed):
            continue
        summary = _child_text(node, {"description", "summary", "encoded", "content"})
        source_name = _child_text(node, {"source"}) or feed_title or host
        date = _published(_child_text(node, {"pubdate", "published", "updated", "date"}))
        result.append({
            "id": _article_id(link, title),
            "title": _plain_text(title, 240),
            "summary": _plain_text(summary, 1800),
            "publisher": _plain_text(source_name, 100),
            "domain": parsed.hostname,
            "published_at": date,
            "url": link,
            "source_type": "publisher_rss",
        })
    return result


def _story_clusters(articles: list[dict]) -> None:
    """Attach corroboration metadata only for closely matching headlines."""
    token_sets = []
    for article in articles:
        tokens = {word for word in _normalize(article["title"]).split()
                  if len(word) > 2 and word not in {"football", "soccer", "reports", "report", "says"}}
        token_sets.append(tokens)
    for i, article in enumerate(articles):
        publishers = {article["publisher"]}
        related = []
        for j, other in enumerate(articles):
            if i == j or not token_sets[i] or not token_sets[j]:
                continue
            overlap = len(token_sets[i] & token_sets[j]) / max(1, len(token_sets[i] | token_sets[j]))
            if overlap >= 0.55:
                publishers.add(other["publisher"])
                related.append(other["id"])
        article["publisher_count"] = len(publishers)
        article["related_source_ids"] = sorted(set(related))


def collect_football_news(topic: str, editorial_format: str = "auto",
                          max_age_days: int = 21, limit: int = 24) -> dict:
    """Collect, filter, rank and retain provenance for recent global football news."""
    if editorial_format not in {
        "auto", "global_roundup", "breaking_news", "transfer_watch", "match_preview",
        "match_recap", "tactical_analysis", "player_spotlight", "club_business",
        "drama", "academy", "history_facts",
    }:
        raise PipelineError("Football News: unsupported editorial format.")
    if not 1 <= max_age_days <= 365 or not 1 <= limit <= MAX_ARTICLES:
        raise PipelineError("Football News: invalid age or article limit.")
    feeds = configured_feeds()
    allowed = _allowed_domains()
    articles = []
    errors = []
    for feed_url in feeds:
        try:
            payload = _fetch_feed(feed_url, allowed)
            parsed = _parse_feed(payload, feed_url, allowed)
            articles.extend(parsed)
        except PipelineError as exc:
            errors.append(str(exc))
            continue
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    unique = {}
    for article in articles:
        if article["published_at"]:
            try:
                if datetime.fromisoformat(article["published_at"]) < cutoff:
                    continue
            except ValueError:
                continue
        unique[article["url"]] = article
    filtered = [
        article for article in unique.values()
        if _matches_topic(article, topic) and _matches_format(article, editorial_format)
    ]
    _story_clusters(filtered)

    def rank(article):
        published = article.get("published_at")
        try:
            age_hours = max(0.0, (now - datetime.fromisoformat(published)).total_seconds() / 3600) if published else 24 * max_age_days
        except ValueError:
            age_hours = 24 * max_age_days
        recency = max(0.0, 1.0 - age_hours / (24 * max_age_days))
        corroboration = min(article.get("publisher_count", 1), 3) / 3
        return (0.75 * recency + 0.25 * corroboration, published or "", article.get("title", ""))

    filtered.sort(key=rank, reverse=True)
    selected = filtered[:limit]
    return {
        "provider": "curated RSS",
        "retrieved_at": now.isoformat(),
        "feed_count": len(feeds),
        "successful_article_count": len(unique),
        "selected_count": len(selected),
        "articles": selected,
        "feed_errors": errors[:5],
        "editorial_note": (
            "RSS headlines and excerpts are publisher-supplied. A report or rumour is not confirmation. "
            "Cross-publisher similarity is a discovery signal, not proof of independent corroboration. "
            "Verify sensitive claims against primary statements before publication."
        ),
    }
