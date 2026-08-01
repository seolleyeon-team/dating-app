from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image

from avatar_generation.analysis.config import SourceSafetyConfig
from avatar_generation.analysis.schema import FaceDetection, FaceDetectorResult

from .config import SmallFacePipelineConfig
from .crop_landmarker import CropFaceLandmarker, CropLandmarkerBackend
from .cropper import HeadShouldersCropper
from .full_range_detector import FullRangeFaceDetector, RawFaceDetector
from .nms import merge_detections_nms
from .neutralize import SecondaryFaceNeutralizer
from .orientation import ImageOrientationNormalizer, NormalizedImage
from .primary_selector import PrimaryFaceSelector
from .tile_detector import OverlappingTileDetector
from .types import InternalFaceAnalysis, InternalFaceDetection


@dataclass(frozen=True)
class SmallFacePipelineResult:
    normalized: Optional[NormalizedImage]
    analysis: InternalFaceAnalysis
    detector_result: FaceDetectorResult
    analysis_reference: Optional[Image.Image]
    public_reject_reasons: Tuple[str, ...]


class SmallFaceSourcePipeline:
    def __init__(
        self,
        *,
        config: Optional[SmallFacePipelineConfig] = None,
        source_config: Optional[SourceSafetyConfig] = None,
        raw_detector: Optional[RawFaceDetector] = None,
        landmarker_backend: Optional[CropLandmarkerBackend] = None,
        landmarker_model_path: str = "",
    ) -> None:
        self._config = config or SmallFacePipelineConfig.from_env()
        self._source_config = source_config or SourceSafetyConfig.from_env()
        self._normalizer = ImageOrientationNormalizer()
        self._detector = FullRangeFaceDetector(
            self._config, raw_detector=raw_detector
        )
        self._tiles = OverlappingTileDetector(self._config, self._detector)
        self._selector = PrimaryFaceSelector(self._config)
        self._cropper = HeadShouldersCropper(self._config)
        self._landmarker = CropFaceLandmarker(
            model_path=landmarker_model_path
            or self._source_config.mediapipe_face_landmarker_model_path,
            min_detection_confidence=0.45,
            min_presence_confidence=0.50,
            backend=landmarker_backend,
        )
        self._neutralizer = SecondaryFaceNeutralizer(self._config)

    @property
    def config(self) -> SmallFacePipelineConfig:
        return self._config

    def run(self, image_data) -> SmallFacePipelineResult:
        metrics: dict = {}
        normalized = self._normalizer.normalize(image_data)
        if normalized is None:
            analysis = InternalFaceAnalysis(
                primary_detection=None,
                secondary_detections=(),
                crop_transform=None,
                classification="no_usable_face",
                reason_code="avatar_source_analysis_failed",
                metrics=metrics,
            )
            return SmallFacePipelineResult(
                normalized=None,
                analysis=analysis,
                detector_result=FaceDetectorResult(
                    provider="small_face_pipeline",
                    image_width=None,
                    image_height=None,
                    faces=[],
                    metadata={"pipeline": "small_face", "corrupt": True},
                ),
                analysis_reference=None,
                public_reject_reasons=("corrupt_image",),
            )

        image = normalized.image
        width, height = image.size

        t0 = time.perf_counter()
        full_detections = self._detector.detect(
            image,
            min_confidence=self._config.fallback_min_confidence,
            detector_pass="full_image",
        )
        metrics["faceDetectionFullMs"] = int((time.perf_counter() - t0) * 1000)
        metrics["detectionPassCount"] = 1

        tile_detections: List[InternalFaceDetection] = []
        used_tile = False
        if self._tiles.should_run_tiles(
            full_detections, image_width=width, image_height=height
        ):
            tile_detections, tile_metrics = self._tiles.detect(image)
            metrics.update(tile_metrics)
            used_tile = True
            metrics["detectionPassCount"] = 1 + int(bool(tile_detections or True))

        t_nms = time.perf_counter()
        merged = merge_detections_nms(
            [*full_detections, *tile_detections],
            iou_threshold=self._config.cross_pass_nms_iou,
        )
        metrics["nmsMs"] = int((time.perf_counter() - t_nms) * 1000)
        metrics["detectedFaceCountBucket"] = _count_bucket(len(merged))
        metrics["usedTileFallback"] = used_tile

        t_sel = time.perf_counter()
        selection = self._selector.select(merged)
        metrics["primarySelectionMs"] = int((time.perf_counter() - t_sel) * 1000)

        if selection.reason_code:
            analysis = InternalFaceAnalysis(
                primary_detection=selection.primary,
                secondary_detections=selection.secondary_faces,
                crop_transform=None,
                used_tile_fallback=used_tile,
                detection_pass_count=int(metrics["detectionPassCount"]),
                classification=selection.classification,
                reason_code=selection.reason_code,
                metrics=metrics,
                face_detected=bool(merged),
                avatar_usable=False,
            )
            return SmallFacePipelineResult(
                normalized=normalized,
                analysis=analysis,
                detector_result=_to_detector_result(merged, width, height, metrics),
                analysis_reference=None,
                public_reject_reasons=_to_public_reasons(selection.reason_code),
            )

        primary = selection.primary
        assert primary is not None

        # Avatar-usable quality gate (stricter than detect).
        if primary.face_short_side_px < self._config.min_short_side_trait_px:
            reason = "avatar_source_face_too_small"
            analysis = InternalFaceAnalysis(
                primary_detection=primary,
                secondary_detections=selection.secondary_faces,
                crop_transform=None,
                used_tile_fallback=used_tile,
                detection_pass_count=int(metrics["detectionPassCount"]),
                classification="no_usable_face",
                reason_code=reason,
                metrics={**metrics, "primaryFaceSizeBucket": _size_bucket(primary.face_short_side_px)},
                face_detected=True,
                avatar_usable=False,
            )
            return SmallFacePipelineResult(
                normalized=normalized,
                analysis=analysis,
                detector_result=_to_detector_result(merged, width, height, metrics),
                analysis_reference=None,
                public_reject_reasons=("face_too_small",),
            )

        if primary.sharpness_score is not None and primary.sharpness_score < 0.12:
            analysis = InternalFaceAnalysis(
                primary_detection=primary,
                secondary_detections=selection.secondary_faces,
                crop_transform=None,
                used_tile_fallback=used_tile,
                detection_pass_count=int(metrics["detectionPassCount"]),
                classification="no_usable_face",
                reason_code="avatar_source_face_too_blurry",
                metrics=metrics,
                face_detected=True,
                avatar_usable=False,
            )
            return SmallFacePipelineResult(
                normalized=normalized,
                analysis=analysis,
                detector_result=_to_detector_result(merged, width, height, metrics),
                analysis_reference=None,
                public_reject_reasons=("face_too_small",),
            )

        crop_result = self._cropper.crop(image, primary)
        t_lm = time.perf_counter()
        ok, landmarks, lm_reason = self._landmarker.run(crop_result.image)
        metrics["cropLandmarkerMs"] = int((time.perf_counter() - t_lm) * 1000)
        if not ok:
            analysis = InternalFaceAnalysis(
                primary_detection=primary,
                secondary_detections=selection.secondary_faces,
                crop_transform=crop_result.transform,
                crop_image=crop_result.image,
                used_tile_fallback=used_tile,
                detection_pass_count=int(metrics["detectionPassCount"]),
                classification="no_usable_face",
                reason_code=lm_reason or "avatar_source_landmarks_unstable",
                metrics=metrics,
                face_detected=True,
                avatar_usable=False,
            )
            return SmallFacePipelineResult(
                normalized=normalized,
                analysis=analysis,
                detector_result=_to_detector_result(merged, width, height, metrics),
                analysis_reference=None,
                public_reject_reasons=_to_public_reasons(
                    lm_reason or "avatar_source_landmarks_unstable"
                ),
            )

        t_ref = time.perf_counter()
        neutralization = self._neutralizer.apply(
            crop_result.image,
            secondary_faces=selection.secondary_faces,
            crop_transform=crop_result.transform,
            original_width=width,
            original_height=height,
            primary=primary,
        )
        metrics["referencePreprocessingMs"] = int((time.perf_counter() - t_ref) * 1000)
        metrics["secondaryFacesDetected"] = neutralization.secondary_faces_detected
        metrics["secondaryFacesNeutralized"] = neutralization.secondary_faces_neutralized
        metrics["secondaryFaceNeutralizationCount"] = (
            neutralization.secondary_faces_neutralized
        )
        metrics["neutralizationMethodVersion"] = neutralization.method_version
        metrics["primaryFaceSizeBucket"] = _size_bucket(primary.face_short_side_px)
        metrics["sourceRejectedBeforeGpu"] = False

        analysis = InternalFaceAnalysis(
            primary_detection=primary,
            secondary_detections=selection.secondary_faces,
            crop_transform=crop_result.transform,
            crop_image=crop_result.image,
            crop_landmarks=landmarks,
            used_tile_fallback=used_tile,
            detection_pass_count=int(metrics["detectionPassCount"]),
            classification=selection.classification,
            reason_code=None,
            metrics=metrics,
            face_detected=True,
            avatar_usable=True,
        )
        return SmallFacePipelineResult(
            normalized=normalized,
            analysis=analysis,
            detector_result=_to_detector_result(merged, width, height, metrics),
            analysis_reference=neutralization.image,
            public_reject_reasons=(),
        )


