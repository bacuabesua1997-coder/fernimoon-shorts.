"""Canonical club identities and visual identity constraints for football videos."""
import re


def normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).split())


# Visual phrases are deliberately more specific than generic football vocabulary.
# The pipeline fails closed when it cannot find a clip whose tags identify the club
# or a distinctive club venue. It never substitutes generic football B-roll.
TEAM_ENTITIES = {
    "manchester united": {
        "aliases": ("manchester united", "man united", "man utd", "mufc"),
        "visual_phrases": ("manchester united", "man utd", "mufc", "old trafford", "carrington"),
        "visual_queries": (
            "Manchester United football team",
            "Manchester United Old Trafford football stadium",
            "Manchester United football fans",
            "Manchester United football training Carrington",
        ),
    },
    "manchester city": {
        "aliases": ("manchester city", "man city", "mcfc"),
        "visual_phrases": ("manchester city", "man city", "mcfc", "etihad stadium"),
        "visual_queries": (
            "Manchester City football team",
            "Manchester City Etihad football stadium",
            "Manchester City football fans",
        ),
    },
    "liverpool": {
        "aliases": ("liverpool", "liverpool fc", "lfc"),
        "visual_phrases": ("liverpool fc", "liverpool football", "anfield", "lfc"),
        "visual_queries": (
            "Liverpool FC football team",
            "Liverpool FC Anfield football stadium",
            "Liverpool football fans Anfield",
        ),
    },
    "arsenal": {
        "aliases": ("arsenal", "arsenal fc", "afc"),
        "visual_phrases": ("arsenal fc", "arsenal football", "emirates stadium"),
        "visual_queries": (
            "Arsenal FC football team",
            "Arsenal Emirates football stadium",
            "Arsenal football fans",
        ),
    },
    "chelsea": {
        "aliases": ("chelsea", "chelsea fc", "cfc"),
        "visual_phrases": ("chelsea fc", "chelsea football", "stamford bridge"),
        "visual_queries": (
            "Chelsea FC football team",
            "Chelsea Stamford Bridge football stadium",
            "Chelsea football fans",
        ),
    },
    "tottenham hotspur": {
        "aliases": ("tottenham hotspur", "tottenham", "spurs"),
        "visual_phrases": ("tottenham hotspur", "tottenham", "spurs", "tottenham hotspur stadium"),
        "visual_queries": (
            "Tottenham Hotspur football team",
            "Tottenham Hotspur football stadium",
            "Tottenham Spurs football fans",
        ),
    },
    "newcastle united": {
        "aliases": ("newcastle united", "newcastle", "nufc"),
        "visual_phrases": ("newcastle united", "newcastle football", "st james park", "nufc"),
        "visual_queries": (
            "Newcastle United football team",
            "Newcastle United St James Park football stadium",
            "Newcastle United football fans",
        ),
    },
    "real madrid": {
        "aliases": ("real madrid",),
        "visual_phrases": ("real madrid", "santiago bernabeu",),
        "visual_queries": (
            "Real Madrid football team",
            "Real Madrid Santiago Bernabeu stadium",
            "Real Madrid football fans",
        ),
    },
    "barcelona": {
        "aliases": ("barcelona", "barca", "fc barcelona"),
        "visual_phrases": ("fc barcelona", "barcelona football", "camp nou", "spotify camp nou"),
        "visual_queries": (
            "FC Barcelona football team",
            "Barcelona Camp Nou football stadium",
            "Barcelona football fans",
        ),
    },
    "atletico madrid": {
        "aliases": ("atletico madrid", "atletico"),
        "visual_phrases": ("atletico madrid", "atletico", "metropolitano stadium"),
        "visual_queries": (
            "Atletico Madrid football team",
            "Atletico Madrid Metropolitano stadium",
            "Atletico Madrid football fans",
        ),
    },
    "bayern munich": {
        "aliases": ("bayern munich", "bayern"),
        "visual_phrases": ("bayern munich", "fc bayern", "allianz arena"),
        "visual_queries": (
            "Bayern Munich football team",
            "Bayern Munich Allianz Arena stadium",
            "Bayern Munich football fans",
        ),
    },
    "borussia dortmund": {
        "aliases": ("borussia dortmund", "dortmund", "bvb"),
        "visual_phrases": ("borussia dortmund", "bvb", "signal iduna park"),
        "visual_queries": (
            "Borussia Dortmund football team",
            "Borussia Dortmund Signal Iduna Park stadium",
            "Borussia Dortmund football fans",
        ),
    },
    "paris saint germain": {
        "aliases": ("paris saint germain", "paris saint-germain", "psg"),
        "visual_phrases": ("paris saint germain", "psg", "parc des princes"),
        "visual_queries": (
            "Paris Saint Germain football team",
            "PSG Parc des Princes stadium",
            "Paris Saint Germain football fans",
        ),
    },
    "inter milan": {
        "aliases": ("inter milan", "internazionale", "inter"),
        "visual_phrases": ("inter milan", "internazionale", "san siro"),
        "visual_queries": (
            "Inter Milan football team",
            "Inter Milan San Siro stadium",
            "Inter Milan football fans",
        ),
    },
    "ac milan": {
        "aliases": ("ac milan", "milan"),
        "visual_phrases": ("ac milan", "milan football", "san siro"),
        "visual_queries": (
            "AC Milan football team",
            "AC Milan San Siro stadium",
            "AC Milan football fans",
        ),
    },
    "juventus": {
        "aliases": ("juventus", "juve"),
        "visual_phrases": ("juventus", "allianz stadium turin"),
        "visual_queries": (
            "Juventus football team",
            "Juventus Allianz Stadium Turin",
            "Juventus football fans",
        ),
    },
    "bayer leverkusen": {
        "aliases": ("bayer leverkusen", "leverkusen"),
        "visual_phrases": ("bayer leverkusen", "bayarena"),
        "visual_queries": (
            "Bayer Leverkusen football team",
            "Bayer Leverkusen BayArena stadium",
            "Bayer Leverkusen football fans",
        ),
    },
    "rb leipzig": {
        "aliases": ("rb leipzig", "leipzig"),
        "visual_phrases": ("rb leipzig", "red bull arena leipzig"),
        "visual_queries": (
            "RB Leipzig football team",
            "RB Leipzig Red Bull Arena stadium",
            "RB Leipzig football fans",
        ),
    },
    "ajax": {
        "aliases": ("ajax", "ajax amsterdam"),
        "visual_phrases": ("ajax amsterdam", "afc ajax", "johan cruyff arena"),
        "visual_queries": (
            "Ajax Amsterdam football team",
            "Ajax Johan Cruyff Arena stadium",
            "Ajax football fans",
        ),
    },
    "benfica": {
        "aliases": ("benfica", "sl benfica"),
        "visual_phrases": ("sl benfica", "benfica football", "estadio da luz"),
        "visual_queries": (
            "Benfica football team",
            "Benfica Estadio da Luz stadium",
            "Benfica football fans",
        ),
    },
    "porto": {
        "aliases": ("porto", "fc porto"),
        "visual_phrases": ("fc porto", "porto football", "estadio do dragao"),
        "visual_queries": (
            "FC Porto football team",
            "FC Porto Estadio do Dragao stadium",
            "FC Porto football fans",
        ),
    },
    "sporting cp": {
        "aliases": ("sporting cp", "sporting lisbon"),
        "visual_phrases": ("sporting cp", "sporting lisbon", "estadio jose alvalade"),
        "visual_queries": (
            "Sporting CP football team",
            "Sporting CP Estadio Jose Alvalade",
            "Sporting CP football fans",
        ),
    },
    "al nassr": {
        "aliases": ("al nassr",),
        "visual_phrases": ("al nassr", "al nassr football"),
        "visual_queries": (
            "Al Nassr football team",
            "Al Nassr football stadium",
            "Al Nassr football fans",
        ),
    },
    "al hilal": {
        "aliases": ("al hilal",),
        "visual_phrases": ("al hilal", "al hilal football"),
        "visual_queries": (
            "Al Hilal football team",
            "Al Hilal football stadium",
            "Al Hilal football fans",
        ),
    },
    "inter miami": {
        "aliases": ("inter miami",),
        "visual_phrases": ("inter miami", "chase stadium"),
        "visual_queries": (
            "Inter Miami football team",
            "Inter Miami Chase Stadium",
            "Inter Miami football fans",
        ),
    },
    "flamengo": {
        "aliases": ("flamengo", "clube de regatas do flamengo"),
        "visual_phrases": ("flamengo", "maracana"),
        "visual_queries": (
            "Flamengo football team",
            "Flamengo Maracana stadium",
            "Flamengo football fans",
        ),
    },
    "boca juniors": {
        "aliases": ("boca juniors", "boca"),
        "visual_phrases": ("boca juniors", "la bombonera"),
        "visual_queries": (
            "Boca Juniors football team",
            "Boca Juniors La Bombonera stadium",
            "Boca Juniors football fans",
        ),
    },
    "river plate": {
        "aliases": ("river plate", "club atletico river plate"),
        "visual_phrases": ("river plate", "monumental stadium"),
        "visual_queries": (
            "River Plate football team",
            "River Plate Monumental stadium",
            "River Plate football fans",
        ),
    },
}


