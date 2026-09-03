"""Dump the OCR text of a screenshot the way the running app sees it.

This is the workhorse for building `i18n/en_US/LC_MESSAGES/ocr.po`. Point it at a Global-client capture and it
prints every text box with its confidence and relative position, marking which strings the catalog already
covers. Copy the uncovered ones into `ocr.po` against the Chinese literal the handler expects.

Run `python scripts/ocr_dump.py <image> [<image> ...]`, or add `--missing` to list only uncovered strings.
"""

import argparse
import gettext
import sys
from pathlib import Path

import cv2
from onnxocr.onnx_paddleocr import ONNXPaddleOcr

REPO_ROOT = Path(__file__).resolve().parent.parent
I18N_ROOT = REPO_ROOT / "i18n"

sys.path.insert(0, str(REPO_ROOT))


def build_engine():
    """Construct the OCR engine with the same parameters the app runs with.

    Reading them from `src.config` rather than hardcoding matters: the OpenVINO and NPU paths recognise text
    slightly differently, so a catalog built against a different engine can miss boxes the app does produce.

    Returns:
        A configured `ONNXPaddleOcr` instance.
    """
    from src.config import config

    return ONNXPaddleOcr(use_angle_cls=False, **config.get("ocr", {}).get("params", {}))


def load_catalog(locale="en_US"):
    """Load the reverse OCR catalog the framework would apply to recognised text.

    Args:
        locale: Locale directory name under `i18n/`.

    Returns:
        A `gettext` translation object, or None when the locale has no compiled catalog.
    """
    try:
        return gettext.translation("ocr", localedir=str(I18N_ROOT), languages=[locale])
    except OSError:
        return None


def is_covered(translation, text):
    """Report whether the catalog already rewrites this text.

    Mirrors the ladder in `Task.fix_texts()`: try the text as recognised, then again with spaces stripped.
    Matching that order here keeps the tool from suggesting entries the app would already have handled.

    Args:
        translation: A `gettext` translation object, or None.
        text: One recognised box name.

    Returns:
        True when the catalog maps the text or its space-stripped form.
    """
    if translation is None:
        return False
    stripped = text.strip()
    if translation.gettext(stripped) != stripped:
        return True
    no_space = stripped.replace(" ", "")
    return translation.gettext(no_space) != no_space


def run_ocr(engine, image_path):
    """Recognise every text box in one image.

    Args:
        engine: The `ONNXPaddleOcr` instance to reuse across images.
        image_path: Path to a screenshot to read.

    Returns:
        A list of `(text, confidence, rel_x, rel_y)` tuples, ordered top to bottom then left to right.

    Raises:
        SystemExit: When the image cannot be read.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise SystemExit(f"could not read image: {image_path}")
    height, width = image.shape[:2]

    boxes = []
    for quad, (text, confidence) in engine.ocr(image)[0] or []:
        centre_x = sum(point[0] for point in quad) / len(quad) / width
        centre_y = sum(point[1] for point in quad) / len(quad) / height
        boxes.append((text, confidence, centre_x, centre_y))
    return sorted(boxes, key=lambda box: (round(box[3], 2), box[2]))


def main():
    """Entry point. Prints the OCR boxes of each image given on the command line.

    Returns:
        0 always, so the script composes in a shell pipeline.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("images", nargs="+", help="screenshots to read")
    parser.add_argument("--missing", action="store_true", help="only show strings ocr.po does not cover")
    args = parser.parse_args()

    # The console is cp1252 on a default Windows install, and game text is routinely non-Latin.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    translation = load_catalog()
    engine = build_engine()
    for image_path in args.images:
        print(f"\n=== {image_path} ===")
        for text, confidence, rel_x, rel_y in run_ocr(engine, image_path):
            covered = is_covered(translation, text)
            if args.missing and covered:
                continue
            print(f"{'  ' if covered else '->'} {confidence:.3f}  ({rel_x:.3f}, {rel_y:.3f})  {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
