"""B3-L8 — AVATAR_WATERMARK_DUAL_CHANNEL_V3 (pre-registered, decision-neutral shadow).

Two evidence channels, composed by max severity, escalate-only:

  CHANNEL T  CANONICAL_FLORENCE_TEXT_POLICY
             The *actual* canonical watermark policy decision
             (avatar_generation.analysis.watermark.evaluate_watermark_risk over
             analyze_florence_visual_risk_outputs) on the *actual* derivative.
             Raw OCR presence is NOT an action.  Nothing in the policy is tuned.
  CHANNEL G  OWLV2_GRAPHICAL_SUPPLEMENT
             OWLv2 combined-prompt hit >= 0.25 -> review (never reject).

V3 is a separate hypothesis: it replaces neither gate v1
(owlv2_provisional_shadow_gate_v1, OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT)
nor gate V2 (OWLV2_CONTROLLED_CHALLENGE_GATE_V2,
OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT).  Their results are frozen.

Runtime inputs are only what production has: Florence task outputs, image size,
OWLv2 detections.  Human labels, construct families and ground-truth boxes are
evaluation metadata and are refused as runtime inputs.

Everything here is pure logic (CI-safe).  Model inference lives in the local
capture runner; user images never enter the repo.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from PIL import Image

SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
from avatar_generation.analysis.visual_risk import analyze_florence_visual_risk_outputs  # noqa: E402
from avatar_generation.analysis.watermark import (  # noqa: E402
    WATERMARK_POLICY_VERSION,
    evaluate_watermark_risk,
)

# ------------------------------------------------------------------ versions

V3_VERSION = "AVATAR_WATERMARK_DUAL_CHANNEL_V3"
EVIDENCE_LABEL = "G004_DUAL_CHANNEL_CONTROLLED_EVIDENCE_V3"
RECALL_LABEL = "CONTROLLED_CHALLENGE_ACTION_RECALL"
GATE_V1_STATUS_FROZEN = "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT"
GATE_V2_STATUS_FROZEN = "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT"
NATURAL_POSITIVE_LIMITATION = "NATURAL_POSITIVE_EVIDENCE_MISSING"

CHANNEL_T = "CANONICAL_FLORENCE_TEXT_POLICY"
CHANNEL_G = "OWLV2_GRAPHICAL_SUPPLEMENT"

# Channel T provenance (fresh audit, main 802e89d5): the production worker
# (ENVIRONMENT=production -> run_mode CANONICAL_AZURE_WORKER_MODE) disables
# source visual risk, so compute_candidate_qa_signals -> _add_visual_signals ->
# evaluate_watermark_risk(regions, source_regions=(), image_size=candidate size).
# The primary-face bbox only re-labels person regions and never reaches the
# text-like filter, so it is not a watermark input.
CHANNEL_T_POLICY_VERSION = WATERMARK_POLICY_VERSION
CHANNEL_T_SOURCE = (
    "avatar_generation.analysis.watermark.evaluate_watermark_risk"
    " <- avatar_generation.analysis.visual_risk.analyze_florence_visual_risk_outputs"
    " (qa_signals._add_visual_signals contract; source_regions=() as in canonical Azure worker mode)"
)

FLORENCE_REPO = "florence-community/Florence-2-large-ft"
FLORENCE_TASKS = (bench.TASK_OCR_WITH_REGION, bench.TASK_OD)
_DOCKERFILE = REPO_ROOT / "lib" / "ai_recommend_model" / "avatar_generation" / "Dockerfile"


def pinned_florence_revision() -> str:
    """Production authority: the Dockerfile ARG, read fresh (never hardcoded)."""

    match = re.search(r"ARG QA_FLORENCE_REVISION=([0-9a-f]{40})", _DOCKERFILE.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("FLORENCE_PIN_MISSING")
    return match.group(1)


OWLV2_REPO = "google/owlv2-base-patch16-ensemble"
OWLV2_REVISION = "cfd3195ba4ea9592eec887ded089f4c08eff231d"
OWLV2_THRESHOLD = 0.25
OWLV2_THRESHOLD_AUTHORITY = "DEVELOPMENT_SELECTED_GRAPHICAL_SUPPLEMENT_THRESHOLD"
PROMPTS = sel.PROMPTS
PROMPT_MODE = sel.PROMPT_MODE
DEVELOPMENT_GROUPS = sel.DEVELOPMENT_GROUPS
HOLDOUT_GROUPS = sel.HOLDOUT_GROUPS
TRUTH_AUTHORITY = "OWNER_DESIGNATED_RATER_A_REFERENCE_TRUTH"

_SEVERITY = {"allow": 0, "review": 1, "reject": 2}
FLAGGED = frozenset({"review", "reject"})

FAMILY_META_FIELDS = frozenset({"family", "familyCode", "constructFamily", "construct"})
GROUND_TRUTH_FIELDS = frozenset({"groundTruthBox", "groundTruthBoxes", "groundTruth", "injectedBox"})
FORBIDDEN_RUNTIME_FIELDS = frozenset(sel.HUMAN_ONLY_FIELDS) | FAMILY_META_FIELDS | GROUND_TRUTH_FIELDS

# ------------------------------------------------------------------ criteria (frozen)

NEW_REVIEW_CEILING = 0.10          # A  OWLv2 supplement new clean-review rate
OVERALL_RECALL_FLOOR = 0.95        # B  V3 overall controlled-positive action recall
FAMILY_RECALL_FLOOR = 0.90         # C..J
GATED_FAMILIES = (
    "TEXT_WATERMARK_OPAQUE",       # C
    "TEXT_WATERMARK_TRANSLUCENT",  # D
    "GRAPHICAL_WATERMARK",         # E
    "LOGO_LIKE_EMBLEM",            # F
    "SMALL_CORNER_MARK",           # G
    "EDGE_MARK",                   # H
    "CENTER_OVERLAY_MARK",         # I
    "REPEATED_TILED_MARK",         # J
)
DIAGNOSTIC_ONLY_FAMILIES = ("BRAND_LIKE_TEXT_AND_SYMBOL", "GRAPHIC_SYMBOL")  # overall recall only
CRITERIA = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L")
V3_HOLDOUT_LOCK_NAME = "v3_holdout_evaluated.lock"
V3_DEV_PASS_MARKER = "v3_development_passed.json"

GAP_TEXT_MODEL = "TEXT_MODEL_GAP"
GAP_TEXT_POLICY = "TEXT_POLICY_GAP"
GAP_GRAPHICAL = "GRAPHICAL_CHANNEL_GAP"
GAP_CLEAN = "CLEAN_BURDEN_GAP"
TEXT_FAMILIES = ("TEXT_WATERMARK_OPAQUE", "TEXT_WATERMARK_TRANSLUCENT", "REPEATED_TILED_MARK")
GRAPHICAL_FAMILIES = ("GRAPHICAL_WATERMARK", "LOGO_LIKE_EMBLEM", "SMALL_CORNER_MARK", "EDGE_MARK", "CENTER_OVERLAY_MARK")


def contract_digest() -> str:
    """Digest of every frozen rule; recorded before any new Florence number exists."""

    payload = {
        "version": V3_VERSION,
        "channelT": {"source": CHANNEL_T_SOURCE, "policyVersion": CHANNEL_T_POLICY_VERSION, "tasks": list(FLORENCE_TASKS)},
        "channelG": {"repo": OWLV2_REPO, "revision": OWLV2_REVISION, "threshold": OWLV2_THRESHOLD,
                     "prompts": list(PROMPTS), "mode": PROMPT_MODE, "action": "review"},
        "composition": "max_severity_escalate_only",
        "criteria": {"A": NEW_REVIEW_CEILING, "B": OVERALL_RECALL_FLOOR, "C-J": [FAMILY_RECALL_FLOOR, list(GATED_FAMILIES)],
                     "K": 0, "L": 0},
        "split": {"development": list(DEVELOPMENT_GROUPS), "holdout": list(HOLDOUT_GROUPS)},
        "forbiddenRuntimeFields": sorted(FORBIDDEN_RUNTIME_FIELDS),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ runtime rule


def _refuse_forbidden(runtime_inputs: Mapping[str, Any]) -> None:
    leaked = FORBIDDEN_RUNTIME_FIELDS & set(runtime_inputs)
    if leaked:
        raise ValueError(f"not a runtime input: {sorted(leaked)}")


def channel_t_action(tasks: Mapping[str, Any], image_size: Sequence[int], **runtime_inputs: Any) -> str:
    """Canonical Florence watermark policy action on the actual derivative.

    Identical call shape to production qa_signals._add_visual_signals in the
    canonical Azure worker mode (no source regions).  Raw OCR presence alone
    is not an action: a plausible, non-repeated, non-overlay token stays allow.
    """

    _refuse_forbidden(runtime_inputs)
    size = (int(image_size[0]), int(image_size[1]))
    analysis = analyze_florence_visual_risk_outputs(tasks, image_size=size)
    decision = evaluate_watermark_risk(analysis.regions, source_regions=(), image_size=size)
    action = decision.watermark_qa_action
    if action not in _SEVERITY:
        raise ValueError("canonical policy returned an unknown action")
    return action


def channel_g_hit(detections: Sequence[Mapping[str, Any]], threshold: float = OWLV2_THRESHOLD, **runtime_inputs: Any) -> bool:
    _refuse_forbidden(runtime_inputs)
    if threshold != OWLV2_THRESHOLD:
        raise ValueError("V3 OWLv2 threshold is frozen at 0.25")
    return sel.detector_hit(detections, OWLV2_THRESHOLD, PROMPTS)


def channel_g_action(graphical_hit: bool) -> str:
    """Review-only supplement.  The graphical channel never rejects."""

    return "review" if graphical_hit else "allow"


def v3_shadow_action(text_action: str, graphical_hit: bool, **runtime_inputs: Any) -> str:
    """max(textAction, graphicalAction) with allow < review < reject."""

    _refuse_forbidden(runtime_inputs)
    if text_action not in _SEVERITY:
        raise ValueError("unknown canonical action")
    graphical = channel_g_action(bool(graphical_hit))
    return text_action if _SEVERITY[text_action] >= _SEVERITY[graphical] else graphical


# ------------------------------------------------------------------ evaluation helpers


def florence_ocr_hit(tasks: Mapping[str, Any], image_size: Sequence[int], truth: Sequence[Mapping[str, Any]]) -> bool:
    """Model-level evidence only: any OCR region overlapping an injected box (IoU >= 0.3)."""

    size = (int(image_size[0]), int(image_size[1]))
    regions = bench._ocr_regions(tasks, size)
    return any(bench.iou(box, t["box"]) >= bench.IOU_MATCH for box, _ in regions for t in truth)


def clean_burden(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Clean human-negative avatars.  Only canonical allow -> V3 review counts as new burden."""

    canonical = Counter(i["canonicalAction"] for i in items)
    v3 = Counter()
    new_review = new_reject = hits = 0
    for i in items:
        hit = bool(i["owlv2Hit"])
        action = v3_shadow_action(i["canonicalAction"], hit)
        v3[action] += 1
        hits += int(hit)
        if i["canonicalAction"] == "allow" and action == "review":
            new_review += 1
        if i["canonicalAction"] != "reject" and action == "reject":
            new_reject += 1
    n = len(items)
    return {
        "n": n,
        "canonical": {a: canonical.get(a, 0) for a in ("allow", "review", "reject")},
        "owlv2Hits": hits,
        "v3": {a: v3.get(a, 0) for a in ("allow", "review", "reject")},
        "newAllowToReview": new_review,
        "newAllowToReject": new_reject,
        "newReviewRate": round(new_review / n, 4) if n else None,
        "newReviewRateCI": calib.wilson(new_review, n) if n else None,
        "existingCanonicalBurdenNotCounted": canonical.get("review", 0) + canonical.get("reject", 0),
    }


