"""Watermark runtime-evidence-authority contract (product decision
REVIEW_WITH_REDACTED_EVIDENCE_PARITY, 2026-08-31).

Locks three things:

1. Policy: a SINGLE, non-repeated, confidence-unknown `implausible` token —
   even when sourceConsistency is inconsistent or not_available — is REVIEW,
   not hard reject. Strong corroborated overlays (repeated, or
   high-confidence artifact evidence) stay hard rejects.
2. Evidence authority: token quality is derived once from raw OCR, then only
   the privacy-safe categorical evidence is serialized; classification from
   the serialized evidence must equal classification from raw regions
   (runtime/offline parity), with no raw token, text, or bbox persisted.
3. Legacy evidence without the derived field stays nonblocking-safe.

All OCR tokens in this file are synthetic. No real G004 candidate text.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.visual_risk import VisualRiskRegion  # noqa: E402
from avatar_generation.analysis.watermark import (  # noqa: E402
    WATERMARK_QA_ACTION_ALLOW,
    WATERMARK_QA_ACTION_REJECT,
    WATERMARK_QA_ACTION_REVIEW,
    classify_watermark_evidence_document,
    evaluate_watermark_risk,
)

SIZE = (1000, 1000)
# Corner + small area -> overlay_like per the location/area evidence bands.
CORNER_BBOX = (20.0, 20.0, 120.0, 60.0)
CENTRAL_BBOX = (400.0, 500.0, 600.0, 560.0)

# Synthetic fragmented token: multiple short fragments -> implausible.
IMPLAUSIBLE_LABEL = "zq xv k9"
PLAUSIBLE_LABEL = "festival"
ARTIFACT_HINT_LABEL = "watermark zz"


def _region(label, *, bbox=CORNER_BBOX, confidence=None, kind="text"):
    return VisualRiskRegion(
        kind=kind,
        bbox_xyxy=bbox,
        confidence=confidence,
        raw_label=label,
    )


def _source_region(label):
    return _region(label, bbox=CENTRAL_BBOX, confidence=0.9)


# --- RED #1: current bug — single weak implausible token must be REVIEW ----

def test_single_weak_implausible_token_with_inconsistent_source_is_review():
    decision = evaluate_watermark_risk(
        [_region(IMPLAUSIBLE_LABEL, confidence=None)],
        source_regions=[_source_region(PLAUSIBLE_LABEL)],
        image_size=SIZE,
        source_image_size=SIZE,
    )
    assert decision.watermark_qa_action == WATERMARK_QA_ACTION_REVIEW
    assert decision.hard_reject is False
    assert decision.needs_review is True
    assert decision.decision_class == "generated_text_artifact"


# --- RED #2: not_available source evidence must not escalate to reject -----

def test_single_weak_implausible_token_with_no_source_evidence_is_review():
    decision = evaluate_watermark_risk(
        [_region(IMPLAUSIBLE_LABEL, confidence=None)],
        source_regions=[],
        image_size=SIZE,
    )
    assert decision.watermark_qa_action == WATERMARK_QA_ACTION_REVIEW
    assert decision.hard_reject is False


# --- #3: true strong overlays stay hard rejects ----------------------------

def test_repeated_overlay_token_still_hard_rejects():
    regions = [
        _region(IMPLAUSIBLE_LABEL, bbox=(20.0, 20.0, 120.0, 60.0)),
        _region(IMPLAUSIBLE_LABEL, bbox=(880.0, 930.0, 980.0, 970.0)),
    ]
    decision = evaluate_watermark_risk(regions, image_size=SIZE)
    assert decision.watermark_qa_action == WATERMARK_QA_ACTION_REJECT
    assert decision.hard_reject is True


def test_high_confidence_artifact_hint_overlay_still_hard_rejects():
    decision = evaluate_watermark_risk(
        [_region(ARTIFACT_HINT_LABEL, confidence=0.95)],
        image_size=SIZE,
    )
    assert decision.watermark_qa_action == WATERMARK_QA_ACTION_REJECT


def test_high_confidence_implausible_overlay_still_hard_rejects():
    decision = evaluate_watermark_risk(
        [_region(IMPLAUSIBLE_LABEL, confidence=0.95)],
        image_size=SIZE,
    )
    assert decision.watermark_qa_action == WATERMARK_QA_ACTION_REJECT


# --- #4: ordinary plausible text stays nonblocking -------------------------

def test_ordinary_plausible_text_stays_allow():
    decision = evaluate_watermark_risk(
        [_region(PLAUSIBLE_LABEL, bbox=CENTRAL_BBOX, confidence=0.9)],
        image_size=SIZE,
    )
    assert decision.watermark_qa_action == WATERMARK_QA_ACTION_ALLOW
    assert decision.hard_reject is False
    assert decision.needs_review is False


# --- #5: ambiguous OCR (unknown token quality) stays nonblocking -----------

def test_unknown_token_quality_stays_allow():
    decision = evaluate_watermark_risk(
        [_region(None, confidence=None)],
        image_size=SIZE,
    )
    assert decision.watermark_qa_action == WATERMARK_QA_ACTION_ALLOW
    assert decision.decision_class == "ambiguous_text_evidence"


# --- #6: derived signal serialization + privacy + parity -------------------

def test_serialized_evidence_is_privacy_safe_and_classifies_identically():
    raw_regions = [_region(IMPLAUSIBLE_LABEL, confidence=None)]
    decision = evaluate_watermark_risk(
        raw_regions,
        source_regions=[_source_region(PLAUSIBLE_LABEL)],
        image_size=SIZE,
        source_image_size=SIZE,
    )
    document = decision.to_document()
    serialized = json.dumps(document, ensure_ascii=False)

    # Raw OCR contents, coordinates, and bboxes must never be serialized.
    for forbidden in ("zq", "xv", "k9", "festival", "bbox", "coordinate", "20.0"):
        assert forbidden not in serialized, forbidden

    evidence = document["evidence"]
    assert evidence["tokenQualityBands"] == {"implausible": 1}
    assert evidence["regionEvidence"], "typed region evidence must be serialized"
    for region in evidence["regionEvidence"]:
        assert set(region) <= {
            "kind",
            "confidenceBand",
            "areaBand",
            "location",
            "overlayLike",
            "tokenQuality",
            "sourceConsistent",
            "repeated",
            "artifactHint",
        }

    replayed = classify_watermark_evidence_document(evidence)
    assert replayed is not None
    assert replayed.watermark_qa_action == decision.watermark_qa_action
    assert replayed.decision_class == decision.decision_class
    assert replayed.hard_reject == decision.hard_reject
    assert replayed.needs_review == decision.needs_review


def test_reject_evidence_replays_to_reject():
    decision = evaluate_watermark_risk(
        [
            _region(IMPLAUSIBLE_LABEL, bbox=(20.0, 20.0, 120.0, 60.0)),
            _region(IMPLAUSIBLE_LABEL, bbox=(880.0, 930.0, 980.0, 970.0)),
        ],
        image_size=SIZE,
    )
    replayed = classify_watermark_evidence_document(decision.to_document()["evidence"])
    assert replayed is not None
    assert replayed.watermark_qa_action == WATERMARK_QA_ACTION_REJECT


# --- #7: legacy evidence without the derived field -------------------------

def test_legacy_evidence_without_token_quality_is_not_reclassified():
    legacy_evidence = {
        "ocrDetectionCount": 1,
        "recognizedTokenCount": 1,
        "confidenceBands": {"unknown": 1},
        "areaBands": {"small": 1},
        "locationBands": {"corner": 1},
        "repeatedTokenCount": 0,
        "sourceConsistency": "inconsistent",
    }
    # Missing derived field must NOT be inferred as implausible/reject.
    assert classify_watermark_evidence_document(legacy_evidence) is None


# --- #8: determinism -------------------------------------------------------

def test_same_typed_evidence_always_yields_the_same_decision():
    def run():
        decision = evaluate_watermark_risk(
            [_region(IMPLAUSIBLE_LABEL, confidence=None)],
            source_regions=[_source_region(PLAUSIBLE_LABEL)],
            image_size=SIZE,
            source_image_size=SIZE,
        )
        return json.dumps(decision.to_document(), sort_keys=True)

    first = run()
    for _ in range(24):
        assert run() == first
