from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence



Embedding = tuple[float, ...]


class ImageEmbeddingEncoder(Protocol):
    provider: str
    version: str

    def is_available(self) -> bool:
        ...

    def encode_image(self, image: Any) -> Sequence[float]:
        ...


@dataclass(frozen=True)
class CalibrationPolicy:
    calibration_version: str
    threshold: float
    review_margin: float = 0.0

    @property
    def is_calibrated(self) -> bool:
        return bool(str(self.calibration_version).strip())


@dataclass(frozen=True)
class SimilarityResult:
    provider: str
    available: bool
    score: float | None
    broad_consistency: float | None
    identity_decision: str
    identity_reliable: bool
    needs_review: bool
    calibration_version: str | None
    threshold: float | None
    provider_version: str | None = None
    availability_reason: str | None = None
    source_embedding: Embedding | None = field(default=None, repr=False, compare=False)
    target_embedding: Embedding | None = field(default=None, repr=False, compare=False)

    def to_document(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "providerVersion": self.provider_version,
            "available": bool(self.available),
            "availabilityReason": self.availability_reason,
            "score": _round_optional(self.score),
            "broadConsistency": _round_optional(self.broad_consistency),
            "identityDecision": self.identity_decision,
            "identityReliable": bool(self.identity_reliable),
            "needsReview": bool(self.needs_review),
            "calibrationVersion": self.calibration_version,
            "threshold": _round_optional(self.threshold),
        }


class ImageSimilarityAdapter:
    """Lazy local image embedding adapter for CLIP or DINOv2-style encoders."""

    def __init__(
        self,
        *,
        provider: str = "clip",
        model_id: str = "openai/clip-vit-base-patch32",
        processor: Any = None,
        model: Any = None,
        local_files_only: bool = True,
        device: str | None = None,
    ) -> None:
        self.provider = provider
        self.model_id = model_id
        self.version = model_id
        self._processor = processor
        self._model = model
        self.local_files_only = bool(local_files_only)
        self.device = device
        self._load_error: str | None = None

    def is_available(self) -> bool:
        if self._load_error is not None:
            return False
        try:
            self._load_components()
        except Exception as exc:  # pragma: no cover - depends on optional local models
            self._load_error = exc.__class__.__name__
            return False
        return True

    def encode_image(self, image: Any) -> Embedding:
        processor, model = self._load_components()
        pil_image = _decode_image(image)
        inputs = processor(images=pil_image, return_tensors="pt")
        if self.device:
            inputs = {
                key: value.to(self.device) if hasattr(value, "to") else value
                for key, value in dict(inputs).items()
            }
        with _torch_no_grad():
            if self.provider.lower().startswith("dino"):
                output = model(**inputs)
                embedding = getattr(output, "pooler_output", None)
                if embedding is None:
                    embedding = output.last_hidden_state[:, 0]
            else:
                embedding = model.get_image_features(**inputs)
        if hasattr(embedding, "detach"):
            embedding = embedding.detach()
        if hasattr(embedding, "cpu"):
            embedding = embedding.cpu()
        if hasattr(embedding, "numpy"):
            values = embedding.numpy().reshape(-1).tolist()
        else:
            values = list(embedding)
        return tuple(float(value) for value in values)

    def _load_components(self) -> tuple[Any, Any]:
        if self._processor is not None and self._model is not None:
            return self._processor, self._model

        if self.provider.lower().startswith("dino"):
            from transformers import AutoImageProcessor, AutoModel

            if self._processor is None:
                self._processor = AutoImageProcessor.from_pretrained(
                    self.model_id,
                    local_files_only=self.local_files_only,
                )
            if self._model is None:
                self._model = AutoModel.from_pretrained(
                    self.model_id,
                    local_files_only=self.local_files_only,
                )
        else:
            from transformers import CLIPImageProcessor, CLIPModel

            if self._processor is None:
                self._processor = CLIPImageProcessor.from_pretrained(
                    self.model_id,
                    local_files_only=self.local_files_only,
                )
            if self._model is None:
                self._model = CLIPModel.from_pretrained(
                    self.model_id,
                    local_files_only=self.local_files_only,
                )
        if self.device and hasattr(self._model, "to"):
            self._model = self._model.to(self.device)
        if hasattr(self._model, "eval"):
            self._model.eval()
        return self._processor, self._model


