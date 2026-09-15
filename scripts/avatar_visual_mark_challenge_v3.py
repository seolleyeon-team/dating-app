"""B3-L11 — VISUAL_MARK_CHALLENGE_V3: deterministic text + graphical mark constructs (pre-registered).

Twelve positive families, each with a DEV_VARIANT and a HOLDOUT_VARIANT that
differ in synthetic string or synthetic geometry.  Alpha axis, size bands and
placements are frozen here before any detector sees a real avatar.  Real
trademarks are refused.  Family / variant / alpha / placement are evaluation
metadata only; no detector ever receives them.

Rendering never mutates the base image; derivatives live only in memory or in
the restricted local scratch.  The family truth of the low-alpha text family
is a LOW_VISIBILITY_STRESS_CONDITION (diagnostic) because no human visibility
authority exists for alpha 0.20.
"""

from __future__ import annotations

import hashlib
import math
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402

CHALLENGE_VERSION = "VISUAL_MARK_CHALLENGE_V3"
GENERATOR_VERSION = "avatar_visual_mark_challenge_v3_generator_v1"
FLORENCE_TELEMETRY_CLOSURE = "FLORENCE_TELEMETRY_TEXT_PATH_CLOSED_ON_CURRENT_CORPUS"
DEV_VARIANT = "DEV_VARIANT"
HOLDOUT_VARIANT = "HOLDOUT_VARIANT"
DEVELOPMENT_GROUPS = sel.DEVELOPMENT_GROUPS
HOLDOUT_GROUPS = sel.HOLDOUT_GROUPS
HOLDOUT_NAME = "DETECTOR_SPECIFIC_FROZEN_HOLDOUT"

ALPHAS = {"OPAQUE": 1.00, "HIGH": 0.65, "MEDIUM": 0.35, "LOW": 0.20}   # PIL RGBA alpha, normalized 0-1
SIZE_BANDS = {"small": 0.035, "medium": 0.07}                          # mark height / min(W, H)
PLACEMENTS = {
    "corner_tl": (0.02, 0.02), "corner_tr": (0.98, 0.02), "corner_br": (0.98, 0.98),
    "edge_top": (0.50, 0.02), "center": (0.50, 0.50), "torso": (0.50, 0.62), "tiled": (0.50, 0.50),
}
PLACEMENT_CLASS = {"corner_tl": "corner", "corner_tr": "corner", "corner_br": "corner", "edge_top": "edge", "center": "center", "torso": "torso", "tiled": "tiled"}
LOW_VISIBILITY_FAMILY = "TEXT_WATERMARK_TRANSLUCENT_LOW"
LOW_VISIBILITY_MARKER = "LOW_VISIBILITY_STRESS_CONDITION"
GEOMETRIES = ("symbol_circle_triangle", "symbol_hexagon_bar", "emblem_shield", "emblem_crest", "icon_ring_star", "icon_asymmetric",
              "monogram_squares", "line_emblem", "badge_ring")
TEXT_SYMBOL_SHAPES = ("diamond", "hexagon")


@dataclass(frozen=True)
class FamilyDef:
    code: str
    family: str
    kind: str                 # text | graphic | text_symbol | tiled_text
    alpha_name: str
    placement: str
    sizes: tuple              # size band names
    dev: str                  # synthetic string (text kinds) or geometry name (graphic kinds)
    holdout: str
    stroke: bool = False
    critical: bool = False    # gate family (C-J)
    diagnostic: bool = False  # LOW alpha: reported, not gated
    dev_shape: Optional[str] = None       # text_symbol only
    holdout_shape: Optional[str] = None

    def variant_value(self, variant: str) -> str:
        return self.dev if variant == DEV_VARIANT else self.holdout

    def variant_shape(self, variant: str) -> Optional[str]:
        return self.dev_shape if variant == DEV_VARIANT else self.holdout_shape