def _to_detector_result(
    detections: Sequence[InternalFaceDetection],
    width: int,
    height: int,
    metrics: dict,
) -> FaceDetectorResult:
    faces = [
        FaceDetection(
            bbox=det.bbox_normalized.as_xywh(),
            confidence=det.confidence,
        )
        for det in detections
    ]
    safe_metrics = {
        key: value
        for key, value in metrics.items()
        if key
        in {
            "faceDetectionFullMs",
            "faceDetectionTileMs",
            "tileCount",
            "nmsMs",
            "primarySelectionMs",
            "cropLandmarkerMs",
            "referencePreprocessingMs",
            "usedTileFallback",
            "detectionPassCount",
            "detectedFaceCountBucket",
            "primaryFaceSizeBucket",
            "secondaryFacesDetected",
            "secondaryFacesNeutralized",
            "secondaryFaceNeutralizationCount",
            "neutralizationMethodVersion",
            "sourceRejectedBeforeGpu",
        }
    }
    return FaceDetectorResult(
        provider="small_face_pipeline",
        image_width=width,
        image_height=height,
        faces=faces,
        metadata={"pipeline": "small_face", **safe_metrics},
    )


def _to_public_reasons(reason_code: str) -> Tuple[str, ...]:
    mapping = {
        "avatar_source_no_face": ("no_face",),
        "avatar_source_face_too_small": ("face_too_small",),
        "avatar_source_face_too_blurry": ("face_too_small",),
        "avatar_source_multiple_primary_faces": ("multi_face_primary",),
        "avatar_source_face_out_of_frame": ("face_too_small",),
        "avatar_source_landmarks_unstable": ("severe_occlusion",),
        "avatar_source_analysis_failed": ("corrupt_image",),
    }
    return mapping.get(reason_code, ("no_face",))


def _count_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count == 2:
        return "2"
    return "3plus"


def _size_bucket(short_side: int) -> str:
    if short_side < 32:
        return "lt32"
    if short_side < 48:
        return "32_47"
    if short_side < 64:
        return "48_63"
    if short_side < 80:
        return "64_79"
    if short_side < 120:
        return "80_119"
    return "ge120"


__all__ = ["SmallFaceSourcePipeline", "SmallFacePipelineResult"]
