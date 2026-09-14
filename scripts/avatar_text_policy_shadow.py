"""B3-L9 — TEXT_POLICY_SHADOW_V1 (pre-registered, decision-neutral, review-only supplement).

Narrow single-text watermark shadow over the *canonical* watermark evidence
document (watermark_policy_v4_runtime_evidence_parity_v1).  It never touches
the canonical policy: shadowAction = max(canonicalAction, proposedTextReview).

Design status: DEVELOPMENT_DESIGNED.  The candidate set was designed after an
aggregate typed-feature inventory of G1-G3 (used several times before as
development evidence); G1-G3 performance is therefore not independent
validation.  The only independent evidence is the unopened G4-G5 holdout,
evaluated exactly once behind text_policy_v1_holdout_evaluated.lock.

Runtime inputs are only typed fields the canonical evidence document already
carries in production (kind, location, areaBand, overlayLike, repeated,
artifactHint, textQuality, ocrDetectionCount).  confidenceBand is always
"unknown" in production and is NOT a probability; sourceConsistent is inert in
the canonical Azure worker mode (source_regions=()); neither may be used.  Raw
OCR text, human labels, construct families, ground-truth boxes, base/group
identifiers are refused.

Prior results are immutable: V1, V2, V3 and the dual-channel H4 verdicts stand.
The graphical channel (OWLv2 0.25, prompts, families) is out of scope.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402

# ------------------------------------------------------------------ versions

VERSION = "TEXT_POLICY_SHADOW_V1"
CANDIDATE_SET_VERSION = "TEXT_POLICY_CANDIDATES_V1"
DESIGNATION = "DEVELOPMENT_DESIGNED"
EVIDENCE_LABEL = "G004_TEXT_POLICY_SHADOW_EVIDENCE_V1"
RECALL_LABEL = "CONTROLLED_CHALLENGE_ACTION_RECALL"
HOLDOUT_LOCK_NAME = "text_policy_v1_holdout_evaluated.lock"
SELECTED_MARKER_NAME = "text_policy_v1_selected.json"
NATURAL_POSITIVE_LIMITATION = "NATURAL_POSITIVE_EVIDENCE_MISSING"
GRAPHICAL_STUDY_MARKER = "GRAPHICAL_DETECTOR_STUDY_REQUIRED"
GRAPHICAL_GAP_FAMILIES = ("GRAPHICAL_WATERMARK", "EDGE_MARK", "CENTER_OVERLAY_MARK")

PRIOR_STATUS = {
    "V1": "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT",
    "V2": "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT",
    "V3": "V3_DUAL_CHANNEL_FAILED_DEVELOPMENT",
    "H4_DUAL_CHANNEL": "H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED",
    "V3_DIAGNOSIS": ("TEXT_POLICY_GAP", "GRAPHICAL_CHANNEL_GAP", "MIXED"),
}

CANONICAL_POLICY_VERSION = v3.CHANNEL_T_POLICY_VERSION
CANONICAL_SOURCE = v3.CHANNEL_T_SOURCE

# ------------------------------------------------------------------ runtime typed evidence (fresh schema audit, main fc28646b)
# analysis/watermark.py::_typed_region_document / _evidence_document
TEXT_LIKE_KINDS = frozenset({"text", "logo", "sign"})
ALL_LOCATIONS = frozenset({"corner", "edge", "central", "clothing_zone"})
ALL_AREA_BANDS = frozenset({"small", "medium", "large"})   # small <= 0.03, medium <= 0.08 of image area
TEXT_QUALITIES = frozenset({"plausible", "implausible", "unknown"})
ALLOWED_RUNTIME_FIELDS = frozenset({
    "kind", "location", "areaBand", "overlayLike", "repeated", "artifactHint", "textQuality",  # per region
    "ocrDetectionCount",                                                                       # per image
})
# Present in the schema but not admissible as predicate inputs:
INERT_OR_NON_PROBABILISTIC_FIELDS = frozenset({"confidenceBand", "sourceConsistent"})
RAW_TEXT_FIELDS = frozenset({"token_key", "tokenKey", "labels", "label", "rawLabel", "raw_label", "quad_boxes", "quadBoxes",
                             "text", "ocr_text", "ocrText", "transcription", "tokens"})
EVALUATION_ONLY_FIELDS = frozenset({"family", "familyCode", "constructFamily", "construct", "groundTruth", "groundTruthBox",
                                    "groundTruthBoxes", "injectedBox", "injected", "markPresent", "textPresent",
                                    "baseOpaqueId", "opaqueId", "groupKey", "split", "conditionId", "derivativeDigest",
                                    "filename", "path"})
FORBIDDEN_RUNTIME_FIELDS = frozenset(sel.HUMAN_ONLY_FIELDS) | RAW_TEXT_FIELDS | EVALUATION_ONLY_FIELDS | INERT_OR_NON_PROBABILISTIC_FIELDS
_SEVERITY = {"allow": 0, "review": 1, "reject": 2}
FLAGGED = frozenset({"review", "reject"})

# ------------------------------------------------------------------ candidates (frozen; strict -> broad)


@dataclass(frozen=True)
class Candidate:
    id: str
    rank: int                              # 1 = strictest; selection takes the lowest eligible rank
    locations: frozenset                   # region.location must be in this set
    overlay_like: Optional[bool]           # None = not constrained
    single_region: bool                    # evidence.ocrDetectionCount == 1
    area_bands: frozenset                  # region.areaBand must be in this set
    confidence_bands: Optional[frozenset] = None   # must stay None: confidence is not a probability

    def __post_init__(self) -> None:
        if self.confidence_bands is not None:
            raise ValueError("confidenceBand is not a probability and cannot be a predicate input")
        if not self.locations <= ALL_LOCATIONS or not self.area_bands <= ALL_AREA_BANDS:
            raise ValueError("unknown typed enum in candidate")

    @property
    def predicate(self) -> str:
        parts = [f"kind in {sorted(TEXT_LIKE_KINDS)}", f"location in {sorted(self.locations)}", f"areaBand in {sorted(self.area_bands)}"]
        if self.overlay_like is not None:
            parts.append(f"overlayLike == {self.overlay_like}")
        if self.single_region:
            parts.append("ocrDetectionCount == 1")
        return " AND ".join(parts)


CANDIDATES: tuple[Candidate, ...] = (
    # T1 STRICT: the classic overlay signature (small text at a corner/edge, overlay-like geometry).
    Candidate("T1", 1, frozenset({"corner", "edge"}), True, False, frozenset({"small"})),
    # T2: one isolated small text region in the non-torso centre.
    Candidate("T2", 2, frozenset({"central"}), False, True, frozenset({"small"})),
    # T3: one isolated small non-overlay-like text region in the centre or torso band.
    Candidate("T3", 3, frozenset({"central", "clothing_zone"}), False, True, frozenset({"small"})),
    # T4 BROAD: one isolated small/medium text region anywhere.
    Candidate("T4", 4, ALL_LOCATIONS, None, True, frozenset({"small", "medium"})),
)
CANDIDATE_BY_ID = {c.id: c for c in CANDIDATES}

# ------------------------------------------------------------------ criteria (frozen; same on development and holdout)

NEW_REVIEW_CEILING = 0.10        # A  new clean allow->review rate
TEXT_RECALL_FLOOR = 0.90         # B opaque, C translucent (N=8 holdout => 8/8)
REPEATED_PRESERVATION = 1.0      # D canonical reject preserved
CRITERIA = ("A", "B", "C", "D", "E", "F")
V4_VERSION = "AVATAR_WATERMARK_DUAL_CHANNEL_V4"
V4_OWLV2_THRESHOLD = v3.OWLV2_THRESHOLD   # 0.25, not tuned
V4_PROMPTS = v3.PROMPTS


def candidate_definitions() -> list[dict[str, Any]]:
    out = []
    for c in CANDIDATES:
        d = asdict(c)
        d["locations"] = sorted(c.locations)
        d["area_bands"] = sorted(c.area_bands)
        d["predicate"] = c.predicate
        out.append(d)
    return out


def contract_digest() -> str:
    payload = {
        "version": VERSION,
        "candidateSet": CANDIDATE_SET_VERSION,
        "candidates": candidate_definitions(),
        "allowedRuntimeFields": sorted(ALLOWED_RUNTIME_FIELDS),
        "forbiddenRuntimeFields": sorted(FORBIDDEN_RUNTIME_FIELDS),
        "composition": "max(canonicalAction, review if proposed else allow)",
        "criteria": {"A": NEW_REVIEW_CEILING, "B": TEXT_RECALL_FLOOR, "C": TEXT_RECALL_FLOOR, "D": REPEATED_PRESERVATION, "E": 0, "F": 0},
        "selection": "lowest rank among eligible (strictest), never by recall",
        "split": {"development": list(sel.DEVELOPMENT_GROUPS), "holdout": list(sel.HOLDOUT_GROUPS)},
        "canonicalPolicyVersion": CANONICAL_POLICY_VERSION,
        "v4": {"owlv2Threshold": V4_OWLV2_THRESHOLD, "prompts": list(V4_PROMPTS)},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ runtime rule


# The canonical evidence document legitimately carries confidenceBand / sourceConsistent on
# every region; the predicate never reads them.  Everything else in FORBIDDEN_RUNTIME_FIELDS
# must not even be present on a runtime input.
_REFUSED_ON_EVIDENCE = FORBIDDEN_RUNTIME_FIELDS - INERT_OR_NON_PROBABILISTIC_FIELDS


def _refuse_forbidden(mapping: Mapping[str, Any], *, where: str) -> None:
    banned = FORBIDDEN_RUNTIME_FIELDS if where == "runtime" else _REFUSED_ON_EVIDENCE
    leaked = banned & set(mapping)
    if leaked:
        raise ValueError(f"{where}: not a runtime input: {sorted(leaked)}")


def proposed_review(candidate: Candidate, evidence: Mapping[str, Any]) -> bool:
    """True when the frozen predicate holds on the canonical typed evidence document."""

    _refuse_forbidden(evidence, where="evidence")
    regions = evidence.get("regionEvidence") or []
    if not regions:
        return False
    if candidate.single_region and int(evidence.get("ocrDetectionCount", len(regions))) != 1:
        return False
    for region in regions:
        _refuse_forbidden(region, where="region")
        if str(region.get("kind")) not in TEXT_LIKE_KINDS:
            continue
        if str(region.get("location")) not in candidate.locations:
            continue
        if str(region.get("areaBand")) not in candidate.area_bands:
            continue
        if candidate.overlay_like is not None and bool(region.get("overlayLike")) != candidate.overlay_like:
            continue
        return True
    return False


def shadow_action(canonical_action: str, proposed: bool) -> str:
    if canonical_action not in _SEVERITY:
        raise ValueError("unknown canonical action")
    supplement = "review" if proposed else "allow"
    return canonical_action if _SEVERITY[canonical_action] >= _SEVERITY[supplement] else supplement


def candidate_action(candidate: Candidate, canonical_action: str, evidence: Mapping[str, Any], **runtime_inputs: Any) -> str:
    _refuse_forbidden(runtime_inputs, where="runtime")
    return shadow_action(canonical_action, proposed_review(candidate, evidence))


# ------------------------------------------------------------------ V4 recomposition (only after a holdout pass)


class HoldoutNotPassed(RuntimeError):
    pass


def require_holdout_pass(text_report: Mapping[str, Any]) -> None:
    if text_report.get("holdoutVerdict") != "TEXT_POLICY_SHADOW_CONTROLLED_GATE_PASSED":
        raise HoldoutNotPassed("V4 recomposition requires the text shadow to pass holdout")


def v4_graphical_hit(detections: Sequence[Mapping[str, Any]], threshold: float = V4_OWLV2_THRESHOLD) -> bool:
    if threshold != V4_OWLV2_THRESHOLD:
        raise ValueError("graphical threshold is frozen at 0.25; no tuning in this task")
    return sel.detector_hit(detections, V4_OWLV2_THRESHOLD, V4_PROMPTS)


def v4_action(canonical_action: str, *, proposed_text_review: bool, graphical_hit: bool) -> str:
    text_action = shadow_action(canonical_action, proposed_text_review)
    graphical = "review" if graphical_hit else "allow"
    return text_action if _SEVERITY[text_action] >= _SEVERITY[graphical] else graphical


# ------------------------------------------------------------------ metrics


def clean_burden(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    canonical = Counter(i["canonicalAction"] for i in items)
    shadow = Counter()
    new_review = 0
    for i in items:
        action = shadow_action(i["canonicalAction"], bool(i["proposed"]))
        shadow[action] += 1
        if i["canonicalAction"] == "allow" and action == "review":
            new_review += 1
    n = len(items)
    return {
        "n": n,
        "canonical": {a: canonical.get(a, 0) for a in ("allow", "review", "reject")},
        "v3": {a: shadow.get(a, 0) for a in ("allow", "review", "reject")},   # key kept for tooling parity: shadow action counts
        "newAllowToReview": new_review,
        "newReviewRate": round(new_review / n, 4) if n else None,
        "newReviewRateCI": calib.wilson(new_review, n) if n else None,
        "existingCanonicalBurdenNotCounted": canonical.get("review", 0) + canonical.get("reject", 0),
    }


def family_recall(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    canonical = sum(1 for r in rows if r["canonicalAction"] in FLAGGED)
    flagged = sum(1 for r in rows if shadow_action(r["canonicalAction"], bool(r["proposed"])) in FLAGGED)
    return {"n": n, "canonicalFlagged": canonical, "shadowFlagged": flagged, "rate": round(flagged / n, 4) if n else None,
            "rateCI": calib.wilson(flagged, n) if n else None, "label": RECALL_LABEL}


def repeated_preservation(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    preserved = sum(1 for r in rows if r["canonicalAction"] == "reject" and shadow_action("reject", bool(r["proposed"])) == "reject")
    return {"n": n, "rejectPreserved": preserved, "rate": round(preserved / n, 4) if n else None}


def safety(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    bypass = regressions = 0
    for r in rows:
        action = shadow_action(r["canonicalAction"], bool(r["proposed"]))
        if _SEVERITY[action] < _SEVERITY[r["canonicalAction"]]:
            regressions += 1
        if r["canonicalAction"] == "reject" and action != "reject":
            bypass += 1
    return {"hardRejectBypass": bypass, "artifactRegressions": regressions}


def eligible(clean: Mapping[str, Any], text_recall: Mapping[str, Optional[float]], repeated_rate: Optional[float],
             *, hard_reject_bypass: int, artifact_regressions: int) -> dict[str, Any]:
    opaque = text_recall.get("TEXT_WATERMARK_OPAQUE")
    translucent = text_recall.get("TEXT_WATERMARK_TRANSLUCENT")
    checks = {
        "A": clean.get("newReviewRate") is not None and clean["newReviewRate"] <= NEW_REVIEW_CEILING,
        "B": opaque is not None and opaque >= TEXT_RECALL_FLOOR,
        "C": translucent is not None and translucent >= TEXT_RECALL_FLOOR,
        "D": repeated_rate is not None and repeated_rate >= REPEATED_PRESERVATION,
        "E": hard_reject_bypass == 0,
        "F": artifact_regressions == 0,
    }
    return {"criteria": checks, "eligible": all(checks[c] for c in CRITERIA), "failed": [c for c in CRITERIA if not checks[c]]}


def select_candidate(development_table: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Strictest (lowest rank) eligible candidate; recall never breaks the order."""

    ordered = sorted(CANDIDATES, key=lambda c: c.rank)
    for cand in ordered:
        if (development_table.get(cand.id) or {}).get("eligible"):
            return {"status": "SELECTED", "selectedCandidate": cand.id, "predicate": cand.predicate, "rank": cand.rank,
                    "reason": "strictest candidate satisfying A-F on development (pre-registered narrowness order)"}
    return {"status": "NONE", "selectedCandidate": None, "predicate": None, "rank": None,
            "reason": "no candidate satisfies A-F on development"}


