"""Pick the best combatant offered at a Sortie draft, and reroll when none of them will do.

Upstream refreshes all three slots whenever no configured name matches, then picks at random - so with no
priority list it spends both rerolls and still takes whatever it lands on.
"""

from ok import Logger

from src.en.handlers import insert_before, loaded, register

logger = Logger.get_logger(__name__)

# The five roles a draft card can carry, best first. `Attack` reaches us as 攻击力, because the catalog
# rewrites that word for the card type label and the equipment stat row, which share it.
ROLES = ("Core", "Attack", "Support", "Healing", "Protection")
ROLE_READINGS = {"Core": ("core",), "Attack": ("attack", "攻击力"), "Support": ("support",),
                 "Healing": ("healing",), "Protection": ("protection",)}
# Rerolling is only worth a slot when nothing on offer does damage.
GOOD_ENOUGH = ("Core", "Attack")

# The band the three cards occupy, and how far a badge may sit from a slot to belong to it.
CARD_REGION = (0.077, 0.100, 0.946, 0.871)
SAME_CARD = 0.12
# The reroll counter reads "1/1" while a slot still has its reroll, and "0/1" once it is spent.
SPENT_REROLL = "0/"

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


def rank(role):
    """Score a role, lowest first.

    Args:
        role: A role name, or None when the card's badge was not read.

    Returns:
        The role's position in `ROLES`, or one past the end when unknown.
    """
    return ROLES.index(role) if role in ROLES else len(ROLES)


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

        def handle_member_draft(task):
            prompt = utils.find_box_at_point(task, 0.500, 0.931)
            if not (prompt and utils._get_game_text(task, "主战员") in prompt.name):
                return False
            if utils._get_card_list(task, "主战员优先级"):
                # A configured priority is upstream's to honour, so stand aside entirely.
                return False

            slots = [slot for slot in utils_sortie._read_member_slots(task) if slot.get("name")]
            if not slots:
                return False
            found = badges(task)
            ranked = sorted(((rank(role_for(slot, found)), slot) for slot in slots), key=lambda pair: pair[0])
            best_rank, best = ranked[0]
            best_role = ROLES[best_rank] if best_rank < len(ROLES) else None

            if best_role not in GOOD_ENOUGH:
                spendable = [slot for slot in slots if rerollable(task, slot)]
                if spendable:
                    task.log_info(f"draft offers no {' or '.join(GOOD_ENOUGH)}, rerolling {len(spendable)} slot(s)")
                    for slot in spendable:
                        utils._move_and_click(task, slot["x"], slot["refresh_y"])
                        task.sleep(1)
                    return True

            task.log_info(f"draft taking {best['name']} ({best_role or 'role unread'})")
            utils._move_and_click(task, best["x"], best["y"])
            task.sleep(1)
            return True

        insert_before("handle_member_selection", handle_member_draft)

    register(install)
    _patched = True