def resolve_team_entity(topic: str) -> tuple[str, dict] | None:
    folded = normalize(topic)
    padded = " " + folded + " "
    matches = []
    for canonical, data in TEAM_ENTITIES.items():
        for alias in data["aliases"]:
            phrase = " " + normalize(alias) + " "
            if phrase in padded:
                matches.append((len(phrase), canonical, data))
                break
    if not matches:
        return None
    _, canonical, data = max(matches, key=lambda item: item[0])
    return canonical, data


def is_entity_reference(text: str, entity: dict) -> bool:
    folded = " " + normalize(text) + " "
    return any(" " + normalize(alias) + " " in folded for alias in entity["aliases"])


def matches_visual_identity(tags: str, entity: dict) -> bool:
    """Require a club name, club abbreviation, or distinctive venue in stock tags."""
    folded = " " + normalize(tags) + " "
    return any(" " + normalize(phrase) + " " in folded for phrase in entity["visual_phrases"])


def visual_query_for_scene(topic: str, search_terms: list[str], scene_index: int) -> list[str]:
    resolved = resolve_team_entity(topic)
    if not resolved:
        return search_terms
    canonical, entity = resolved
    terms = []
    for term in search_terms:
        value = " ".join(term.split())
        if not is_entity_reference(value, entity):
            value = f"{canonical} {value}"
        if not re.search(r"\b(football|soccer)\b", value, re.I):
            value += " football"
        terms.append(value[:80].strip())
    # Always keep one canonical, venue-specific query in each scene's query set.
    venue_query = entity["visual_queries"][scene_index % len(entity["visual_queries"])]
    if venue_query not in terms:
        terms[-1] = venue_query
    return terms
