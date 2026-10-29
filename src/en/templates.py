"""Make the image templates that miss on the Global client match it again.

`ok_tasks/assets/` ships 79 templates and nearly all of them match the Global client unchanged. `leveltag` is a
crop of 等级, the caption the client draws as "LEVEL" beside a combatant portrait, and the camp's free Epiphany icon
comes in more sizes than the two templates upstream ships for it. A card-type icon can also match the sparkle beside a party card's portrait.
"""

import cv2
from ok import Logger

from src.en.handlers import loaded, register, standing_in, wrap
from src.en.screen import centre_of

logger = Logger.get_logger(__name__)

# Each template that is a picture of a word, and the captions drawn in its place. Both forms are listed
# because the catalog may rewrite the English one: `LV` is already mapped to 等级 for the draft screen, and
# mapping `LEVEL` too would otherwise leave this looking for a string that no longer reaches it.
# Losing `leveltag` is not cosmetic. `_find_member_level_tags` counts those captions to learn how many
# combatants are on screen, so zero matches reads as "nobody can take this equipment" and the piece is
# extracted for credits instead of equipped. The catalog cannot help - it rewrites OCR text, and this is
# template matching - so the fallback reads the English caption out of the OCR pass the handler already ran.
TEXT_TEMPLATES = {
    "leveltag": ("LEVEL", "等级"),
}
# Each template the Global client also draws at another size, and that size as a factor of the template's own. The camp's
# Epiphany icon comes in three sizes and `handle_rest` tries both templates: each matches one size as is (0.97) and the next
# size up at 1.1x (0.95-0.97), while every other pairing scores 0.51-0.75 against the 0.8 cutoff. Replacing a template with
# its 1.1x copy loses the size it matched as is. At 1.1x `special_flash_luosi` scored no higher than 0.67 on any of 850
# frames in `captures/`.
EXTRA_SIZES = {
    "special_flash_luosi": 1.1,
    "special_flash_luosi2": 1.1,
}

# The function every card recognizer reads through, and the name of this change on it.
RECOGNIZER = "_recognize_cards_by_features"
NAMED_TAG = "named icons only"

_patched = False


def boxes_in(task, region, captions):
    """Find the OCR boxes inside a region whose text is one of the given captions.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        region: The `Box` the caller restricted the search to, or None for the whole frame.
        captions: The captions the template stood for.

    Returns:
        A list of matching boxes, which may be empty.
    """
    wanted = {caption.casefold() for caption in captions}
    found = []
    for box in getattr(task, "all_texts", None) or []:
        if box.name.strip().casefold() not in wanted:
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
    captions = TEXT_TEMPLATES[feature_name]
    fallback = boxes_in(task, region, captions)
    if fallback:
        logger.debug(f"{feature_name} template found nothing, matched {len(fallback)} boxes on {captions}")
    return fallback


def find_at_any_size(find, get_feature, feature_name, **kwargs):
    """Search for a template at its own size, then at the other size the Global client draws it if that found nothing.

    Args:
        find: Upstream's `find_feature`, taking a template name and its keyword arguments.
        get_feature: Looks up a loaded `Feature` by name, for the template to resize.
        feature_name: The template, or list of templates, the caller searched for.
        **kwargs: The caller's own search arguments, passed through unchanged.

    Returns:
        The matches at the template's own size when there are any, otherwise those at the other size.
    """
    found = find(feature_name, **kwargs)
    if found or kwargs.get("template") is not None:
        return found
    for name in feature_name if isinstance(feature_name, list) else [feature_name]:
        factor = EXTRA_SIZES.get(name)
        if factor:
            template = cv2.resize(get_feature(name).mat, None, fx=factor, fy=factor, interpolation=cv2.INTER_LINEAR)
            found = found + find(name, **{**kwargs, "template": template})
    return found


def name_region(task, box, offsets):
    """Work out where a card's name sits for one icon match, the way upstream's recognizer does.

    Args:
        task: The running task, for the screen's size.
        box: The card-type icon match, in pixels.
        offsets: The recognizer's `name_offsets`, as (left, top, right, bottom) from the icon's centre.

    Returns:
        The region as screen fractions, clamped to the frame.
    """
    center_x, center_y = centre_of(box, task.width, task.height)
    return (max(0.0, center_x + offsets[0]), max(0.0, center_y + offsets[1]),
            min(1.0, center_x + offsets[2]), min(1.0, center_y + offsets[3]))


def named_only(recognise, utils):
    """Wrap upstream's card recognizer so an icon match with no card name beside it never hides one that has a name.

    Upstream keeps the most confident match in each neighbourhood and drops the rest unread, then drops a match whose
    name reads empty. On the Global client the Upgrade bolt scores 0.794 on the sparkle beside a party card's portrait,
    just over the 0.79 of the Skill icon beside it, so the card was never read. Filtering the nameless matches first
    changes nothing else.

    Args:
        recognise: The recognizer to wrap, upstream's or another patch's.
        utils: The module holding `_get_region_text`.

    Returns:
        The wrapped recognizer.
    """
    def wrapped(task, *args, **kwargs):
        offsets = kwargs.get("name_offsets")
        if offsets is None:
            return recognise(task, *args, **kwargs)
        find_feature = task.find_feature

        def named(*inner_args, **inner_kwargs):
            kept = []
            for box in find_feature(*inner_args, **inner_kwargs) or []:
                if utils._get_region_text(task, name_region(task, box, offsets)).strip():
                    kept.append(box)
                else:
                    logger.debug(f"{inner_kwargs.get('feature_name')} icon at ({box.x}, {box.y}) has no card name beside it, so it is dropped")
            return kept

        with standing_in(task, find_feature=named):
            return recognise(task, *args, **kwargs)

    return wrapped


def install(utils):
    """Drop nameless icon matches before upstream's card recognizer deduplicates them.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is not None:
        wrap(utils, RECOGNIZER, lambda recognise: named_only(recognise, utils), NAMED_TAG)


def apply():
    """Fall back to the English caption when a Chinese-text template finds nothing, and read past nameless icon matches."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    from ok.task.task import FindFeature

    original_find_feature = FindFeature.find_feature

    def patched_find_feature(self, feature_name=None, *args, **kwargs):
        find = lambda name, **inner: original_find_feature(self, name, *args, **inner)
        found = find_at_any_size(find, self.get_feature_by_name, feature_name, **kwargs)
        return resolve(found, feature_name, self, kwargs.get("box"))

    FindFeature.find_feature = patched_find_feature
    _patched = True
