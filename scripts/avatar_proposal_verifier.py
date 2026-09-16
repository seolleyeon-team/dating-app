"""B3-L13 — VISUAL_MARK_PROPOSAL_VERIFIER_V1 (pre-registered, decision-neutral research).

Architecture hypothesis: the three B3-L11 detectors (frozen models, revisions,
prompts and operating points) act only as a PROPOSAL UNION; a LOCAL CONTENT
VERIFIER — the production CLIP image embedding + one fixed L2 logistic
regression — decides whether a proposal crop looks like a mark.  This is
distinct from the raw OR rejected in B3-L12A because the verifier can remove
proposals: PROPOSAL_UNION_WITH_DOWNSTREAM_VERIFIER_DISTINCT_FROM_REJECTED_RAW_OR.

Closed paths: GDINO_GEOMETRY_FILTER_PATH_CLOSED_ON_CURRENT_CORPUS (no more
area/aspect/location rules); FACE_SUPPRESSION_PROHIBITED (no "inside primary
face box -> ignore" and no face-detector feature: it would create a
deterministic blind spot for marks over the face).

Runtime verifier input is the proposal crop only (pixels via a deterministic
crop contract).  Ground-truth boxes, family, alpha, placement, variant, base
identity, human labels and clean/positive flags are label/evaluation
authority, never features.  The verifier output is an UNCALIBRATED_VERIFIER_SCORE;
no confidence band is derived.  Development evidence is group out-of-fold
(G1/G2/G3, base-disjoint); in-sample training results never select anything.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_gdino_geometry_filter as gf  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

VERSION = "VISUAL_MARK_PROPOSAL_VERIFIER_V1"
GEOMETRY_CLOSURE = "GDINO_GEOMETRY_FILTER_PATH_CLOSED_ON_CURRENT_CORPUS"
UNION_MARKER = "PROPOSAL_UNION_WITH_DOWNSTREAM_VERIFIER_DISTINCT_FROM_REJECTED_RAW_OR"
FACE_SUPPRESSION = "FACE_SUPPRESSION_PROHIBITED"
SCORE_ROLE = "UNCALIBRATED_VERIFIER_SCORE"
SELECTED_ROLE = "VISUAL_MARK_PROPOSAL_VERIFIER_CONTROLLED_SHADOW_CANDIDATE"
SELECTED_MARKER_NAME = "proposal_verifier_v1_selected.json"
HOLDOUT_LOCK_NAME = det.HOLDOUT_LOCK_NAME            # canonical B3-L11 lock, reused (first and only opening)
PRIOR_STATUS = {**gf.PRIOR_STATUS, "B3_L12A": "GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT",
                "B3_L12A_DIAGNOSIS": ["CLEAN_GEOMETRY_NOT_SEPARATING", "EDGE_FAMILY_STILL_UNDERDETECTED", "GRAPHICAL_WATERMARK_STILL_UNDERDETECTED", "MIXED"]}

# ------------------------------------------------------------------ proposal generators (frozen B3-L11 baselines)

PROPOSAL_GENERATORS: dict[str, str] = {"owlv2-base-patch16-ensemble": "legacy_0.25", "grounding-dino-tiny": "historical_0.25", "florence2-phrase-grounding": "presence"}
IOU_MATCH = det.IOU_MATCH                              # 0.30 canonical match (no containment clause exists in the B3-L11 contract)


def proposals(name: str, detections: Sequence[Mapping[str, Any]], image_size: Sequence[int]) -> list[dict[str, Any]]:
    op = det.CANDIDATES[name]["operatingPoints"][PROPOSAL_GENERATORS[name]]
    return [{"box": [float(v) for v in d["box"]], "source": name} for d in det.filter_detections(name, detections, op, image_size)]


def union_proposals(detections_by_generator: Mapping[str, Sequence[Mapping[str, Any]]], image_size: Sequence[int]) -> list[dict[str, Any]]:
    out = []
    for name in PROPOSAL_GENERATORS:
        out.extend(proposals(name, detections_by_generator.get(name, []), image_size))
    return out


def coverage_hit(props: Sequence[Mapping[str, Any]], truth: Sequence[Mapping[str, Any]]) -> bool:
    return any(bench.iou(p["box"], t["box"]) >= IOU_MATCH for p in props for t in truth)


# ------------------------------------------------------------------ verifier (production CLIP embedding; frozen)

VERIFIER = {
    "repo": "openai/clip-vit-large-patch14", "revision": "32bd64288804d66eefd0ccbe215aa642df71cc41",
    "productionUse": "LocalClipRiskScorer clipSafety (Dockerfile QA_CLIP_LARGE_REVISION, AVATAR_QA_CALIBRATION_EXPECTED_MODELS_JSON)",
    "license": "mit", "licenseAuthority": "official repository openai/CLIP LICENSE (MIT License, Copyright (c) 2021 OpenAI); the Hugging Face model card links that repository and carries no license field of its own",
    "package": "transformers CLIPModel/CLIPProcessor (local_files_only)", "preprocessing": "CLIPProcessor: resize shortest side 224, center crop 224, CLIP mean/std", "embeddingDim": 768,
    "feature": "get_image_features, L2-normalized", "device": "cpu", "scoreRole": SCORE_ROLE,
}
CROP = {"paddingRelative": 0.15, "paddingBasis": "each side by 0.15 x box width (x) / 0.15 x box height (y)", "clipToImage": True, "minSidePx": 8, "then": "CLIPProcessor default"}
CLASSIFIER = {"estimator": "sklearn.linear_model.LogisticRegression", "penalty": "l2", "C": 1.0, "solver": "lbfgs", "class_weight": "balanced", "max_iter": 1000, "random_state": 0,
              "input": "L2-normalized CLIP image embedding", "hyperparameterSearch": "none", "sklearnVersionPinned": "1.9.1"}
THRESHOLD_GRID = (0.20, 0.35, 0.50, 0.65, 0.80)      # sigmoid output of the fixed classifier; coarse; frozen
NEUTRAL_THRESHOLD = 0.50
LABEL_POSITIVE_IOU = IOU_MATCH                          # >= 0.30 -> CONTROLLED_POSITIVE_PROPOSAL
LABEL_NEGATIVE_IOU = 0.05                               # <= 0.05 and no containment -> safe negative; between -> AMBIGUOUS_EXCLUDED
FOLDS = (("G1", "G2", "G3"), ("G1", "G3", "G2"), ("G2", "G3", "G1"))   # (train a, train b, evaluate)
FORBIDDEN_FEATURE_INPUTS = frozenset({"groundTruth", "groundTruthBox", "groundTruthBoxes", "family", "familyCode", "alphaName", "alpha", "placement", "placementClass",
                                      "variant", "baseOpaqueId", "opaqueId", "groupKey", "participantGroup", "isClean", "markPresent", "label", "proposalLabel", "truth",
                                      "primaryFaceBBox", "faceBox", "face", "detectorScore"}) | frozenset(sel.HUMAN_ONLY_FIELDS)


def contract_digest() -> str:
    payload = {"version": VERSION, "generators": PROPOSAL_GENERATORS, "detectorSet": det.contract_digest(), "constructs": c3.construct_digest(), "iouMatch": IOU_MATCH,
               "verifier": VERIFIER, "crop": CROP, "classifier": CLASSIFIER, "thresholdGrid": list(THRESHOLD_GRID), "labels": {"positiveIou": LABEL_POSITIVE_IOU, "negativeIou": LABEL_NEGATIVE_IOU, "containmentExcluded": True},
               "folds": [list(f) for f in FOLDS], "selection": "lowest clean new-review -> highest min critical-family recall -> highest overall recall -> closest to 0.50",
               "markers": [GEOMETRY_CLOSURE, UNION_MARKER, FACE_SUPPRESSION], "forbiddenFeatureInputs": sorted(FORBIDDEN_FEATURE_INPUTS)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ crop contract (deterministic)


def crop_box(box: Sequence[float], image_size: Sequence[int], **runtime_inputs: Any) -> tuple[int, int, int, int]:
    leaked = FORBIDDEN_FEATURE_INPUTS & set(runtime_inputs)
    if leaked:
        raise ValueError(f"not a runtime verifier input: {sorted(leaked)}")
    W, H = int(image_size[0]), int(image_size[1])
    x0, y0, x1, y1 = (float(v) for v in box)
    w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    px, py = CROP["paddingRelative"] * w, CROP["paddingRelative"] * h
    left, top = int(max(0, round(x0 - px))), int(max(0, round(y0 - py)))
    right, bottom = int(min(W, round(x1 + px))), int(min(H, round(y1 + py)))
    if right - left < CROP["minSidePx"]:
        right = min(W, left + CROP["minSidePx"])
        left = max(0, right - CROP["minSidePx"])
    if bottom - top < CROP["minSidePx"]:
        bottom = min(H, top + CROP["minSidePx"])
        top = max(0, bottom - CROP["minSidePx"])
    return left, top, right, bottom


# ------------------------------------------------------------------ labels (evaluation authority only)


def _center_inside(inner: Sequence[float], outer: Sequence[float]) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def proposal_label(box: Sequence[float], truth: Sequence[Mapping[str, Any]], *, clean_image: bool) -> tuple[str, float]:
    if clean_image:
        return "negative", 0.0
    best = max((bench.iou(box, t["box"]) for t in truth), default=0.0)
    if best >= LABEL_POSITIVE_IOU:
        return "positive", best
    contained = any(_center_inside(box, t["box"]) or _center_inside(t["box"], box) for t in truth)
    if best <= LABEL_NEGATIVE_IOU and not contained:
        return "negative", best
    return "ambiguous", best


# ------------------------------------------------------------------ classifier + OOF


def fit_classifier(embeddings, labels):
    from sklearn.linear_model import LogisticRegression
    import numpy as np

    X = np.asarray(embeddings, dtype=float)
    X = X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
    y = np.asarray([1 if l == "positive" else 0 for l in labels])
    clf = LogisticRegression(penalty=CLASSIFIER["penalty"], C=CLASSIFIER["C"], solver=CLASSIFIER["solver"], class_weight=CLASSIFIER["class_weight"],
                             max_iter=CLASSIFIER["max_iter"], random_state=CLASSIFIER["random_state"])
    clf.fit(X, y)
    return clf


def score(clf, embeddings):
    import numpy as np

    X = np.asarray(embeddings, dtype=float)
    X = X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
    return [float(v) for v in clf.predict_proba(X)[:, 1]]


def assert_group_disjoint(train_groups: Sequence[str], eval_group: str, rows: Sequence[Mapping[str, Any]]) -> None:
    train_bases = {r["opaqueId"] for r in rows if r["groupKey"] in train_groups}
    eval_bases = {r["opaqueId"] for r in rows if r["groupKey"] == eval_group}
    if train_bases & eval_bases or eval_group in train_groups:
        raise ValueError("base-level leakage: the same avatar appears in train and evaluation folds")


def oof_scores(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """rows: proposal records with opaqueId, groupKey, label, embedding, proposalId. Returns proposalId -> OOF score (ambiguous rows scored, never trained on)."""

    out: dict[str, float] = {}
    for a, b, evaluate in FOLDS:
        assert_group_disjoint((a, b), evaluate, rows)
        train = [r for r in rows if r["groupKey"] in (a, b) and r["label"] in ("positive", "negative")]
        test = [r for r in rows if r["groupKey"] == evaluate]
        if not train or not test:
            continue
        clf = fit_classifier([r["embedding"] for r in train], [r["label"] for r in train])
        for r, s in zip(test, score(clf, [r["embedding"] for r in test])):
            out[r["proposalId"]] = s
    return out


# ------------------------------------------------------------------ image-level pipeline + gate


def image_outcome(props: Sequence[Mapping[str, Any]], scores_by_id: Mapping[str, float], threshold: float, truth: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    survivors = [p for p in props if scores_by_id.get(p["proposalId"], -1.0) >= threshold]
    hit = any(bench.iou(p["box"], t["box"]) >= IOU_MATCH for p in survivors for t in truth)
    return {"survivors": len(survivors), "hit": hit, "response": len(survivors) > 0}


shadow_action = det.shadow_action    # review-only; never reject, never downgrade


def select_threshold(table: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Development OOF table only."""

    elig = [t for t in table if t["eligible"]]
    if not elig:
        return {"status": "NONE", "threshold": None, "reason": "no verifier threshold satisfies J1-J12 on OOF development"}
    best = sorted(elig, key=lambda t: (t["clean"]["newReviewRate"], -(t["criticalFamilyMinRecall"] or 0), -(t["overall"]["rate"] or 0), abs(t["threshold"] - NEUTRAL_THRESHOLD)))[0]
    return {"status": "SELECTED", "threshold": best["threshold"], "role": SELECTED_ROLE, "reason": "lowest clean new-review -> highest min critical recall -> highest overall recall -> closest to 0.50"}


