from __future__ import annotations

import copy
import json

from avatar_generation.fidelity_shadow import (
    build_shadow_corridor_evidence,
    build_shadow_ranking_document,
)


def _active_qa() -> dict[str, object]:
    return {
        "qaVersion": "avatar_qa_v2",
        "adultQa": "pass",
        "childlikeRisk": "low",
        "privacyQa": "pass",
        "brandQa": "pass",
        "beautificationRisk": "low",
        "cropConsistency": "pass",
        "cropIsolationQuality": "pass",
        "identifiabilityRisk": "low",
        "previewAllowed": True,
        "requiresHumanReview": False,
        "softPass": False,
        "rejectReasons": [],
        "reviewReasons": [],
        "debug": {"modelAvailability": {"faceSimilarity": "available"}},
    }


def test_shadow_attachment_preserves_every_active_qa_field():
    active = _active_qa()
    before = copy.deepcopy(active)

    evidence = build_shadow_corridor_evidence(
        active_qa=active,
        candidate_id="candidate-b",
        source_trait_validation={
            "criticalTraitCoverage": {"meetsMinimum": True}
        },
    )

    assert active == before
    attached = evidence.qa_document
    assert {key: value for key, value in attached.items() if key != "fidelityCorridor"} == before
    corridor = attached["fidelityCorridor"]
    assert corridor["mode"] == "shadow"
    assert corridor["calibrationVersion"] == "uncalibrated"
    assert corridor["criticalSignalsAvailable"] is False
    assert corridor["gates"]["fidelityLowerBound"] == "review"
    assert corridor["bands"]["identityRisk"] == "low"
    assert "identity" not in json.dumps(corridor["scores"]).lower()


def test_shadow_fails_closed_when_source_trait_coverage_is_insufficient():
    evidence = build_shadow_corridor_evidence(
        active_qa=_active_qa(),
        candidate_id="candidate-a",
        source_trait_validation={
            "criticalTraitCoverage": {"meetsMinimum": False}
        },
    )

    corridor = evidence.qa_document["fidelityCorridor"]
    assert corridor["gates"]["fidelityLowerBound"] == "review"
    assert "candidate_trait_mismatch" in corridor["reasonCodes"]
    assert evidence.candidate.decision.eligible_for_ranking is False


def test_unreliable_identity_signal_is_unavailable_not_a_positive_rank_feature():
    active = _active_qa()
    active["debug"] = {"modelAvailability": {"faceSimilarity": "uncalibrated"}}

    evidence = build_shadow_corridor_evidence(
        active_qa=active,
        candidate_id="candidate-a",
    )

    corridor = evidence.qa_document["fidelityCorridor"]
    assert corridor["bands"]["identityRisk"] == "unavailable"
    assert corridor["modelAvailability"]["identitySimilarity"] == "unavailable"
    assert "privacy_signal_unavailable" in corridor["reasonCodes"]


def test_shadow_ranking_is_separate_and_uncalibrated():
    first = build_shadow_corridor_evidence(
        active_qa=_active_qa(),
        candidate_id="candidate-b",
    )
    second = build_shadow_corridor_evidence(
        active_qa=_active_qa(),
        candidate_id="candidate-a",
    )

    document = build_shadow_ranking_document([first.candidate, second.candidate])

    assert document["mode"] == "shadow"
    assert document["calibrationVersion"] == "uncalibrated"
    assert document["rankedCandidateIds"] == []
    assert set(document["excludedReasonCodesByCandidateId"]) == {
        "candidate-a",
        "candidate-b",
    }
