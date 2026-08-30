import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.schema import FaceDetection, FaceDetectorResult  # noqa: E402
from avatar_generation.analysis.visual_risk import (  # noqa: E402
    ACTION_NEUTRALIZE_TEXT_LOGO,
    STATUS_CRITICAL_UNAVAILABLE,
    VisualRiskAnalysis,
    VisualRiskRegion,
)
from avatar_generation.model_adapters.clip_risk import ClipRiskResult  # noqa: E402
from avatar_generation.qa import run_avatar_candidate_qa  # noqa: E402
from avatar_generation.qa_runtime import (  # noqa: E402
    AvatarQARuntime,
    build_actual_candidate_qa_signals,
    get_default_qa_runtime,
    get_default_clip_risk_scorer,
    get_default_similarity_adapter,
    get_default_visual_risk_adapter,
)


def _image(color):
    image = Image.new("RGB", (96, 96), color)
    pixels = image.load()
    base = tuple(int(channel) for channel in color)
    for x in range(0, 96, 6):
        for y in range(96):
            pixels[x, y] = (
                (base[0] + x + y) % 255,
                (base[1] + (2 * x)) % 255,
                (base[2] + (3 * y)) % 255,
            )
    for y in range(0, 96, 8):
        for x in range(96):
            pixels[x, y] = (
                (base[0] + (2 * y)) % 255,
                (base[1] + x + y) % 255,
                (base[2] + x) % 255,
            )
    return image


def _face():
    return FaceDetection(bbox=(0.2, 0.18, 0.55, 0.62), confidence=0.96)


def _traits():
    return {
        "hair_color_range": "black",
        "hair_color_range_confidence": 0.96,
        "eyewear_present": False,
        "eyewear_present_confidence": 0.97,
        "facial_hair_present": False,
        "facial_hair_present_confidence": 0.98,
        "clothing_category": "hoodie",
        "clothing_category_confidence": 0.94,
        "clothing_color": "navy",
        "clothing_color_confidence": 0.95,
    }


class FakeFaceDetector:
    def __init__(self, faces=None, *, fail=False):
        self.faces = tuple(faces if faces is not None else [_face()])
        self.fail = fail

    def detect(self, image):
        if self.fail:
            raise RuntimeError("private/source/path.jpg")
        return FaceDetectorResult(
            provider="fake-face",
            image_width=image.width,
            image_height=image.height,
            faces=self.faces,
            model_availability={"faceDetector": "available"},
        )


class FakeVisualAdapter:
    def __init__(self, analysis=None, *, fail=False):
        self.analysis = analysis or VisualRiskAnalysis(
            provider="fake-visual",
            provider_available=True,
            status="available",
            risk="pass",
            detector_availability={"ocr": "available"},
            background_complexity="low",
        )
        self.fail = fail

    def analyze(self, image, *, primary_face_bbox_xyxy=None):
        if self.fail:
            raise ValueError("raw OCR Jane Campus")
        return self.analysis


class FakeClipRiskAdapter:
    def __init__(self, result=None, *, fail=False):
        self.result = result or ClipRiskResult(
            provider="clip",
            version="clip-v1",
            availability="available",
            available=True,
            childlike_score=0.05,
            sexualized_score=0.02,
            beautification_score=0.08,
            brand_mismatch_score=0.03,
            severe_artifact_score=0.04,
            adult_like_score=0.95,
            brand_fit_score=0.94,
            calibrated=True,
            calibration_version="clip-cal-v1",
            needs_review=False,
        )
        self.fail = fail

    def analyze(self, image):
        if self.fail:
            raise OSError("clip raw labels")
        return self.result


@dataclass(frozen=True)
class FakeSimilarityResult:
    available: bool = True
    score: float | None = 0.12
    identity_decision: str = "low_similarity_risk"
    identity_reliable: bool = True
    needs_review: bool = False
    calibration_version: str | None = "sim-cal-v1"


