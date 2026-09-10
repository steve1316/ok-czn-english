"""The English that upstream's Chinese log lines and dashboard rows come out as.

Data only - the matching lives in `src/en/log_text.py`. Split from it so a translation commit reads as a diff
of string pairs rather than of logic.

Both tables are keyed on the string as it was *written* in `ok_tasks/`, which is what
`scripts/scan_log_strings.py` prints. `MESSAGES` holds the lines with nothing interpolated. `TEMPLATES` holds
the rest, with each interpolation written `{}` on the left and `{0}`, `{1}` on the right, so the English can
put them in its own order. Storing shapes rather than regexes keeps the keys diffable against the extractor by
plain equality, and keeps anyone from having to hand-escape the parens sitting in a line like
`点击目标坐标=({}, {})`.

A shape with no entry is left in Chinese. That is the intended failure: `scan_log_strings.py --missing` names
it and `tests/TestLogText.py` fails on the coverage floor, where a half-translated line would just read as a
bug in the tool.

The Tasks tab's Info rows come through the same tables, because `info_set` is patched alongside the logging
methods. Three of those rows are composed at runtime, so no catalog entry could ever have reached them - which
is why they are here rather than in `ok.po`.
"""

# Lines written with nothing interpolated, keyed on the exact string. The run-status rows come first: those are
# `info_set` keys from `log_node_status` and `log_credit` rather than log lines, and they are what the Tasks tab
# draws down its Info column.
MESSAGES = {
    "当前信用点": "Credits",
    "版本号": "Version",
    "游戏语言": "Game Language",
    "所处层数，节点，类型": "Floor, node, type",
    "是否到达关底boss": "Boss node reached",
    "是否进入关底boss战斗": "Boss fight entered",
    "是否已逃脱": "Escaped",
    "是否已获得特定闪光": "Target Epiphany taken",
    "获取刷存档主战员头像": "Target portrait captured",
    "本局已移除卡牌": "Cards removed this run",
    "本局已获得中立牌": "Neutral cards taken this run",
    "装备信息": "Equipment",
    "当前胜率": "Win rate",
}

# Lines written as f-strings, keyed on the literal runs with each interpolation collapsed to `{}`.
TEMPLATES = {
    # One Info row per card the run is meditating on, so the card's name is the interpolation.
    "冥想：{}": "Meditating on {0}",
    # The two rows a catalog cannot reach. The equipment row is a join, but always over exactly three slots,
    # so it still renders as one fixed shape.
    "第{}层，第{}节点，{}": "floor {0}, node {1}, {2}",
    "{}号位：{}，{}号位：{}，{}号位：{}": "slot {0} {1}, slot {2} {3}, slot {4} {5}",
}

# What a template's interpolations may themselves say. Several of them are handed a Chinese constant rather
# than a number - the `page=` label upstream gives a card read, the action word on a card screen - so without
# these a translated line still comes out with Chinese in the middle of it. Exact matches only: anything not
# listed is runtime data, usually a card name off the screen, and passes through untouched.
VALUES = {
    # The route node types, from the `node_types` map in `ok_tasks/utils.py`. The first four are spelled the
    # way `i18n/en_US/LC_MESSAGES/ok.po` already spells them for the Route Priority setting, so the log and the
    # settings screen cannot drift apart.
    "休息": "Safe Zones",
    "事件": "Unidentified Area",
    "小怪": "Normal Battle Area",
    "精英": "Elite Battle Area",
    "结算": "Settlement",
    "当前位置": "current position",
    # What the equipment row says about a slot with nothing in it.
    "空": "empty",
}
