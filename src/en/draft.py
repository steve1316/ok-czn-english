"""Draft the role a Sortie team lacks, and reroll when none of the offers fill it.

Upstream refreshes all three slots whenever no configured name matches, then picks at random - so with no
priority list it spends both rerolls and still takes whatever it lands on. A debug run drafts whoever has played least instead, so
every combatant's kit gets run live.
"""

from ok import Logger

from src.en import quality, tested
from src.en.battle import PARTY
from src.en.dashboard import TEAM_GEAR
from src.en.equipment import EMPTY_TIER
from src.en.game_quality import COMBATANT_ROLE
from src.en.handlers import insert_before, loaded, register, wrap
from src.en.rewards import show_team

logger = Logger.get_logger(__name__)

# The two damage roles, then the supporting roles in the order a team wants them. Any one of the supporting roles fills the team's one support slot.
DAMAGE = ("Core", "Attack")
SUPPORTING = ("Healing", "Protection", "Support")
# What to settle for once the rerolls are spent and nothing the team lacks is on offer.
ROLES = DAMAGE + SUPPORTING
# The team size at which the draft goes back to damage, so the fourth pick wants a Core, then an Attack.
FOURTH_PICK = 3
# The badge readings for each role. `Attack` reaches us as 攻击力, because the catalog rewrites that word for the
# card type label and the equipment stat row, which share it.
ROLE_READINGS = {"Core": ("core",), "Attack": ("attack", "攻击力"), "Support": ("support",),
                 "Healing": ("healing",), "Protection": ("protection",)}

# The band the three cards occupy, and how far a badge may sit from a slot to belong to it.
CARD_REGION = (0.077, 0.100, 0.946, 0.871)
SAME_CARD = 0.12
# The reroll counter reads "1/1" while a slot still has its reroll, and "0/1" once it is spent.
SPENT_REROLL = "0/"
# What a drafted combatant joins wearing, until an install or the Combatants screen reads the team again.
BARE = "/".join([EMPTY_TIER] * 3)
# Who the draft took on this screen, in `node_status`, which upstream rebuilds when a run or a layer starts.
DRAFTED = "_en_drafted"

_patched = False


def role_of(text):
    """Name the role a badge reading stands for.

    Args:
        text: A box's text.

    Returns:
        One of `ROLES`, or None when the box is not a role badge.
    """
    reading = (text or "").strip().casefold()
    for role, readings in ROLE_READINGS.items():
        if reading in readings:
            return role
    return None


def wanted(party):
    """Name the roles a team still lacks, best first.

    A team wants a damage dealer first, then one Healer, Protector or Supporter, then damage again. The fourth pick always wants damage.

    Args:
        party: Names of the combatants on the team, from `battle.PARTY`.

    Returns:
        A tuple of roles, best first.
    """
    have = {COMBATANT_ROLE.get(name) for name in party}
    if len(party) >= FOURTH_PICK or not have & set(DAMAGE) or have & set(SUPPORTING):
        return DAMAGE
    return SUPPORTING


def rank(role, wants=()):
    """Score a role, lowest first.

    Args:
        role: A role name, or None when the card's role was not read.
        wants: The roles the team lacks, as `wanted` returns them.

    Returns:
        The wanted roles first in their own order, then the rest of `ROLES`, then an unread role.
    """
    order = wants + tuple(other for other in ROLES if other not in wants)
    return order.index(role) if role in order else len(order)


def choose(roles, wants, can_reroll, played=None):
    """Pick the offer to take, or decide to reroll.

    With play counts, an offer who has never played is taken whatever their role, a reroll goes looking for one, and once the rerolls are
    spent the least played is taken. The role the team wants only breaks ties.

    Args:
        roles: The role of each offer, left to right, None where it was not read.
        wants: The roles the team lacks, as `wanted` returns them.
        can_reroll: True while any slot still has its reroll.
        played: How many cards each offer has played across debug runs, from `tested.plays`, or None to draft by role alone.

    Returns:
        The index of the offer to take, or None when a reroll should be spent first.
    """
    if played:
        best = min(range(len(roles)), key=lambda index: (played[index], rank(roles[index], wants)))
        lacking = played[best] > 0
    else:
        best = min(range(len(roles)), key=lambda index: rank(roles[index], wants))
        lacking = bool(wants) and roles[best] not in wants
    return None if lacking and can_reroll else best


def badges(task):
    """Collect the role badges on screen with their horizontal position.

    Args:
        task: The running task.

    Returns:
        A list of `(centre_x, role)` pairs.
    """
    left, top, right, bottom = CARD_REGION
    found = []
    for box in task.all_texts or []:
        role = role_of(box.name)
        if role is None:
            continue
        center_x = (box.x + box.width / 2) / task.width
        center_y = (box.y + box.height / 2) / task.height
        if left <= center_x <= right and top <= center_y <= bottom:
            found.append((center_x, role))
    return found


def role_for(slot, found):
    """Match a candidate to the badge on their own card.

    Args:
        slot: A slot dict from `_read_member_slots`, carrying the name's `x`.
        found: The badges, as `badges` returns them.

    Returns:
        The role, or None when no badge sits close enough to be theirs.
    """
    near = [(abs(center_x - slot["x"]), role) for center_x, role in found]
    near = [pair for pair in near if pair[0] <= SAME_CARD]
    return min(near)[1] if near else None