# ------------------------------------------------------------------ guards / verdicts


class NotFrozen(RuntimeError):
    pass


class CoverageInsufficient(RuntimeError):
    pass


def require_coverage(coverage: Mapping[str, Any]) -> None:
    if not coverage.get("pass"):
        raise CoverageInsufficient("PROPOSAL_UNION_COVERAGE_INSUFFICIENT: a verifier cannot recover proposals that do not exist")


def write_selected(private_dir: Path, threshold: float, digest: str, dev_digest: str) -> Path:
    path = Path(private_dir) / SELECTED_MARKER_NAME
    path.write_text(json.dumps({"role": SELECTED_ROLE, "version": VERSION, "detectors": list(PROPOSAL_GENERATORS), "generatorOperatingPoints": PROPOSAL_GENERATORS,
                                "verifier": VERIFIER, "crop": CROP, "classifier": CLASSIFIER, "threshold": threshold, "contractDigest": digest,
                                "detectorSetDigest": det.contract_digest(), "constructDigest": c3.construct_digest(), "developmentInputsDigest": dev_digest,
                                "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    # B3-L11 capture-script marker (union form) so the holdout capture can verify detector membership and both digests
    union = Path(private_dir) / det.SELECTED_MARKER_NAME
    union.write_text(json.dumps({"role": SELECTED_ROLE, "detector": "union", "detectors": list(PROPOSAL_GENERATORS), "contractDigest": det.contract_digest(),
                                 "constructDigest": c3.construct_digest(), "proposalVerifierContractDigest": digest, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_selected(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / SELECTED_MARKER_NAME
    if not path.exists():
        raise NotFrozen("holdout requires a frozen selected verifier threshold")
    record = json.loads(path.read_text(encoding="utf-8"))
    if (record.get("contractDigest") != digest or record.get("version") != VERSION or record.get("threshold") not in THRESHOLD_GRID
            or record.get("detectorSetDigest") != det.contract_digest() or record.get("constructDigest") != c3.construct_digest() or record.get("classifier") != CLASSIFIER or record.get("crop") != CROP):
        raise NotFrozen("selected record does not match the frozen contract (retuning refused)")
    return record


def holdout_unopened_audit(capture_dir: Path) -> dict[str, Any]:
    p = Path(capture_dir)
    audit = {name: (p / f"capture_{name}_holdout.jsonl").exists() for name in PROPOSAL_GENERATORS}
    audit["holdoutEmbeddingsExist"] = (p / "proposal_embeddings_holdout.jsonl").exists()
    audit["lockExists"] = (p / HOLDOUT_LOCK_NAME).exists()
    audit["unopened"] = not any(audit[name] for name in PROPOSAL_GENERATORS) and not audit["holdoutEmbeddingsExist"] and not audit["lockExists"]
    return audit


def holdout_guard(private_dir: Path, digest: str) -> Path:
    require_selected(private_dir, digest)
    lock = Path(private_dir) / HOLDOUT_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"holdout already evaluated once: {lock.name}")
    return lock


def verdict(coverage_pass: bool, dev_selected: Optional[bool], holdout_pass: Optional[bool]) -> dict[str, str]:
    if not coverage_pass:
        return {"verdict": "PROPOSAL_UNION_COVERAGE_INSUFFICIENT", "support": "VISUAL_MARK_PROPOSAL_VERIFIER_NOT_SUPPORTED"}
    if not dev_selected:
        return {"verdict": "PROPOSAL_VERIFIER_FAILED_DEVELOPMENT", "support": "VISUAL_MARK_PROPOSAL_VERIFIER_NOT_SUPPORTED"}
    if holdout_pass is None:
        return {"verdict": "PROPOSAL_VERIFIER_DEVELOPMENT_ELIGIBLE_HOLDOUT_PENDING", "support": "VISUAL_MARK_PROPOSAL_VERIFIER_NOT_SUPPORTED"}
    if holdout_pass:
        return {"verdict": "VISUAL_MARK_PROPOSAL_VERIFIER_CONTROLLED_GATE_PASSED", "support": "VISUAL_MARK_PROPOSAL_VERIFIER_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY"}
    return {"verdict": "VISUAL_MARK_PROPOSAL_VERIFIER_HOLDOUT_FAILED", "support": "VISUAL_MARK_PROPOSAL_VERIFIER_NOT_SUPPORTED"}


def diagnosis(coverage: Mapping[str, Any], table: Sequence[Mapping[str, Any]]) -> list[str]:
    out = set()
    if not coverage.get("pass"):
        out.add("PROPOSAL_CEILING_INSUFFICIENT")
        if not coverage["criteria"].get("H", True):
            out.add("EDGE_PROPOSAL_GAP")
        if not coverage["criteria"].get("E", True):
            out.add("TRANSLUCENT_GRAPHIC_PROPOSAL_GAP")
    for t in table:
        c = t["criteria"]
        if not c["J1"]:
            out.add("CLEAN_HARD_NEGATIVES_NOT_SEPARATING")
        if c["J1"] and not all(c[k] for k in ("J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10")):
            out.add("VERIFIER_REMOVES_TRUE_MARKS")
    if any(not t["criteria"]["J1"] for t in table) and any(t["clean"]["newReviewRate"] is not None and t["clean"]["newReviewRate"] > 0.5 for t in table):
        out.add("CONTENT_VERIFIER_NOT_SEPARATING")
    if len(out) > 1:
        out.add("MIXED")
    return sorted(out)
