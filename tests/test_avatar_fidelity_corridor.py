import json
import sys
from dataclasses import fields
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.fidelity_corridor import (  # noqa: E402
    CorridorCandidate,
    CorridorMode,
    CorridorPolicy,
    FidelityLowerBoundGate,
    GateStatus,
    IdentityPrivacySignal,
    PrivacyUpperBoundGate,
    REASON_CODE_ALLOWLIST,
    REASON_CODE_ORDER,
    SafeCandidateRanking,
    SafetyGate,
    attach_shadow_corridor_document,
    evaluate_fidelity_corridor,
)
from avatar_generation.fidelity_signals import (  # noqa: E402
    FIDELITY_COMPONENT_KEYS,
    FidelitySignalBundle,
)


ACTIVE_PREVIEW_FIELDS = (
    "previewAllowed",
    "requiresHumanReview",
    "softPass",
    "rejectReasons",
    "reviewReasons",
    "selectedForPreview",
)


def _active_pass():
    return {
        "previewAllowed": True,
        "requiresHumanReview": False,
        "softPass": False,
        "rejectReasons": [],
        "reviewReasons": [],
        "selectedForPreview": True,
        "adultQa": "pass",
        "childlikeRisk": "low",
        "beautificationRisk": "low",
        "cropConsistency": "pass",
        "cropIsolationQuality": "pass",
        "uniqueMarkCopyRisk": "low",
        "logoTextWatermarkRisk": "low",
        "textLogoWatermarkRisk": "low",
        "backgroundLeakageRisk": "low",
        "secondaryFaceLeakageRisk": "low",
    }


def _identity(*, decision="pass", band="low"):
    return IdentityPrivacySignal(
        available=True,
        calibrated=True,
        upper_bound_decision=decision,
        risk_band=band,
        model_version="identity_privacy_v1",
        timing_ms=1.23456,
    )


def _signals(
    *,
    score=0.7,
    decision="pass",
    conflicting=False,
    trait_coverage_status="sufficient",
    reason_codes=(),
):
    return FidelitySignalBundle(
        fidelity_score=score,
        broad_visual_score=score,
        geometry_score=score,
        trait_consistency_score=score,
        composition_score=score,
        adult_naturalness_score=score,
        bands={
            "fidelity": "high",
            "traitConsistency": "high",
            "composition": "high",
        },
        model_availability={
            key: "available" for key in FIDELITY_COMPONENT_KEYS
        },
        model_versions={
            key: f"{key.lower()}_v1" for key in FIDELITY_COMPONENT_KEYS
        },
        timing_ms={
            **{key: 1.11119 for key in FIDELITY_COMPONENT_KEYS},
            "total": 5.55559,
        },
        trait_coverage_status=trait_coverage_status,
        lower_bound_decision=decision,
        reason_codes=reason_codes,
        conflicting=conflicting,
    )


def _calibrated_policy(mode=CorridorMode.SHADOW):
    return CorridorPolicy(
        mode=mode,
        calibration_version="corridor_calibration_fixture_v1",
    )


def _decision(*, score=0.7, identity=None, active_qa=None):
    return evaluate_fidelity_corridor(
        active_qa=active_qa or _active_pass(),
        identity_signal=identity or _identity(),
        fidelity_signals=_signals(score=score),
        policy=_calibrated_policy(),
    )


def test_policy_defaults_to_shadow_and_uncalibrated_without_numeric_thresholds():
    policy = CorridorPolicy()

    assert policy.mode is CorridorMode.SHADOW
    assert policy.calibration_version == "uncalibrated"
    assert policy.calibrated is False
    assert all("threshold" not in item.name.lower() for item in fields(policy))


def test_policy_accepts_only_off_shadow_enforced_and_invalid_falls_back_to_shadow():
    assert CorridorMode.parse("off") is CorridorMode.OFF
    assert CorridorMode.parse("shadow") is CorridorMode.SHADOW
    assert CorridorMode.parse("enforced") is CorridorMode.ENFORCED
    assert CorridorMode.parse("invented-mode") is CorridorMode.SHADOW


