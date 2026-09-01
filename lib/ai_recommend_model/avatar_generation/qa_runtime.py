from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from PIL import Image

from .analysis.config import SourceSafetyConfig
from .analysis.detectors import build_default_face_detector
from .calibration_artifact import CalibrationArtifactError, load_configured_calibration_artifact
from .model_adapters.clip_risk import ClipRiskCalibrationPolicy, LocalClipRiskScorer, classify_clip_risk
from .model_adapters.florence2_visual import Florence2VisualRiskAdapter
from .model_adapters.image_similarity import CalibrationPolicy, ImageSimilarityAdapter, compare_image_similarity
from .qa_signals import CandidateQASignalResult, build_candidate_qa_signals


_ENV_SIMILARITY_CALIBRATION_VERSION = "AVATAR_QA_SIMILARITY_CALIBRATION_VERSION"
_ENV_SIMILARITY_THRESHOLD = "AVATAR_QA_SIMILARITY_THRESHOLD"
_ENV_SIMILARITY_REVIEW_MARGIN = "AVATAR_QA_SIMILARITY_REVIEW_MARGIN"
_ENV_VISUAL_RISK_MODEL_ID = "AVATAR_QA_VISUAL_RISK_MODEL_ID"
_ENV_CLIP_RISK_MODEL_ID = "AVATAR_CLIP_RISK_MODEL_ID"
_ENV_SIMILARITY_MODEL_ID = "AVATAR_QA_SIMILARITY_MODEL_ID"

# The official Transformers-converted checkpoint avoids the original
# Microsoft checkpoint's tokenizer compatibility issue on Transformers 4.57.
_DEFAULT_VISUAL_RISK_MODEL_ID = "florence-community/Florence-2-large-ft"
_DEFAULT_CLIP_RISK_MODEL_ID = "openai/clip-vit-large-patch14"
_DEFAULT_SIMILARITY_MODEL_ID = "openai/clip-vit-base-patch32"

_DEFAULT_FACE_DETECTOR: Any = None
_DEFAULT_VISUAL_RISK_ADAPTER: Florence2VisualRiskAdapter | None = None
_DEFAULT_CLIP_RISK_SCORER: LocalClipRiskScorer | None = None
_DEFAULT_SIMILARITY_ADAPTER: CachedImageSimilarityAdapter | None = None
_DEFAULT_QA_RUNTIME: "AvatarQARuntime" | None = None


@dataclass
class CachedImageSimilarityAdapter:
    def __init__(self, encoder: ImageSimilarityAdapter) -> None:
        self.encoder = encoder
        self.provider = encoder.provider
        self.version = encoder.version

    def is_available(self) -> bool:
        return bool(self.encoder.is_available())

    def compare(
        self,
        source_crop: Image.Image,
        candidate_crop: Image.Image,
        *,
        calibration_policy: Any = None,
    ) -> Any:
        return compare_image_similarity(
            source_crop,
            candidate_crop,
            encoder=self.encoder,
            calibration_policy=calibration_policy,
        )


