#!/usr/bin/env python3
"""Generate a thicker-outline variant of FestivalMeongi (Cafe24 Meongi W style).

Requires: pip install fonttools pyclipper

Usage:
  python3 tools/thicken_meongi_outline.py

Output:
  assets/fonts/FestivalMeongiOutlineThick.ttf
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".font_tools"))

try:
    import pyclipper
except ImportError:
    print("Install pyclipper: pip install pyclipper", file=sys.stderr)
    sys.exit(1)

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

SRC = ROOT / "assets/fonts/FestivalMeongi.ttf"
OUT = ROOT / "assets/fonts/FestivalMeongiOutlineThick.ttf"

SCALE = 64
DELTA = -3.125  # Thick outline used after fixing hollow web rendering.
FAMILY = "FestivalMeongiOutlineThick"


def contour_area(pts: list[tuple[float, float]]) -> float:
    area = 0.0
    for i in range(len(pts) - 1):
        area += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return area / 2


def offset_contour(pts: list[tuple[float, float]], delta: float) -> list[tuple[float, float]]:
    source_area = contour_area(pts)
    int_path = [(int(round(x * SCALE)), int(round(y * SCALE))) for x, y in pts]
    if len(int_path) > 1 and int_path[0] == int_path[-1]:
        int_path = int_path[:-1]
    if len(int_path) < 3:
        return pts

    sign = 1 if contour_area(pts) < 0 else -1
    pco = pyclipper.PyclipperOffset(miter_limit=2.0, arc_tolerance=0.25 * SCALE)
    pco.AddPath(int_path, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    result = pco.Execute(sign * delta * SCALE)
    if not result:
        return pts

    best = max(result, key=lambda p: abs(pyclipper.Area(p)))
    out = [(p[0] / SCALE, p[1] / SCALE) for p in best]
    if out[0] != out[-1]:
        out.append(out[0])
    if source_area and contour_area(out) * source_area < 0:
        out = list(reversed(out))
    return out


def extract_contours(glyph) -> list[list[tuple[float, float]]]:
    if glyph.numberOfContours <= 0:
        return []
    coords = glyph.coordinates
    end_pts = glyph.endPtsOfContours
    start = 0
    contours = []
    for end in end_pts:
        pts = [(float(coords[i][0]), float(coords[i][1])) for i in range(start, end + 1)]
        contours.append(pts)
        start = end + 1
    return contours


def build_glyph(contours: list[list[tuple[float, float]]]):
    pen = TTGlyphPen(None)
    for pts in contours:
        if len(pts) < 2:
            continue
        pen.moveTo(pts[0])
        for point in pts[1:]:
            pen.lineTo(point)
        pen.closePath()
    return pen.glyph()


def set_name(font: TTFont, name_id: int, string: str, platform=(3, 1, 0x409)) -> None:
    font["name"].setName(string, name_id, platform[0], platform[1], platform[2])


def main() -> None:
    font = TTFont(SRC)
    glyf = font["glyf"]

    for gname in font.getGlyphOrder():
        glyph = glyf[gname]
        if glyph.numberOfContours <= 0:
            continue
        contours = extract_contours(glyph)
        glyf[gname] = build_glyph([offset_contour(c, DELTA) for c in contours])

    set_name(font, 1, FAMILY)
    set_name(font, 2, "Regular")
    set_name(font, 4, f"{FAMILY} Regular")
    set_name(font, 6, f"{FAMILY}-Regular")
    set_name(font, 1, FAMILY, platform=(1, 0, 0))
    set_name(font, 4, f"{FAMILY} Regular", platform=(1, 0, 0))
    set_name(font, 6, f"{FAMILY}-Regular", platform=(1, 0, 0))

    font.save(OUT)
    font.close()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
