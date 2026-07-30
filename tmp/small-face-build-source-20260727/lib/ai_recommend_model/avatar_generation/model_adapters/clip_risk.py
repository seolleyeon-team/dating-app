from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


DEFAULT_MODEL_ID = "openai/clip-vit-large-patch14"
ENV_MODEL_ID = "AVATAR_CLIP_RISK_MODEL_ID"
ENV_CALIBRATION_VERSION = "AVATAR_CLIP_RISK_CALIBRATION_VERSION"
DEFAULT_CALIBRATION_VERSION = ""

DECISION_PASS = "pass"
DECISION_REVIEW = "review"
DECISION_UNAVAILABLE = "unavailable"

_DEFAULT_THRESHOLDS = {
    "childlike": 0.35,
    "sexualized": 0.35,
    "beautification": 0.55,
    "brand_mismatch": 0.45,
    "severe_artifact": 0.35,
}
_DEFAULT_MINIMUMS = {
    "adult_like": 0.55,
    "brand_fit": 0.55,
}
_THRESHOLD_ENV_KEYS = {
    "childlike": "AVATAR_CLIP_RISK_CHILDLIKE_THRESHOLD",
    "sexualized": "AVATAR_CLIP_RISK_SEXUALIZED_THRESHOLD",
    "beautification": "AVATAR_CLIP_RISK_BEAUTIFICATION_THRESHOLD",
    "brand_mismatch": "AVATAR_CLIP_RISK_BRAND_MISMATCH_THRESHOLD",
    "severe_artifact": "AVATAR_CLIP_RISK_SEVERE_ARTIFACT_THRESHOLD",
}
_MINIMUM_ENV_KEYS = {
    "adult_like": "AVATAR_CLIP_RISK_ADULT_LIKE_MINIMUM",
    "brand_fit": "AVATAR_CLIP_RISK_BRAND_FIT_MINIMUM",
}

_PROMPT_GROUPS = {
    "adult_childlike": {
        "adult_like": (
            "a privacy preserving portrait of an adult university student",
            "a mature adult profile avatar candidate",
            "an adult person represented as a clean profile image",
        ),
        "childlike": (
            "a childlike face with juvenile features",
            "a young child or minor represented in a portrait",
            "a baby faced childlike avatar candidate",
        ),
    },
    "sexualized_safe": {
        "safe": (
            "a modest ordinary profile portrait",
            "a casual non sexualized portrait photo",
            "a safe everyday avatar candidate",
        ),
        "sexualized": (
            "a sexualized nightlife portrait",
            "a revealing club themed glamour image",
            "a provocative dating profile style image",
        ),
    },
    "natural_beautified": {
        "natural": (
            "an ordinary natural profile portrait",
            "a realistic casual avatar with natural styling",
            "a simple everyday profile image",
        ),
        "beautified": (
            "an idol style heavily beautified portrait",
            "a fashion model glamour headshot",
            "a highly polished influencer beauty image",
        ),
    },
    "brand_fit_mismatch": {
        "brand_fit": (
            "a quiet trustworthy university profile avatar",
            "a warm restrained respectful profile portrait",
            "a clean low key social profile image",
        ),
        "brand_mismatch": (
            "a loud commercial advertisement style image",
            "a flashy nightlife promotional poster style portrait",
            "an image that feels mismatched for a quiet trust focused app",
        ),
    },
    "clean_artifact": {
        "clean": (
            "a clean coherent generated profile portrait",
            "a high quality avatar without visual defects",
            "a natural looking complete face image",
        ),
        "severe_artifact": (
            "a distorted generated face with severe artifacts",
            "a broken image with malformed facial features",
            "a corrupted avatar with obvious rendering defects",
        ),
    },
}


class ClipRiskUnavailable(RuntimeError):
    """Coarse sanitized adapter exception for local CLIP risk scoring failures."""


class ClipRiskScorer(Protocol):
    provider: str
    version: str

    def is_available(self) -> bool:
        ...

    def score_prompt_groups(
        self,
        image: Any,
        prompt_groups: Mapping[str, Mapping[str, Sequence[str]]],
    ) -> Mapping[str, Mapping[str, float]]:
        ...


