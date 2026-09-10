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

# Lines written with nothing interpolated, keyed on the exact string. The run-status rows come first: those
# are `info_set` keys from `log_node_status` and `log_credit` rather than log lines, and they are what the
# Tasks tab draws down its Info column.
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
    "检测到最终boss战斗开始，final_boss_battle=True": "final boss fight started, final_boss_battle=True",
    "检测到页面中央确认按钮，点击确认": "Confirm button in the centre of the page, clicking it",
    "点击屏幕事件，点击屏幕": "tap-the-screen prompt, tapping",
    "handle_shop: 通过页面判定（移除卡牌或售罄）": "handle_shop: page identified by its Remove Card or Sold Out text",
    "检测到路线选择页面，按优先级依次点击节点": "route selection screen, clicking nodes in priority order",
    "检测到路线选择页面，更新 node_status['flash_or_rest']=True":
        "route selection screen, setting node_status['flash_or_rest']=True",
    "进入商店配置为True，更新 node_status['shop']=True": "Enter Shop is set, so node_status['shop']=True",
    "小地图规划与当前节点识别一致，按规划结果进入": "the minimap plan agrees with the node just read, entering as planned",
    "_hand_cards: 单张卡牌，分配按键1": "_hand_cards: one card in hand, assigning key 1",
    "德朗商店: 移除卡牌已售罄": "Dellang Shop: card removal is sold out",
    "检测到获得奖励页面，点击领取": "reward screen, clicking Claim",
    "检测到装备页面": "equipment screen",
    "检测到休息界面，点击休息": "Safe Zone screen, resting",
}

# Lines written as f-strings, keyed on the literal runs with each interpolation collapsed to `{}`.
TEMPLATES = {
    "冥想：{}": "Meditating on {0}",
    "第{}层，第{}节点，{}": "floor {0}, node {1}, {2}",
    "{}号位：{}，{}号位：{}，{}号位：{}": "slot {0} {1}, slot {2} {3}, slot {4} {5}",
    "当前生命值: {}/{} = {}%": "health {0}/{1} = {2}%",
    "自动战斗按钮区域白色占比: {}": "auto-battle button area, white share {0}",
    "_hand_card_names 区域: cx=[{}, {}], cy=[{}, {}]": "_hand_card_names region: cx=[{0}, {1}], cy=[{2}, {3}]",
    "_hand_card_names 区域共{}个文本，过滤后剩{}个: {}":
        "_hand_card_names region held {0} texts, {1} left after filtering: {2}",
    "_hand_cards: 识别到 {} 张手牌: {}": "_hand_cards: read {0} cards in hand: {1}",
    "小地图连接: 节点{} -> 节点{}，亮线覆盖率={}": "minimap link: node {0} -> node {1}, lit-line coverage {2}",
    "_hand_cards: 卡牌「{}」 left_x={} 基于「{}」(key={}) offset={} → {}":
        "_hand_cards: card {0} left_x={1} from {2} (key={3}) offset={4} -> {5}",
    "手牌数 OCR 识别为{}，纠正为{}": "hand count read as {0}, corrected to {1}",
    "小地图节点{}: 类型={}，第{}列第{}个，位置=({}, {})，特征={}，置信度={}，特殊标志={}，特殊优先级={}":
        "minimap node {0}: type={1}, column {2} item {3}, at ({4}, {5}), feature={6}, confidence={7}, "
        "special flag={8}, special priority={9}",
    "_hand_cards: 最小间距={}": "_hand_cards: minimum spacing {0}",
    "{}卡牌识别调试: 特征={}，特征中心=({},{})，特征置信度={}，名称区域={}，名称OCR={}，类型区域={}，类型OCR={}，描述区域={}":
        "{0}card recognition: feature={1}, centre=({2},{3}), confidence={4}, name region={5}, name OCR={6}, "
        "type region={7}, type OCR={8}, description region={9}",
    "_hand_cards: 卡牌「{}」 left_x={} → 最左卡牌分配按键1":
        "_hand_cards: card {0} left_x={1} -> leftmost card takes key 1",
    "{}卡牌{}: 名称=「{}」，类型=「{}」，描述=「{}」，特征={}，置信度={}":
        "{0}card {1}: name={2}, type={3}, description={4}, feature={5}, confidence={6}",
    "{}卡牌「{}」是否选中={}，金色边框得分={}，上={}，下={}，左={}，右={}":
        "{0}card {1} selected={2}, gold border score={3}, top={4}, bottom={5}, left={6}, right={7}",
    "德朗商店第{}个商品: 类型={}，名称=「{}」，价格={}": "Dellang Shop item {0}: type={1}, name={2}, price={3}",
    "页面处理「{}」触发点击事件，点击目标坐标=({}, {})": "page handler {0} clicked at ({1}, {2})",
    "{}事件选项{}: 描述=「{}」，特征={}，置信度={}": "{0}event option {1}: description={2}, feature={3}, confidence={4}",
    "{}卡牌识别调试: 因名称为空排除该特征": "{0}card recognition: feature dropped, its name read empty",
    "{}卡牌识别到{}张卡牌": "{0}read {1} cards",
    "德朗商店: {}特征绑定第{}个信用点图标": "Dellang Shop: {0} feature bound to credit icon {1}",
    "按钮左侧区域颜色: B={}, G={}, R={}, 是否禁用灰色={} (范围{}-{}, 最大差异={})":
        "button left-hand area colour: B={0}, G={1}, R={2}, disabled grey={3} (range {4}-{5}, spread {6})",
    "{}识别到{}个事件选项": "{0}read {1} event options",
    "第{}号主战员leveltag: 中心=({}, {})，置信度={}": "combatant {0} leveltag: centre ({1}, {2}), confidence {3}",
    "第{}号装备位颜色RGB={}，识别品质={}": "equipment slot {0} colour RGB={1}, quality read as {2}",
    "{}未检测到选中卡牌的金色边框": "{0}no gold border found, so no card is selected",
    "{}: 点({}, {})颜色=B{}/G{}/R{}，是否白色={}": "{0}: point ({1}, {2}) colour B{3}/G{4}/R{5}, white={6}",
    "离开路线选择页面，当前节点计数: {}": "leaving the route selection screen, node count now {0}",
    "{}卡牌识别调试: 因类型或描述缺失排除该特征，类型=「{}」，描述=「{}」":
        "{0}card recognition: feature dropped, type or description missing - type={1}, description={2}",
    "路线优先级配置: {}": "Route Priority setting: {0}",
    "识别到的路线节点: {}": "route nodes read: {0}",
    "小地图当前位置X={}，过滤X小于{}的已走过节点，排除{}个普通节点特征":
        "minimap position X={0}, dropping visited nodes with X below {1}, {2} ordinary node features excluded",
    "小地图识别到{}个节点、{}条亮线连接": "minimap read {0} nodes and {1} lit-line links",
    "小地图有向邻接关系: {}": "minimap directed adjacency: {0}",
    "小地图规划路线={}，下一列第{}个节点，预计={}+{}，当前节点识别={}+{}":
        "minimap planned route={0}, next column item {1}, expected={2}+{3}, node read={4}+{5}",
    "更新 node_type 为「{}」": "node_type set to {0}",
    "点击{}节点（特殊特征: {}，位置: {}, {}）": "clicking the {0} node (special feature {1}, at {2}, {3})",
    "{}: 在({}, {}){}滚动": "{0}: scrolling {3} at ({1}, {2})",
    "德朗商店挑选商品: 当前信用点={}": "Dellang Shop, choosing an item: {0} credits",
}