# ------------------------------------------------------------------ freeze + one-shot holdout


class CandidateNotFrozen(RuntimeError):
    pass


def selected_marker(private_dir: Path) -> Path:
    return Path(private_dir) / SELECTED_MARKER_NAME


def write_selected_marker(private_dir: Path, candidate_id: str, digest: str, dev_inputs_digest: str) -> Path:
    marker = selected_marker(private_dir)
    marker.write_text(json.dumps({"version": VERSION, "candidateSet": CANDIDATE_SET_VERSION, "selectedCandidate": candidate_id,
                                  "predicate": CANDIDATE_BY_ID[candidate_id].predicate if candidate_id in CANDIDATE_BY_ID else None,
                                  "contractDigest": digest, "developmentInputsDigest": dev_inputs_digest,
                                  "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return marker


def require_selected(private_dir: Path, digest: str) -> Mapping[str, Any]:
    marker = selected_marker(private_dir)
    if not marker.exists():
        raise CandidateNotFrozen("holdout requires a frozen selected-candidate record")
    record = json.loads(marker.read_text(encoding="utf-8"))
    if record.get("contractDigest") != digest or record.get("version") != VERSION or record.get("selectedCandidate") not in CANDIDATE_BY_ID:
        raise CandidateNotFrozen("selected-candidate record does not match the frozen contract")
    return record


def holdout_guard(private_dir: Path, digest: str) -> Path:
    require_selected(private_dir, digest)
    lock = Path(private_dir) / HOLDOUT_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"text-policy holdout already evaluated once: {lock.name}")
    return lock


def mark_holdout_evaluated(lock: Path, digest: str) -> None:
    lock.write_text(json.dumps({"version": VERSION, "contractDigest": digest, "evaluatedAt": datetime.now(timezone.utc).isoformat()}),
                    encoding="utf-8")


def verdicts(dev_pass: bool, holdout_pass: Optional[bool]) -> dict[str, str]:
    if not dev_pass:
        return {"verdict": "TEXT_POLICY_SHADOW_FAILED_DEVELOPMENT", "support": "TEXT_POLICY_SHADOW_NOT_SUPPORTED"}
    if holdout_pass:
        return {"verdict": "TEXT_POLICY_SHADOW_CONTROLLED_GATE_PASSED", "support": "TEXT_POLICY_SHADOW_SUPPORTED_FOR_CONTROLLED_CANARY"}
    return {"verdict": "TEXT_POLICY_SHADOW_HOLDOUT_FAILED", "support": "TEXT_POLICY_SHADOW_NOT_SUPPORTED"}
