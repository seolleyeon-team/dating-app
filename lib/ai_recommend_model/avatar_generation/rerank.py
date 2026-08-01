from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from avatar_generation.adaptive_generation import AdaptiveGenerationPolicy
from avatar_generation.preview_policy import (
    is_hard_pass,
    is_hard_reject,
    is_needs_review,
    is_preview_eligible,
    is_soft_pass,
)


ENV_RERANK_PROVIDER = "AVATAR_RERANK_PROVIDER"
ENV_CLIP_PROVIDER = "AVATAR_RERANK_CLIP_PROVIDER"
ENV_DINO_PROVIDER = "AVATAR_RERANK_DINO_PROVIDER"
ENV_CLIP_MODEL_ID = "AVATAR_CLIP_MODEL_ID"
ENV_DINO_MODEL_ID = "AVATAR_DINO_MODEL_ID"
DEFAULT_RERANK_PROVIDER = "deterministic_qa_tier"
DEFAULT_CLIP_PROVIDER = "clip_lazy_disabled"
DEFAULT_DINO_PROVIDER = "dino_lazy_disabled"
DEFAULT_CLIP_MODEL_ID = "openai/clip-vit-large-patch14"
DEFAULT_DINO_MODEL_ID = "facebook/dinov2-base"

METADATA_SCHEMA_KEYS = (
    "overall",
    "trait",
    "hairClothing",
    "brand",
    "privacyPenalty",
    "beautificationPenalty",
    "selectionTier",
    "selectedForPreview",
)

ScoreHook = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class RerankProviderConfig:
    rerank_provider: str = DEFAULT_RERANK_PROVIDER
    clip_provider: str = DEFAULT_CLIP_PROVIDER
    dino_provider: str = DEFAULT_DINO_PROVIDER
    clip_model_id: str = DEFAULT_CLIP_MODEL_ID
    dino_model_id: str = DEFAULT_DINO_MODEL_ID

    @classmethod
    def from_env(cls) -> "RerankProviderConfig":
        return cls(
            rerank_provider=os.environ.get(ENV_RERANK_PROVIDER, DEFAULT_RERANK_PROVIDER)
            .strip()
            or DEFAULT_RERANK_PROVIDER,
            clip_provider=os.environ.get(ENV_CLIP_PROVIDER, DEFAULT_CLIP_PROVIDER)
            .strip()
            or DEFAULT_CLIP_PROVIDER,
            dino_provider=os.environ.get(ENV_DINO_PROVIDER, DEFAULT_DINO_PROVIDER)
            .strip()
            or DEFAULT_DINO_PROVIDER,
            clip_model_id=os.environ.get(ENV_CLIP_MODEL_ID, DEFAULT_CLIP_MODEL_ID)
            .strip()
            or DEFAULT_CLIP_MODEL_ID,
            dino_model_id=os.environ.get(ENV_DINO_MODEL_ID, DEFAULT_DINO_MODEL_ID)
            .strip()
            or DEFAULT_DINO_MODEL_ID,
        )


@dataclass(frozen=True)
class PreviewRerankResult:
    status: str
    selected_candidate_ids: list[str]
    metadata_by_candidate_id: dict[str, dict[str, Any]]
    ranked_candidate_ids: list[str]
    provider_config: RerankProviderConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "selectedCandidateIds": list(self.selected_candidate_ids),
            "rankedCandidateIds": list(self.ranked_candidate_ids),
            "providerConfig": {
                "rerankProvider": self.provider_config.rerank_provider,
                "clipProvider": self.provider_config.clip_provider,
                "dinoProvider": self.provider_config.dino_provider,
                "clipModelId": self.provider_config.clip_model_id,
                "dinoModelId": self.provider_config.dino_model_id,
            },
            "metadataByCandidateId": {
                candidate_id: dict(metadata)
                for candidate_id, metadata in self.metadata_by_candidate_id.items()
            },
        }


