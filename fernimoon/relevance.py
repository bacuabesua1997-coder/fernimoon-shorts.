"""Conservative metadata checks for historical stock-video illustrations.

These checks cannot certify where, when or how a clip was recorded. They only
prevent obvious mismatches before download and before paid narration.
"""
import re

# Distinctive visual subjects matter more than generic search qualifiers.
GENERIC_QUERY_WORDS = frozenset("""
a an the of for to in on with and or from at under over
old new ancient vintage retro historical history historic
dark darkness night daytime bright cinematic dramatic footage video film
flying walking moving running slow fast mysterious spooky haunting
sunset sunrise sky clouds cloud cloudy beautiful view landscape
closeup close up real realistic scene nature shot background
football soccer sport sports match game team teams club player players fan fans stadium pitch field ball
""".split())

# Never use Japanese, Czech or Chinese landmark footage as Vietnamese archival imagery.
LOCATION_HINTS = {
    "vietnam": ("vietnam", "viet nam", "vietnamese", "hanoi", "saigon", "ho chi minh"),
    "japan": ("japan", "japanese", "kyoto", "osaka", "tokyo"),
    "czechia": ("czech", "prague", "praha"),
    "china": ("china", "chinese", "shanghai", "beijing"),
    "france": ("france", "french", "paris"),
    "indonesia": ("indonesia", "jakarta", "bali"),
    "germany": ("germany", "berlin", "german"),
    "united kingdom": ("united kingdom", "britain", "british", "london"),
    "united states": ("united states", "usa", "american", "new york"),
    "italy": ("italy", "italian", "rome"),
    "egypt": ("egypt", "egyptian", "cairo"),
}

# These are factual object mismatches, not aesthetic judgments.
INCOMPATIBLE_SUBJECTS = (
    (frozenset({"tape", "reel", "recorder", "cassette"}), frozenset({"vinyl", "turntable", "gramophone", "phonograph"})),
    (frozenset({"battle", "battlefield", "gunfire", "combat", "soldier", "soldiers"}), frozenset({"fireworks", "festival", "celebration"})),
)


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z]+", (value or "").casefold()))


def _has_phrase(value: str, phrase: str) -> bool:
    text = " " + re.sub(r"[^a-z]+", " ", (value or "").casefold()).strip() + " "
    needle = re.sub(r"[^a-z]+", " ", (phrase or "").casefold()).strip()
    return bool(needle) and " " + needle + " " in text


def target_location(context: str) -> str | None:
    """Return the first explicitly named location, or None for a global topic."""
    for country, cues in LOCATION_HINTS.items():
        if any(_has_phrase(context, cue) for cue in cues):
            return country
    return None


def visual_relevance(query: str, tags: str, *, location: str | None = None,
                     required_phrases: tuple[str, ...] | list[str] | None = None) -> tuple[bool, int, str]:
    """Require a shared specific subject and reject explicit country/object conflicts.

    A positive result means 'plausible stock illustration', NOT historic evidence.
    """
    query_words = _words(query)
    tag_words = _words(tags)
    if not query_words or not tag_words:
        return False, 0, "missing visual subject metadata"

    if required_phrases and not any(_has_phrase(tags, phrase) for phrase in required_phrases):
        return False, 0, "missing required club identity or venue in footage tags"

    if location:
        for other_country, cues in LOCATION_HINTS.items():
            if other_country != location and any(_has_phrase(tags, cue) for cue in cues):
                return False, 0, "different location in footage tags"

    for requested, disallowed in INCOMPATIBLE_SUBJECTS:
        if query_words & requested and tag_words & disallowed:
            return False, 0, "incompatible visual object"

    meaningful = query_words - GENERIC_QUERY_WORDS
    matches = meaningful & tag_words
    if not matches:
        return False, 0, "no matching visual subject in footage tags"
    score = len(matches) * 10
    if location and any(_has_phrase(tags, cue) for cue in LOCATION_HINTS[location]):
        score += 10
    return True, score, "matched source tags: " + ", ".join(sorted(matches))