@dataclass(frozen=True)
class ClipRiskCalibrationPolicy:
    calibration_version: str = DEFAULT_CALIBRATION_VERSION
    risk_thresholds: Mapping[str, float] | None = None
    minimum_scores: Mapping[str, float] | None = None

    @classmethod
    def from_env(cls) -> "ClipRiskCalibrationPolicy":
        return cls(
            calibration_version=os.environ.get(ENV_CALIBRATION_VERSION, ""),
            risk_thresholds=_env_policy_values(_THRESHOLD_ENV_KEYS),
            minimum_scores=_env_policy_values(_MINIMUM_ENV_KEYS),
        )

    @property
    def is_valid(self) -> bool:
        if not str(self.calibration_version).strip():
            return False
        if self.risk_thresholds is None or self.minimum_scores is None:
            return False
        thresholds = self.thresholds
        minimums = self.minimums
        required_thresholds = set(_DEFAULT_THRESHOLDS)
        required_minimums = set(_DEFAULT_MINIMUMS)
        if set(thresholds) != required_thresholds or set(minimums) != required_minimums:
            return False
        return all(_is_probability(value) for value in thresholds.values()) and all(
            _is_probability(value) for value in minimums.values()
        )

    @property
    def thresholds(self) -> Mapping[str, float]:
        return self.risk_thresholds or {}

    @property
    def minimums(self) -> Mapping[str, float]:
        return self.minimum_scores or {}


@dataclass(frozen=True)
class ClipRiskResult:
    provider: str
    version: str | None
    availability: str
    available: bool
    childlike_score: float | None
    sexualized_score: float | None
    beautification_score: float | None
    brand_mismatch_score: float | None
    severe_artifact_score: float | None
    adult_like_score: float | None
    brand_fit_score: float | None
    calibrated: bool
    calibration_version: str | None
    needs_review: bool
    decision: str = DECISION_REVIEW
    availability_reason: str | None = None

    def to_document(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "version": self.version,
            "availability": self.availability,
            "available": bool(self.available),
            "availabilityReason": self.availability_reason,
            "childlikeScore": _round_optional(self.childlike_score),
            "sexualizedScore": _round_optional(self.sexualized_score),
            "beautificationScore": _round_optional(self.beautification_score),
            "brandMismatchScore": _round_optional(self.brand_mismatch_score),
            "severeArtifactScore": _round_optional(self.severe_artifact_score),
            "adultLikeScore": _round_optional(self.adult_like_score),
            "brandFitScore": _round_optional(self.brand_fit_score),
            "calibrated": bool(self.calibrated),
            "calibrationVersion": self.calibration_version,
            "needsReview": bool(self.needs_review),
            "decision": self.decision,
        }

    def to_signals(self) -> dict[str, object]:
        return self.to_document()


class LocalClipRiskScorer:
    """Lazy local CLIP zero-shot scorer. Embeddings stay process-local only."""

    provider = "clip"

    def __init__(
        self,
        model_id: str | None = None,
        *,
        processor: Any = None,
        model: Any = None,
        processor_factory: Any = None,
        model_factory: Any = None,
        local_files_only: bool = True,
        device: str | None = None,
        temperature: float | None = None,
    ) -> None:
        self.model_id = model_id or os.environ.get(ENV_MODEL_ID, DEFAULT_MODEL_ID)
        self.version = self.model_id
        self.local_files_only = bool(local_files_only)
        self.device = device
        self._processor = processor
        self._model = model
        self._processor_factory = processor_factory
        self._model_factory = model_factory
        self._load_error: str | None = None
        self.temperature = temperature

    def is_available(self) -> bool:
        if self._load_error is not None:
            return False
        try:
            self._load_components()
        except Exception as exc:  # pragma: no cover - depends on optional local model files
            self._load_error = _sanitize_exception_reason(exc)
            return False
        return True

    def score_prompt_groups(
        self,
        image: Any,
        prompt_groups: Mapping[str, Mapping[str, Sequence[str]]],
    ) -> Mapping[str, Mapping[str, float]]:
        processor, model = self._load_components()
        results: dict[str, Mapping[str, float]] = {}
        for group_name, labels in prompt_groups.items():
            label_names = list(labels)
            texts: list[str] = []
            text_labels: list[str] = []
            for label, label_prompts in labels.items():
                for text in label_prompts:
                    texts.append(str(text))
                    text_labels.append(label)
            inputs = processor(text=texts, images=image, return_tensors="pt", padding=True)
            if self.device and hasattr(inputs, "to"):
                inputs = inputs.to(self.device)
            text_kwargs = {"input_ids": inputs["input_ids"]}
            if "attention_mask" in inputs:
                text_kwargs["attention_mask"] = inputs["attention_mask"]
            with _torch_no_grad():
                image_features = model.get_image_features(pixel_values=inputs["pixel_values"])
                text_features = model.get_text_features(**text_kwargs)
            similarities = _cosine_scores(image_features, text_features)
            label_scores = _average_label_scores(label_names, text_labels, similarities)
            logit_scale = _clip_logit_scale(model, self.temperature)
            probabilities = _softmax([label_scores[label] * logit_scale for label in label_names])
            results[group_name] = {
                label: float(probability)
                for label, probability in zip(label_names, probabilities)
            }
        return results

    def _load_components(self) -> tuple[Any, Any]:
        if self._processor is not None and self._model is not None:
            return self._processor, self._model
        processor_factory, model_factory = self._factories()
        if self._processor is None:
            self._processor = processor_factory(
                self.model_id,
                local_files_only=self.local_files_only,
            )
        if self._model is None:
            self._model = model_factory(
                self.model_id,
                local_files_only=self.local_files_only,
            )
        if self.device and hasattr(self._model, "to"):
            self._model = self._model.to(self.device)
        if hasattr(self._model, "eval"):
            self._model.eval()
        return self._processor, self._model

    def _factories(self) -> tuple[Any, Any]:
        if self._processor_factory is not None and self._model_factory is not None:
            return self._processor_factory, self._model_factory
        from transformers import CLIPModel, CLIPProcessor  # type: ignore

        return CLIPProcessor.from_pretrained, CLIPModel.from_pretrained