def family_attribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per family: Florence OCR hit / canonical policy flag / OWLv2 hit / V3 flag, plus channel attribution."""

    out: dict[str, Any] = {}
    by_family: dict[str, list] = {}
    for r in rows:
        by_family.setdefault(r["family"], []).append(r)
    for family, frows in sorted(by_family.items()):
        n = len(frows)
        ocr = sum(1 for r in frows if r["florenceOcrHit"])
        policy = sum(1 for r in frows if r["canonicalAction"] in FLAGGED)
        owl = sum(1 for r in frows if r["owlv2Hit"])
        v3 = sum(1 for r in frows if v3_shadow_action(r["canonicalAction"], r["owlv2Hit"]) in FLAGGED)
        both = sum(1 for r in frows if r["canonicalAction"] in FLAGGED and r["owlv2Hit"])
        neither = sum(1 for r in frows if r["canonicalAction"] not in FLAGGED and not r["owlv2Hit"])
        out[family] = {
            "n": n,
            "florenceOcrHit": ocr,
            "canonicalPolicyFlagged": policy,
            "owlv2Hit": owl,
            "v3Flagged": v3,
            "v3ActionRecall": round(v3 / n, 4) if n else None,
            "v3ActionRecallCI": calib.wilson(v3, n) if n else None,
            "textChannelFlagged": policy,
            "graphicalChannelFlagged": owl,
            "bothChannelsFlagged": both,
            "neitherFlagged": neither,
            "florenceModelDetectedPolicyDidNotFlag": sum(1 for r in frows if r["florenceOcrHit"] and r["canonicalAction"] not in FLAGGED),
            "florenceModelMiss": n - ocr,
            "owlv2ModelMiss": n - owl,
            "actionSources": {
                "reused": sum(1 for r in frows if r.get("florenceSource") == "reused_exact"),
                "locallyInferred": sum(1 for r in frows if r.get("florenceSource") == "local_inference"),
            },
        }
    return out


def safety(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """K: any V3 action below the canonical action; L: canonical reject not preserved."""

    regressions = bypass = 0
    for r in rows:
        action = v3_shadow_action(r["canonicalAction"], r["owlv2Hit"])
        if _SEVERITY[action] < _SEVERITY[r["canonicalAction"]]:
            regressions += 1
        if r["canonicalAction"] == "reject" and action != "reject":
            bypass += 1
    return {"artifactRegressions": regressions, "hardRejectBypass": bypass}


def eligible_v3(clean: Mapping[str, Any], families: Mapping[str, Mapping[str, Any]], overall_recall: Optional[float],
                *, artifact_regressions: int, hard_reject_bypass: int) -> dict[str, Any]:
    checks = {
        "A": clean.get("newReviewRate") is not None and clean["newReviewRate"] <= NEW_REVIEW_CEILING,
        "B": overall_recall is not None and overall_recall >= OVERALL_RECALL_FLOOR,
    }
    for letter, family in zip("CDEFGHIJ", GATED_FAMILIES):
        rate = (families.get(family) or {}).get("v3ActionRecall")
        checks[letter] = rate is not None and rate >= FAMILY_RECALL_FLOOR
    checks["K"] = artifact_regressions == 0
    checks["L"] = hard_reject_bypass == 0
    return {"criteria": checks, "eligible": all(checks[c] for c in CRITERIA), "failed": [c for c in CRITERIA if not checks[c]]}


def diagnose(clean: Mapping[str, Any], families: Mapping[str, Mapping[str, Any]], eligibility: Mapping[str, Any]) -> list[str]:
    """Exact channel-gap diagnosis for a development failure."""

    gaps: set[str] = set()
    if not eligibility["criteria"]["A"]:
        gaps.add(GAP_CLEAN)
    for letter, family in zip("CDEFGHIJ", GATED_FAMILIES):
        if eligibility["criteria"][letter]:
            continue
        f = families.get(family) or {}
        n = f.get("n") or 0
        ocr_rate = f.get("florenceOcrHit", 0) / n if n else 0.0
        if family in TEXT_FAMILIES:
            gaps.add(GAP_TEXT_POLICY if ocr_rate >= FAMILY_RECALL_FLOOR else GAP_TEXT_MODEL)
        else:
            gaps.add(GAP_GRAPHICAL)
    if eligibility["criteria"]["B"] is False and not gaps:
        gaps.add("MIXED")
    ordered = [g for g in (GAP_TEXT_MODEL, GAP_TEXT_POLICY, GAP_GRAPHICAL, GAP_CLEAN, "MIXED") if g in gaps]
    if len([g for g in ordered if g != "MIXED"]) > 1:
        ordered.append("MIXED")
    return ordered


# ------------------------------------------------------------------ exact Florence reuse audit

REUSE_EXACT = "EXACT_REUSABLE"
REUSE_PARTIAL = "PARTIALLY_REUSABLE"
REUSE_NONE = "NOT_REUSABLE"
BITWISE_UNPROVEN = "BITWISE_IDENTITY_UNPROVEN"


@dataclass(frozen=True)
class NormalizedSpec:
    kind: str
    text: Optional[str]
    alpha: float
    rel_size: float
    anchor: tuple[float, float]
    repeated: bool
    stroke: bool


def normalized_family_spec(spec: v2.FamilySpec) -> NormalizedSpec:
    return NormalizedSpec(spec.kind, spec.text, float(spec.alpha), float(spec.rel_size), tuple(spec.anchor), bool(spec.repeated), bool(spec.stroke))


def normalized_overlay_spec(spec: bench.OverlaySpec) -> Optional[NormalizedSpec]:
    if not spec.overlay_present:
        return None
    kind = "symbol" if spec.logo else "text"
    return NormalizedSpec(kind, spec.text, float(spec.alpha), float(spec.rel_size), tuple(spec.at), bool(spec.repeated), bool(spec.stroke))


def exact_spec_match(family: v2.FamilySpec, overlay: bench.OverlaySpec) -> bool:
    """EXACT means every rendering parameter is equal; semantic similarity is never enough."""

    target = normalized_overlay_spec(overlay)
    return target is not None and target == normalized_family_spec(family)


def candidate_variants(family: v2.FamilySpec) -> list[str]:
    return [spec.variant for spec in bench.CORE_VARIANTS if exact_spec_match(family, spec)]


def image_digest(image: Image.Image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def render_identity(base: Image.Image, family: v2.FamilySpec, variant: str) -> bool:
    """Both generators must produce byte-identical pixels AND boxes on this base."""

    a, boxes_a = v2.render_family(base, family)
    b, boxes_b = bench.render(base, bench.spec_for(variant))
    return a.size == b.size and a.tobytes() == b.tobytes() and [x["box"] for x in boxes_a] == [x["box"] for x in boxes_b]


def reuse_verdict(family: v2.FamilySpec, bases: Sequence[Image.Image], existing_variants: Iterable[str]) -> dict[str, Any]:
    """Classify one family for Florence-output reuse against the B3-L4 capture."""

    matches = [v for v in candidate_variants(family) if v in set(existing_variants)]
    if not matches:
        return {"family": family.family, "verdict": REUSE_NONE, "variant": None, "reason": "no B3-L4 variant with an identical rendering spec"}
    variant = matches[0]
    identical = all(render_identity(base, family, variant) for base in bases)
    if not identical:
        return {"family": family.family, "verdict": REUSE_NONE, "variant": variant, "reason": "identical spec but pixels differ between generators"}
    return {"family": family.family, "verdict": REUSE_EXACT, "variant": variant,
            "reason": "identical spec, byte-identical re-render and boxes on every base",
            "bitwiseIdentityOfHistoricalCapture": BITWISE_UNPROVEN}


# ------------------------------------------------------------------ holdout contract


class DevelopmentNotPassed(RuntimeError):
    pass


def dev_pass_marker(private_dir: Path) -> Path:
    return Path(private_dir) / V3_DEV_PASS_MARKER


def require_development_pass(private_dir: Path, digest: str) -> Mapping[str, Any]:
    marker = dev_pass_marker(private_dir)
    if not marker.exists():
        raise DevelopmentNotPassed("holdout inference/evaluation requires a development pass marker")
    record = json.loads(marker.read_text(encoding="utf-8"))
    if record.get("contractDigest") != digest or record.get("version") != V3_VERSION or not record.get("developmentPassed"):
        raise DevelopmentNotPassed("development pass marker does not match the frozen V3 contract")
    return record


def write_dev_pass_marker(private_dir: Path, digest: str, dev_summary: Mapping[str, Any]) -> Path:
    marker = dev_pass_marker(private_dir)
    marker.write_text(json.dumps({"version": V3_VERSION, "contractDigest": digest, "developmentPassed": True,
                                  "frozenAt": datetime.now(timezone.utc).isoformat(), "development": dev_summary}, indent=2),
                      encoding="utf-8")
    return marker


def holdout_guard_v3(private_dir: Path, digest: str) -> Path:
    require_development_pass(private_dir, digest)
    lock = Path(private_dir) / V3_HOLDOUT_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"V3 holdout already evaluated once: {lock.name}")
    return lock


def mark_holdout_evaluated_v3(lock: Path, digest: str) -> None:
    lock.write_text(json.dumps({"version": V3_VERSION, "contractDigest": digest,
                                "evaluatedAt": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


def verdicts(dev_eligible: bool, holdout_eligible: Optional[bool], safe: bool) -> dict[str, str]:
    if not dev_eligible:
        return {"v3": "V3_DUAL_CHANNEL_FAILED_DEVELOPMENT", "h4": "H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED"}
    if holdout_eligible and safe:
        return {"v3": "V3_DUAL_CHANNEL_CONTROLLED_GATE_PASSED", "h4": "H4_DUAL_CHANNEL_SHADOW_SUPPORTED_FOR_CONTROLLED_CANARY"}
    return {"v3": "V3_DUAL_CHANNEL_HOLDOUT_FAILED", "h4": "H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED"}


__all__ = [
    "BITWISE_UNPROVEN", "CHANNEL_G", "CHANNEL_T", "CHANNEL_T_SOURCE", "CRITERIA", "DIAGNOSTIC_ONLY_FAMILIES",
    "EVIDENCE_LABEL", "FAMILY_RECALL_FLOOR", "FLAGGED", "FORBIDDEN_RUNTIME_FIELDS", "GATED_FAMILIES",
    "NEW_REVIEW_CEILING", "OVERALL_RECALL_FLOOR", "OWLV2_REVISION", "OWLV2_THRESHOLD", "OWLV2_THRESHOLD_AUTHORITY",
    "PROMPTS", "RECALL_LABEL", "REUSE_EXACT", "REUSE_NONE", "REUSE_PARTIAL", "V3_HOLDOUT_LOCK_NAME", "V3_VERSION",
    "channel_g_action", "channel_g_hit", "channel_t_action", "clean_burden", "contract_digest", "diagnose",
    "eligible_v3", "exact_spec_match", "family_attribution", "florence_ocr_hit", "holdout_guard_v3",
    "mark_holdout_evaluated_v3", "pinned_florence_revision", "render_identity", "require_development_pass",
    "reuse_verdict", "safety", "v3_shadow_action", "verdicts", "write_dev_pass_marker",
]
