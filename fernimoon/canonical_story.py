"""Editorially reviewed narration for the unverified Black-Eyed Children legend.

A 1996 claimed encounter is not a verified 1996 online publication, and the
children allegedly wanted a ride to obtain movie money, not a ride to the
cinema itself. This script deliberately separates claim from evidence.

Background: PBS Monstrum and USC Digital Folklore Archive. Both describe
folklore, not corroborated supernatural events.
"""
from .original_art import is_black_eyed_children


def canonical_legend_script(topic: str, duration: int) -> dict | None:
    if not is_black_eyed_children(topic):
        return None
    if duration == 35:
        narration = [
            "A strange internet legend began with a reporter's chilling claim.",
            "In nineteen ninety-six, Brian Bethel claimed two boys approached his parked car in Abilene, Texas.",
            "He said they wanted a ride to get movie money, and grew insistent.",
            "Then, he said, he noticed their eyes: completely black, without any visible whites.",
            "He drove away frightened. The alleged encounter has no independently verified supernatural evidence.",
            "The story circulated online by the late nineteen nineties and became the Black-Eyed Children urban legend."
        ]
    else:
        narration = [
            "A strange internet legend began with a reporter's chilling claim.",
            "Brian Bethel said that in nineteen ninety-six, two boys approached his parked car in Abilene, Texas, late one evening.",
            "They allegedly wanted a ride to their mother's house to collect movie money. Bethel remembered feeling increasingly uneasy as they insisted.",
            "Then, he said, he noticed their eyes: completely black, without any visible whites.",
            "Frightened, he drove away. The encounter was only his account, not independently verified evidence of anything supernatural.",
            "The story circulated online by the late nineteen nineties and became the Black-Eyed Children urban legend."
        ]
    scenes = []
    for i, line in enumerate(narration, 1):
        scenes.append({
            "narration": line,
            "source_id": f"R{i}",
            "search_terms": ["black eyed children folklore", "1990s urban legend"],
            "archive_queries": ["Black Eyed Children urban legend"],
        })
    return {
        "title": "Black-Eyed Children: The Story Behind the Legend",
        "description": (
            "In the late 1990s, journalist Brian Bethel's account of a claimed "
            "encounter in Abilene, Texas, became one of the internet's best-known "
            "urban legends. No independently verified supernatural encounter is "
            "established. All visuals are original dramatizations, NOT authentic "
            "footage of the event. "
            "#BlackEyedChildren #UrbanLegend #Mystery #Shorts #FERNIMOONSTUDIO"
        ),
        "scenes": scenes,
    }
