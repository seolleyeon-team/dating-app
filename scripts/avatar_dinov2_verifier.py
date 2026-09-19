"""B3-L16A — DINOv2_FROZEN_VISUAL_REPRESENTATION_VERIFIER_V1 (pre-registered, decision-neutral research).

Single new hypothesis: with the B3-L15A proposal architecture frozen exactly
(EDGE_SCAN_PROPOSAL_CONTRACT_FROZEN_AFTER_B3_L15A: frozen three-detector union
OR EDGE_SCAN_PROPOSAL_V1, same crops, same labels, same folds, same linear
classifier recipe, same threshold grid), replace the CLIP ViT-L/14 image
embedding by ONE orthogonal frozen visual representation, facebook/dinov2-base
(pinned revision), and test whether a linear separation between clean
hard-negative crops and controlled mark crops exists.

Exactly one representation candidate; no non-linear head; no layer / pooling
/ preprocessing / crop search.  If development fails, verifier shopping ends
(FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE) and the next step is
SUPERVISED_WATERMARK_LOGO_DATA_DESIGN.  Prior verdicts (B3-L13, B3-L14A,
B3-L15A) are immutable.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_edge_scan_verifier as es  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402

VERSION = "DINOv2_FROZEN_VISUAL_REPRESENTATION_VERIFIER_V1"
PROPOSAL_FREEZE_MARKER = "EDGE_SCAN_PROPOSAL_CONTRACT_FROZEN_AFTER_B3_L15A"
SCAN_ONLY_REJECT = "SCAN_ONLY_CURRENT_REPRESENTATION_DOMINATED_BY_EXISTING_EVIDENCE"
STOP_RULE = "FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE"
NEXT_ON_FAILURE = "SUPERVISED_WATERMARK_LOGO_DATA_DESIGN"
STRESS_NAME = es.STRESS_NAME
STRESS_DATASET = es.STRESS_DATASET
CRITICAL_MARKER = es.CRITICAL_MARKER
SCORE_ROLE = pv.SCORE_ROLE
DEVELOPMENT_EVIDENCE = es.DEVELOPMENT_EVIDENCE
SELECTED_ROLE = "DINOV2_VERIFIER_CONTROLLED_SHADOW_CANDIDATE"
NEW_REVIEW_CEILING = es.NEW_REVIEW_CEILING
OVERALL_RECALL_FLOOR = es.OVERALL_RECALL_FLOOR
FAMILY_RECALL_FLOOR = es.FAMILY_RECALL_FLOOR
NEW_DETECTOR_INFERENCE_EXPECTED = dict(es.NEW_DETECTOR_INFERENCE_EXPECTED)
NON_LINEAR_HEADS_PROHIBITED = ("RBF SVM", "kernel search", "random forest", "boosting", "MLP", "neural classifier", "polynomial features")
NO_SEARCH = ("layer", "pooling", "patch pooling", "multi-layer concat", "CLS vs mean-pool", "preprocessing", "padding", "crop")
NO_CHANGE_AFTER_HOLDOUT = ("DINO revision", "preprocessing", "embedding semantics", "crop", "classifier", "threshold", "scan", "detectors", "prompts", "matching", "family floors")
FORBIDDEN_INTERPRETATIONS = ("synthetic style is the cause", "all embeddings fail", "visual verification impossible")
PRIOR_STATUS = {**es.PRIOR_STATUS, "B3_L15A": "EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT",
                "B3_L15A_CEILING": "PASS (B3-L11 dev 166/168, EDGE_MARK 12/12; B3-L14A dev 192/192, all cells 12/12)",
                "B3_L15A_DIAGNOSIS": ["BROAD_MARK_RECALL_REGRESSION", "EDGE_SCAN_CLEAN_BURDEN_TOO_HIGH", "SYNTHETIC_STYLE_NOT_SEPARATING", "MIXED"],
                "B3_L15A_STRESS": "NOT_EXECUTED", "B3_L15A_HOLDOUT": "UNOPENED"}

# ------------------------------------------------------------------ proposal architecture (B3-L15A exact; frozen)

PROPOSAL_CONTRACT_DIGEST_PREFIX = "de771758cc30"
SCAN_DIGEST_PREFIX = "1b45958a524d"
if es.contract_digest()[:12] != PROPOSAL_CONTRACT_DIGEST_PREFIX or es.scan_digest()[:12] != SCAN_DIGEST_PREFIX:
    raise RuntimeError("B3-L16A requires the frozen B3-L15A proposal contract (scan, union, matching, labels)")
runtime_proposals = es.runtime_proposals
proposal_matches = es.proposal_matches
proposal_label = es.proposal_label
runtime_crop = es.runtime_crop
CROP = es.CROP
FORBIDDEN_FEATURE_INPUTS = frozenset(es.FORBIDDEN_FEATURE_INPUTS) | frozenset({"isClean", "cleanFlag", "positiveFlag"})

# ------------------------------------------------------------------ the single representation candidate (frozen before any embedding)

REPRESENTATION_CANDIDATES = ("facebook/dinov2-base",)
PREPROCESSING = {"processor": "BitImageProcessor (AutoImageProcessor from the pinned snapshot)", "do_convert_rgb": True, "do_resize": True, "size": {"shortest_edge": 256}, "resample": "bicubic (3)",
                 "do_center_crop": True, "crop_size": {"height": 224, "width": 224}, "do_rescale": True, "rescale_factor": 1 / 255, "do_normalize": True,
                 "image_mean": [0.485, 0.456, 0.406], "image_std": [0.229, 0.224, 0.225], "source": "preprocessor_config.json at the pinned revision; official defaults, no custom search"}
VERIFIER = {
    "repo": "facebook/dinov2-base", "revision": "f9e44c814b77203eaa57a6bdbbd535f21ede1415", "license": "apache-2.0",
    "licenseAuthority": "official model card (facebook/dinov2-base README front matter license: apache-2.0; Hugging Face API cardData.license apache-2.0), fetched fresh before the freeze",
    "architecture": "ViT-B/14 self-supervised DINOv2 (Dinov2Model; hidden 768, 12 layers, patch 14, ~86M parameters, model.safetensors ~346 MB)",
    "package": "transformers 4.57.6 AutoImageProcessor + Dinov2Model, local_files_only", "preprocessing": PREPROCESSING,
    "embeddingSemantics": "pooler_output: the [CLS] token of the final LayerNorm output (== last_hidden_state[:, 0]); no mean pooling", "embeddingDim": 768,
    "feature": "pooler_output, L2-normalized", "device": "cpu", "scoreRole": SCORE_ROLE, "role": "orthogonal frozen visual representation; the only candidate in B3-L16A",
}


def register_representation(repo: str, revision: str) -> None:
    raise RuntimeError("B3-L16A has exactly one representation candidate; no second embedding, grid or ensemble")


def require_pinned_revision(revision: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise ValueError("a floating branch name is not a pinned revision")
    return revision


def image_embedding(outputs: Any):
    """Frozen semantics: Dinov2Model.pooler_output (final-LayerNorm [CLS] token). Nothing else is read."""

    return outputs.pooler_output


# ------------------------------------------------------------------ classifier / folds / grid (B3-L15A exact)

CLASSIFIER = es.CLASSIFIER
THRESHOLD_GRID = es.THRESHOLD_GRID
NEUTRAL_THRESHOLD = es.NEUTRAL_THRESHOLD
FOLDS = es.FOLDS
DEVELOPMENT_GROUPS = es.DEVELOPMENT_GROUPS
HOLDOUT_GROUPS = es.HOLDOUT_GROUPS
fit_classifier = es.fit_classifier
score = es.score
assert_group_disjoint = es.assert_group_disjoint
leakage_audit = es.leakage_audit
oof_scores = es.oof_scores
image_outcome = es.image_outcome
shadow_action = es.shadow_action
select_threshold = es.select_threshold


def feature_matrix(flat: Sequence[Mapping[str, Any]], include_source: bool = False):
    return es.feature_matrix(flat, include_source=include_source)


# ------------------------------------------------------------------ scan-only rejection (existing evidence; no new run)


def scan_only_dominance(l15a_aggregate: Mapping[str, Any]) -> dict[str, Any]:
    per = l15a_aggregate["developmentDescriptive"]["perThreshold"]
    table = {str(t["threshold"]): t for t in l15a_aggregate["development"]["table"]}
    scan_imgs = {k: per[k]["cleanImagesWithSurvivorBySource"].get("edge_scan", 0) for k in ("0.5", "0.65")}
    edge_at_08 = table["0.8"]["broadFamilies"]["EDGE_MARK"]
    return {"marker": SCAN_ONLY_REJECT, "rejected": True, "scanCleanSurvivorImages": scan_imgs, "cleanCeiling": "<= 1/12",
            "combinedEdgeMarkAt0.8": f"{edge_at_08['k']}/{edge_at_08['n']}",
            "reason": "scan-only clean survivors already exceed the 1/12 ceiling at 0.50 and 0.65; at 0.80 even the combined union misses the EDGE_MARK floor (9/12) and scan-only recall cannot exceed the combined union, so no threshold can pass"}


# ------------------------------------------------------------------ digests / markers / guards

FROZEN_MARKER_NAME = "dinov2_verifier_v1_frozen.json"
SELECTED_MARKER_NAME = "dinov2_verifier_v1_selected.json"
STRESS_RESULT_NAME = "dinov2_verifier_v1_stress_result.json"
L11_AUDIT_NAME = "dinov2_verifier_v1_l11_holdout_audit.json"
FINAL_CLASSIFIER_NAME = "dinov2_verifier_v1_final_classifier.json"
EMBEDDINGS_PREFIX = "dinov2_embeddings_"


class NotFrozen(RuntimeError):
    pass


def contract_digest() -> str:
    payload = {"version": VERSION, "proposalContract": es.contract_digest(), "scan": es.scan_digest(), "detectorSet": det.contract_digest(), "verifier": VERIFIER, "preprocessing": PREPROCESSING,
               "crop": CROP, "classifier": CLASSIFIER, "thresholdGrid": list(THRESHOLD_GRID), "folds": [list(f) for f in FOLDS], "labels": "B3-L15A exact (positive / negative / excluded)",
               "gates": {"cleanCeiling": NEW_REVIEW_CEILING, "overall": OVERALL_RECALL_FLOOR, "family": FAMILY_RECALL_FLOOR, "edge": "B3-L14A gate (cell 11/12 dev, 8/8 stress)", "holdoutClean": "0/8"},
               "selection": "lowest clean new-review -> highest min critical recall (broad + edge cells) -> highest broad overall -> highest edge overall -> closest to 0.50",
               "markers": [PROPOSAL_FREEZE_MARKER, SCAN_ONLY_REJECT, STOP_RULE, CRITICAL_MARKER, STRESS_NAME], "candidates": list(REPRESENTATION_CANDIDATES),
               "constructs": {"l11": c3.construct_digest()}, "forbiddenFeatureInputs": sorted(FORBIDDEN_FEATURE_INPUTS)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def write_frozen(private_dir: Path, digest: str, commit: str) -> Path:
    path = Path(private_dir) / FROZEN_MARKER_NAME
    path.write_text(json.dumps({"version": VERSION, "contractDigest": digest, "freezeCommit": commit, "verifier": VERIFIER, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_frozen(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / FROZEN_MARKER_NAME
    if not path.exists():
        raise NotFrozen("DINOv2 embeddings require the pre-registration freeze marker (commit) first")
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("contractDigest") != digest or r.get("version") != VERSION or not r.get("freezeCommit") or r.get("verifier") != VERIFIER:
        raise NotFrozen("freeze marker does not match the current contract")
    return r


def _frozen_record(threshold: float, digest: str, dev_digest: str) -> dict[str, Any]:
    return {"role": SELECTED_ROLE, "version": VERSION, "contractDigest": digest, "proposalContractDigest": es.contract_digest(), "scanDigest": es.scan_digest(), "detectorSetDigest": det.contract_digest(),
            "verifier": VERIFIER, "preprocessing": PREPROCESSING, "crop": CROP, "classifier": CLASSIFIER, "threshold": threshold, "thresholdGrid": list(THRESHOLD_GRID),
            "developmentInputsDigest": dev_digest, "frozenAt": datetime.now(timezone.utc).isoformat()}


def write_selected(private_dir: Path, threshold: float, digest: str, dev_digest: str) -> Path:
    path = Path(private_dir) / SELECTED_MARKER_NAME
    path.write_text(json.dumps(_frozen_record(threshold, digest, dev_digest), indent=2), encoding="utf-8")
    return path


def require_selected(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / SELECTED_MARKER_NAME
    if not path.exists():
        raise NotFrozen("stress/holdout require the frozen selected DINOv2 verifier threshold")
    r = json.loads(path.read_text(encoding="utf-8"))
    expected = _frozen_record(r.get("threshold"), digest, r.get("developmentInputsDigest"))
    for k in ("role", "version", "contractDigest", "proposalContractDigest", "scanDigest", "detectorSetDigest", "verifier", "preprocessing", "crop", "classifier", "thresholdGrid"):
        if r.get(k) != expected[k]:
            raise NotFrozen(f"selected record differs from the frozen contract ({k}); retuning refused")
    if r.get("threshold") not in THRESHOLD_GRID:
        raise NotFrozen("selected threshold outside the frozen grid")
    return r


def write_stress_result(private_dir: Path, digest: str, *, passed: bool) -> Path:
    path = Path(private_dir) / STRESS_RESULT_NAME
    if path.exists():
        raise NotFrozen("the known-construct stress gate is evaluated once")
    require_selected(private_dir, digest)
    path.write_text(json.dumps({"name": STRESS_NAME, "dataset": STRESS_DATASET, "contractDigest": digest, "passed": bool(passed), "evaluatedAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_stress_passed(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / STRESS_RESULT_NAME
    if not path.exists():
        raise NotFrozen("the original B3-L11 holdout requires the known-construct stress gate to have passed")
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("contractDigest") != digest or r.get("passed") is not True:
        raise NotFrozen("stress gate not passed under this contract; the original B3-L11 holdout stays unopened")
    return r


def l11_holdout_unopened_audit(l11_dir: Path, private_dir: Optional[Path] = None) -> dict[str, Any]:
    base = es.l11_holdout_unopened_audit(l11_dir, private_dir)
    dino = (Path(private_dir) / f"{EMBEDDINGS_PREFIX}l11_holdout.jsonl").exists() if private_dir else False
    base["dinov2EmbeddingsExist"] = dino
    base["unopened"] = base["unopened"] and not dino
    return base


def write_l11_union_marker(private_dir: Path, l11_dir: Path, digest: str) -> Path:
    require_selected(private_dir, digest)
    require_stress_passed(private_dir, digest)
    audit = l11_holdout_unopened_audit(l11_dir, private_dir)
    if not audit["unopened"]:
        raise NotFrozen(f"original B3-L11 holdout is not unopened: {audit}")
    (Path(private_dir) / L11_AUDIT_NAME).write_text(json.dumps({"audit": audit, "contractDigest": digest, "auditedAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    path = Path(l11_dir) / det.SELECTED_MARKER_NAME
    path.write_text(json.dumps({"role": SELECTED_ROLE, "detector": "union", "detectors": list(es.PROPOSAL_GENERATORS), "contractDigest": det.contract_digest(), "constructDigest": c3.construct_digest(),
                                "dinov2VerifierContractDigest": digest, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def holdout_guard(private_dir: Path, l11_dir: Path, digest: str) -> Path:
    require_selected(private_dir, digest)
    require_stress_passed(private_dir, digest)
    lock = Path(l11_dir) / det.HOLDOUT_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"original B3-L11 holdout already evaluated once: {lock.name}")
    return lock


# ------------------------------------------------------------------ verdicts / interpretation


def verdict(dev_selected: Optional[bool], stress_pass: Optional[bool], holdout_pass: Optional[bool]) -> str:
    if not dev_selected:
        return "DINOV2_VERIFIER_FAILED_DEVELOPMENT"
    if stress_pass is None:
        return "DINOV2_VERIFIER_DEVELOPMENT_PASSED"
    if not stress_pass:
        return "DINOV2_VERIFIER_KNOWN_CONSTRUCT_STRESS_FAILED"
    if holdout_pass is None:
        return "DINOV2_VERIFIER_KNOWN_CONSTRUCT_STRESS_PASSED"
    return "DINOv2_VISUAL_MARK_VERIFIER_CONTROLLED_GATE_PASSED" if holdout_pass else "DINOV2_VISUAL_MARK_VERIFIER_HOLDOUT_FAILED"


def support(passed: bool) -> str:
    return "VISUAL_MARK_EDGE_SCAN_VERIFIER_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY" if passed else "DINOV2_VISUAL_MARK_VERIFIER_NOT_SUPPORTED"


def diagnosis(table: Sequence[Mapping[str, Any]]) -> list[str]:
    out = set()
    clean_ok = [t for t in table if t["criteria"]["J1"]]
    recall_ok = [t for t in table if all(t["criteria"][k] for k in ("J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10")) and t["edge"]["gate"]["pass"]]
    if table and not any(t["eligible"] for t in table) and clean_ok and recall_ok and not set(id(t) for t in clean_ok) & set(id(t) for t in recall_ok):
        out.add("FROZEN_VISUAL_REPRESENTATION_NOT_SEPARATING")
    for t in table:
        c = t["criteria"]
        broad_ok = all(c[k] for k in ("J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10"))
        if not c["J1"] and broad_ok and t["edge"]["gate"]["pass"]:
            out.add("CLEAN_HARD_NEGATIVES_NOT_SEPARATING")
        if c["J1"] and not broad_ok:
            out.add("BROAD_MARK_RECALL_REGRESSION")
        if c["J1"] and (not c["J9"] or not t["edge"]["gate"]["pass"]):
            out.add("EDGE_MARK_RECALL_REGRESSION")
    if table and not recall_ok and not clean_ok:
        out.add("FROZEN_VISUAL_REPRESENTATION_NOT_SEPARATING")
    if len(out) > 1:
        out.add("MIXED")
    return sorted(out)


def failure_escalation() -> dict[str, Any]:
    return {"rule": STOP_RULE, "next": NEXT_ON_FAILURE, "notTried": ["SigLIP", "OpenCLIP", "DINOv2-large", "new classifier head", "new threshold", "new crop"],
            "note": "a DINOv2 development failure ends B3 verifier shopping; the next research step is supervised watermark/logo data design"}


def interpretation_note() -> dict[str, Any]:
    return {"b3l13": "PROPOSAL_UNION_COVERAGE_INSUFFICIENT", "b3l14a": "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED", "b3l15a": "EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT", "priorFailuresReopened": False,
            "proposalArchitecture": PROPOSAL_FREEZE_MARKER, "forbiddenInterpretations": list(FORBIDDEN_INTERPRETATIONS), "note": "one representation swap under the frozen proposal architecture; NATURAL_POSITIVE_EVIDENCE_MISSING always"}


def stress_designation() -> dict[str, Any]:
    d = es.stress_designation()
    d["note"] = "B3-L14A G4-G5 EDGE_HOLDOUT_VARIANT: detector captures consumed in B3-L14A, scan deterministic; only the DINOv2 verifier outputs are new"
    return d