class FakeSimilarityAdapter:
    def __init__(self, result=None, *, fail=False):
        self.result = result or FakeSimilarityResult()
        self.fail = fail
        self.source_images = []

    def compare(self, source_crop, candidate_crop, *, calibration_policy=None):
        if self.fail:
            raise LookupError("private embedding ref")
        self.source_images.append(source_crop.copy())
        return self.result


def _runtime(**overrides):
    values = {
        "face_detector": FakeFaceDetector(),
        "visual_risk_adapter": FakeVisualAdapter(),
        "local_risk_adapter": FakeClipRiskAdapter(),
        "similarity_adapter": FakeSimilarityAdapter(),
    }
    values.update(overrides)
    return AvatarQARuntime(**values)


def test_runtime_injectable_safe_set_can_hard_pass():
    result = build_actual_candidate_qa_signals(
        source_image=_image((10, 90, 120)),
        candidate_image=_image((140, 130, 100)),
        metadata={
            "pipelineMode": "flux",
            "traitQaMode": "enabled",
            "traitQaAuthority": "server",
        },
        source_traits=_traits(),
        candidate_traits=_traits(),
        runtime=_runtime(),
    )

    assert result.needs_review is False
    assert result.models_unavailable == ()
    assert result.signals["faceSimilarityReliable"] is True
    assert result.signals["faceSimilarityScore"] == 0.12


def test_canonical_azure_runtime_propagates_trait_na_without_review():
    result = build_actual_candidate_qa_signals(
        source_image=_image((10, 90, 120)),
        candidate_image=_image((140, 130, 100)),
        metadata={
            "provider": "azure",
            "generationBackend": "azure_gpt_image_2",
            "sourceInputMode": "storage_normalized_original_direct",
            "uploadNormalization": "existing_avatar_media_ingestion",
            "preGenerationTransform": "none",
            "pipelineMode": "azure_gpt_image_2",
            "legacyTraitExtraction": False,
            "legacyReferencePreprocessing": False,
            "legacyFlux": False,
            "traitQaMode": "disabled_by_pipeline",
            "traitQaAuthority": "server",
        },
        runtime=_runtime(),
    )

    assert result.needs_review is False
    assert result.signals["traitQaApplicability"] == "not_applicable"
    assert result.signals["traitQaAction"] == "allow"
    assert result.signals["traitReviewContribution"] is False


def test_runtime_debug_maps_local_safety_risk_to_clip_availability():
    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": _image((20, 100, 130)),
            "_qa_runtime": _runtime(),
        },
    )

    assert result.debug["modelAvailability"]["clip"] == "available"
    assert result.debug["modelAvailability"]["localSafetyRisk"] == "available"
    assert result.debug["modelAvailability"]["clipSafety"] == "available"
    assert result.debug["modelAvailability"]["visualRisk"] == "available"
    assert result.debug["signalContract"]["requiredSignalFailures"] == []


def test_runtime_debug_preserves_visual_risk_unavailable_and_typed_failure():
    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": _image((20, 100, 130)),
            "_qa_runtime": _runtime(visual_risk_adapter=FakeVisualAdapter(fail=True)),
        },
    )

    assert result.debug["modelAvailability"]["visualRisk"] == "unavailable"
    assert "visual_risk_unavailable" in result.debug["signalContract"]["requiredSignalFailures"]


def test_runtime_debug_separates_visual_risk_availability_from_semantic_status():
    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": _image((20, 100, 130)),
            "_qa_runtime": _runtime(
                visual_risk_adapter=FakeVisualAdapter(
                    VisualRiskAnalysis(
                        provider="fake-visual",
                        provider_available=True,
                        status="needs_review",
                        risk="review",
                        background_complexity="high",
                    )
                )
            ),
        },
    )

    assert result.debug["modelAvailability"]["visualRisk"] == "available"
    assert result.debug["visualRiskStatus"] == "needs_review"
    assert "visual_risk_unavailable" not in result.debug["signalContract"]["requiredSignalFailures"]