def classify_clip_risk(
    image: Any,
    *,
    scorer: ClipRiskScorer | None = None,
    calibration_policy: ClipRiskCalibrationPolicy | None = None,
) -> ClipRiskResult:
    active_scorer = scorer or LocalClipRiskScorer()
    policy = calibration_policy
    provider = getattr(active_scorer, "provider", "unknown")
    version = getattr(active_scorer, "version", None)

    try:
        if not active_scorer.is_available():
            return _unavailable_result(provider, version, policy, "unavailable")
        scores = active_scorer.score_prompt_groups(image, _PROMPT_GROUPS)
        scalar_scores = _extract_scalar_scores(scores)
    except Exception as exc:
        return _unavailable_result(provider, version, policy, _sanitize_exception_reason(exc))

    calibrated = policy is not None and policy.is_valid
    if not calibrated:
        return ClipRiskResult(
            provider=provider,
            version=version,
            availability="available",
            available=True,
            calibrated=False,
            calibration_version=_policy_version(policy),
            needs_review=True,
            decision=DECISION_REVIEW,
            **scalar_scores,
        )

    needs_review = _needs_review(scalar_scores, policy)
    return ClipRiskResult(
        provider=provider,
        version=version,
        availability="available",
        available=True,
        calibrated=True,
        calibration_version=policy.calibration_version,
        needs_review=needs_review,
        decision=DECISION_REVIEW if needs_review else DECISION_PASS,
        **scalar_scores,
    )