@dataclass
class AvatarQARuntime:
    face_detector: Any
    visual_risk_adapter: Any
    local_risk_adapter: Any
    similarity_adapter: Any
    similarity_policy: Any = None

    def build_signals(
        self,
        *,
        source_image: Image.Image,
        candidate_image: Image.Image,
        metadata: Mapping[str, Any],
        source_traits: Mapping[str, Any] | None = None,
        candidate_traits: Mapping[str, Any] | None = None,
        source_primary_bbox: Sequence[float] | None = None,
    ) -> CandidateQASignalResult:
        source_analysis = _mapping_child(metadata, "sourceAnalysis")
        reference_preprocess = _mapping_child(metadata, "referencePreprocess")
        source_visual_risk: Any = None
        source_visual_unavailable = False
        if metadata.get("compareSourceVisualRisk") is True:
            try:
                source_visual_risk = self.visual_risk_adapter.analyze(
                    source_image,
                    primary_face_bbox_xyxy=None,
                )
            except Exception:
                # Candidate QA still runs, but cannot call text source-consistency
                # evidence reliable when the source-side detector is unavailable.
                source_visual_unavailable = True
        result = build_candidate_qa_signals(
            source_image=source_image,
            candidate_image=candidate_image,
            source_analysis=source_analysis,
            reference_preprocess=reference_preprocess,
            source_traits=source_traits or _mapping_child(metadata, "sourceTraitCard"),
            candidate_traits=candidate_traits or _mapping_child(metadata, "candidateTraitCard"),
            source_primary_bbox=source_primary_bbox or _source_primary_bbox(source_analysis),
            face_detector=self.face_detector,
            visual_risk_adapter=self.visual_risk_adapter,
            local_risk_adapter=self.local_risk_adapter,
            similarity_adapter=self.similarity_adapter,
            similarity_policy=self.similarity_policy,
            source_visual_risk=source_visual_risk,
            source_visual_image_size=source_image.size,
            trait_qa_context=metadata,
        )
        if not source_visual_unavailable:
            return result
        availability = dict(result.model_availability)
        availability["sourceVisualRisk"] = "unavailable"
        unavailable = tuple(dict.fromkeys((*result.models_unavailable, "sourceVisualRisk")))
        signals = dict(result.signals)
        signals["sourceVisualConsistency"] = "unknown"
        return CandidateQASignalResult(
            signals=signals,
            model_availability=availability,
            stage=result.stage,
            cascade=result.cascade,
            models_unavailable=unavailable,
            needs_review=True,
            skipped_heavy_reason=result.skipped_heavy_reason,
            trait_matches=result.trait_matches,
        )

    def cache_snapshot(self) -> dict[str, Any]:
        return {
            "faceDetector": self.face_detector,
            "visualRiskAdapter": self.visual_risk_adapter,
            "localRiskAdapter": self.local_risk_adapter,
            "similarityAdapter": self.similarity_adapter,
        }


def get_default_face_detector() -> Any:
    global _DEFAULT_FACE_DETECTOR
    if _DEFAULT_FACE_DETECTOR is None:
        _DEFAULT_FACE_DETECTOR = build_default_face_detector(SourceSafetyConfig.from_env())
    return _DEFAULT_FACE_DETECTOR


def get_default_visual_risk_adapter() -> Florence2VisualRiskAdapter:
    global _DEFAULT_VISUAL_RISK_ADAPTER
    if _DEFAULT_VISUAL_RISK_ADAPTER is None:
        _DEFAULT_VISUAL_RISK_ADAPTER = Florence2VisualRiskAdapter(
            model_id=(
                os.environ.get(_ENV_VISUAL_RISK_MODEL_ID, "").strip()
                or _DEFAULT_VISUAL_RISK_MODEL_ID
            ),
            local_files_only=True,
        )
    return _DEFAULT_VISUAL_RISK_ADAPTER


def get_default_clip_risk_scorer() -> LocalClipRiskScorer:
    global _DEFAULT_CLIP_RISK_SCORER
    if _DEFAULT_CLIP_RISK_SCORER is None:
        _DEFAULT_CLIP_RISK_SCORER = LocalClipRiskScorer(
            model_id=(
                os.environ.get(_ENV_CLIP_RISK_MODEL_ID, "").strip()
                or _DEFAULT_CLIP_RISK_MODEL_ID
            ),
            local_files_only=True,
        )
    return _DEFAULT_CLIP_RISK_SCORER


def get_default_similarity_adapter() -> CachedImageSimilarityAdapter:
    global _DEFAULT_SIMILARITY_ADAPTER
    if _DEFAULT_SIMILARITY_ADAPTER is None:
        _DEFAULT_SIMILARITY_ADAPTER = CachedImageSimilarityAdapter(
            ImageSimilarityAdapter(
                model_id=(
                    os.environ.get(_ENV_SIMILARITY_MODEL_ID, "").strip()
                    or _DEFAULT_SIMILARITY_MODEL_ID
                ),
                local_files_only=True,
            )
        )
    return _DEFAULT_SIMILARITY_ADAPTER


