"""The Auto Analysis setting, which turns on recording what the game's own Auto plays.

`observe.py` records Chaos battles for `scripts/study_auto.py`, at the cost of extra OCR on every battle frame and, with the burst
grabs, a second OCR engine. Upstream has no such recorder, so the fork keeps it off until this is on.
"""

from ok import ConfigOption, og

# The switch's label, and the key it is saved under.
LABEL = "Auto Analysis"
# The line under the label.
DESCRIPTION = "Record what the game's Auto plays in Chaos battles, for offline study. Costs extra OCR on every battle frame."
# The file under `configs/` the switch is saved to. It doubles as the section's name, which `ok.po` turns into its title.
CONFIG_NAME = "auto_analysis"

# Listed in `global_configs`, which is what puts it on the Settings page.
analysis_option = ConfigOption(CONFIG_NAME, {LABEL: False}, config_description={LABEL: DESCRIPTION})


def enabled():
    """Say whether Auto Analysis is switched on.

    Returns:
        True once the switch on the Settings page is on.
    """
    return bool(og.global_config.get_config(analysis_option).get(LABEL))
