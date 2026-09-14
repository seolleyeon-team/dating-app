"""B3-L7 - OWLv2 positive-construct challenge set and controlled gate V2.

PRE-REGISTERED BEFORE ANY V2 PERFORMANCE NUMBER WAS COMPUTED.

Why a V2 exists
---------------
Gate v1 (owlv2_provisional_shadow_gate_v1) ended POSITIVE_GROUND_TRUTH_INSUFFICIENT:
under the owner-designated Rater A truth all 20 clean avatars are human-negative,
so natural precision/recall are not estimable. v1 is left exactly as it is. V2 is
a NEW version that separates what the two corpora can actually measure:

  * CLEAN HUMAN-NEGATIVE CORPUS (20 avatars)  -> specificity / new review burden
  * KNOWN-POSITIVE CHALLENGE CORPUS (injected) -> family / placement sensitivity

Those two sides are never merged into one "precision". V2 is a controlled shadow
feasibility gate; it is not production validation.

Construct families
------------------
The existing injected mark (circle+triangle) is one shape; B3-L6 showed only the
"a graphic symbol" query found it. So V2 renders several families on every
avatar with one normalized specification each (same relative size, alpha and
normalized position on every base). Vocabulary is synthetic only; a real
trademark blocklist is asserted by tests. Originals are never overwritten;
derivatives are rendered in memory.
"""

from __future__ import annotations

import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402

GATE_VERSION = "OWLV2_CONTROLLED_CHALLENGE_GATE_V2"
EVIDENCE_LABEL = "G004_CONTROLLED_MARK_CHALLENGE_EVIDENCE"
RECALL_LABEL = "CONTROLLED_CHALLENGE_RECALL"
GENERATOR_VERSION = "avatar_owlv2_challenge_v2_generator_v1"
H4_VERSION = sel.H4_VERSION

# Frozen, identical to v1 / selection V1.
THRESHOLD_GRID = sel.THRESHOLD_GRID
PROMPTS = sel.PROMPTS
DEVELOPMENT_GROUPS = sel.DEVELOPMENT_GROUPS
HOLDOUT_GROUPS = sel.HOLDOUT_GROUPS
FLOOR_SCORE = 0.01

# ---- V2 criteria (frozen) -------------------------------------------------
NEW_REVIEW_CEILING = 0.10          # A: clean human-negative new allow->review rate
OVERALL_RECALL_FLOOR = 0.95        # B: overall controlled-positive image recall
CRITICAL_FAMILIES = (              # C: each >= CRITICAL_FAMILY_FLOOR
    "TEXT_WATERMARK_OPAQUE",
    "TEXT_WATERMARK_TRANSLUCENT",
    "GRAPHICAL_WATERMARK",
    "LOGO_LIKE_EMBLEM",
)
CRITICAL_FAMILY_FLOOR = 0.90
CORNER_FAMILY, CORNER_FLOOR = "SMALL_CORNER_MARK", 0.90   # D
EDGE_FAMILY, EDGE_FLOOR = "EDGE_MARK", 0.90               # E
# F: generative-artifact regression == 0 ; G: hard-reject bypass == 0

SYNTHETIC_WORDS = ("SAMPLE", "NOVA")
REAL_TRADEMARK_BLOCKLIST = (
    "nike", "adidas", "apple", "coca", "cola", "pepsi", "samsung", "google", "kakao", "naver",
    "instagram", "facebook", "meta", "puma", "reebok", "gucci", "chanel", "louis", "vuitton",
    "starbucks", "mcdonald", "disney", "netflix", "amazon", "microsoft", "sony", "lg",
)


