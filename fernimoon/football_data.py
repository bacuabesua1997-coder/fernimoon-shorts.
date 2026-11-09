"""API-Football adapter for global major competitions and match facts.

The provider's coverage varies by competition and season. Every returned fact
keeps its provider identifiers and retrieval timestamp for editorial auditing.
"""
import re
import unicodedata
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .config import PipelineError
from .http import request_json

API_ROOT = "https://v3.football.api-sports.io"
LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"

# League IDs are resolved from the provider at runtime; the registry is name-based.
MAJOR_COMPETITIONS = {
    "premier league": ("england",),
    "championship": ("england",),
    "la liga": ("spain",),
    "bundesliga": ("germany",),
    "serie a": ("italy", "brazil"),
    "ligue 1": ("france",),
    "eredivisie": ("netherlands",),
    "primeira liga": ("portugal",),
    "super lig": ("turkey",),
    "scottish premiership": ("scotland",),
    "belgian pro league": ("belgium",),
    "saudi pro league": ("saudi arabia",),
    "major league soccer": ("usa", "united states"),
    "liga mx": ("mexico",),
    "campeonato brasileiro serie a": ("brazil",),
    "liga profesional": ("argentina",),
    "j1 league": ("japan",),
    "k league 1": ("south korea",),
    "a league men": ("australia",),
    "uefa champions league": (),
    "uefa europa league": (),
    "uefa europa conference league": (),
    "uefa nations league": (),
    "copa libertadores": (),
    "copa sudamericana": (),
    "afc champions league elite": (),
    "afc champions league": (),
    "caf champions league": (),
    "concacaf champions cup": (),
    "fifa club world cup": (),
    "fifa world cup": (),
    "euro championship": (),
    "copa america": (),
    "africa cup of nations": (),
    "asian cup": (),
}


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def is_major_competition(league: dict, country: dict | None = None) -> bool:
    name = _fold(league.get("name", ""))
    country_name = _fold((country or {}).get("name", ""))
    for alias, countries in MAJOR_COMPETITIONS.items():
        if name == alias or name.startswith(alias + " "):
            return not countries or any(country_name == _fold(item) for item in countries)
    return False


def _response_list(data: dict, service: str) -> list:
    errors = data.get("errors")
    if errors:
        raise PipelineError(f"{service}: provider rejected the request or this data is outside the API plan.")
    result = data.get("response")
    if not isinstance(result, list):
        raise PipelineError(f"{service}: malformed response; expected a list.")
    return result