def get_default_qa_runtime() -> AvatarQARuntime:
    global _DEFAULT_QA_RUNTIME
    if _DEFAULT_QA_RUNTIME is None:
        _DEFAULT_QA_RUNTIME = AvatarQARuntime(
            face_detector=get_default_face_detector(),
            visual_risk_adapter=get_default_visual_risk_adapter(),
            local_risk_adapter=_classify_clip_risk_from_env,
            similarity_adapter=get_default_similarity_adapter(),
            similarity_policy=_similarity_policy_from_env(),
        )
    return _DEFAULT_QA_RUNTIME


def build_actual_candidate_qa_signals(
    *,
    source_image: Image.Image,
    candidate_image: Image.Image,
    metadata: Mapping[str, Any],
    source_traits: Mapping[str, Any] | None = None,
    candidate_traits: Mapping[str, Any] | None = None,
    runtime: AvatarQARuntime | None = None,
) -> CandidateQASignalResult:
    active_runtime = runtime or get_default_qa_runtime()
    return active_runtime.build_signals(
        source_image=source_image.convert("RGB"),
        candidate_image=candidate_image.convert("RGB"),
        metadata=metadata,
        source_traits=source_traits,
        candidate_traits=candidate_traits,
    )


def _classify_clip_risk_from_env(image: Image.Image) -> Any:
    return classify_clip_risk(
        image,
        scorer=get_default_clip_risk_scorer(),
        calibration_policy=_clip_risk_policy_from_env(),
    )


def _calibration_artifact_is_configured() -> bool:
    return bool(os.environ.get("AVATAR_QA_CALIBRATION_ARTIFACT_PATH", "").strip())


def _configured_calibration_artifact() -> Any | None:
    if not _calibration_artifact_is_configured():
        return None
    try:
        return load_configured_calibration_artifact(required=True)
    except CalibrationArtifactError:
        return None


def _clip_risk_policy_from_env() -> ClipRiskCalibrationPolicy | None:
    if _calibration_artifact_is_configured():
        artifact = _configured_calibration_artifact()
        return artifact.to_clip_policy() if artifact is not None else None
    return ClipRiskCalibrationPolicy.from_env()


def _similarity_policy_from_env() -> CalibrationPolicy | None:
    if _calibration_artifact_is_configured():
        artifact = _configured_calibration_artifact()
        return artifact.to_similarity_policy() if artifact is not None else None
    version = os.environ.get(_ENV_SIMILARITY_CALIBRATION_VERSION, "").strip()
    if not version:
        return None
    try:
        threshold = float(os.environ[_ENV_SIMILARITY_THRESHOLD])
    except (KeyError, ValueError):
        return None
    try:
        margin = float(os.environ.get(_ENV_SIMILARITY_REVIEW_MARGIN, "0"))
    except ValueError:
        margin = 0.0
    return CalibrationPolicy(
        calibration_version=version,
        threshold=threshold,
        review_margin=max(0.0, margin),
    )


def _mapping_child(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    child = parent.get(key)
    return child if isinstance(child, Mapping) else {}


def _source_primary_bbox(source_analysis: Mapping[str, Any]) -> Optional[Sequence[float]]:
    value = source_analysis.get("primaryFaceBbox") or source_analysis.get("primaryFaceBBox")
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return tuple(float(item) for item in value[:4])
    face = source_analysis.get("primaryFace")
    if isinstance(face, Mapping):
        bbox = face.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            return tuple(float(item) for item in bbox[:4])
    return None


__all__ = [
    "AvatarQARuntime",
    "CachedImageSimilarityAdapter",
    "build_actual_candidate_qa_signals",
    "get_default_face_detector",
    "get_default_visual_risk_adapter",
    "get_default_clip_risk_scorer",
    "get_default_similarity_adapter",
    "get_default_qa_runtime",
]