def rerollable(task, slot):
    """Say whether a slot still has its reroll.

    Args:
        task: The running task.
        slot: A slot dict, carrying the `refresh_y` of its Search again button.

    Returns:
        True when the counter beside the button has not been spent.
    """
    if slot.get("refresh_y") is None:
        return False
    for box in task.all_texts or []:
        center_x = (box.x + box.width / 2) / task.width
        center_y = (box.y + box.height / 2) / task.height
        if abs(center_x - slot["x"]) <= SAME_CARD and abs(center_y - slot["refresh_y"]) <= 0.03:
            if box.name.strip().startswith(SPENT_REROLL):
                return False
    return True


def offers(task, utils, utils_sortie):
    """Read what a Sortie draft offers, when the pick is ours to make.

    Args:
        task: The running task.
        utils: The loaded `utils` module.
        utils_sortie: The loaded `utils_sortie` module, which reads the slots.

    Returns:
        `(name, slot)` pairs, the name in the client's own spelling where the reader could place it. Empty off the
        draft screen, and when a configured priority makes the pick upstream's to honour.
    """
    prompt = utils.find_box_at_point(task, 0.500, 0.931)
    if not (prompt and utils._get_game_text(task, "主战员") in prompt.name):
        return []
    if utils._get_card_list(task, "主战员优先级"):
        return []
    slots = [slot for slot in utils_sortie._read_member_slots(task) if slot.get("name")]
    return [(quality.COMBATANT_INDEX.look_up(slot["name"]) or slot["name"], slot) for slot in slots]


def confirming_our_pick(confirm, utils, utils_sortie):
    """Hold upstream's Confirm on a draft screen until the draft has picked one of its offers.

    Upstream's Confirm runs ahead of the draft, so a card still highlighted from before a restart was confirmed
    without the draft ever seeing it.

    Args:
        confirm: Upstream's `handle_confirm`.
        utils: The loaded `utils` module.
        utils_sortie: The loaded `utils_sortie` module.

    Returns:
        The wrapped handler.
    """
    def handle_confirm(task):
        offered = offers(task, utils, utils_sortie)
        if offered and task.node_status.get(DRAFTED) not in [name for name, _ in offered]:
            return False
        return confirm(task)

    return handle_confirm


def drafting(utils, utils_sortie):
    """Build the handler that picks, or rerolls for, the role the team lacks at a Sortie draft.

    Args:
        utils: The loaded `utils` module.
        utils_sortie: The loaded `utils_sortie` module.

    Returns:
        The handler, which claims the frame when it clicks.
    """
    def handle_member_draft(task):
        offered = offers(task, utils, utils_sortie)
        if not offered:
            return False
        names, slots = zip(*offered)
        found = badges(task)
        # The data knows every combatant's role, and the badge covers a name the reader could not place.
        roles = [COMBATANT_ROLE.get(name) or role_for(slot, found) for name, slot in offered]
        # Whoever is still on offer has not joined, even if an earlier pass picked them and the Confirm did not take.
        party = getattr(task, PARTY, frozenset()) - set(names)
        wants = wanted(party)
        counts = tested.plays()
        played = None if counts is None else [counts[name] for name in names]
        labels = [f"{name} ({role or 'role unread'})" for name, role in zip(names, roles)]
        task.log_info(f"draft offers {', '.join(labels)} to team {sorted(party)}, wanting {'/'.join(wants) or 'nothing'}"
                      f"{'' if played is None else f', card plays so far {played}'}")

        spendable = [slot for slot in slots if rerollable(task, slot)]
        pick = choose(roles, wants, bool(spendable), played)
        if pick is None:
            task.log_info(f"draft offers {'no one untested' if played else 'no ' + ' or '.join(wants)}, rerolling {len(spendable)} slot(s)")
            for slot in spendable:
                utils._move_and_click(task, slot["x"], slot["refresh_y"])
                task.sleep(1)
            return True

        task.log_info(f"draft taking {labels[pick]}")
        utils._move_and_click(task, slots[pick]["x"], slots[pick]["y"])
        task.sleep(1)
        task.node_status[DRAFTED] = names[pick]
        team = [*sorted(party), names[pick]]
        show_team(task, team)
        gear = getattr(task, TEAM_GEAR, None)
        if gear and len(gear.split(", ")) < len(team):
            setattr(task, TEAM_GEAR, f"{gear}, {BARE}")
        return True

    return handle_member_draft


def apply():
    """Rank the candidates at a Sortie draft, ahead of upstream's own handler."""
    global _patched
    if _patched:
        return

    def install():
        utils = loaded("utils")
        utils_sortie = loaded("utils_sortie")
        if utils is None or utils_sortie is None:
            return

        wrap(utils, "handle_confirm", lambda confirm: confirming_our_pick(confirm, utils, utils_sortie), "confirms a draft only once it has picked")
        insert_before("handle_member_selection", drafting(utils, utils_sortie))

    register(install)
    _patched = True