class FootballAPI:
    def __init__(self, api_key: str):
        if not isinstance(api_key, str) or not api_key.strip():
            raise PipelineError("Football Mode requires FOOTBALL_API_KEY.")
        self.api_key = api_key.strip()

    def get(self, endpoint: str, params: dict | None = None) -> list:
        if not re.fullmatch(r"[a-z/]+", endpoint):
            raise PipelineError("API-Football: invalid endpoint.")
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{API_ROOT}/{endpoint}" + (f"?{query}" if query else "")
        data = request_json(url, service="API-Football", headers={"x-apisports-key": self.api_key})
        return _response_list(data, "API-Football")

    def current_major_leagues(self) -> list[dict]:
        entries = self.get("leagues", {"current": "true"})
        result = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            league = item.get("league") or {}
            country = item.get("country") or {}
            if not isinstance(league, dict) or not is_major_competition(league, country):
                continue
            seasons = item.get("seasons") or []
            active = next((s for s in seasons if isinstance(s, dict) and s.get("current")), None)
            if not active:
                continue
            result.append({
                "id": league.get("id"),
                "name": league.get("name", ""),
                "type": league.get("type", ""),
                "country": country.get("name", ""),
                "season": active.get("year"),
                "coverage": active.get("coverage", {}),
            })
        return result

    def fixtures(self, *, match_date: str | None = None, live: bool = False) -> list[dict]:
        if live:
            params = {"live": "all", "timezone": LOCAL_TIMEZONE}
        else:
            if not match_date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", match_date):
                raise PipelineError("Football match date must use YYYY-MM-DD.")
            params = {"date": match_date, "timezone": LOCAL_TIMEZONE}
        entries = self.get("fixtures", params)
        normalized = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            fixture = item.get("fixture") or {}
            league = item.get("league") or {}
            teams = item.get("teams") or {}
            goals = item.get("goals") or {}
            if not isinstance(fixture, dict) or not isinstance(league, dict):
                continue
            home, away = teams.get("home") or {}, teams.get("away") or {}
            status = fixture.get("status") or {}
            normalized.append({
                "fixture_id": fixture.get("id"),
                "date": fixture.get("date"),
                "timestamp": fixture.get("timestamp"),
                "status": status.get("short"),
                "status_long": status.get("long"),
                "elapsed": status.get("elapsed"),
                "league": {
                    "id": league.get("id"),
                    "name": league.get("name"),
                    "country": league.get("country"),
                    "season": league.get("season"),
                    "round": league.get("round"),
                },
                "home": {"id": home.get("id"), "name": home.get("name")},
                "away": {"id": away.get("id"), "name": away.get("name")},
                "score": {"home": goals.get("home"), "away": goals.get("away")},
                "halftime": (item.get("score") or {}).get("halftime"),
                "source": "API-Football",
            })
        return normalized

    def events(self, fixture_id: int) -> list[dict]:
        if not isinstance(fixture_id, int) or fixture_id <= 0:
            raise PipelineError("Football fixture ID must be a positive integer.")
        return self.get("fixtures/events", {"fixture": fixture_id})

    def standings(self, league_id: int, season: int) -> list[dict]:
        if not all(isinstance(v, int) and v > 0 for v in (league_id, season)):
            raise PipelineError("Football standings require valid league and season IDs.")
        return self.get("standings", {"league": league_id, "season": season})


def build_football_context(api_key: str, topic: str, match_date: str | None = None) -> dict:
    """Build a source-grounded daily/live fixture pack across major competitions."""
    client = FootballAPI(api_key)
    local_now = datetime.now(ZoneInfo(LOCAL_TIMEZONE))
    live = bool(re.search(r"\blive\b|live score|in[- ]play", topic, re.I))
    target_date = match_date or local_now.date().isoformat()
    if not live and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date):
        raise PipelineError("Football match date must use YYYY-MM-DD.")

    leagues = client.current_major_leagues()
    if not leagues:
        raise PipelineError("API-Football returned no active competitions from the global major-league registry.")
    league_by_id = {item["id"]: item for item in leagues if isinstance(item.get("id"), int)}
    fixtures = client.fixtures(match_date=target_date, live=live)
    selected = [item for item in fixtures if item["league"].get("id") in league_by_id]

    # Narrow to a named team or competition only when the topic clearly matches.
    topic_fold = _fold(topic)
    focused = []
    for item in selected:
        names = [
            _fold(item["league"].get("name", "")),
            _fold(item["home"].get("name", "")),
            _fold(item["away"].get("name", "")),
        ]
        if any(name and (name in topic_fold or topic_fold in name) for name in names):
            focused.append(item)
    if focused:
        selected = focused

    selected.sort(key=lambda item: (
        0 if item.get("status") in {"1H", "HT", "2H", "ET", "P", "LIVE"} else 1,
        item.get("timestamp") or 0,
    ))
    selected = selected[:40]
    if not selected:
        when = "live right now" if live else f"on {target_date}"
        raise PipelineError(
            f"No fixtures from the configured major competitions were returned {when}. "
            "Choose another match date or remove the live-only topic filter."
        )

    competition_ids = {item["league"]["id"] for item in selected}
    return {
        "provider": "API-Football",
        "retrieved_at": local_now.isoformat(),
        "timezone": LOCAL_TIMEZONE,
        "query": topic,
        "match_date": "live" if live else target_date,
        "competitions": [item for item in leagues if item["id"] in competition_ids],
        "fixtures": selected,
        "editorial_note": (
            "Scores, dates, competition names and match states are provider data. "
            "Coverage and update latency vary by competition. Any analysis is editorial interpretation."
        ),
    }
