import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.adaptive_generation import (  # noqa: E402
    AdaptiveGenerationPolicy,
    GenerationBudget,
    plan_generation_round,
)
from avatar_generation.preview_policy import (  # noqa: E402
    is_preview_eligible,
    passes_absolute_preview_checks,
)
from avatar_generation.qa import (  # noqa: E402
    build_avatar_qa_from_signals,
    needs_review_model_unavailable_result,
)


def _candidate(candidate_id, *, status="needs_review", qa=None):
    return {"candidateId": candidate_id, "status": status, "qa": dict(qa or {})}


def _absolute_soft_qa(**overrides):
    qa = {
        "previewAllowed": False,
        "requiresHumanReview": False,
        "rejectReasons": [],
        "softPass": True,
        "adultQa": "pass",
        "privacyQa": "pass",
        "brandQa": "pass",
        "cropConsistency": "pass",
        "cropIsolationQuality": "pass",
        "childlikeRisk": "low",
        "beautificationRisk": "low",
        "identifiabilityRisk": "low",
        "uniqueMarkCopyRisk": "low",
        "logoTextWatermarkRisk": "low",
        "backgroundLeakageRisk": "low",
        "secondaryFaceLeakageRisk": "low",
        "textLogoWatermarkRisk": "low",
    }
    qa.update(overrides)
    return qa


def _load_canary_module():
    script_path = REPO_ROOT / "scripts" / "run_canary_from_validated_map.py"
    spec = importlib.util.spec_from_file_location("run_canary_from_validated_map_p0", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Snapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def stream(self):
        return [_Snapshot(row) for row in self._rows]


class _Collection:
    def __init__(self, rows):
        self._rows = rows

    def where(self, field, op, value):
        assert (field, op) == ("jobId", "==")
        return _Query([row for row in self._rows if row.get("jobId") == value])


class _Db:
    def __init__(self, rows):
        self._rows = rows

    def collection(self, name):
        assert name == "avatarCandidates"
        return _Collection(self._rows)


def test_soft_pass_with_model_unavailable_is_not_preview_eligible():
    qa = _absolute_soft_qa(
        qaVersion="avatar_qa_v2",
        reviewReasons=["faceSimilarity_unavailable"],
        debug={"modelAvailability": {"faceSimilarity": "unavailable"}},
    )
    candidate = _candidate("soft_unavailable", status="soft_pass", qa=qa)

    assert passes_absolute_preview_checks(candidate) is False
    assert is_preview_eligible(candidate) is False


def test_model_unavailable_result_uses_availability_not_medium_risk():
    doc = needs_review_model_unavailable_result().to_document()

    assert doc["childlikeRisk"] == "unavailable"
    assert doc["beautificationRisk"] == "unavailable"
    assert doc["previewAllowed"] is False
    assert doc["requiresHumanReview"] is True


def test_active_qa_contract_marks_dino_not_required_without_relaxing_preview_gate():
    result = build_avatar_qa_from_signals(
        {
            "adultLike": True,
            "brandFit": True,
            "cropConsistent": True,
            "cropIsolationQuality": "pass",
            "logoTextWatermarkDetected": False,
            "uniqueMarkCopied": False,
            "faceSimilarityReliable": True,
            "faceSimilarityScore": 0.10,
            "childlikeScore": 0.05,
            "beautificationScore": 0.05,
            "localSafetyRiskAvailability": "available",
        }
    )

    assert result.debug["modelAvailability"]["dino"] == "not_required"
    absolute_qa = _absolute_soft_qa(
        debug={"modelAvailability": {"faceSimilarity": "available", "clip": "available", "dino": "not_required"}}
    )
    assert passes_absolute_preview_checks(
        _candidate("dino_optional", status="soft_pass", qa=absolute_qa)
    ) is True


def test_uniform_first_round_systemic_unavailable_suppresses_extra_generation():
    candidates = [
        _candidate(
            f"unavailable_{idx}",
            qa={
                "previewAllowed": False,
                "requiresHumanReview": True,
                "rejectReasons": [],
                "qaVersion": "avatar_qa_v1_model_unavailable",
                "reviewReasons": ["model_unavailable"],
            },
        )
        for idx in range(2)
    ]

    plan = plan_generation_round(candidates, policy=AdaptiveGenerationPolicy())

    assert plan.should_generate is False
    assert plan.candidate_count == 0
    assert plan.reason == "extra_suppressed_systemic_unavailable"
    assert plan.blocked_reasons == ("qa_critical_model_unavailable",)


def test_mixed_failures_and_caps_do_not_use_systemic_suppression():
    policy = AdaptiveGenerationPolicy(max_candidate_count=5, extra_candidate_count=4)
    mixed = [
        _candidate(
            "unavailable",
            qa={"qaVersion": "avatar_qa_v1_model_unavailable", "reviewReasons": ["model_unavailable"]},
        ),
        _candidate("review", qa={"requiresHumanReview": True, "reviewReasons": ["qa_signal_uncertain"]}),
    ]

    mixed_plan = plan_generation_round(mixed, policy=policy)
    assert mixed_plan.should_generate is True
    assert mixed_plan.candidate_count == 3
    assert mixed_plan.reason == "extra_insufficient_safe"

    capped = plan_generation_round(
        [_candidate(f"capped_{idx}", qa={"requiresHumanReview": True}) for idx in range(5)],
        policy=policy,
    )
    assert capped.should_generate is False
    assert capped.reason == "max_total_reached"
    assert capped.blocked_reasons == ("max_total_reached",)


def test_budget_cap_blocks_extra_without_running_generation():
    candidates = [_candidate("review", qa={"requiresHumanReview": True})]

    plan = plan_generation_round(
        candidates,
        policy=AdaptiveGenerationPolicy(),
        budget=GenerationBudget(remaining_candidate_budget=0),
    )

    assert plan.should_generate is False
    assert plan.reason == "budget_blocked"
    assert plan.blocked_reasons == ("candidate_budget_exhausted",)


def test_canary_risk_aggregation_uses_typed_actual_values_only():
    module = _load_canary_module()
    rows = [
        {"jobId": "job", "status": "needs_review", "qa": {"childlikeRisk": "high", "beautificationRisk": "low"}},
        {"jobId": "job", "status": "needs_review", "qa": {"childlikeRisk": False, "beautificationRisk": None}},
        {"jobId": "job", "status": "needs_review", "qa": {"beautificationRisk": "unavailable", "reviewReasons": ["model_unavailable"]}},
        {"jobId": "other", "status": "needs_review", "qa": {"childlikeRisk": True, "beautificationRisk": "high"}},
    ]

    stats = module._candidate_counts(_Db(rows), "job")

    assert stats["candidateCount"] == 3
    assert stats["childlikeRiskCount"] == 1
    assert stats["beautificationRiskCount"] == 0
    assert stats["modelUnavailableCount"] == 1
    assert stats["childlikeRiskValues"] == {
        "trueCount": 0,
        "falseCount": 1,
        "nullCount": 0,
        "missingCount": 1,
        "stringLowCount": 0,
        "stringMediumCount": 0,
        "stringHighCount": 1,
        "stringUnknownCount": 0,
        "stringUnavailableCount": 0,
        "stringOtherCount": 0,
    }
    assert stats["beautificationRiskValues"]["stringLowCount"] == 1
    assert stats["beautificationRiskValues"]["nullCount"] == 1
    assert stats["beautificationRiskValues"]["stringUnavailableCount"] == 1
