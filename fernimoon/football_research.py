"""Combine verified match data and allowlisted publisher news into an editorial research pack."""
from .config import PipelineError
from .football_data import build_football_context
from .football_news import collect_football_news, _matches_topic
from .football_entities import resolve_team_entity, normalize as normalize_team

FORMATS = {
    "auto", "global_roundup", "breaking_news", "transfer_watch", "match_preview",
    "match_recap", "tactical_analysis", "player_spotlight", "club_business",
    "drama", "academy", "history_facts",
}
NEWS_REQUIRED = {
    "breaking_news", "transfer_watch", "player_spotlight", "club_business",
    "drama", "academy", "history_facts",
}


def _fixture_fact(fixture: dict) -> dict:
    home = (fixture.get("home") or {}).get("name") or "Home team"
    away = (fixture.get("away") or {}).get("name") or "Away team"
    score = fixture.get("score") or {}
    score_text = (
        f"{score['home']}–{score['away']}"
        if score.get("home") is not None and score.get("away") is not None
        else "no score recorded"
    )
    return {
        "id": f"fixture-{fixture.get('fixture_id')}",
        "kind": "match_data",
        "claim_type": "provider_record",
        "summary": (
            f"{home} vs {away}; {fixture.get('league', {}).get('name')}; "
            f"status {fixture.get('status')}; score {score_text}; "
            f"kickoff {fixture.get('date')}."
        ),
        "fixture_id": fixture.get("fixture_id"),
    }


def build_football_research(api_key: str, topic: str, match_date: str | None,
                            editorial_format: str = "auto") -> dict:
    """Fetch the smallest evidence pack needed for the selected editorial format."""
    if editorial_format not in FORMATS:
        raise PipelineError("Football Research: unsupported editorial format.")

    need_events = editorial_format == "match_recap"
    need_stats = editorial_format == "tactical_analysis"
    match_context = build_football_context(
        api_key,
        topic,
        match_date,
        allow_empty=True,
        include_events=need_events,
        include_statistics=need_stats,
    )
    news = collect_football_news(topic, editorial_format)
    print(
        "Football news retrieval: "
        f"{news.get('feed_count', 0)} feeds; "
        f"{news.get('successful_article_count', 0)} unique publisher articles; "
        f"{news.get('selected_count', 0)} selected for '{editorial_format}'.",
        flush=True,
    )
    for warning in news.get("feed_errors", [])[:5]:
        print(f"Football RSS warning: {warning}", flush=True)

    fixtures = match_context.get("fixtures") or []
    articles = news.get("articles") or []
    entity = resolve_team_entity(topic)
    if entity:
        canonical, entity_data = entity
        # Defence in depth: the evidence pack cannot widen to a global roundup.
        articles = [item for item in articles if _matches_topic(item, topic)]
        aliases = [normalize_team(alias) for alias in entity_data["aliases"]]
        fixtures = [
            item for item in fixtures
            if any(
                alias == normalize_team(team.get("name", ""))
                or alias in normalize_team(team.get("name", ""))
                for alias in aliases
                for team in (item.get("home") or {}, item.get("away") or {})
                if team.get("name")
            )
        ]
        if not articles and not fixtures:
            raise PipelineError(
                f"Football Research: no {canonical}-specific evidence was found. "
                "The system will not substitute unrelated global football stories. "
                "Try again when a relevant publisher report or fixture is available."
            )
    if editorial_format in NEWS_REQUIRED and not articles:
        details = " Publisher feeds returned no matching articles."
        if news.get("feed_errors"):
            details += " Some configured feeds were unavailable."
        raise PipelineError(
            f"Football Research: no verified RSS material for '{editorial_format}'."
            + details + " Try a broader topic or configure additional approved feeds."
        )
    if editorial_format == "match_preview":
        upcoming = [item for item in fixtures if item.get("status") in {"NS", "TBD"}]
        if not upcoming:
            raise PipelineError("Football Research: no upcoming fixture found for this topic and date.")
    if editorial_format == "match_recap":
        completed = [item for item in fixtures if item.get("status") == "FT"]
        if not completed:
            raise PipelineError("Football Research: no completed fixture found; choose the match date.")
    if editorial_format == "tactical_analysis":
        if not any(item.get("statistics") for item in fixtures):
            raise PipelineError(
                "Football Research: provider statistics are unavailable for the selected fixtures. "
                "Choose another covered competition or use Auto format."
            )
    if not articles and not fixtures:
        raise PipelineError(
            "Football Research: no usable football news or match data was found. "
            "Check API access, publisher feeds, topic and date."
        )

    facts = []
    for article in articles:
        facts.append({
            "id": article["id"],
            "kind": "publisher_report",
            "claim_type": "reported",
            "summary": article.get("title", "") + ". " + article.get("summary", ""),
            "publisher": article.get("publisher"),
            "published_at": article.get("published_at"),
            "url": article.get("url"),
            "publisher_count": article.get("publisher_count", 1),
        })
    for fixture in fixtures:
        fact = _fixture_fact(fixture)
        if fixture.get("events"):
            event_lines = []
            for event in fixture["events"]:
                minute = event.get("elapsed")
                event_lines.append(
                    f"{minute or '?'} minute: {event.get('team') or 'Unknown team'}; "
                    f"{event.get('type') or 'event'}; {event.get('detail') or 'no detail'}; "
                    f"player {event.get('player') or 'not recorded'}; "
                    f"assist {event.get('assist') or 'not recorded'}."
                )
            fact["events"] = event_lines
        if fixture.get("statistics"):
            fact["statistics"] = fixture["statistics"]
        facts.append(fact)

    return {
        "provider": "API-Football + curated RSS",
        "retrieved_at": match_context["retrieved_at"],
        "timezone": match_context["timezone"],
        "query": topic,
        "match_date": match_context["match_date"],
        "editorial_format": editorial_format,
        "target_entity": entity[0] if entity else None,
        "visual_entity_phrases": list(entity[1]["visual_phrases"]) if entity else [],
        "competitions": match_context.get("competitions") or [],
        "fixtures": fixtures,
        "news": articles,
        "news_metadata": {
            "provider": news["provider"],
            "retrieved_at": news["retrieved_at"],
            "feed_count": news["feed_count"],
            "successful_article_count": news["successful_article_count"],
            "feed_errors": news["feed_errors"],
        },
        "fact_index": facts,
        "editorial_note": (
            "Every factual narration scene must cite one or more IDs in fact_index. "
            "Publisher RSS excerpts are reports, not proof of the underlying claim. "
            "Distinguish official confirmation, attributed reporting, rumours and editorial analysis. "
            "Never infer injury, transfer, lineup, quote or dressing-room facts without an explicit source. "
            + match_context["editorial_note"]
        ),
    }