def test_calibrated_similarity_review_band_is_available_with_observed_score():
    runtime = _runtime(
        similarity_adapter=FakeSimilarityAdapter(
            FakeSimilarityResult(
                score=0.70,
                identity_decision="review_similarity",
                identity_reliable=False,
                needs_review=True,
                calibration_version="sim-cal-v1",
            )
        )
    )

    result = build_actual_candidate_qa_signals(
        source_image=_image((10, 90, 120)),
        candidate_image=_image((140, 130, 100)),
        metadata={
            "pipelineMode": "flux",
            "traitQaMode": "enabled",
            "traitQaAuthority": "server",
        },
        source_traits=_traits(),
        candidate_traits=_traits(),
        runtime=runtime,
    )

    assert result.model_availability["faceSimilarity"] == "available"
    assert result.signals["faceSimilarityObservedScore"] == 0.70
    assert result.signals["faceSimilarityDecision"] == "review_similarity"


def test_runtime_compares_source_visual_risk_when_calibration_requests_it():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        status="available",
        regions=(
            VisualRiskRegion(
                "text",
                (20, 50, 60, 62),
                confidence=0.96,
                raw_label="CAMPUS",
            ),
        ),
    )

    class RecordingVisualAdapter(FakeVisualAdapter):
        def __init__(self):
            super().__init__(visual)
            self.calls = 0

        def analyze(self, image, *, primary_face_bbox_xyxy=None):
            self.calls += 1
            return super().analyze(
                image,
                primary_face_bbox_xyxy=primary_face_bbox_xyxy,
            )

    adapter = RecordingVisualAdapter()
    runtime = _runtime(visual_risk_adapter=adapter)
    result = build_actual_candidate_qa_signals(
        source_image=_image((10, 90, 120)),
        candidate_image=_image((140, 130, 100)),
        metadata={"compareSourceVisualRisk": True},
        runtime=runtime,
    )

    assert adapter.calls == 2
    assert result.signals["watermarkDecisionClass"] == "source_consistent_clothing_text"
    assert result.signals["logoTextWatermarkDetected"] is False


def test_runtime_adapter_outage_requires_review_without_raw_markers():
    cases = [
        _runtime(face_detector=FakeFaceDetector(fail=True)),
        _runtime(visual_risk_adapter=FakeVisualAdapter(fail=True)),
        _runtime(local_risk_adapter=FakeClipRiskAdapter(fail=True)),
        _runtime(similarity_adapter=FakeSimilarityAdapter(fail=True)),
    ]

    for runtime in cases:
        result = build_actual_candidate_qa_signals(
            source_image=_image((10, 90, 120)),
            candidate_image=_image((140, 130, 100)),
            metadata={},
            source_traits={},
            candidate_traits={},
            runtime=runtime,
        )
        serialized = json.dumps(result.to_document(), sort_keys=True)

        assert result.needs_review is True
        assert result.models_unavailable
        assert "faceSimilarityScore" not in result.signals
        assert "private" not in serialized.lower()
        assert "raw" not in serialized.lower()
        assert "jane" not in serialized.lower()
        assert "embedding" not in serialized.lower()


def test_runtime_high_actual_signals_hard_reject_through_qa():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        status="available",
        risk="review",
        actions_required=(ACTION_NEUTRALIZE_TEXT_LOGO,),
        regions=(
            VisualRiskRegion(
                "logo",
                (2, 2, 18, 18),
                confidence=0.96,
                raw_label="BRAND",
            ),
            VisualRiskRegion(
                "logo",
                (178, 2, 198, 18),
                confidence=0.95,
                raw_label="BRAND",
            ),
        ),
        background_complexity="low",
    )
    runtime = _runtime(visual_risk_adapter=FakeVisualAdapter(visual))

    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": _image((20, 100, 130)),
            "_qa_runtime": runtime,
        },
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is False
    assert "logo_text_watermark" in result.rejectReasons
    serialized = str(result.to_document())
    assert result.debug["watermarkDecisionClass"] == "generated_overlay_logo"
    assert result.watermarkQaAction == "reject"
    assert "BRAND" not in serialized
    assert "bbox" not in serialized.lower()