def test_enforced_uncalibrated_is_fail_closed_review_and_never_passes():
    decision = evaluate_fidelity_corridor(
        active_qa=_active_pass(),
        identity_signal=_identity(),
        fidelity_signals=_signals(),
        policy=CorridorPolicy(mode=CorridorMode.ENFORCED),
    )

    assert decision.mode is CorridorMode.ENFORCED
    assert decision.fidelity_lower_bound.status is GateStatus.REVIEW
    assert decision.critical_signals_available is False
    assert decision.eligible_for_ranking is False
    assert "fidelity_signal_unavailable" in decision.reason_codes
    assert set(decision.to_document()["gates"].values()) != {"pass"}


def test_three_gates_keep_identity_as_privacy_upper_bound_only():
    active_reject = {
        **_active_pass(),
        "previewAllowed": False,
        "rejectReasons": ["multiple_faces_generated"],
    }
    safety = SafetyGate().evaluate(active_reject)
    privacy = PrivacyUpperBoundGate().evaluate(
        _identity(decision="reject", band="high")
    )
    fidelity = FidelityLowerBoundGate().evaluate(
        _signals(),
        policy=_calibrated_policy(),
    )

    assert safety.status is GateStatus.REJECT
    assert safety.reason_codes == ("candidate_multiple_people",)
    assert privacy.status is GateStatus.REJECT
    assert privacy.reason_codes == ("candidate_too_identifiable",)
    assert fidelity.status is GateStatus.PASS
    assert all(
        "identity" not in item.name.lower()
        and "face_similarity" not in item.name.lower()
        for item in fields(FidelitySignalBundle)
    )


def test_unavailable_and_conflicting_signals_review_without_fake_risk_true():
    unavailable = evaluate_fidelity_corridor(
        active_qa={
            **_active_pass(),
            "previewAllowed": False,
            "requiresHumanReview": True,
            "reviewReasons": ["faceDetector_unavailable"],
        },
        identity_signal=IdentityPrivacySignal(),
        fidelity_signals=FidelitySignalBundle.unavailable(),
        policy=CorridorPolicy(),
    )
    conflict = evaluate_fidelity_corridor(
        active_qa=_active_pass(),
        identity_signal=_identity(),
        fidelity_signals=_signals(
            conflicting=True,
            reason_codes=("candidate_trait_mismatch",),
        ),
        policy=_calibrated_policy(),
    )

    unavailable_doc = unavailable.to_document()
    assert unavailable_doc["gates"] == {
        "safety": "review",
        "privacyUpperBound": "review",
        "fidelityLowerBound": "review",
    }
    assert unavailable_doc["bands"]["identityRisk"] == "unavailable"
    assert unavailable_doc["criticalSignalsAvailable"] is False
    assert "model_unavailable_systemic" in unavailable.reason_codes
    assert "privacy_signal_unavailable" in unavailable.reason_codes
    assert "fidelity_signal_unavailable" in unavailable.reason_codes
    assert conflict.fidelity_lower_bound.status is GateStatus.REVIEW
    assert "conflicting_fidelity_signals" in conflict.reason_codes


def test_critical_trait_coverage_is_a_fail_closed_fidelity_contract():
    mismatch = FidelityLowerBoundGate().evaluate(
        _signals(trait_coverage_status="mismatch"),
        policy=_calibrated_policy(),
    )
    unavailable = FidelityLowerBoundGate().evaluate(
        _signals(trait_coverage_status="unavailable"),
        policy=_calibrated_policy(),
    )

    assert mismatch.status is GateStatus.REVIEW
    assert mismatch.reason_codes == ("candidate_trait_mismatch",)
    assert unavailable.status is GateStatus.REVIEW
    assert unavailable.reason_codes == ("fidelity_signal_unavailable",)
    assert (
        _signals(trait_coverage_status="mismatch").critical_signals_available
        is False
    )
    assert (
        _signals(trait_coverage_status="unavailable").critical_signals_available
        is False
    )