FAMILIES: tuple[FamilyDef, ...] = (
    FamilyDef("F1", "TEXT_WATERMARK_OPAQUE", "text", "OPAQUE", "torso", ("small", "medium"), "DRAFT", "PROOF", stroke=True, critical=True),
    FamilyDef("F2", "TEXT_WATERMARK_TRANSLUCENT_HIGH", "text", "HIGH", "torso", ("medium",), "PLACEHOLDER", "UNCONFIRMED", critical=True),
    FamilyDef("F3", "TEXT_WATERMARK_TRANSLUCENT_MEDIUM", "text", "MEDIUM", "torso", ("medium",), "NOT FINAL", "FOR REVIEW", critical=True),
    FamilyDef("F4", LOW_VISIBILITY_FAMILY, "text", "LOW", "torso", ("medium",), "RX7Q2", "QZ4K9", diagnostic=True),
    FamilyDef("F5", "GRAPHICAL_WATERMARK_TRANSLUCENT", "graphic", "MEDIUM", "center", ("medium",), "icon_ring_star", "icon_asymmetric", critical=True),
    FamilyDef("F6", "LOGO_LIKE_EMBLEM", "graphic", "OPAQUE", "corner_tl", ("small", "medium"), "emblem_shield", "emblem_crest", critical=True),
    FamilyDef("F7", "BRAND_LIKE_TEXT_AND_SYMBOL", "text_symbol", "OPAQUE", "corner_br", ("medium",), "VERA", "KOLT", stroke=True, dev_shape="diamond", holdout_shape="hexagon"),
    FamilyDef("F8", "SMALL_CORNER_MARK", "graphic", "OPAQUE", "corner_br", ("small",), "symbol_circle_triangle", "monogram_squares", critical=True),
    FamilyDef("F9", "EDGE_MARK", "graphic", "OPAQUE", "edge_top", ("small",), "line_emblem", "icon_asymmetric", critical=True),
    FamilyDef("F10", "CENTER_OVERLAY_MARK", "graphic", "HIGH", "center", ("medium",), "badge_ring", "emblem_crest", critical=True),
    FamilyDef("F11", "REPEATED_TILED_MARK", "tiled_text", "MEDIUM", "tiled", ("small",), "DRAFT", "PROOF"),
    FamilyDef("F12", "GRAPHIC_SYMBOL", "graphic", "OPAQUE", "corner_tr", ("small", "medium"), "symbol_circle_triangle", "symbol_hexagon_bar"),
)
FAMILY_BY_CODE = {f.code: f for f in FAMILIES}
CRITICAL_FAMILIES = tuple(f.family for f in FAMILIES if f.critical)
GATED_FAMILIES = tuple(f.family for f in FAMILIES if not f.diagnostic)   # overall recall excludes the diagnostic LOW family


def text_length_class(text: str) -> str:
    words = text.split()
    if len(words) >= 2:
        return "two_word"
    if any(ch.isdigit() for ch in text):
        return "alphanumeric"
    return "short_word" if len(text) <= 6 else "long_word"


def all_strings() -> list[str]:
    return sorted({v for f in FAMILIES if f.kind in ("text", "text_symbol", "tiled_text") for v in (f.dev, f.holdout)})


EXTRA_TRADEMARK_BLOCKLIST = ("yonsei", "seolleyeon", "coca", "cola", "apple", "samsung", "kakao", "naver", "google", "instagram", "tiktok")


def no_real_trademark(text: str) -> bool:
    lowered = text.lower()
    if any(token in lowered for token in EXTRA_TRADEMARK_BLOCKLIST):
        return False
    return v2.no_real_trademark(text)


@dataclass(frozen=True)
class Condition:
    family_code: str
    family: str
    variant: str
    size_band: str
    alpha_name: str
    alpha: float
    rel_size: float
    placement: str
    anchor: tuple
    kind: str
    text: Optional[str]
    geometry: Optional[str]
    shape: Optional[str]
    stroke: bool

    @property
    def code(self) -> str:
        return f"{self.family_code}:{self.size_band}:{'D' if self.variant == DEV_VARIANT else 'H'}"

    @property
    def text_length_class(self) -> Optional[str]:
        return text_length_class(self.text) if self.text else None


def conditions(variant: str) -> list[Condition]:
    if variant not in (DEV_VARIANT, HOLDOUT_VARIANT):
        raise ValueError(variant)
    out = []
    for f in FAMILIES:
        value = f.variant_value(variant)
        is_text = f.kind in ("text", "text_symbol", "tiled_text")
        if is_text and not no_real_trademark(value):
            raise ValueError(f"real trademark string in construct {f.code}")
        if not is_text and value not in GEOMETRIES:
            raise ValueError(f"unknown geometry {value}")
        for size in f.sizes:
            out.append(Condition(f.code, f.family, variant, size, f.alpha_name, ALPHAS[f.alpha_name], SIZE_BANDS[size], f.placement, PLACEMENTS[f.placement],
                                 f.kind, value if is_text else None, None if is_text else value, f.variant_shape(variant), f.stroke))
    return out