@dataclass(frozen=True)
class FamilySpec:
    code: str
    family: str
    kind: str                 # symbol | emblem | text | icon | text_symbol
    text: str | None
    alpha: float
    rel_size: float           # mark height / min(W, H)
    placement: str            # corner | edge | center | tiled
    anchor: tuple[float, float]
    repeated: bool = False
    stroke: bool = False
    safety_critical: bool = False
    reuse_variant: str | None = None   # existing capture variant to reuse instead of new inference

    @property
    def text_present(self) -> bool:
        return self.text is not None

    @property
    def graphical_present(self) -> bool:
        return self.kind in ("symbol", "emblem", "icon", "text_symbol")


FAMILIES: tuple[FamilySpec, ...] = (
    # F1 is the existing V8 construct (same spec as bench V8): reused, not re-rendered.
    FamilySpec("F1", "GRAPHIC_SYMBOL", "symbol", None, 0.90, 0.08, "corner", (0.98, 0.02), reuse_variant="V8"),
    FamilySpec("F2", "LOGO_LIKE_EMBLEM", "emblem", None, 0.95, 0.10, "corner", (0.02, 0.02), safety_critical=True),
    FamilySpec("F3", "TEXT_WATERMARK_OPAQUE", "text", "SAMPLE", 1.00, 0.06, "center", (0.50, 0.62), stroke=True, safety_critical=True),
    FamilySpec("F4", "TEXT_WATERMARK_TRANSLUCENT", "text", "SAMPLE", 0.35, 0.06, "center", (0.50, 0.62), safety_critical=True),
    FamilySpec("F5", "GRAPHICAL_WATERMARK", "icon", None, 0.35, 0.12, "center", (0.50, 0.50), safety_critical=True),
    FamilySpec("F6", "BRAND_LIKE_TEXT_AND_SYMBOL", "text_symbol", "NOVA", 1.00, 0.05, "corner", (0.98, 0.98), stroke=True),
    FamilySpec("F7", "SMALL_CORNER_MARK", "symbol", None, 1.00, 0.035, "corner", (0.98, 0.98)),
    FamilySpec("F8", "EDGE_MARK", "symbol", None, 1.00, 0.035, "edge", (0.50, 0.02)),
    FamilySpec("F9", "CENTER_OVERLAY_MARK", "symbol", None, 0.85, 0.10, "center", (0.50, 0.50)),
    FamilySpec("F10", "REPEATED_TILED_MARK", "text", "SAMPLE", 0.45, 0.04, "tiled", (0.50, 0.50), repeated=True),
)
FAMILY_BY_CODE = {f.code: f for f in FAMILIES}
FAMILY_BY_NAME = {f.family: f for f in FAMILIES}


# ---------------------------------------------------------------- rendering


def _font(px: float) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=max(8, int(round(px))))


def _corner_box(width: int, height: int, anchor: tuple[float, float], size: int) -> tuple[int, int, int, int]:
    """Square box of `size` px whose outer corner sits at the normalized anchor."""

    ax, ay = anchor
    left = round(ax * width) - (size if ax > 0.5 else 0)
    top = round(ay * height) - (size if ay > 0.5 else 0)
    if 0.25 < ax < 0.75:
        left = round(ax * width - size / 2)
    if 0.25 < ay < 0.75:
        top = round(ay * height - size / 2)
    return (left, top, left + size, top + size)


def _symbol(draw: ImageDraw.ImageDraw, box, alpha: int) -> None:
    left, top, right, bottom = box
    d = right - left
    draw.ellipse(box, fill=(250, 200, 40, alpha))
    draw.polygon([(left + d * 0.5, top + d * 0.14), (left + d * 0.86, top + d * 0.8), (left + d * 0.14, top + d * 0.8)], fill=(30, 30, 30, alpha))


