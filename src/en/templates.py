"""Stand in for the one image template that is a picture of a Chinese word.

`ok_tasks/assets/` ships 79 templates and 77 of them are icons, which match the Global client unchanged. Only
two are pictures of Chinese words, and one of those - `xuanwo_in_deck`, a crop of 漩涡 - is declared in the
annotations but referenced by no code at all, which leaves `leveltag`: a crop of 等级, the caption the client
draws as "LEVEL" beside a combatant portrait.

Losing it is not cosmetic. `_find_member_level_tags` counts those captions to learn how many combatants
are on screen, so zero matches reads as "nobody can take this equipment" and the equipment gets extracted for
credits instead of equipped.

The catalog cannot help here - it rewrites OCR text, and this is template matching - so the fallback reads the
English caption out of the OCR pass the handler has already run and hands back boxes shaped like the ones the
template would have produced.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# Each template that is a picture of a word, and the English caption drawn in its place.
TEXT_TEMPLATES = {
    "leveltag": "LEVEL",
}

_patched = False


def boxes_in(task, region, caption):
    """Find the OCR boxes inside a region whose text is the given caption.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        region: The `Box` the caller restricted the search to, or None for the whole frame.
        caption: The English caption the template stood for.

    Returns:
        A list of matching boxes, which may be empty.
    """
    wanted = caption.casefold()
    found = []
    for box in getattr(task, "all_texts", None) or []:
        if box.name.strip().casefold() != wanted:
            continue
        if region is not None:
            center_x = box.x + box.width / 2
            center_y = box.y + box.height / 2
            inside_x = region.x <= center_x <= region.x + region.width
            inside_y = region.y <= center_y <= region.y + region.height
            if not (inside_x and inside_y):
                continue
        found.append(box)
    return found


def resolve(found, feature_name, task, region):
    """Decide what a feature search should return once the real template has had its turn.

    Args:
        found: What matching the real template produced.
        feature_name: The template that was searched for.
        task: The running task, whose `all_texts` holds the current OCR pass.
        region: The `Box` the caller restricted the search to, or None.

    Returns:
        The original result whenever there was one, otherwise the English captions standing in for it.
    """
    # Only step in when the template genuinely matched nothing, so a Chinese client is never affected.
    # `find_one` searches several templates at once by passing a list, and none of those groups name a
    # Chinese-text template, so anything that is not a single name is left alone.
    if found or not isinstance(feature_name, str) or feature_name not in TEXT_TEMPLATES:
        return found
    caption = TEXT_TEMPLATES[feature_name]
    fallback = boxes_in(task, region, caption)
    if fallback:
        logger.debug(f"{feature_name} template found nothing, matched {len(fallback)} boxes on {caption}")
    return fallback


def apply():
    """Fall back to the English caption when a Chinese-text template finds nothing."""
    global _patched
    if _patched:
        return
    from ok.task.task import FindFeature

    original_find_feature = FindFeature.find_feature

    def patched_find_feature(self, feature_name=None, *args, **kwargs):
        found = original_find_feature(self, feature_name, *args, **kwargs)
        return resolve(found, feature_name, self, kwargs.get("box"))

    FindFeature.find_feature = patched_find_feature
    _patched = True