def rerank_preview_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    policy: Optional[AdaptiveGenerationPolicy] = None,
    score_hooks: Optional[Sequence[ScoreHook]] = None,
    provider_config: Optional[RerankProviderConfig] = None,
) -> PreviewRerankResult:
    active_policy = policy or AdaptiveGenerationPolicy.from_env()
    active_provider_config = provider_config or RerankProviderConfig.from_env()

    ranked = [
        _RankedCandidate(
            candidate_id=_candidate_id(candidate),
            tier=_selection_tier(candidate),
            metadata=_metadata_for_candidate(candidate, score_hooks or ()),
        )
        for candidate in candidates
    ]

    ranked.sort(key=_rank_sort_key)
    metadata_by_candidate_id = {
        item.candidate_id: _unselected_metadata(item.metadata, item.tier)
        for item in ranked
    }

    selected: list[str] = []
    _select_from_tier(
        ranked,
        metadata_by_candidate_id,
        selected,
        "hard_pass",
        active_policy.preview_candidate_count,
    )
    if active_policy.soft_pass_fill_enabled:
        _select_from_tier(
            ranked,
            metadata_by_candidate_id,
            selected,
            "soft_pass",
            active_policy.preview_candidate_count,
        )
    min_preview_count = max(1, int(active_policy.min_preview_candidate_count))
    status = "preview_ready" if len(selected) >= min_preview_count else "no_previewable"
    if (
        len(selected) >= min_preview_count
        and active_policy.require_four_preview
        and len(selected) < max(0, int(active_policy.preview_candidate_count))
    ):
        status = "insufficient_preview_candidates"
        for candidate_id in selected:
            metadata_by_candidate_id[candidate_id] = _unselected_metadata(
                metadata_by_candidate_id[candidate_id],
                "needs_review",
            )

    return PreviewRerankResult(
        status=status,
        selected_candidate_ids=selected,
        metadata_by_candidate_id=metadata_by_candidate_id,
        ranked_candidate_ids=[item.candidate_id for item in ranked],
        provider_config=active_provider_config,
    )


@dataclass(frozen=True)
class _RankedCandidate:
    candidate_id: str
    tier: str
    metadata: dict[str, Any]


def _select_from_tier(
    ranked: Sequence[_RankedCandidate],
    metadata_by_candidate_id: dict[str, dict[str, Any]],
    selected: list[str],
    tier: str,
    preview_limit: int,
) -> None:
    for item in ranked:
        if len(selected) >= max(0, int(preview_limit)):
            return
        if item.tier != tier or item.candidate_id in selected:
            continue
        selected.append(item.candidate_id)
        metadata_by_candidate_id[item.candidate_id] = _selected_metadata(
            item.metadata,
            tier,
        )


def _rank_sort_key(item: _RankedCandidate) -> tuple[int, float, str]:
    tier_order = {
        "hard_pass": 0,
        "soft_pass": 1,
        "needs_review": 2,
        "not_previewable": 3,
        "hard_reject": 4,
    }
    return (
        tier_order.get(item.tier, 99),
        -float(item.metadata["overall"]),
        item.candidate_id,
    )


def _selection_tier(candidate: Mapping[str, Any]) -> str:
    if is_hard_reject(candidate):
        return "hard_reject"
    if is_preview_eligible(candidate) and is_hard_pass(candidate):
        return "hard_pass"
    if is_preview_eligible(candidate) and is_soft_pass(candidate):
        return "soft_pass"
    if is_needs_review(candidate):
        return "needs_review"
    return "not_previewable"