# ------------------------------------------------------------------ geometry drawers (all synthetic; no real trademark)


def _draw_geometry(name: str, draw: ImageDraw.ImageDraw, box, alpha: int) -> None:
    left, top, right, bottom = box
    w, h = right - left, bottom - top
    cx, cy = (left + right) / 2, (top + bottom) / 2
    if name == "symbol_circle_triangle":
        v2._symbol(draw, box, alpha)
    elif name == "emblem_shield":
        v2._emblem(draw, box, alpha)
    elif name == "icon_ring_star":
        v2._icon(draw, box, alpha)
    elif name == "symbol_hexagon_bar":
        pts = [(cx + w / 2 * math.cos(math.pi / 3 * i), cy + h / 2 * math.sin(math.pi / 3 * i)) for i in range(6)]
        draw.polygon(pts, fill=(60, 180, 200, alpha))
        draw.rectangle((left + w * 0.25, cy - h * 0.08, right - w * 0.25, cy + h * 0.08), fill=(20, 20, 40, alpha))
    elif name == "emblem_crest":
        crest = [(left + w * 0.5, top), (right, top + h * 0.3), (right - w * 0.15, bottom), (left + w * 0.15, bottom), (left, top + h * 0.3)]
        draw.polygon(crest, fill=(150, 40, 60, alpha), outline=(250, 230, 200, alpha))
        for k in (0.45, 0.62, 0.79):
            draw.line([(left + w * 0.25, top + h * k), (right - w * 0.25, top + h * k)], fill=(250, 230, 200, alpha), width=max(2, w // 16))
    elif name == "icon_asymmetric":
        draw.ellipse(box, fill=(255, 255, 255, alpha))
        draw.ellipse((left + w * 0.35, top - h * 0.05, right + w * 0.15, top + h * 0.55), fill=(0, 0, 0, 0))
        draw.polygon([(left + w * 0.2, bottom), (left + w * 0.55, top + h * 0.45), (left + w * 0.8, bottom)], fill=(30, 30, 30, alpha))
    elif name == "monogram_squares":
        draw.rectangle((left, top, left + w * 0.7, top + h * 0.7), outline=(240, 240, 240, alpha), width=max(2, w // 10))
        draw.rectangle((left + w * 0.3, top + h * 0.3, right, bottom), fill=(240, 120, 40, alpha))
    elif name == "line_emblem":
        draw.line([(left, cy), (right, cy)], fill=(255, 255, 255, alpha), width=max(2, h // 6))
        draw.ellipse((cx - w * 0.15, cy - h * 0.15, cx + w * 0.15, cy + h * 0.15), fill=(255, 80, 80, alpha))
        draw.line([(left, top + h * 0.2), (left + w * 0.3, top + h * 0.2)], fill=(255, 255, 255, alpha), width=max(2, h // 8))
    elif name == "badge_ring":
        draw.rounded_rectangle(box, radius=max(4, w // 5), fill=(40, 90, 160, alpha))
        draw.ellipse((left + w * 0.2, top + h * 0.2, right - w * 0.2, bottom - h * 0.2), outline=(250, 250, 250, alpha), width=max(2, w // 12))
    else:
        raise ValueError(name)


def _text_symbol(draw: ImageDraw.ImageDraw, shape: str, sx: float, ty: float, sym: float, alpha: int) -> None:
    if shape == "diamond":
        draw.polygon([(sx + sym / 2, ty), (sx + sym, ty + sym / 2), (sx + sym / 2, ty + sym), (sx, ty + sym / 2)], fill=(240, 200, 60, alpha))
    elif shape == "hexagon":
        cx, cy, r = sx + sym / 2, ty + sym / 2, sym / 2
        draw.polygon([(cx + r * math.cos(math.pi / 3 * i + math.pi / 6), cy + r * math.sin(math.pi / 3 * i + math.pi / 6)) for i in range(6)], fill=(80, 200, 120, alpha))
    else:
        raise ValueError(shape)


def render(base: Image.Image, cond: Condition) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Deterministic derivative + ground-truth boxes (pixel xyxy). Never mutates base."""

    image = base.convert("RGB")
    width, height = image.size
    ref = min(width, height)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    alpha = int(round(255 * cond.alpha))
    size = int(round(cond.rel_size * ref))
    boxes: list[dict[str, Any]] = []
    if cond.kind == "graphic":
        box = v2._corner_box(width, height, cond.anchor, size)
        _draw_geometry(cond.geometry, draw, box, alpha)
        boxes.append({"box": [float(v) for v in box], "text": None})
    elif cond.kind in ("text", "tiled_text"):
        font = v2._font(size)
        stroke = max(1, size // 18) if cond.stroke else 0
        points = [((c + 0.5) / 3 * width, (r + 0.5) / 4 * height) for r in range(4) for c in range(3)] if cond.kind == "tiled_text" else [(cond.anchor[0] * width, cond.anchor[1] * height)]
        for x, y in points:
            bbox = draw.textbbox((x, y), cond.text, font=font, anchor="mm", stroke_width=stroke)
            kwargs: dict[str, Any] = {"font": font, "anchor": "mm", "fill": (255, 255, 255, alpha)}
            if stroke:
                kwargs.update(stroke_width=stroke, stroke_fill=(0, 0, 0, alpha))
            draw.text((x, y), cond.text, **kwargs)
            boxes.append({"box": [float(max(0, bbox[0])), float(max(0, bbox[1])), float(min(width, bbox[2])), float(min(height, bbox[3]))], "text": cond.text})
    elif cond.kind == "text_symbol":
        font = v2._font(size)
        stroke = max(1, size // 18) if cond.stroke else 0
        margin = int(round(0.02 * ref))
        tb = draw.textbbox((0, 0), cond.text, font=font, anchor="lt", stroke_width=stroke)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        right = round(cond.anchor[0] * width) - margin
        bottom = round(cond.anchor[1] * height) - margin
        tx, ty = right - tw, bottom - th
        sx = tx - th - max(4, th // 4)
        _text_symbol(draw, cond.shape, sx, ty, th, alpha)
        kwargs = {"font": font, "anchor": "lt", "fill": (255, 255, 255, alpha)}
        if stroke:
            kwargs.update(stroke_width=stroke, stroke_fill=(0, 0, 0, alpha))
        draw.text((tx, ty), cond.text, **kwargs)
        boxes.append({"box": [float(sx), float(ty), float(right), float(bottom)], "text": cond.text})
    else:
        raise ValueError(cond.kind)
    out = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
    return out, boxes


def image_digest(image: Image.Image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def manifest_row(cond: Condition, base_opaque_id: str, group_key: Optional[str], boxes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"challengeVersion": CHALLENGE_VERSION, "conditionId": f"{base_opaque_id}:{cond.code}", "baseOpaqueId": base_opaque_id, "participantGroup": group_key,
            "family": cond.family, "familyCode": cond.family_code, "variant": cond.variant, "alphaName": cond.alpha_name, "alpha": cond.alpha,
            "sizeBand": cond.size_band, "relativeSize": cond.rel_size, "placement": cond.placement, "placementClass": PLACEMENT_CLASS[cond.placement],
            "textLengthClass": cond.text_length_class, "markPresent": True, "diagnostic": FAMILY_BY_CODE[cond.family_code].diagnostic,
            "groundTruthBoxes": [list(b["box"]) for b in boxes]}


def definitions() -> dict[str, Any]:
    return {"challengeVersion": CHALLENGE_VERSION, "generatorVersion": GENERATOR_VERSION, "alphas": ALPHAS, "sizeBands": SIZE_BANDS, "placements": {k: list(v) for k, v in PLACEMENTS.items()},
            "families": [asdict(f) for f in FAMILIES], "conditionsPerBase": len(conditions(DEV_VARIANT)), "split": {"development": list(DEVELOPMENT_GROUPS), "holdout": list(HOLDOUT_GROUPS), "holdoutName": HOLDOUT_NAME},
            "lowVisibilityFamily": LOW_VISIBILITY_FAMILY, "lowVisibilityMarker": LOW_VISIBILITY_MARKER, "closureMarker": FLORENCE_TELEMETRY_CLOSURE}


def construct_digest() -> str:
    import json

    return hashlib.sha256(json.dumps(definitions(), sort_keys=True).encode("utf-8")).hexdigest()
