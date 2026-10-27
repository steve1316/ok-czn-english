"""Back out of the Charge Reason dialog when there is no Aether to charge with, rather than pressing its Confirm forever.

Upstream's `handle_rational_supply` cancels the dialog and turns off reward claiming, but it sits far below `handle_center_confirm`, which
presses any centred Confirm first, greyed out or not. A run out of Reason then loops on "Insufficient quantity." until it is stopped.
"""

from src.en.handlers import insert_before, loaded, register

_patched = False


def apply():
    """Run upstream's Charge Reason handler ahead of the centre Confirm in every mode that has both."""
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

    register(install)
    _patched = True
