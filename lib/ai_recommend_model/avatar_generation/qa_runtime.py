from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from PIL import Image

from .analysis.config import SourceSafetyConfig
from .analysis.detectors import build_default_face_detector
from .model_adapters.clip_risk import ClipRiskCalibrationPolicy, LocalClipRiskScorer, classify_clip_risk
from .model_adapters.florence2_visual import Florence2VisualRiskAdapter
from .model_adapters.image_similarity import CalibrationPolicy, ImageSimilarityAdapter, compare_image_similarity
from .qa_signals import CandidateQASignalResult, build_candidate_qa_signals


_ENV_SIMILARITY_CALIBRATION_VERSION = "AVATAR_QA_SIMILARITY_CALIBRATION_VERSION"
_ENV_SIMILARITY_THRESHOLD = "AVATAR_QA_SIMILARITY_THRESHOLD"
_ENV_SIMILARITY_REVIEW_MARGIN = "AVATAR_QA_SIMILARITY_REVIEW_MARGIN"

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
        return build_candidate_qa_signals(
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
        _DEFAULT_VISUAL_RISK_ADAPTER = Florence2VisualRiskAdapter(local_files_only=True)
    return _DEFAULT_VISUAL_RISK_ADAPTER


def get_default_clip_risk_scorer() -> LocalClipRiskScorer:
    global _DEFAULT_CLIP_RISK_SCORER
    if _DEFAULT_CLIP_RISK_SCORER is None:
        _DEFAULT_CLIP_RISK_SCORER = LocalClipRiskScorer(local_files_only=True)
    return _DEFAULT_CLIP_RISK_SCORER


def get_default_similarity_adapter() -> CachedImageSimilarityAdapter:
    global _DEFAULT_SIMILARITY_ADAPTER
    if _DEFAULT_SIMILARITY_ADAPTER is None:
        _DEFAULT_SIMILARITY_ADAPTER = CachedImageSimilarityAdapter(
            ImageSimilarityAdapter(local_files_only=True)
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
        calibration_policy=ClipRiskCalibrationPolicy.from_env(),
    )


def _similarity_policy_from_env() -> CalibrationPolicy | None:
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
