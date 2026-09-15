"""B3-L11 — DETECTOR_CANDIDATE_SET_V1 (frozen before any real-avatar inference).

Three candidates, one model resident at a time, CPU only:

  A  owlv2-base-patch16-ensemble  (apache-2.0)  legacy operating point 0.25, prompts frozen since B3-L5; not retuned
  B  grounding-dino-tiny          (apache-2.0)  historical operating point box 0.25 / text 0.25 (B3-L5, fixed);
                                                a coarse pre-registered grid is reported SEPARATELY from the baseline
  C  florence2-phrase-grounding   (MIT)         the production Florence-2-large-ft checkpoint used as an open-vocabulary
                                                grounder (<CAPTION_TO_PHRASE_GROUNDING>); no score -> fixed "presence"
                                                operating point; full-frame boxes (area >= 0.50) are dropped, a filter
                                                pre-registered from a pure-synthetic smoke (blank image returned a
                                                full-frame "a watermark" box)

Scores are model-internal and never compared across models as probabilities.
Excluded: Ultralytics YOLO-World (EXCLUDED_PENDING_PRODUCT_LICENSE_DECISION,
AGPL-3.0 obligations are an owner decision, not evaluated), owlv2-large /
grounding-dino-base (EXCLUDED_LOCAL_RESOURCE_BUDGET: 5.3 GB disk, 16 GB RAM
CPU box).  License authority: official model cards / repository LICENSE only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_logo_detector_benchmark as logo  # noqa: E402

CANDIDATE_SET_VERSION = "DETECTOR_CANDIDATE_SET_V1"
PROMPTS = logo.PROMPTS                                   # ("a logo", "a watermark", "a brand emblem", "a graphic symbol")
IOU_MATCH = bench.IOU_MATCH                              # 0.30, canonical since B3-L4
MAX_LONG_SIDE = logo.MAX_LONG_SIDE                       # 2048 LANCZOS pre-injection downscale (avatars untouched)
DEVICE = "cpu"
FULL_FRAME_AREA_RATIO = 0.50
SCORE_SEMANTICS_NOTE = "model-internal scores; never compared across models; never a probability"
PERMISSIVE_LICENSES = frozenset({"apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause"})

CANDIDATES: dict[str, dict[str, Any]] = {
    "owlv2-base-patch16-ensemble": {
        "repo": "google/owlv2-base-patch16-ensemble", "revision": "cfd3195ba4ea9592eec887ded089f4c08eff231d", "license": "apache-2.0",
        "licenseAuthority": "official model card (google/owlv2-base-patch16-ensemble)", "dir": "owlv2", "kind": "owl", "role": "BASELINE_A",
        "prompts": list(PROMPTS), "floor": 0.01, "scoreSemantics": "OWLv2 post-processed detection score (sigmoid logit)",
        "operatingPoints": {"legacy_0.25": {"threshold": 0.25}}, "gridOperatingPoints": {}, "boxFilter": None,
    },
    "grounding-dino-tiny": {
        "repo": "IDEA-Research/grounding-dino-tiny", "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71", "license": "apache-2.0",
        "licenseAuthority": "official model card (IDEA-Research/grounding-dino-tiny)", "dir": "gdino", "kind": "gdino", "role": "BASELINE_B",
        "prompts": list(PROMPTS), "floor": 0.05, "scoreSemantics": "Grounding DINO box score (max token logit sigmoid)",
        "operatingPoints": {"historical_0.25": {"threshold": 0.25}},
        "gridOperatingPoints": {"grid_0.15": {"threshold": 0.15}, "grid_0.35": {"threshold": 0.35}, "grid_0.45": {"threshold": 0.45}},
        "boxFilter": None,
    },
    "florence2-phrase-grounding": {
        "repo": v3.FLORENCE_REPO, "revision": v3.pinned_florence_revision(), "license": "mit",
        "licenseAuthority": "official model card README (license: mit; license_link microsoft/Florence-2-large LICENSE)", "dir": "florence2", "kind": "florence", "role": "NEW_CANDIDATE_C",
        "task": "<CAPTION_TO_PHRASE_GROUNDING>", "caption": ". ".join(PROMPTS) + ".", "prompts": list(PROMPTS), "floor": None,
        "scoreSemantics": "none (presence of a grounded phrase box)", "generation": {"num_beams": 3, "max_new_tokens": 256},
        "operatingPoints": {"presence": {"threshold": None}}, "gridOperatingPoints": {},
        "boxFilter": {"dropFullFrameAreaRatio": FULL_FRAME_AREA_RATIO, "origin": "pure-synthetic blank-image smoke before freeze"},
    },
}
EXCLUDED: dict[str, dict[str, str]] = {
    "ultralytics-yolo-world": {"status": "EXCLUDED_PENDING_PRODUCT_LICENSE_DECISION", "license": "AGPL-3.0", "note": "owner licensing decision pending; not downloaded, not evaluated, no legality claim"},
    "google/owlv2-large-patch14-ensemble": {"status": "EXCLUDED_LOCAL_RESOURCE_BUDGET", "license": "apache-2.0", "note": "~2.4 GB weights / CPU cost beyond the 5.3 GB disk and 16 GB RAM budget"},
    "IDEA-Research/grounding-dino-base": {"status": "EXCLUDED_LOCAL_RESOURCE_BUDGET", "license": "apache-2.0", "note": "heavier variant; same budget reason"},
}
SELECTED_ROLE = "CONTROLLED_SHADOW_DETECTOR_CANDIDATE"
HOLDOUT_LOCK_NAME = "visual_mark_detector_v1_holdout.lock"
SELECTED_MARKER_NAME = "visual_mark_detector_v1_selected.json"


def _verify_candidate(name: str, spec: Mapping[str, Any]) -> None:
    if spec["license"] not in PERMISSIVE_LICENSES:
        raise ValueError(f"{name}: license not permissive/verified -> EXCLUDED_LICENSE_UNVERIFIED")
    if not spec.get("licenseAuthority", "").startswith("official"):
        raise ValueError(f"{name}: license authority must be the official card/repository")


for _name, _spec in CANDIDATES.items():
    _verify_candidate(_name, _spec)


def register_candidate(name: str, spec: Mapping[str, Any]) -> None:
    """Refused: the candidate set is frozen (contract digest) before real-image inference."""

    raise RuntimeError("DETECTOR_CANDIDATE_SET_V1 is frozen; no candidate may be added after inference")


def operating_points(name: str) -> dict[str, dict[str, Any]]:
    spec = CANDIDATES[name]
    return {**spec["operatingPoints"], **spec["gridOperatingPoints"]}


def contract_digest() -> str:
    payload = {"version": CANDIDATE_SET_VERSION, "candidates": CANDIDATES, "excluded": EXCLUDED, "iouMatch": IOU_MATCH, "maxLongSide": MAX_LONG_SIDE,
               "device": DEVICE, "scoreSemantics": SCORE_SEMANTICS_NOTE, "matching": "image-level construct hit: >=1 detection with IoU >= 0.30 to a known box"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ filtering (on stored raw captures; no re-inference)


def _label_is_query(spec: Mapping[str, Any], label: str) -> bool:
    """A detection counts only when labelled by one of the frozen queries.

    Grounding DINO's post-processor at the low capture text floor labels a box
    with the concatenation of every query phrase whose tokens cleared the
    floor (e.g. "a logo a watermark ..."), so membership is tested as
    phrase-containment; at the historical text threshold that label is a
    subset of the same phrases.  Implementation detail fixed before any
    development table was computed; no query was added or removed.
    """

    if spec["kind"] == "gdino":
        return any(prompt in label for prompt in spec["prompts"])
    return label in spec["prompts"]


def filter_detections(name: str, detections: Sequence[Mapping[str, Any]], op: Mapping[str, Any], image_size: Sequence[int]) -> list[Mapping[str, Any]]:
    spec = CANDIDATES[name]
    out = []
    area = float(image_size[0]) * float(image_size[1])
    for d in detections:
        if not _label_is_query(spec, str(d.get("label", ""))):
            continue
        if op.get("threshold") is not None and float(d.get("score", 0.0)) < float(op["threshold"]):
            continue
        if spec["boxFilter"] and spec["boxFilter"].get("dropFullFrameAreaRatio") is not None:
            b = d["box"]
            if ((b[2] - b[0]) * (b[3] - b[1])) / area >= spec["boxFilter"]["dropFullFrameAreaRatio"]:
                continue
        out.append(d)
    return out


def image_hit(name: str, detections: Sequence[Mapping[str, Any]], truth: Sequence[Mapping[str, Any]], op: Mapping[str, Any], image_size: Sequence[int]) -> dict[str, Any]:
    kept = filter_detections(name, detections, op, image_size)
    ious = [max((bench.iou(d["box"], t["box"]) for d in kept), default=0.0) for t in truth]
    hits = sum(1 for v in ious if v >= IOU_MATCH)
    return {"hit": hits > 0, "boxHits": hits, "boxes": len(truth), "bestIou": max(ious, default=0.0), "detections": len(kept)}


def clean_response(name: str, detections: Sequence[Mapping[str, Any]], op: Mapping[str, Any], image_size: Sequence[int]) -> bool:
    return len(filter_detections(name, detections, op, image_size)) > 0


def shadow_action(canonical_action: str, hit: bool) -> str:
    """Review-only supplement: max(canonical, review); never reject, never downgrade."""

    order = {"allow": 0, "review": 1, "reject": 2}
    if canonical_action not in order:
        raise ValueError("unknown canonical action")
    supplement = "review" if hit else "allow"
    return canonical_action if order[canonical_action] >= order[supplement] else supplement


# ------------------------------------------------------------------ model runtime (local only; heavy imports inside)


def load(name: str, model_dir: Path):
    spec = CANDIDATES[name]
    if spec["kind"] in ("owl", "gdino"):
        return logo._load(spec["kind"], model_dir)
    from avatar_generation.model_adapters.florence2_visual import Florence2VisualRiskAdapter

    adapter = Florence2VisualRiskAdapter(model_id=str(model_dir), local_files_only=True)
    adapter._ensure_loaded()
    return adapter._processor, adapter._model


def detect_floor(name: str, processor, model, image) -> list[dict[str, Any]]:
    """One inference at the low score floor; every operating point is a filter over this output."""

    spec = CANDIDATES[name]
    if spec["kind"] == "owl":
        return logo._detect("owl", processor, model, image, {"threshold": spec["floor"]})
    if spec["kind"] == "gdino":
        return logo._detect("gdino", processor, model, image, {"box_threshold": spec["floor"], "text_threshold": spec["floor"]})
    inputs = processor(text=spec["task"] + spec["caption"], images=image, return_tensors="pt")
    generated = model.generate(input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"], **spec["generation"])
    text = processor.batch_decode(generated, skip_special_tokens=False)[0]
    parsed = processor.post_process_generation(text, task=spec["task"], image_size=image.size)
    payload = parsed.get(spec["task"], {}) if isinstance(parsed, dict) else {}
    boxes = payload.get("bboxes", []) or []
    labels = payload.get("labels", []) or []
    return [{"box": [float(v) for v in b], "score": None, "label": str(l)} for b, l in zip(boxes, labels)]