def test_uncalibrated_similarity_needs_review_not_hard_reject_or_pass():
    runtime = _runtime(
        similarity_adapter=FakeSimilarityAdapter(
            FakeSimilarityResult(
                score=0.99,
                identity_decision="uncertain",
                identity_reliable=False,
                needs_review=True,
                calibration_version=None,
            )
        )
    )

    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": _image((20, 100, 130)),
            "_qa_runtime": runtime,
        },
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.rejectReasons == []
    assert result.faceSimilarityScore is None
    assert "too_identifiable" not in result.rejectReasons


def test_production_missing_analysis_reference_requires_review_without_decoded_source_fallback(
    monkeypatch,
):
    similarity = FakeSimilarityAdapter()
    monkeypatch.setenv("ENVIRONMENT", "production")

    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_qa_runtime": _runtime(similarity_adapter=similarity),
        },
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.reviewReasons == ["analysis_reference_image_unavailable"]
    assert similarity.source_images == []


def test_process_local_analysis_reference_is_used_and_not_serialized():
    reference = _image((240, 10, 10))
    source = _image((10, 90, 120))
    similarity = FakeSimilarityAdapter()

    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": source,
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": reference,
            "_qa_runtime": _runtime(similarity_adapter=similarity),
        },
    )
    encoded = json.dumps(result.to_document(), sort_keys=True)

    assert similarity.source_images
    assert similarity.source_images[0].getpixel((0, 0)) == reference.getpixel((0, 0))
    assert "_analysis_reference_image" not in encoded
    assert "_source_image" not in encoded
    assert "_candidate_image" not in encoded



def test_missing_face_similarity_reliability_flag_with_high_score_requires_review():
    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "qaSignals": {
                "adultLike": True,
                "brandFit": True,
                "cropConsistent": True,
                "cropIsolationQuality": "pass",
                "backgroundLeakageRisk": "low",
                "secondaryFaceLeakageRisk": "low",
                "textLogoWatermarkRisk": "low",
                "logoTextWatermarkRisk": "low",
                "uniqueMarkCopied": False,
                "faceSimilarityScore": 0.99,
                "childlikeScore": 0.1,
                "beautificationScore": 0.1,
            },
        },
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.faceSimilarityScore is None
    assert "too_identifiable" not in result.rejectReasons


def test_production_bridge_ignores_pass_like_supplied_signals_when_actual_runtime_fails(
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production_bridge")

    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": _image((20, 100, 130)),
            "_qa_runtime": _runtime(face_detector=FakeFaceDetector(fail=True)),
            "qaSignals": {
                "adultLike": True,
                "brandFit": True,
                "cropConsistent": True,
                "cropIsolationQuality": "pass",
                "backgroundLeakageRisk": "low",
                "secondaryFaceLeakageRisk": "low",
                "textLogoWatermarkRisk": "low",
                "logoTextWatermarkRisk": "low",
                "uniqueMarkCopied": False,
                "faceSimilarityReliable": True,
                "faceSimilarityScore": 0.1,
                "childlikeScore": 0.05,
                "beautificationScore": 0.05,
            },
        },
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.softPass is False
    assert result.qaVersion == "avatar_qa_v6_unique_mark_applicability_v1"
    assert "faceDetector_unavailable" in result.reviewReasons

def test_actual_hard_signal_reason_codes_are_specific():
    runtime = _runtime(
        local_risk_adapter=FakeClipRiskAdapter(
            ClipRiskResult(
                provider="clip",
                version="clip-v1",
                availability="available",
                available=True,
                childlike_score=0.05,
                sexualized_score=0.99,
                beautification_score=0.08,
                brand_mismatch_score=0.03,
                severe_artifact_score=0.99,
                adult_like_score=0.95,
                brand_fit_score=0.94,
                calibrated=True,
                calibration_version="clip-cal-v1",
                needs_review=True,
            )
        )
    )

    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": _image((20, 100, 130)),
            "_qa_runtime": runtime,
        },
    )

    assert "sexualized_or_nightlife" in result.rejectReasons
    assert "severe_artifact" in result.rejectReasons
    assert "not_adult_university_student_tone" not in result.rejectReasons
    assert "crop_expanded_to_unseen_body" not in result.rejectReasons


