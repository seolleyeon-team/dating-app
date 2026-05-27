import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.adaptive_generation import (  # noqa: E402
    DEFAULT_EXTRA_CANDIDATE_COUNT,
    DEFAULT_INITIAL_CANDIDATE_COUNT,
    DEFAULT_MAX_CANDIDATE_COUNT,
    DEFAULT_MIN_PREVIEW_CANDIDATE_COUNT,
    DEFAULT_MIN_SAFE_BEFORE_EXTRA,
    DEFAULT_PREVIEW_CANDIDATE_COUNT,
    AdaptiveGenerationPolicy,
    plan_generation_round,
)
from avatar_generation.rerank import (  # noqa: E402
    RerankProviderConfig,
    rerank_preview_candidates,
)


def _candidate(
    candidate_id,
    *,
    status="preview_ready",
    qa=None,
    scores=None,
):
    default_qa = {
        "previewAllowed": True,
        "requiresHumanReview": False,
        "rejectReasons": [],
        "adultQa": "pass",
        "privacyQa": "pass",
        "brandQa": "pass",
        "cropConsistency": "pass",
        "childlikeRisk": "low",
        "beautificationRisk": "low",
        "identifiabilityRisk": "low",
        "uniqueMarkCopyRisk": "low",
        "logoTextWatermarkRisk": "low",
    }
    return {
        "candidateId": candidate_id,
        "status": status,
        "qa": dict(qa or default_qa),
        "scores": dict(scores or {}),
    }


def _hard_reject(candidate_id):
    return _candidate(
        candidate_id,
        status="rejected",
        qa={
            "previewAllowed": False,
            "requiresHumanReview": False,
            "rejectReasons": ["too_identifiable"],
        },
    )


def _soft_pass(candidate_id):
    return _candidate(
        candidate_id,
        status="soft_pass",
        qa={
            "previewAllowed": False,
            "requiresHumanReview": False,
            "rejectReasons": [],
            "softPass": True,
            "adultQa": "pass",
            "privacyQa": "pass",
            "brandQa": "pass",
            "cropConsistency": "pass",
            "childlikeRisk": "low",
            "beautificationRisk": "low",
            "identifiabilityRisk": "low",
            "uniqueMarkCopyRisk": "low",
            "logoTextWatermarkRisk": "low",
        },
    )


def _needs_review_low_risk(candidate_id):
    return _candidate(
        candidate_id,
        status="needs_review",
        qa={
            "previewAllowed": False,
            "requiresHumanReview": True,
            "rejectReasons": [],
            "adultQa": "pass",
            "privacyQa": "pass",
            "brandQa": "pass",
            "cropConsistency": "pass",
            "childlikeRisk": "low",
            "beautificationRisk": "low",
            "identifiabilityRisk": "low",
            "uniqueMarkCopyRisk": "low",
            "logoTextWatermarkRisk": "low",
        },
    )


def test_policy_defaults_and_env_overrides(monkeypatch):
    assert DEFAULT_INITIAL_CANDIDATE_COUNT == 4
    assert DEFAULT_EXTRA_CANDIDATE_COUNT == 4
    assert DEFAULT_MAX_CANDIDATE_COUNT == 8
    assert DEFAULT_PREVIEW_CANDIDATE_COUNT == 4
    assert DEFAULT_MIN_SAFE_BEFORE_EXTRA == 2
    assert DEFAULT_MIN_PREVIEW_CANDIDATE_COUNT == 1

    default_policy = AdaptiveGenerationPolicy.from_env()
    assert default_policy.initial_candidate_count == 4
    assert default_policy.extra_candidate_count == 4
    assert default_policy.max_candidate_count == 8
    assert default_policy.preview_candidate_count == 4
    assert default_policy.min_safe_before_extra == 2
    assert default_policy.min_preview_candidate_count == 1
    assert default_policy.require_four_preview is False
    assert default_policy.soft_pass_fill_enabled is True
    assert default_policy.hard_reject_fill_enabled is False
    assert default_policy.needs_review_low_risk_enabled is False

    monkeypatch.setenv("AVATAR_INITIAL_CANDIDATE_COUNT", "3")
    monkeypatch.setenv("AVATAR_EXTRA_CANDIDATE_COUNT", "2")
    monkeypatch.setenv("AVATAR_MAX_TOTAL_CANDIDATES", "5")
    monkeypatch.setenv("AVATAR_PREVIEW_COUNT", "3")
    monkeypatch.setenv("AVATAR_MIN_PREVIEW_CANDIDATES", "2")
    monkeypatch.setenv("AVATAR_PREVIEW_REQUIRE_FOUR", "true")
    monkeypatch.setenv("AVATAR_MIN_SAFE_CANDIDATES_BEFORE_EXTRA", "1")
    monkeypatch.setenv("AVATAR_PREVIEW_FILL_WITH_SOFT_PASS", "false")
    monkeypatch.setenv("AVATAR_PREVIEW_FILL_WITH_NEEDS_REVIEW_LOW_RISK", "1")

    env_policy = AdaptiveGenerationPolicy.from_env()
    assert env_policy.initial_candidate_count == 3
    assert env_policy.extra_candidate_count == 2
    assert env_policy.max_candidate_count == 5
    assert env_policy.preview_candidate_count == 3
    assert env_policy.min_preview_candidate_count == 2
    assert env_policy.require_four_preview is True
    assert env_policy.min_safe_before_extra == 1
    assert env_policy.soft_pass_fill_enabled is False
    assert env_policy.needs_review_low_risk_enabled is True


