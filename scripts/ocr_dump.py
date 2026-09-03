"""Dump the OCR text of a screenshot the way the running app sees it.

This is the workhorse for building `i18n/en_US/LC_MESSAGES/ocr.po`. Point it at a Global-client capture and it
prints every text box with its confidence and relative position, marking which strings the catalog already
covers. Copy the uncovered ones into `ocr.po` against the Chinese literal the handler expects.

Run `python scripts/ocr_dump.py <image> [<image> ...]`, or add `--missing` to list only uncovered strings.
"""

import argparse
import sys
from pathlib import Path

import cv2
import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
OCR_PO = REPO_ROOT / "i18n" / "en_US" / "LC_MESSAGES" / "ocr.po"


def covered_msgids():
    """Read the msgids the reverse OCR catalog already maps.

    Returns:
        A set of msgid strings, empty when the catalog does not exist yet.
    """
    if not OCR_PO.exists():
        return set()
    return {e.msgid for e in polib.pofile(str(OCR_PO)) if not e.obsolete and e.msgid}


def run_ocr(image_path):
    """Recognise every text box in one image using the same engine the app configures.

    Args:
        image_path: Path to a screenshot to read.

    Returns:
        A list of `(text, confidence, rel_x, rel_y)` tuples, ordered top to bottom then left to right.

    Raises:
        SystemExit: When the image cannot be read.
    """
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr

    image = cv2.imread(str(image_path))
    if image is None:
        raise SystemExit(f"could not read image: {image_path}")
    height, width = image.shape[:2]

    ocr = ONNXPaddleOcr(use_angle_cls=False, use_openvino=False)
    results = ocr.ocr(image)[0] or []

    boxes = []
    for quad, (text, confidence) in results:
        xs = [point[0] for point in quad]
        ys = [point[1] for point in quad]
        centre_x = sum(xs) / len(xs) / width
        centre_y = sum(ys) / len(ys) / height
        boxes.append((text, confidence, centre_x, centre_y))
    return sorted(boxes, key=lambda b: (round(b[3], 2), b[2]))


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

    covered = covered_msgids()
    for image_path in args.images:
        print(f"\n=== {image_path} ===")
        for text, confidence, rel_x, rel_y in run_ocr(image_path):
            is_covered = text in covered or text.replace(" ", "") in covered
            if args.missing and is_covered:
                continue
            mark = "  " if is_covered else "->"
            print(f"{mark} {confidence:.3f}  ({rel_x:.3f}, {rel_y:.3f})  {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