def _extract_scalar_scores(
    scores: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    return {
        "childlike_score": _score(scores, "adult_childlike", "childlike"),
        "adult_like_score": _score(scores, "adult_childlike", "adult_like"),
        "sexualized_score": _score(scores, "sexualized_safe", "sexualized"),
        "beautification_score": _score(scores, "natural_beautified", "beautified"),
        "brand_mismatch_score": _score(scores, "brand_fit_mismatch", "brand_mismatch"),
        "brand_fit_score": _score(scores, "brand_fit_mismatch", "brand_fit"),
        "severe_artifact_score": _score(scores, "clean_artifact", "severe_artifact"),
    }


def _score(scores: Mapping[str, Mapping[str, float]], group: str, label: str) -> float:
    value = float(scores[group][label])
    if not _is_probability(value):
        raise ClipRiskUnavailable("invalid_score")
    return value


def _needs_review(
    scores: Mapping[str, float],
    policy: ClipRiskCalibrationPolicy | None,
) -> bool:
    thresholds = policy.thresholds
    minimums = policy.minimums
    return (
        scores["childlike_score"] >= thresholds["childlike"]
        or scores["sexualized_score"] >= thresholds["sexualized"]
        or scores["beautification_score"] >= thresholds["beautification"]
        or scores["brand_mismatch_score"] >= thresholds["brand_mismatch"]
        or scores["severe_artifact_score"] >= thresholds["severe_artifact"]
        or scores["adult_like_score"] < minimums["adult_like"]
        or scores["brand_fit_score"] < minimums["brand_fit"]
    )


def _unavailable_result(
    provider: str,
    version: str | None,
    policy: ClipRiskCalibrationPolicy | None,
    reason: str,
) -> ClipRiskResult:
    return ClipRiskResult(
        provider=provider,
        version=version,
        availability="unavailable",
        available=False,
        availability_reason=reason,
        childlike_score=None,
        sexualized_score=None,
        beautification_score=None,
        brand_mismatch_score=None,
        severe_artifact_score=None,
        adult_like_score=None,
        brand_fit_score=None,
        calibrated=False,
        calibration_version=_policy_version(policy),
        needs_review=True,
        decision=DECISION_UNAVAILABLE,
    )


def _cosine_scores(image_features: Any, text_features: Any) -> Sequence[float]:
    image_values = _first_vector(image_features)
    text_vectors = _vectors(text_features)
    image_norm = _l2_norm(image_values)
    if image_norm == 0.0:
        raise ClipRiskUnavailable("invalid_image_embedding")
    scores = []
    for text_vector in text_vectors:
        text_norm = _l2_norm(text_vector)
        if text_norm == 0.0:
            raise ClipRiskUnavailable("invalid_text_embedding")
        dot = sum(a * b for a, b in zip(image_values, text_vector))
        scores.append(dot / (image_norm * text_norm))
    return scores


def _vectors(value: Any) -> Sequence[Sequence[float]]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not value:
        raise ClipRiskUnavailable("empty_embedding")
    first = value[0]
    if isinstance(first, (int, float)):
        return [tuple(float(item) for item in value)]
    return [tuple(float(item) for item in row) for row in value]


def _first_vector(value: Any) -> Sequence[float]:
    return _vectors(value)[0]


def _softmax(values: Sequence[float]) -> Sequence[float]:
    if not values:
        raise ClipRiskUnavailable("empty_logits")
    maximum = max(values)
    exps = [math.exp(float(value) - maximum) for value in values]
    total = sum(exps)
    if total <= 0.0:
        raise ClipRiskUnavailable("invalid_logits")
    return [value / total for value in exps]


def _l2_norm(values: Sequence[float]) -> float:
    return math.sqrt(sum(float(value) ** 2 for value in values))


def _average_label_scores(
    label_names: Sequence[str],
    text_labels: Sequence[str],
    similarities: Sequence[float],
) -> dict[str, float]:
    averaged = {}
    for label in label_names:
        values = [score for text_label, score in zip(text_labels, similarities) if text_label == label]
        if not values:
            raise ClipRiskUnavailable("empty_prompt_group")
        averaged[label] = sum(values) / len(values)
    return averaged


def _clip_logit_scale(model: Any, temperature: float | None) -> float:
    if temperature is not None:
        value = float(temperature)
        if not math.isfinite(value) or value <= 0.0:
            raise ClipRiskUnavailable("invalid_temperature")
        return 1.0 / value
    raw_scale = getattr(model, "logit_scale", None)
    if raw_scale is None:
        raise ClipRiskUnavailable("missing_logit_scale")
    if hasattr(raw_scale, "detach"):
        raw_scale = raw_scale.detach()
    if hasattr(raw_scale, "cpu"):
        raw_scale = raw_scale.cpu()
    if hasattr(raw_scale, "item"):
        raw_scale = raw_scale.item()
    raw_value = float(raw_scale)
    if not math.isfinite(raw_value):
        raise ClipRiskUnavailable("invalid_logit_scale")
    scale = math.exp(raw_value)
    if not math.isfinite(scale) or scale <= 0.0:
        raise ClipRiskUnavailable("invalid_logit_scale")
    return scale


def _policy_version(policy: ClipRiskCalibrationPolicy | None) -> str | None:
    return None if policy is None else policy.calibration_version


def _env_policy_values(env_keys: Mapping[str, str]) -> Mapping[str, float] | None:
    values = {}
    for key, env_key in env_keys.items():
        raw = os.environ.get(env_key)
        if raw is None:
            return None
        try:
            values[key] = float(raw)
        except ValueError:
            values[key] = float("nan")
    return values


def _is_probability(value: float) -> bool:
    return math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0


def _sanitize_exception_reason(exc: Exception) -> str:
    name = exc.__class__.__name__
    return name if name else "ClipRiskUnavailable"


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


class _torch_no_grad:
    def __enter__(self) -> None:
        try:
            import torch

            self._context = torch.no_grad()
        except Exception:  # pragma: no cover - optional dependency
            self._context = None
        if self._context is not None:
            self._context.__enter__()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._context is not None:
            self._context.__exit__(exc_type, exc, traceback)


__all__ = [
    "ClipRiskCalibrationPolicy",
    "ClipRiskResult",
    "ClipRiskScorer",
    "ClipRiskUnavailable",
    "LocalClipRiskScorer",
    "classify_clip_risk",
]
