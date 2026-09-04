"""Check the fixed screen coordinates in `ok_tasks/` against real captures of the Global client.

Many handlers identify a page by reading whatever text box sits at a hardcoded relative point, using
`find_box_at_point`. That lookup has no tolerance at all - the point must fall strictly inside the box - so a
coordinate that was measured on the CN client silently stops matching if the Global client lays that screen out
differently. The handler then just never fires, with no error.

This reports, for every distinct coordinate in the source, which texts actually sit at that point across a
directory of captures. A coordinate that never lands on anything is a candidate for re-measuring.

Run `python scripts/check_points.py screenshots/` after capturing a run.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "ok_tasks"
CACHE_PATH = REPO_ROOT / "captures" / ".ocr_cache.json"
POINT_CALL = re.compile(r"find_box_at_point\(\s*task\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)")
DEF_LINE = re.compile(r"^def\s+(\w+)")

sys.path.insert(0, str(REPO_ROOT))


def collect_points():
    """Find every hardcoded `find_box_at_point` coordinate in the task sources.

    Returns:
        A dict of `(rel_x, rel_y)` to a sorted list of `"<file>:<line> <function>"` strings.
    """
    points = defaultdict(set)
    for path in sorted(TASKS_DIR.glob("*.py")):
        function = "?"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            named = DEF_LINE.match(line)
            if named:
                function = named.group(1)
            for match in POINT_CALL.finditer(line):
                key = (float(match.group(1)), float(match.group(2)))
                points[key].add(f"{path.name}:{number} {function}")
    return {key: sorted(value) for key, value in points.items()}


def ocr_boxes(engine, image_path):
    """Recognise one image, returning boxes as relative rectangles.

    Args:
        engine: The OCR engine to reuse.
        image_path: Path to the capture.

    Returns:
        A list of `(text, x1, y1, x2, y2)` tuples in relative coordinates, or an empty list when unreadable.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        return []
    height, width = image.shape[:2]
    boxes = []
    for quad, (text, _confidence) in engine.ocr(image)[0] or []:
        xs = [point[0] / width for point in quad]
        ys = [point[1] / height for point in quad]
        boxes.append((text, min(xs), min(ys), max(xs), max(ys)))
    return boxes


def build_cache(image_paths):
    """Recognise every capture once and remember the result on disk.

    Args:
        image_paths: The captures to read.

    Returns:
        A dict of image name to its list of boxes.
    """
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    missing = [p for p in image_paths if p.name not in cache]
    if missing:
        from ocr_dump import build_engine

        engine = build_engine()
        for index, path in enumerate(missing, start=1):
            cache[path.name] = ocr_boxes(engine, path)
            if index % 25 == 0:
                print(f"... recognised {index}/{len(missing)}", file=sys.stderr)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    return cache


def box_at(boxes, rel_x, rel_y):
    """Find the text at one point the way `find_box_at_point` does.

    Args:
        boxes: The `(text, x1, y1, x2, y2)` tuples for one frame.
        rel_x: Relative x of the point.
        rel_y: Relative y of the point.

    Returns:
        The text of the smallest box containing the point, or None.
    """
    hits = [b for b in boxes if b[1] <= rel_x <= b[3] and b[2] <= rel_y <= b[4]]
    if not hits:
        return None
    return min(hits, key=lambda b: (b[3] - b[1]) * (b[4] - b[2]))[0]


def main():
    """Entry point. Prints what text sits at each hardcoded coordinate across the captures.

    Returns:
        0 always.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", help="directory of captures to check against")
    parser.add_argument("--misses-only", action="store_true", help="only show coordinates that never matched")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    image_paths = sorted(Path(args.directory).glob("*.png"))
    if not image_paths:
        raise SystemExit(f"no captures found in {args.directory}")
    cache = build_cache(image_paths)

    points = collect_points()
    print(f"{len(points)} distinct coordinates, {len(image_paths)} captures\n")

    misses = 0
    for (rel_x, rel_y), sites in sorted(points.items(), key=lambda item: item[0]):
        found = Counter()
        for path in image_paths:
            text = box_at(cache.get(path.name, []), rel_x, rel_y)
            if text:
                found[text] += 1
        if found and args.misses_only:
            continue
        if not found:
            misses += 1
        summary = ", ".join(f"{t!r} x{n}" for t, n in found.most_common(4)) or "NEVER MATCHED"
        print(f"({rel_x:.3f}, {rel_y:.3f})  {summary}")
        for site in sites:
            print(f"    {site}")
    print(f"\n{misses} of {len(points)} coordinates never landed on any text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
