"""Claim Sortie rewards with Reason alone, never buying more Reason with Aether.

Upstream presses Obtain whatever Reason is left, and `handle_center_confirm` then pays Aether in the Charge Reason dialog that follows. Its
own `handle_rational_supply` only backs out when Confirm is greyed, and sits too far down the list to get there first.
"""

from src.en.dice import find_currency
from src.en.handlers import answering, insert_before, loaded, register, wrap
from src.en.screen import text_in_region

# The dialog's title as `ocr.po` rewrites it, the band upstream finds it in, and the button that backs out without charging.
CHARGE_REASON = "补充理性"
CHARGE_REASON_REGION = (0.438, 0.101, 0.561, 0.250)
DECLINE_POINT = (0.352, 0.774)
# Set in `node_status` once the dialog was declined. Upstream rebuilds `node_status` on Enter, so the next run tries again.
OUT_OF_REASON = "_en_out_of_reason"
CLAIMING = "领取奖励"
SETTLEMENT_TAG = "skips Obtain without Reason"
CLAIM_TAG = "skips the loot without Reason"

_patched = False


def claiming_with_reason(task, claiming):
    """Read the reward claiming setting as off while this run has no Reason to claim with.

    Only for this read, so the setting is still on once Reason has come back.

    Args:
        task: The running task, on the Settlement page or the Chaos Loot dialog.
        claiming: The reward claiming setting as upstream read it.

    Returns:
        False when the Charge Reason dialog was declined this run or the top-right counter reads 0, otherwise the setting as it was.
    """
    if (getattr(task, "node_status", None) or {}).get(OUT_OF_REASON):
        return False
    counter = find_currency(task.all_texts or [], task.width, task.height)
    return claiming and (counter is None or counter[0] > 0)


def with_reason_only(handler, utils_sortie):
    """Run one of upstream's reward handlers with reward claiming read through `claiming_with_reason`.

    Args:
        handler: `handle_sortie_reward_settlement` or `handle_sortie_reward_claim`, as currently installed.
        utils_sortie: Upstream's Sortie module, whose `_get_config_value` the handler reads the setting through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        with answering(utils_sortie, CLAIMING, claiming_with_reason):
            return handler(task)

    return wrapped


def charge_reason_handler(utils_sortie):
    """Build the handler that backs out of the Charge Reason dialog, so Aether is never spent on Reason.

    Args:
        utils_sortie: Upstream's Sortie module, for its click helper.

    Returns:
        The handler.
    """
    def handle_charge_reason(task):
        if text_in_region(task, CHARGE_REASON, CHARGE_REASON_REGION) is None:
            return False
        task.log_info("out of Reason, so declining to charge it with Aether and leaving the rest of this run's rewards")
        task.node_status[OUT_OF_REASON] = True
        utils_sortie._move_and_click(task, *DECLINE_POINT)
        task.sleep(1)
        return True

    return handle_charge_reason


def apply():
    """Back out of the Charge Reason dialog ahead of the centre Confirm, and skip Obtain and the loot without Reason."""
    global _patched
    if _patched:
        return

    def install():
        utils_sortie = loaded("utils_sortie")
        if utils_sortie is None:
            return
        insert_before("handle_center_confirm", charge_reason_handler(utils_sortie))
        wrap(utils_sortie, "handle_sortie_reward_settlement", lambda handler: with_reason_only(handler, utils_sortie), SETTLEMENT_TAG)
        wrap(utils_sortie, "handle_sortie_reward_claim", lambda handler: with_reason_only(handler, utils_sortie), CLAIM_TAG)

    register(install)
    _patched = True