def test_generation_plan_initial_and_extra_decision():
    policy = AdaptiveGenerationPolicy()

    initial = plan_generation_round([], policy=policy)
    assert initial.should_generate is True
    assert initial.candidate_count == 4
    assert initial.reason == "initial"

    one_safe = [_candidate("pass_1")]
    extra = plan_generation_round(one_safe, policy=policy)
    assert extra.should_generate is True
    assert extra.candidate_count == 4
    assert extra.reason == "extra_insufficient_safe"

    enough_safe = [_candidate("pass_1"), _candidate("pass_2")]
    hold = plan_generation_round(enough_safe, policy=policy)
    assert hold.should_generate is False
    assert hold.candidate_count == 0
    assert hold.reason == "enough_safe"


def test_regenerate_adds_extra_and_stops_at_max_total():
    policy = AdaptiveGenerationPolicy()
    existing = [_candidate(f"pass_{idx}") for idx in range(4)]

    regenerate = plan_generation_round(existing, policy=policy, regenerate_requested=True)
    assert regenerate.should_generate is True
    assert regenerate.candidate_count == 4
    assert regenerate.reason == "regenerate_extra"
    assert regenerate.total_after_generation == 8

    capped = plan_generation_round(
        [_candidate(f"pass_{idx}") for idx in range(8)],
        policy=policy,
        regenerate_requested=True,
    )
    assert capped.should_generate is False
    assert capped.candidate_count == 0
    assert capped.reason == "max_total_reached"


def test_hard_reject_is_never_selected_for_preview():
    result = rerank_preview_candidates(
        [
            _hard_reject("reject_1"),
            _candidate("pass_1"),
            _candidate("pass_2"),
        ],
        policy=AdaptiveGenerationPolicy(),
    )

    assert result.status == "preview_ready"
    assert result.selected_candidate_ids == ["pass_1", "pass_2"]
    assert result.metadata_by_candidate_id["pass_1"]["selectedForPreview"] is True
    assert result.metadata_by_candidate_id["pass_2"]["selectedForPreview"] is True
    rejected_metadata = result.metadata_by_candidate_id["reject_1"]
    assert rejected_metadata["selectionTier"] == "hard_reject"
    assert rejected_metadata["selectedForPreview"] is False


def test_soft_pass_candidates_fill_preview_only_when_enabled():
    candidates = [
        _candidate("pass_1"),
        _candidate("pass_2"),
        _soft_pass("soft_1"),
        _soft_pass("soft_2"),
    ]

    disabled = rerank_preview_candidates(
        candidates,
        policy=AdaptiveGenerationPolicy(soft_pass_fill_enabled=False),
    )
    assert disabled.selected_candidate_ids == ["pass_1", "pass_2"]
    assert disabled.metadata_by_candidate_id["soft_1"]["selectedForPreview"] is False

    enabled = rerank_preview_candidates(
        candidates,
        policy=AdaptiveGenerationPolicy(soft_pass_fill_enabled=True),
    )
    assert enabled.selected_candidate_ids == ["pass_1", "pass_2", "soft_1", "soft_2"]
    assert enabled.metadata_by_candidate_id["soft_1"]["selectionTier"] == "soft_pass"
    assert enabled.metadata_by_candidate_id["soft_1"]["selectedForPreview"] is True


def test_needs_review_low_risk_requires_configuration():
    candidates = [_needs_review_low_risk("review_1")]

    disabled = rerank_preview_candidates(candidates, policy=AdaptiveGenerationPolicy())
    assert disabled.status == "no_previewable"
    assert disabled.selected_candidate_ids == []
    assert disabled.metadata_by_candidate_id["review_1"]["selectionTier"] == "needs_review"
    assert disabled.metadata_by_candidate_id["review_1"]["selectedForPreview"] is False

    enabled = rerank_preview_candidates(
        candidates,
        policy=AdaptiveGenerationPolicy(needs_review_low_risk_enabled=True),
    )
    assert enabled.status == "no_previewable"
    assert enabled.selected_candidate_ids == []
    assert enabled.metadata_by_candidate_id["review_1"]["selectionTier"] == "needs_review"
    assert enabled.metadata_by_candidate_id["review_1"]["selectedForPreview"] is False


def test_soft_pass_requires_absolute_privacy_safety_checks():
    malformed_soft = _candidate(
        "soft_bad",
        status="soft_pass",
        qa={
            "previewAllowed": False,
            "requiresHumanReview": False,
            "rejectReasons": [],
            "softPass": True,
            "adultQa": "pass",
            "privacyQa": "needs_review",
            "brandQa": "pass",
            "cropConsistency": "pass",
            "childlikeRisk": "low",
            "beautificationRisk": "low",
            "identifiabilityRisk": "medium",
            "uniqueMarkCopyRisk": "low",
            "logoTextWatermarkRisk": "low",
        },
    )

    result = rerank_preview_candidates(
        [malformed_soft],
        policy=AdaptiveGenerationPolicy(soft_pass_fill_enabled=True),
    )

    assert result.status == "no_previewable"
    assert result.selected_candidate_ids == []
    assert result.metadata_by_candidate_id["soft_bad"]["selectionTier"] == "needs_review"
    assert result.metadata_by_candidate_id["soft_bad"]["selectedForPreview"] is False