def test_metadata_models_unavailable_preserves_actual_hard_reject():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        status="available",
        risk="review",
        actions_required=(ACTION_NEUTRALIZE_TEXT_LOGO,),
        regions=(
            VisualRiskRegion(
                "logo",
                (2, 2, 18, 18),
                confidence=0.96,
                raw_label="BRAND",
            ),
            VisualRiskRegion(
                "logo",
                (178, 2, 198, 18),
                confidence=0.95,
                raw_label="BRAND",
            ),
        ),
        background_complexity="low",
    )

    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "_analysis_reference_image": _image((20, 100, 130)),
            "_qa_runtime": _runtime(visual_risk_adapter=FakeVisualAdapter(visual)),
            "modelsUnavailable": True,
        },
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is False
    assert "logo_text_watermark" in result.rejectReasons
    assert result.qaVersion == "avatar_qa_v6_unique_mark_applicability_v1"
    assert result.debug["qaVersion"] == "avatar_qa_v6_unique_mark_applicability_v1"

def test_default_cache_contains_adapters_only_not_user_data():
    runtime = get_default_qa_runtime()
    visual = get_default_visual_risk_adapter()
    cache = runtime.cache_snapshot()

    assert runtime.visual_risk_adapter is visual
    assert set(cache) == {
        "faceDetector",
        "visualRiskAdapter",
        "localRiskAdapter",
        "similarityAdapter",
    }
    assert all(not isinstance(value, Image.Image) for value in cache.values())


def test_default_runtime_resolves_immutable_local_qa_model_artifact_paths(monkeypatch):
    import avatar_generation.qa_runtime as qa_runtime

    calls = {}

    class FakeVisual:
        provider = "florence2"

        def __init__(self, model_id, *, local_files_only):
            calls["visual"] = (model_id, local_files_only)

    class FakeClip:
        provider = "clip"

        def __init__(self, model_id, *, local_files_only):
            calls["clip"] = (model_id, local_files_only)

    class FakeEncoder:
        provider = "clip"
        version = "fake"

        def __init__(self, model_id, *, local_files_only):
            calls["similarity"] = (model_id, local_files_only)

    monkeypatch.setenv("AVATAR_QA_VISUAL_RISK_MODEL_ID", "/app/models/qa/florence2")
    monkeypatch.setenv("AVATAR_CLIP_RISK_MODEL_ID", "/app/models/qa/clip-large")
    monkeypatch.setenv("AVATAR_QA_SIMILARITY_MODEL_ID", "/app/models/qa/clip-base")
    monkeypatch.setattr(qa_runtime, "Florence2VisualRiskAdapter", FakeVisual)
    monkeypatch.setattr(qa_runtime, "LocalClipRiskScorer", FakeClip)
    monkeypatch.setattr(qa_runtime, "ImageSimilarityAdapter", FakeEncoder)
    monkeypatch.setattr(qa_runtime, "_DEFAULT_VISUAL_RISK_ADAPTER", None)
    monkeypatch.setattr(qa_runtime, "_DEFAULT_CLIP_RISK_SCORER", None)
    monkeypatch.setattr(qa_runtime, "_DEFAULT_SIMILARITY_ADAPTER", None)

    get_default_visual_risk_adapter()
    get_default_clip_risk_scorer()
    get_default_similarity_adapter()

    assert calls == {
        "visual": ("/app/models/qa/florence2", True),
        "clip": ("/app/models/qa/clip-large", True),
        "similarity": ("/app/models/qa/clip-base", True),
    }