def test_reason_codes_are_allowlisted_deduplicated_and_deterministically_ordered():
    active = {
        **_active_pass(),
        "previewAllowed": False,
        "rejectReasons": [
            "multiple_faces_generated",
            "childlike_or_teenager",
            "background_leakage",
        ],
    }
    decision = evaluate_fidelity_corridor(
        active_qa=active,
        identity_signal=_identity(decision="reject", band="high"),
        fidelity_signals=_signals(
            conflicting=True,
            reason_codes=(
                "candidate_generation_generic",
                "not_allowlisted",
                "candidate_trait_mismatch",
                "candidate_generation_generic",
            ),
        ),
        policy=_calibrated_policy(),
    )

    assert set(decision.reason_codes) <= REASON_CODE_ALLOWLIST
    assert decision.reason_codes == tuple(
        code for code in REASON_CODE_ORDER if code in set(decision.reason_codes)
    )
    assert decision.reason_codes == (
        "candidate_trait_mismatch",
        "candidate_generation_generic",
        "candidate_too_identifiable",
        "candidate_childlike",
        "candidate_privacy_leak",
        "candidate_multiple_people",
        "conflicting_fidelity_signals",
    )


def test_nested_document_is_strictly_sanitized_and_rounded():
    signals = FidelitySignalBundle(
        fidelity_score=0.9999999,
        broad_visual_score=0.87654321,
        geometry_score=0.76543219,
        trait_consistency_score=0.65432198,
        composition_score=0.54321987,
        adult_naturalness_score=0.43219876,
        bands={
            "fidelity": "high",
            "traitConsistency": "medium",
            "composition": "low",
            "rawTraits": "PRIVATE TRAITS",
        },
        model_availability={
            **{key: "available" for key in FIDELITY_COMPONENT_KEYS},
            "embedding": "available",
            "imageHash": "available",
        },
        trait_coverage_status="sufficient",
        model_versions={
            "broadVisual": r"C:\private\embedding.bin",
            "geometry": "geometry_v1",
            "traitConsistency": "draw private prompt",
            "composition": "composition_v1",
            "adultNaturalness": "adult_v1",
            "landmarks": "raw_landmarks",
        },
        timing_ms={
            "broadVisual": 1.23456,
            "geometry": -5,
            "imageHash": 99,
            "prompt": 100,
        },
    )
    decision = evaluate_fidelity_corridor(
        active_qa=_active_pass(),
        identity_signal=IdentityPrivacySignal(
            available=True,
            calibrated=True,
            upper_bound_decision="pass",
            risk_band="low",
            model_version="https://private/model",
            timing_ms=2.34567,
        ),
        fidelity_signals=signals,
        policy=CorridorPolicy(),
    )
    document = decision.to_document()
    serialized = json.dumps(document, sort_keys=True)

    assert set(document) == {
        "schemaVersion",
        "mode",
        "policyVersion",
        "calibrationVersion",
        "criticalSignalsAvailable",
        "gates",
        "bands",
        "reasonCodes",
        "modelAvailability",
        "modelVersions",
        "scores",
        "timingMs",
    }
    assert document["scores"] == {
        "fidelity": 1.0,
        "broadVisual": 0.8765,
        "geometry": 0.7654,
        "traitConsistency": 0.6543,
        "composition": 0.5432,
        "adultNaturalness": 0.4322,
    }
    assert all("identity" not in key.lower() for key in document["scores"])
    assert document["timingMs"]["broadVisual"] == 1.235
    assert document["timingMs"]["geometry"] == 0.0
    assert document["timingMs"]["identitySimilarity"] == 2.346
    assert document["modelVersions"]["broadVisual"] == "unknown"
    assert document["modelVersions"]["traitConsistency"] == "unknown"
    assert document["modelVersions"]["identitySimilarity"] == "unknown"
    for forbidden in (
        "PRIVATE TRAITS",
        "private\\embedding",
        "draw private prompt",
        "https://private",
        "raw_landmarks",
        "imageHash",
        '"prompt"',
        '"embedding"',
        '"landmarks"',
        '"boxes"',
        '"masks"',
        '"images"',
        '"identitySimilarityScore"',
        '"rawGeometry"',
        '"rawTraits"',
        '"traitCoverageStatus"',
    ):
        assert forbidden not in serialized


