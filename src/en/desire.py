"""Read and steer Season 4's Desire cards.

Season 4 gives every combatant one Desire card. Obtaining another of the same faction levels the card up;
obtaining a different one opens an inherit screen where the two merge into a single card carrying both tags.
Each card caps at level three, so a team of three carries nine points, and reaching three, five or seven
points in one faction unlocks a team-wide bonus. Concentrating on one faction is therefore worth much more
than spreading across four, which is what the target-faction setting is for.

**The tag is the whole state.** The client prints it on the card itself: `[ Inquiry ]` at level one,
`[ Inquiry 2 ]` at level two, `[ Control / Inquiry 2 ]` once two factions have merged. Faction and points are
both there, and the points total is the card's level. Nothing has to be remembered between frames, which
matters because a run can be resumed, or the bot restarted, part way through a node.

**Reading it is the hard part.** The tag shares a region with the effect text below it, and the reader loses
brackets, drops spaces and sometimes glues the tag straight onto the sentence under it - one captured frame
produced `Control200% Damage to all...`. So the shape is tested rather than searched: a reading only counts as
a tag when everything in it is a faction name, a number, or bracket-and-slash punctuation, and when its points
add up to a level a card can actually reach. That turns away a mangled tag, and it turns away a sentence that
happens to contain the word Control. Turning away a real tag costs one frame of a screen the bot re-reads
every second; acting on a misread one would steer every card pick for the rest of the run.
"""

import re

from ok import Logger

logger = Logger.get_logger(__name__)

# The four Desire factions, spelled as the client spells them. Survival is event-only - it cannot be bought.
FACTIONS = ("Claim", "Inquiry", "Control", "Survival")
# A card stops at level three, and its points total is its level. A tag claiming more than that is a reading
# that ran into the effect text, not a card.
MAX_LEVEL = 3
# One faction and the points beside it. The number is absent at a single point.
TAGGED = re.compile(rf"({'|'.join(FACTIONS)})\s*(\d*)", re.I)
# What a tag may contain besides its faction names: the points, and the brackets and slash the client draws.
# Anything else means the reading has run into the effect text and cannot be trusted.
DECORATION = re.compile(r"[\s\[\]()/|,.:0-9]*")


def tags_of(text):
    """Read the factions and points out of a card's Desire tag.

    Args:
        text: One OCR box's text, which may or may not be a tag.

    Returns:
        A dict of faction to points, empty when the reading is not a tag.
    """
    if not text:
        return {}
    # Everything the tag is allowed to be made of is stripped out; a tag leaves nothing behind.
    remainder = DECORATION.sub("", TAGGED.sub("", text))
    if remainder:
        return {}
    tags = {}
    for faction, points in TAGGED.findall(text):
        # The client spells the faction; the reader's casing is not worth carrying.
        name = next(known for known in FACTIONS if known.casefold() == faction.casefold())
        tags[name] = int(points) if points else 1
    if not tags or sum(tags.values()) > MAX_LEVEL:
        return {}
    return tags


def points_of(tags):
    """Total a tag's points, which is the card's level.

    Args:
        tags: The dict `tags_of` produced.

    Returns:
        The number of points, zero when there is no tag.
    """
    return sum(tags.values())