def compare_image_similarity(
    source_image: Any,
    target_image: Any,
    *,
    encoder: ImageEmbeddingEncoder | None = None,
    calibration_policy: CalibrationPolicy | None = None,
) -> SimilarityResult:
    active_encoder = encoder or ImageSimilarityAdapter()
    provider = getattr(active_encoder, "provider", "unknown")
    version = getattr(active_encoder, "version", None)

    try:
        if not active_encoder.is_available():
            return _unavailable_result(
                provider=provider,
                version=version,
                calibration_policy=calibration_policy,
                reason="unavailable",
            )

        source_embedding = _normalize_embedding(active_encoder.encode_image(source_image))
        target_embedding = _normalize_embedding(active_encoder.encode_image(target_image))
        score = cosine_similarity(source_embedding, target_embedding)
    except Exception as exc:
        return _unavailable_result(
            provider=provider,
            version=version,
            calibration_policy=calibration_policy,
            reason=_sanitize_exception_reason(exc),
        )
    calibrated = calibration_policy is not None and calibration_policy.is_calibrated

    if not calibrated:
        return SimilarityResult(
            provider=provider,
            provider_version=version,
            available=True,
            score=score,
            broad_consistency=score,
            identity_decision="uncertain",
            identity_reliable=False,
            needs_review=True,
            calibration_version=_policy_version(calibration_policy),
            threshold=_policy_threshold(calibration_policy),
            source_embedding=source_embedding,
            target_embedding=target_embedding,
        )

    threshold = float(calibration_policy.threshold)
    review_margin = max(0.0, float(calibration_policy.review_margin))
    if score >= threshold:
        decision = "high_similarity_risk"
        reliable = True
        needs_review = True
    elif review_margin and score >= threshold - review_margin:
        decision = "review_similarity"
        reliable = False
        needs_review = True
    else:
        decision = "low_similarity_risk"
        reliable = True
        needs_review = False

    return SimilarityResult(
        provider=provider,
        provider_version=version,
        available=True,
        score=score,
        broad_consistency=score,
        identity_decision=decision,
        identity_reliable=reliable,
        needs_review=needs_review,
        calibration_version=calibration_policy.calibration_version,
        threshold=threshold,
        source_embedding=source_embedding,
        target_embedding=target_embedding,
    )


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embeddings must have the same dimensionality.")
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    return round(max(-1.0, min(1.0, dot / (left_norm * right_norm))), 6)


def _normalize_embedding(values: Sequence[float]) -> Embedding:
    return tuple(float(value) for value in values)


def _decode_image(image: Any) -> Any:
    from PIL import Image

    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, bytes):
        with Image.open(io.BytesIO(image)) as opened:
            return opened.convert("RGB")
    return image


class _torch_no_grad:
    def __enter__(self) -> None:
        try:
            import torch

            self._context = torch.no_grad()
        except Exception:  # pragma: no cover - only used without torch installed
            self._context = None
        if self._context is not None:
            self._context.__enter__()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._context is not None:
            self._context.__exit__(exc_type, exc, traceback)


def _policy_version(policy: CalibrationPolicy | None) -> str | None:
    return None if policy is None else policy.calibration_version


def _policy_threshold(policy: CalibrationPolicy | None) -> float | None:
    return None if policy is None else float(policy.threshold)


def _unavailable_result(
    *,
    provider: str,
    version: str | None,
    calibration_policy: CalibrationPolicy | None,
    reason: str,
) -> SimilarityResult:
    return SimilarityResult(
        provider=provider,
        provider_version=version,
        available=False,
        availability_reason=reason,
        score=None,
        broad_consistency=None,
        identity_decision="needs_review",
        identity_reliable=False,
        needs_review=True,
        calibration_version=_policy_version(calibration_policy),
        threshold=_policy_threshold(calibration_policy),
    )


def _sanitize_exception_reason(exc: Exception) -> str:
    name = exc.__class__.__name__
    return name if name else "adapter_error"


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


__all__ = [
    "CalibrationPolicy",
    "ImageEmbeddingEncoder",
    "ImageSimilarityAdapter",
    "SimilarityResult",
    "compare_image_similarity",
    "cosine_similarity",
]