def _metadata_for_candidate(
    candidate: Mapping[str, Any],
    score_hooks: Sequence[ScoreHook],
) -> dict[str, Any]:
    scores = _base_scores(candidate)
    for hook in score_hooks:
        hook_scores = hook(candidate)
        if isinstance(hook_scores, Mapping):
            scores.update(hook_scores)

    trait = _number(scores.get("trait"), 0.0)
    hair_clothing = _number(scores.get("hairClothing"), 0.0)
    brand = _number(scores.get("brand"), 0.0)
    privacy_penalty = _number(scores.get("privacyPenalty"), 0.0)
    beautification_penalty = _number(scores.get("beautificationPenalty"), 0.0)
    explicit_overall = scores.get("overall")
    if explicit_overall is None:
        overall = trait + hair_clothing + brand - privacy_penalty - beautification_penalty
    else:
        overall = _number(explicit_overall, 0.0)

    return {
        "overall": round(overall, 6),
        "overallScore": round(overall, 6),
        "trait": round(trait, 6),
        "traitConsistencyScore": round(trait, 6),
        "hairClothing": round(hair_clothing, 6),
        "hairClothingScore": round(hair_clothing, 6),
        "brand": round(brand, 6),
        "brandFitScore": round(brand, 6),
        "privacyPenalty": round(privacy_penalty, 6),
        "beautificationPenalty": round(beautification_penalty, 6),
        "selectionTier": "not_previewable",
        "selectedForPreview": False,
    }


def _base_scores(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    for key in ("scores", "rerank", "rerankScores"):
        value = candidate.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    qa = candidate.get("qa")
    qa_doc = qa if isinstance(qa, Mapping) else {}
    consistency = qa_doc.get("candidateTraitConsistency")
    if not isinstance(consistency, Mapping):
        debug = qa_doc.get("debug")
        if isinstance(debug, Mapping):
            consistency = debug.get("candidateTraitConsistency")
    if isinstance(consistency, Mapping):
        eyewear_match = str(consistency.get("eyewearMatch") or "").strip().lower()
        if eyewear_match == "fail":
            return {
                "trait": -1.0,
                "hairClothing": 0.0,
                "brand": 0.0,
                "privacyPenalty": 2.0,
                "overall": -3.0,
            }
        if eyewear_match == "pass":
            return {"trait": 0.25}
    return {}


def _selected_metadata(metadata: Mapping[str, Any], tier: str) -> dict[str, Any]:
    updated = _metadata_with_tier(metadata, tier)
    updated["selectedForPreview"] = True
    return updated


def _unselected_metadata(metadata: Mapping[str, Any], tier: str) -> dict[str, Any]:
    updated = _metadata_with_tier(metadata, tier)
    updated["selectedForPreview"] = False
    return updated


def _metadata_with_tier(metadata: Mapping[str, Any], tier: str) -> dict[str, Any]:
    public_tier = "needs_review" if tier == "not_previewable" else tier
    return {
        "overall": metadata["overall"],
        "overallScore": metadata.get("overallScore", metadata["overall"]),
        "trait": metadata["trait"],
        "traitConsistencyScore": metadata.get("traitConsistencyScore", metadata["trait"]),
        "hairClothing": metadata["hairClothing"],
        "hairClothingScore": metadata.get("hairClothingScore", metadata["hairClothing"]),
        "brand": metadata["brand"],
        "brandFitScore": metadata.get("brandFitScore", metadata["brand"]),
        "privacyPenalty": metadata["privacyPenalty"],
        "beautificationPenalty": metadata["beautificationPenalty"],
        "selectionTier": public_tier,
        "selectedForPreview": bool(metadata["selectedForPreview"]),
    }


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("candidateId") or candidate.get("id") or "")


def _number(value: Any, fallback: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback


__all__ = [
    "DEFAULT_CLIP_PROVIDER",
    "DEFAULT_DINO_PROVIDER",
    "DEFAULT_CLIP_MODEL_ID",
    "DEFAULT_DINO_MODEL_ID",
    "DEFAULT_RERANK_PROVIDER",
    "ENV_CLIP_MODEL_ID",
    "ENV_CLIP_PROVIDER",
    "ENV_DINO_MODEL_ID",
    "ENV_DINO_PROVIDER",
    "ENV_RERANK_PROVIDER",
    "METADATA_SCHEMA_KEYS",
    "PreviewRerankResult",
    "RerankProviderConfig",
    "rerank_preview_candidates",
]
