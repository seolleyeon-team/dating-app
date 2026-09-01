from __future__ import annotations

from .config import (
    DEFAULT_MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
    DEFAULT_MIN_FACE_AREA_RATIO,
    DEFAULT_SEVERE_OCCLUSION_THRESHOLD,
    DEFAULT_SOURCE_ANALYSIS_VERSION,
    SourceSafetyConfig,
)
from .detectors import (
    DeterministicFallbackFaceDetector,
    FaceDetector,
    MediaPipeFaceDetector,
    OpenCvHaarFaceDetector,
    StaticFaceDetector,
    build_default_face_detector,
)
from .redaction import redact_source_ref, redacted_source_ref
from .schema import FaceDetection, FaceDetectorResult, SourceAnalysisResult
from .visual_risk import (
    VisualRiskAdapter,
    VisualRiskAnalysis,
    VisualRiskRegion,
    analyze_florence_visual_risk_outputs,
)
from .watermark import (
    WATERMARK_QA_ACTION_ALLOW,
    WATERMARK_QA_ACTION_REJECT,
    WATERMARK_QA_ACTION_REVIEW,
    WATERMARK_POLICY_VERSION,
    WatermarkDecision,
    evaluate_watermark_risk,
    resolve_watermark_qa_action,
    watermark_risk_for_action,
)
from .source_analyzer import (
    REJECT_CORRUPT_IMAGE,
    REJECT_FACE_TOO_SMALL,
    REJECT_MULTIPLE_FACES,
    REJECT_NO_FACE,
    REJECT_SEVERE_OCCLUSION,
    analyze_avatar_source_image,
)

__all__ = [
    "DEFAULT_MEDIAPIPE_MIN_DETECTION_CONFIDENCE",
    "DEFAULT_MIN_FACE_AREA_RATIO",
    "DEFAULT_SEVERE_OCCLUSION_THRESHOLD",
    "DEFAULT_SOURCE_ANALYSIS_VERSION",
    "DeterministicFallbackFaceDetector",
    "FaceDetection",
    "FaceDetector",
    "FaceDetectorResult",
    "MediaPipeFaceDetector",
    "OpenCvHaarFaceDetector",
    "REJECT_CORRUPT_IMAGE",
    "REJECT_FACE_TOO_SMALL",
    "REJECT_MULTIPLE_FACES",
    "REJECT_NO_FACE",
    "REJECT_SEVERE_OCCLUSION",
    "SourceAnalysisResult",
    "SourceSafetyConfig",
    "StaticFaceDetector",
    "VisualRiskRegion",
    "VisualRiskAnalysis",
    "VisualRiskAdapter",
    "WATERMARK_QA_ACTION_ALLOW",
    "WATERMARK_QA_ACTION_REJECT",
    "WATERMARK_QA_ACTION_REVIEW",
    "WATERMARK_POLICY_VERSION",
    "WatermarkDecision",
    "analyze_avatar_source_image",
    "analyze_florence_visual_risk_outputs",
    "build_default_face_detector",
    "evaluate_watermark_risk",
    "resolve_watermark_qa_action",
    "redact_source_ref",
    "redacted_source_ref",
    "watermark_risk_for_action",
]