def test_conflicting_needs_review_flags_cannot_be_previewed():
    conflicting = _candidate(
        "conflicting_review",
        status="needs_review",
        qa={
            "previewAllowed": True,
            "requiresHumanReview": True,
            "rejectReasons": [],
            "adultQa": "pass",
            "privacyQa": "pass",
            "brandQa": "pass",
            "cropConsistency": "pass",
            "childlikeRisk": "low",
            "beautificationRisk": "low",
            "identifiabilityRisk": "low",
            "uniqueMarkCopyRisk": "low",
            "logoTextWatermarkRisk": "low",
        },
    )

    result = rerank_preview_candidates(
        [conflicting],
        policy=AdaptiveGenerationPolicy(),
    )

    assert result.status == "no_previewable"
    assert result.selected_candidate_ids == []
    assert result.metadata_by_candidate_id["conflicting_review"]["selectionTier"] == "needs_review"
    assert result.metadata_by_candidate_id["conflicting_review"]["selectedForPreview"] is False


def test_no_previewable_when_no_acceptable_candidates():
    result = rerank_preview_candidates(
        [_hard_reject("reject_1"), _hard_reject("reject_2")],
        policy=AdaptiveGenerationPolicy(soft_pass_fill_enabled=True),
    )

    assert result.status == "no_previewable"
    assert result.selected_candidate_ids == []
    assert all(
        metadata["selectedForPreview"] is False
        for metadata in result.metadata_by_candidate_id.values()
    )


def test_rerank_metadata_schema_provider_env_and_deterministic_scorer(monkeypatch):
    monkeypatch.setenv("AVATAR_RERANK_PROVIDER", "clip")
    monkeypatch.setenv("AVATAR_RERANK_CLIP_PROVIDER", "clip-vit-test")
    monkeypatch.setenv("AVATAR_RERANK_DINO_PROVIDER", "dino-v2-test")
    monkeypatch.setenv("AVATAR_CLIP_MODEL_ID", "openai/clip-vit-large-patch14")
    monkeypatch.setenv("AVATAR_DINO_MODEL_ID", "facebook/dinov2-base")

    provider_config = RerankProviderConfig.from_env()
    assert provider_config.rerank_provider == "clip"
    assert provider_config.clip_provider == "clip-vit-test"
    assert provider_config.dino_provider == "dino-v2-test"
    assert provider_config.clip_model_id == "openai/clip-vit-large-patch14"
    assert provider_config.dino_model_id == "facebook/dinov2-base"

    def deterministic_hook(candidate):
        candidate_id = candidate["candidateId"]
        return {
            "trait": 0.50 if candidate_id == "pass_1" else 0.90,
            "hairClothing": 0.20,
            "brand": 0.10,
            "privacyPenalty": 0.05,
            "beautificationPenalty": 0.02,
        }

    result = rerank_preview_candidates(
        [_candidate("pass_1"), _candidate("pass_2")],
        policy=AdaptiveGenerationPolicy(require_four_preview=False),
        score_hooks=[deterministic_hook],
        provider_config=provider_config,
    )

    assert result.selected_candidate_ids == ["pass_2", "pass_1"]
    assert result.to_dict()["providerConfig"] == {
        "rerankProvider": "clip",
        "clipProvider": "clip-vit-test",
        "dinoProvider": "dino-v2-test",
        "clipModelId": "openai/clip-vit-large-patch14",
        "dinoModelId": "facebook/dinov2-base",
    }
    metadata = result.metadata_by_candidate_id["pass_2"]
    assert set(metadata) == {
        "overall",
        "overallScore",
        "trait",
        "traitConsistencyScore",
        "hairClothing",
        "hairClothingScore",
        "brand",
        "brandFitScore",
        "privacyPenalty",
        "beautificationPenalty",
        "selectionTier",
        "selectedForPreview",
    }
    assert metadata["overall"] == 1.13
    assert metadata["selectionTier"] == "hard_pass"
    assert metadata["selectedForPreview"] is True


def test_default_rerank_provider_does_not_claim_clip_model_execution(monkeypatch):
    monkeypatch.delenv("AVATAR_RERANK_PROVIDER", raising=False)
    monkeypatch.delenv("AVATAR_RERANK_CLIP_PROVIDER", raising=False)
    monkeypatch.delenv("AVATAR_RERANK_DINO_PROVIDER", raising=False)

    provider_config = RerankProviderConfig.from_env()

    assert provider_config.rerank_provider == "deterministic_qa_tier"
    assert provider_config.clip_provider == "clip_lazy_disabled"
    assert provider_config.dino_provider == "dino_lazy_disabled"
