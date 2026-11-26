"""The Auto Analysis settings: recording what the game's own Auto plays, and drafting Sortie combatants for kit coverage.

`observe.py` records Chaos battles for `scripts/study_auto.py`, at the cost of extra OCR on every battle frame and, with the burst
grabs, a second OCR engine. Drafting the least played combatant ignores the role the team lacks. Upstream has neither, so both stay off.
"""

from ok import ConfigOption, og

# The recording switch's label, and the key it is saved under.
LABEL = "Auto Analysis"
# The line under the label.
DESCRIPTION = "Record what the game's Auto plays in Chaos battles, for offline study. Costs extra OCR on every battle frame."
# The coverage draft's label, and the key it is saved under.
DRAFT_LABEL = "Draft Least Played"
# The line under that label.
DRAFT_DESCRIPTION = ("In Sortie, draft the combatant who has played the fewest cards so far, so every kit gets run live. "
                     "Off, the draft fills the role the team lacks.")
# The file under `configs/` the switch is saved to. It doubles as the section's name, which `ok.po` turns into its title.
CONFIG_NAME = "auto_analysis"

# Listed in `global_configs`, which is what puts it on the Settings page.
analysis_option = ConfigOption(CONFIG_NAME, {LABEL: False, DRAFT_LABEL: False}, config_description={LABEL: DESCRIPTION, DRAFT_LABEL: DRAFT_DESCRIPTION})


def switched_on(label):
    """Read one of this section's switches.

    Args:
        label: The switch's key, `LABEL` or `DRAFT_LABEL`.

    Returns:
        True once that switch on the Settings page is on, and False before the app has loaded its settings.
    """
    config = og.global_config
    return bool(config and config.get_config(analysis_option).get(label))


def enabled():
    """Say whether Auto Analysis is switched on.

    Returns:
        True once the switch on the Settings page is on.
    """
    return switched_on(LABEL)


def drafting_least_played():
    """Say whether Draft Least Played is switched on.

    Returns:
        True once its switch on the Settings page is on.
    """
    return switched_on(DRAFT_LABEL)