def test_shadow_attachment_does_not_change_active_preview_fields_or_source_mapping():
    active = _active_pass()
    before = copy_active = json.loads(json.dumps(active))
    decision = evaluate_fidelity_corridor(
        active_qa=active,
        identity_signal=IdentityPrivacySignal(),
        fidelity_signals=FidelitySignalBundle.unavailable(),
        policy=CorridorPolicy(),
    )

    attached = attach_shadow_corridor_document(active, decision)

    assert active == before
    assert copy_active == before
    assert "fidelityCorridor" in attached
    assert "previewAllowed" not in attached["fidelityCorridor"]
    for key in ACTIVE_PREVIEW_FIELDS:
        assert attached[key] == before[key]


def test_off_mode_does_not_attach_corridor_document():
    active = _active_pass()
    decision = evaluate_fidelity_corridor(
        active_qa=active,
        identity_signal=None,
        fidelity_signals=None,
        policy=CorridorPolicy(mode=CorridorMode.OFF),
    )

    attached = attach_shadow_corridor_document(active, decision)

    assert attached == active
    assert "fidelityCorridor" not in attached


def test_safe_ranking_excludes_unsafe_high_fidelity_and_uses_candidate_id_tie_break():
    unsafe_active = {
        **_active_pass(),
        "previewAllowed": False,
        "rejectReasons": ["multiple_faces_generated"],
    }
    unsafe_decision = evaluate_fidelity_corridor(
        active_qa=unsafe_active,
        identity_signal=_identity(),
        fidelity_signals=_signals(score=0.99),
        policy=_calibrated_policy(),
    )
    equal_a = _decision(score=0.75)
    equal_b = _decision(score=0.75)

    result = SafeCandidateRanking().rank(
        [
            CorridorCandidate("candidate_unsafe", unsafe_decision, _signals(score=0.99)),
            CorridorCandidate("candidate_b", equal_b, _signals(score=0.75)),
            CorridorCandidate("candidate_a", equal_a, _signals(score=0.75)),
        ]
    )

    assert result.ranked_candidate_ids == ("candidate_a", "candidate_b")
    assert result.excluded_reason_codes_by_candidate_id["candidate_unsafe"] == (
        "candidate_multiple_people",
        "unsafe_candidate_excluded_from_ranking",
    )
    assert result.to_document() == SafeCandidateRanking().rank(
        [
            CorridorCandidate("candidate_b", equal_b, _signals(score=0.75)),
            CorridorCandidate("candidate_unsafe", unsafe_decision, _signals(score=0.99)),
            CorridorCandidate("candidate_a", equal_a, _signals(score=0.75)),
        ]
    ).to_document()


def test_identity_privacy_reject_cannot_be_rescued_by_high_fidelity():
    rejected_identity = evaluate_fidelity_corridor(
        active_qa=_active_pass(),
        identity_signal=_identity(decision="reject", band="high"),
        fidelity_signals=_signals(score=1.0),
        policy=_calibrated_policy(),
    )

    result = SafeCandidateRanking().rank(
        [
            CorridorCandidate(
                "identity_risk",
                rejected_identity,
                _signals(score=1.0),
            )
        ]
    )

    assert result.ranked_candidate_ids == ()
    assert result.excluded_reason_codes_by_candidate_id["identity_risk"] == (
        "candidate_too_identifiable",
        "unsafe_candidate_excluded_from_ranking",
    )
