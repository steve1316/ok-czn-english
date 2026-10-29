"""Stop spending Reason on Sortie rewards once there is none left, rather than pressing Confirm forever or Obtain for nothing.

Upstream's `handle_rational_supply` cancels the dialog and turns off reward claiming, but it sits far below `handle_center_confirm`, which
presses any centred Confirm first, greyed out or not. A run out of Reason then loops on "Insufficient quantity." until it is stopped.
"""

from src.en.dice import find_currency
from src.en.handlers import answering, insert_before, loaded, register, wrap

SETTLEMENT_TAG = "skips Obtain without Reason"

_patched = False


def claiming_with_reason(task, claiming):
    """Read the reward claiming setting as off while the Settlement page's top-right counter shows no Reason to pay for Obtain with.

    Only for this read, so the setting is still on once Reason has come back.

    Args:
        task: The running task, on the Settlement page.
        claiming: The reward claiming setting as upstream read it.

    Returns:
        False when the counter reads 0, otherwise the setting as it was.
    """
    counter = find_currency(task.all_texts or [], task.width, task.height)
    return claiming and (counter is None or counter[0] > 0)


def skipping_obtain(handler, utils_sortie):
    """Run upstream's Settlement handler with reward claiming read through `claiming_with_reason`.

    Args:
        handler: The `handle_sortie_reward_settlement` currently installed.
        utils_sortie: Upstream's Sortie module, whose `_get_config_value` the handler reads the setting through.

    Returns:
        The wrapped handler.
    """
    def handle_sortie_reward_settlement(task):
        with answering(utils_sortie, "领取奖励", claiming_with_reason):
            return handler(task)

    return handle_sortie_reward_settlement


def apply():
    """Run upstream's Charge Reason handler ahead of the centre Confirm, and skip Obtain on a Settlement page with no Reason."""
    global _patched
    if _patched:
        return

    def install():
        utils_sortie = loaded("utils_sortie")
        if utils_sortie is None:
            return

        # Under its own name, since `insert_before` skips a handler whose name the list already holds further down.
        def handle_charge_reason(task):
            return utils_sortie.handle_rational_supply(task)

        insert_before("handle_center_confirm", handle_charge_reason)
        wrap(utils_sortie, "handle_sortie_reward_settlement", lambda handler: skipping_obtain(handler, utils_sortie), SETTLEMENT_TAG)

    register(install)
    _patched = True