# What a template's interpolations may themselves say. Several are handed a Chinese constant rather than a
# number - the `page=` label upstream prefixes a card read with, a node type, a scroll direction - so
# without these a translated line still comes out with Chinese in the middle of it. Exact matches only:
# anything not listed is runtime data, usually a card name off the screen, and passes through untouched.
VALUES = {
    "休息": "Safe Zones",
    "事件": "Unidentified Area",
    "小怪": "Normal Battle Area",
    "精英": "Elite Battle Area",
    "结算": "Settlement",
    "当前位置": "current position",
    "空": "empty",
    "向下": "down",
    "向上": "up",
    "主战员选择页面: ": "Combatant Select: ",
    "事件任务页面: ": "Event Task: ",
    "人格面具卡牌获得页面: ": "Persona Card Obtained: ",
    "卡牌分配页面: ": "Card Assign: ",
    "卡牌功能选择页面: ": "Card Function Select: ",
    "卡牌奖励页面: ": "Card Reward: ",
    "卡牌闪光页面: ": "Card Epiphany: ",
    "复制卡牌选择页面: ": "Duplicate Card Select: ",
    "安装装备页面: ": "Install Equipment: ",
    "尼娅的好奇心页面: ": "Nia's Curiosity: ",
    "画面卡住兜底: ": "stuck-screen fallback: ",
    "获得卡牌页面: ": "Obtain Card: ",
    "购买卡牌页面: ": "Purchase Card: ",
    "购买装备页面: ": "Purchase Equipment: ",
    # `select_card` composes its own label from the action, and adds `-兜底` on the fallback pass.
    "select_card: ": "card select: ",
    "select_card-移除: ": "card removal: ",
    "select_card-复制: ": "card duplication: ",
    "select_card-闪光: ": "card Epiphany: ",
    "select_card-灵光: ": "card Epiphany: ",
    "select_card-冥想: ": "card meditation: ",
    "select_card-移除-兜底: ": "card removal fallback: ",
    "select_card-复制-兜底: ": "card duplication fallback: ",
    "select_card-闪光-兜底: ": "card Epiphany fallback: ",
    "select_card-灵光-兜底: ": "card Epiphany fallback: ",
    "select_card-冥想-兜底: ": "card meditation fallback: ",
}
