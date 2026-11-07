"""Research the event and choose event-specific Commons footage BEFORE writing narration.

Filename/description matches are only candidate evidence; they do not prove a
video's age or historical authenticity. No generative images or paid search.
"""
import re
from pathlib import Path

from .commons import download_media, pick_media, search_commons
from .config import PipelineError

STOP = set("""
a an the of and or from in at on how why what when who where
was were is are has have happened history historic historical mysterious
collapse collapsed collapsing destruction disaster disasterous dramatic
event events explained mystery mysterys footage film films photo photograph
video videos true story original real in 19 20
""".split())
YEAR = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})\b")
EVENT_HINTS = {
    "collapse": ("collapse", "collapsed", "collapsing", "destruction"),
    "explosion": ("explosion", "exploded", "blast"),
    "eruption": ("eruption", "erupted", "volcano"),
    "fire": ("fire", "burning", "flames", "blaze"),
}


def event_core(topic: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", topic)
    core = [w for w in words if w.lower() not in STOP and not YEAR.fullmatch(w)]
    return " ".join(core[:7]) or topic[:80]


def research_queries(topic: str) -> list[str]:
    core = event_core(topic)
    year = next(iter(YEAR.findall(topic)), None)
    options = [topic, (core + " " + year) if year else core, core]
    lower = topic.casefold()
    for name, aliases in EVENT_HINTS.items():
        if name in lower or any(w in lower for w in aliases):
            options.append((core + " " + aliases[-1])[:100])
            break
    return list(dict.fromkeys(" ".join(s.split())[:100] for s in options if len(s.strip()) >= 3))[:4]


def relevance_to_event(topic: str, asset: dict) -> tuple[bool, int]:
    """Fail closed on generic bridges, landscape B-roll and contradictory years."""
    core_words = {s.lower() for s in re.findall(r"[A-Za-z]+", event_core(topic))
                  if len(s) >= 3 and s.lower() not in {"bridge", "war", "world", "space", "signal"}}
    if not core_words:
        core_words = {s.lower() for s in re.findall(r"[A-Za-z]+", event_core(topic)) if len(s) >= 4}
    title = (asset.get("title") or "").removeprefix("File:")
    description = asset.get("source_description", "") or ""
    combined = title + " " + description
    text_words = set(re.findall(r"[a-z]+", combined.lower()))
    overlap = len(core_words & text_words)
    minimum = 2 if len(core_words) >= 2 else 1
    if overlap < minimum:
        return False, 0

    year = next(iter(YEAR.findall(topic)), None)
    years_in_text = set(YEAR.findall(combined))
    wrong_year = bool(year and years_in_text and year not in years_in_text)
    if wrong_year:
        return False, 0
    triggers = {x for key, names in EVENT_HINTS.items()
                if key in topic.casefold() or any(w in topic.casefold() for w in names)
                for x in names}
    matching_event = bool(triggers & text_words)
    if year and year not in years_in_text and not matching_event:
        return False, 0

    score = overlap * 20 + (15 if year and year in years_in_text else 0) + (15 if matching_event else 0)
    # For events that were filmed, prefer the original motion footage.
    if asset.get("kind") == "video":
        score += 40
    return True, score


def research_topic(topic: str, work: Path, *, max_sources: int = 3) -> dict:
    candidates = {}
    successful_requests = 0
    for query in research_queries(topic):
        try:
            pages = search_commons(query, limit=30)
            successful_requests += 1
        except PipelineError:
            continue
        for page in pages:
            asset = pick_media([page], event_core(topic), kind="real")
            if not asset:
                continue
            match, score = relevance_to_event(topic, asset)
            if not match:
                continue
            title = asset["title"]
            if title not in candidates or candidates[title][0] < score:
                candidates[title] = (score, asset, query)
    if not successful_requests:
        raise PipelineError("Wikimedia Commons search unavailable; not substituting unrelated footage.")

    # Download only a small set of the strongest event-specific sources.
    sources = []
    for _, asset, query in sorted(candidates.values(), key=lambda x: -x[0]):
        if len(sources) >= max_sources:
            break
        extension = asset["extension"]
        path = work / f"research-{len(sources):02d}{extension}"
        try:
            download_media(asset["url"], path)
        except PipelineError:
            continue
        source = {k: v for k, v in asset.items() if k != "url"}
        source.update({"id": f"R{len(sources)+1}", "file": path.name,
                       "research_query": query, "event_match": True,
                       "priority_tier": 1,
                       "authenticity": "event_specific_candidate_not_independently_verified"})
        sources.append(source)
    if not sources:
        # A named event with no verifiable visual source must not silently turn
        # into generic unrelated stock imagery. For urban legends in particular,
        # an anonymous photo is NOT a verified sighting.
        art_candidates = {}
        for query in research_queries(topic)[:2]:
            try:
                pages = search_commons((query + " illustration")[:100], limit=30)
            except PipelineError:
                continue
            for page in pages:
                asset = pick_media([page], event_core(topic), kind="illustration")
                if asset is None:
                    continue
                match, score = relevance_to_event(topic, asset)
                if match:
                    art_candidates[asset["title"]] = (score, asset, query)
        for _, asset, query in sorted(art_candidates.values(), key=lambda item: -item[0]):
            if len(sources) >= max_sources:
                break
            filename = f"research-{len(sources):02d}{asset['extension']}"
            try:
                download_media(asset["url"], work / filename)
            except PipelineError:
                continue
            source = {k: v for k, v in asset.items() if k != "url"}
            source.update({"id": f"R{len(sources) + 1}", "file": filename,
                           "research_query": query, "event_match": True,
                           "priority_tier": 3, "authenticity": "illustration_not_documentary"})
            sources.append(source)
    if not sources:
        raise PipelineError(
            "SOURCE QUALITY GATE: no event-specific, suitably licensed original "
            "footage/photo or correctly labeled illustration was found. "
            "No unrelated Pixabay footage will be used and no paid voice call was made.")
    print(f"Research: {len(sources)} event-specific licensed media located before script.", flush=True)
    return {"topic": topic, "searched": research_queries(topic), "sources": sources,
            "quality_note": "Candidate media matches event metadata and reuse license only; human verification is still required."}