def _emblem(draw: ImageDraw.ImageDraw, box, alpha: int) -> None:
    """Shield/badge geometry: outer shield, inner ring, chevron. No text."""

    left, top, right, bottom = box
    w, h = right - left, bottom - top
    shield = [
        (left + w * 0.5, top), (right, top + h * 0.18), (right - w * 0.08, top + h * 0.62),
        (left + w * 0.5, bottom), (left + w * 0.08, top + h * 0.62), (left, top + h * 0.18),
    ]
    draw.polygon(shield, fill=(40, 60, 140, alpha), outline=(240, 240, 240, alpha))
    ring = (left + w * 0.25, top + h * 0.22, right - w * 0.25, top + h * 0.72)
    draw.ellipse(ring, outline=(240, 200, 60, alpha), width=max(2, w // 18))
    draw.line([(left + w * 0.32, top + h * 0.5), (left + w * 0.5, top + h * 0.34), (right - w * 0.32, top + h * 0.5)], fill=(240, 200, 60, alpha), width=max(2, w // 18))


def _icon(draw: ImageDraw.ImageDraw, box, alpha: int) -> None:
    """Text-free watermark icon: ring with a four-point star."""

    left, top, right, bottom = box
    w = right - left
    cx, cy = (left + right) / 2, (top + bottom) / 2
    draw.ellipse(box, outline=(255, 255, 255, alpha), width=max(3, w // 14))
    r, r2 = w * 0.42, w * 0.14
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = r if i % 2 == 0 else r2
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=(255, 255, 255, alpha))


def render_family(base: Image.Image, spec: FamilySpec) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Deterministic derivative + ground-truth boxes in pixel xyxy. Never mutates base."""

    image = base.convert("RGB")
    width, height = image.size
    ref = min(width, height)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    alpha = int(round(255 * spec.alpha))
    boxes: list[dict[str, Any]] = []
    size = int(round(spec.rel_size * ref))

    if spec.kind in ("symbol", "emblem", "icon"):
        box = _corner_box(width, height, spec.anchor, size)
        {"symbol": _symbol, "emblem": _emblem, "icon": _icon}[spec.kind](draw, box, alpha)
        boxes.append({"box": [float(v) for v in box], "text": None})
    elif spec.kind == "text":
        font = _font(size)
        stroke = max(1, size // 18) if spec.stroke else 0
        if spec.repeated:
            points = [((c + 0.5) / 3 * width, (r + 0.5) / 4 * height) for r in range(4) for c in range(3)]
            anchor = "mm"
        else:
            points = [(spec.anchor[0] * width, spec.anchor[1] * height)]
            anchor = "mm"
        for x, y in points:
            bbox = draw.textbbox((x, y), spec.text, font=font, anchor=anchor, stroke_width=stroke)
            kwargs: dict[str, Any] = {"font": font, "anchor": anchor, "fill": (255, 255, 255, alpha)}
            if stroke:
                kwargs.update(stroke_width=stroke, stroke_fill=(0, 0, 0, alpha))
            draw.text((x, y), spec.text, **kwargs)
            boxes.append({"box": [float(max(0, bbox[0])), float(max(0, bbox[1])), float(min(width, bbox[2])), float(min(height, bbox[3]))], "text": spec.text})
    elif spec.kind == "text_symbol":
        font = _font(size)
        stroke = max(1, size // 18) if spec.stroke else 0
        # symbol (diamond) then word, anchored at the bottom-right corner with a margin
        margin = int(round(0.02 * ref))
        text_box = draw.textbbox((0, 0), spec.text, font=font, anchor="lt", stroke_width=stroke)
        tw, th = text_box[2] - text_box[0], text_box[3] - text_box[1]
        sym = th
        right = round(spec.anchor[0] * width) - margin
        bottom = round(spec.anchor[1] * height) - margin
        tx, ty = right - tw, bottom - th
        sx = tx - sym - max(4, sym // 4)
        draw.polygon([(sx + sym / 2, ty), (sx + sym, ty + sym / 2), (sx + sym / 2, ty + sym), (sx, ty + sym / 2)], fill=(240, 200, 60, alpha))
        kwargs = {"font": font, "anchor": "lt", "fill": (255, 255, 255, alpha)}
        if stroke:
            kwargs.update(stroke_width=stroke, stroke_fill=(0, 0, 0, alpha))
        draw.text((tx, ty), spec.text, **kwargs)
        boxes.append({"box": [float(sx), float(ty), float(right), float(bottom)], "text": spec.text})
    else:
        raise ValueError(spec.kind)

    out = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
    return out, boxes


def manifest_row(spec: FamilySpec, base_opaque_id: str, group_key: str | None, boxes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "conditionId": f"{base_opaque_id}:{spec.code}",
        "baseOpaqueId": base_opaque_id,
        "groupKey": group_key,
        "family": spec.family,
        "familyCode": spec.code,
        "markPresent": True,
        "textPresent": spec.text_present,
        "graphicalMarkPresent": spec.graphical_present,
        "overlayPresent": True,
        "alpha": spec.alpha,
        "relativeSize": spec.rel_size,
        "placement": spec.placement,
        "repeated": spec.repeated,
        "safetyCritical": spec.safety_critical,
        "groundTruthBoxes": [list(b["box"]) for b in boxes],
    }


def family_definitions() -> list[dict[str, Any]]:
    """Repo-safe description of the construct set (no image content)."""

    return [asdict(f) for f in FAMILIES]


def no_real_trademark(text: str | None) -> bool:
    if text is None:
        return True
    low = text.lower()
    return not any(mark in low for mark in REAL_TRADEMARK_BLOCKLIST)


# ---------------------------------------------------------------- gate V2


def eligible_v2(
    clean_confusion: Mapping[str, Any],
    family_recall: Mapping[str, Mapping[str, Any]],
    overall_recall: float | None,
    *,
    artifact_regressions: int,
    hard_reject_bypass: int,
) -> dict[str, Any]:
    rate = clean_confusion.get("newReviewRate")

    def fam(name: str) -> float | None:
        block = family_recall.get(name)
        return None if block is None else block.get("rate")

    criteria = {
        "A_clean_negative_new_review_rate": {"value": rate, "ceiling": NEW_REVIEW_CEILING, "pass": rate is not None and rate <= NEW_REVIEW_CEILING},
        "B_overall_controlled_positive_recall": {"value": overall_recall, "floor": OVERALL_RECALL_FLOOR, "pass": overall_recall is not None and overall_recall >= OVERALL_RECALL_FLOOR},
        "C_safety_critical_family_recall": {
            "value": {name: fam(name) for name in CRITICAL_FAMILIES},
            "floor": CRITICAL_FAMILY_FLOOR,
            "pass": all(fam(name) is not None and fam(name) >= CRITICAL_FAMILY_FLOOR for name in CRITICAL_FAMILIES),
        },
        "D_small_corner_recall": {"value": fam(CORNER_FAMILY), "floor": CORNER_FLOOR, "pass": fam(CORNER_FAMILY) is not None and fam(CORNER_FAMILY) >= CORNER_FLOOR},
        "E_edge_recall": {"value": fam(EDGE_FAMILY), "floor": EDGE_FLOOR, "pass": fam(EDGE_FAMILY) is not None and fam(EDGE_FAMILY) >= EDGE_FLOOR},
        "F_generative_artifact_regression": {"value": artifact_regressions, "required": 0, "pass": artifact_regressions == 0},
        "G_hard_reject_bypass": {"value": hard_reject_bypass, "required": 0, "pass": hard_reject_bypass == 0},
    }
    return {"gateVersion": GATE_VERSION, "criteria": criteria, "eligible": all(c["pass"] for c in criteria.values())}


__all__ = [
    "CRITICAL_FAMILIES",
    "EVIDENCE_LABEL",
    "FAMILIES",
    "FAMILY_BY_CODE",
    "FAMILY_BY_NAME",
    "FLOOR_SCORE",
    "GATE_VERSION",
    "GENERATOR_VERSION",
    "RECALL_LABEL",
    "REAL_TRADEMARK_BLOCKLIST",
    "FamilySpec",
    "eligible_v2",
    "family_definitions",
    "manifest_row",
    "no_real_trademark",
    "render_family",
]
