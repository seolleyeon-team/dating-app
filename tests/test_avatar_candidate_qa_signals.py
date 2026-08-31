import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.schema import FaceDetection, FaceDetectorResult  # noqa: E402
from avatar_generation.analysis.visual_risk import (  # noqa: E402
    ACTION_NEUTRALIZE_BACKGROUND_PERSON,
    ACTION_NEUTRALIZE_TEXT_LOGO,
    ACTION_REVIEW_BACKGROUND_COMPLEXITY,
    STATUS_CRITICAL_UNAVAILABLE,
    VisualRiskAnalysis,
    VisualRiskRegion,
)
from avatar_generation.model_adapters.clip_risk import ClipRiskResult  # noqa: E402
from avatar_generation.qa import build_avatar_qa_from_signals  # noqa: E402
from avatar_generation.qa_contract import required_signal_failure_codes  # noqa: E402
from avatar_generation import qa_signals  # noqa: E402
from avatar_generation.qa_signals import (  # noqa: E402
    CandidateQASignalResult,
    LocalSafetyRiskResult,
    build_candidate_qa_signals,
)


def _image(color=(180, 160, 140)):
    return Image.new("RGB", (80, 80), color)


def _face(confidence=0.95):
    return FaceDetection(bbox=(0.25, 0.2, 0.5, 0.55), confidence=confidence)


def _traits(**overrides):
    values = {
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
    values.update(overrides)
    return values


class FakeFaceDetector:
    def __init__(self, faces, *, availability=None, provider="fake-face"):
        self.faces = faces
        self.calls = 0
        self.availability = availability or {"faceDetector": "available"}
        self.provider = provider

    def detect(self, image):
        self.calls += 1
        return FaceDetectorResult(
            provider=self.provider,
            provider_version="face-v1",
            image_width=image.width,
            image_height=image.height,
            faces=tuple(self.faces),
            model_availability=self.availability,
        )


class FailingFaceDetector:
    def detect(self, image):
        raise RuntimeError("private face path")


class FakeVisualRiskAdapter:
    provider = "fake-visual"

    def __init__(self, analysis):
        self.analysis = analysis
        self.calls = 0

    def analyze(self, image, *, primary_face_bbox_xyxy=None):
        self.calls += 1
        return self.analysis


class FailingVisualRiskAdapter:
    def analyze(self, image, *, primary_face_bbox_xyxy=None):
        raise ValueError("raw OCR Jane School")


class FakeLocalRiskAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def analyze(self, image):
        self.calls += 1
        return self.result


class FailingLocalRiskAdapter:
    def analyze(self, image):
        raise OSError("clip cache path")


@dataclass(frozen=True)
class FakeSimilarityResult:
    available: bool = True
    score: float | None = 0.2
    identity_decision: str = "low_similarity_risk"
    identity_reliable: bool = True
    needs_review: bool = False
    calibration_version: str | None = "sim-cal-v1"
    provider: str = "fake-sim"
    availability_reason: str | None = None


class FakeSimilarityAdapter:
    def __init__(self, result=None, *, fail=False):
        self.result = result or FakeSimilarityResult()
        self.calls = 0
        self.fail = fail

    def compare(self, source_crop, candidate_crop, *, calibration_policy=None):
        self.calls += 1
        if self.fail:
            raise LookupError("embedding raw prompt")
        assert source_crop.size[0] > 0
        assert candidate_crop.size[1] > 0
        return self.result


def _visual_pass():
    return VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        risk="pass",
        status="available",
        detector_availability={"ocr": "available", "od": "available"},
        background_complexity="low",
    )


def _clip_result(
    *,
    available=True,
    calibrated=True,
    childlike_score=0.05,
    sexualized_score=0.02,
    beautification_score=0.08,
    severe_artifact_score=0.1,
    adult_like_score=0.92,
    brand_fit_score=0.91,
    needs_review=False,
):
    return ClipRiskResult(
        provider="clip",
        version="clip-test-v1",
        availability="available" if available else "unavailable",
        available=available,
        childlike_score=childlike_score,
        sexualized_score=sexualized_score,
        beautification_score=beautification_score,
        brand_mismatch_score=None,
        severe_artifact_score=severe_artifact_score,
        adult_like_score=adult_like_score,
        brand_fit_score=brand_fit_score,
        calibrated=calibrated,
        calibration_version="clip-cal-v1" if calibrated else None,
        needs_review=needs_review,
        availability_reason=None if available else "unavailable",
    )


def _build(
    *,
    face_detector=None,
    faces=None,
    visual_adapter=None,
    visual=None,
    local_risk_adapter=None,
    local_risk=None,
    similarity_adapter=None,
    similarity=None,
    source_traits=None,
    candidate_traits=None,
    allow_similarity=True,
    source_analysis=None,
    reference_preprocess=None,
    source_visual=None,
):
    active_similarity = similarity_adapter or FakeSimilarityAdapter(similarity)
    result = build_candidate_qa_signals(
        source_image=_image(),
        candidate_image=_image((130, 170, 190)),
        source_analysis=source_analysis or {},
        reference_preprocess=reference_preprocess or {},
        source_traits=source_traits if source_traits is not None else _traits(),
        candidate_traits=candidate_traits if candidate_traits is not None else _traits(),
        source_primary_bbox=(0.25, 0.2, 0.5, 0.55),
        face_detector=face_detector or FakeFaceDetector(tuple(faces if faces is not None else [_face()])),
        visual_risk_adapter=visual_adapter or FakeVisualRiskAdapter(visual or _visual_pass()),
        local_risk_adapter=local_risk_adapter or FakeLocalRiskAdapter(local_risk or _clip_result()),
        similarity_adapter=active_similarity,
        allow_similarity=allow_similarity,
        source_visual_risk=source_visual,
        trait_qa_context={
            "pipelineMode": "flux",
            "traitQaMode": "enabled",
            "traitQaAuthority": "server",
        },
    )
    return result, active_similarity


def test_safe_hard_pass_capable_signal_set_accepts_callable_clip_risk_result():
    def classifier(image):
        return _clip_result()

    result, similarity = _build(local_risk_adapter=classifier)

    assert isinstance(result, CandidateQASignalResult)
    assert result.needs_review is False
    assert result.models_unavailable == ()
    assert result.skipped_heavy_reason is None
    assert similarity.calls == 1
    assert result.signals["adultLike"] is True
    assert result.signals["brandFit"] is True
    assert result.signals["cropConsistent"] is True
    assert result.signals["faceSimilarityReliable"] is True
    assert result.signals["faceSimilarityScore"] == 0.2
    assert result.signals["sexualizedScore"] == 0.02
    assert result.signals["severeArtifactScore"] == 0.1
    assert result.signals["brandMismatchScore"] is None
    assert result.model_availability["localSafetyRisk.calibrationVersion"] == "clip-cal-v1"
    assert result.model_availability["localSafetyRisk.needsReview"] == "false"
    assert build_avatar_qa_from_signals(
        result.signals,
        pipeline_contract={
            "uniqueMarkQaMode": "disabled_by_pipeline",
            "uniqueMarkQaAuthority": "server",
        },
    ).previewAllowed is True


def test_two_candidate_faces_sets_hard_issue_and_skips_heavy_similarity():
    result, similarity = _build(faces=[_face(), _face(0.8)])

    assert result.signals["multipleFacesGenerated"] is True
    assert result.signals["secondaryFaceLeakageRisk"] == "high"
    assert result.skipped_heavy_reason == "hard_lightweight_issue"
    assert similarity.calls == 0
    assert "multiple_faces_generated" in build_avatar_qa_from_signals(result.signals).rejectReasons


def test_zero_candidate_faces_sets_no_face_hard_issue_and_skips_similarity():
    result, similarity = _build(faces=[])

    assert result.signals["noFaceDetected"] is True
    assert result.signals["cropConsistent"] is False
    assert result.signals["cropIsolationQuality"] == "fail"
    assert result.skipped_heavy_reason == "hard_lightweight_issue"
    assert similarity.calls == 0


def test_deterministic_fallback_face_detector_is_model_unavailable():
    result, similarity = _build(
        face_detector=FakeFaceDetector([], provider="deterministic_fallback")
    )

    assert result.needs_review is True
    assert result.models_unavailable == ("faceDetector",)
    assert result.model_availability["faceDetector"] == "unavailable"
    assert "noFaceDetected" not in result.signals
    assert result.signals["cropIsolationQuality"] == "needs_review"
    assert result.skipped_heavy_reason == "critical_model_unavailable"
    assert similarity.calls == 0


def test_ocr_or_background_person_sets_hard_issue_and_skips_heavy_similarity():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        risk="review",
        actions_required=(
            ACTION_NEUTRALIZE_TEXT_LOGO,
            ACTION_NEUTRALIZE_BACKGROUND_PERSON,
        ),
        regions=(
            VisualRiskRegion(
                "logo",
                (1, 2, 15, 16),
                confidence=0.96,
                raw_label="BRAND",
            ),
            VisualRiskRegion("background-person", (10, 10, 30, 60)),
        ),
        background_complexity="medium",
    )

    result, similarity = _build(visual=visual)

    assert result.signals["logoTextWatermarkDetected"] is False
    assert result.signals["watermarkDecisionClass"] == "benign_text_or_logo"
    assert result.signals["watermarkQaAction"] == "allow"
    assert result.signals["secondaryPersonGenerated"] is True
    assert result.signals["textLogoWatermarkRisk"] == "low"
    assert result.signals["backgroundLeakageRisk"] == "high"
    assert result.skipped_heavy_reason == "hard_lightweight_issue"
    assert similarity.calls == 0


def test_source_consistent_clothing_text_does_not_skip_heavy_similarity():
    source_visual = VisualRiskAnalysis(
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
    candidate_visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        status="available",
        regions=(
            VisualRiskRegion(
                "text",
                (21, 51, 61, 63),
                confidence=0.96,
                raw_label="CAMPUS",
            ),
        ),
    )

    result, similarity = _build(
        visual=candidate_visual,
        source_visual=source_visual,
    )

    assert result.signals["logoTextWatermarkDetected"] is False
    assert result.signals["textLogoWatermarkRisk"] == "low"
    assert result.skipped_heavy_reason is None
    assert similarity.calls == 1


def test_visual_high_background_complexity_is_diagnostic_not_background_leakage():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        risk="review",
        actions_required=(),
        regions=(),
        background_complexity="high",
    )

    result, similarity = _build(visual=visual)

    assert result.signals["backgroundLeakageRisk"] == "low"
    assert result.signals["backgroundComplexityNeedsReview"] is True
    assert similarity.calls == 1


@pytest.mark.parametrize(
    ("provider_available", "status"),
    [
        (True, "available"),
        (True, "needs_review"),
        (True, "reject"),
    ],
)
def test_visual_risk_availability_does_not_leak_semantic_status(provider_available, status):
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=provider_available,
        status=status,
        risk="review" if status == "needs_review" else "pass",
    )

    result, _ = _build(visual=visual)

    assert result.model_availability["visualRisk"] == "available"
    assert result.signals["visualRiskStatus"] == status
    assert result.signals["watermarkQaAction"] == "allow"
    assert result.signals["textLogoWatermarkRisk"] == "low"
    assert result.needs_review is False
    assert "visual_risk_unavailable" not in required_signal_failure_codes(
        result.model_availability
    )


def test_unavailable_visual_risk_fails_closed_even_with_stale_review_status():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=False,
        status="needs_review",
        risk="pass",
    )

    result, _ = _build(visual=visual)

    assert result.model_availability["visualRisk"] == "unavailable"
    assert result.signals["visualRiskStatus"] == "needs_review"
    assert result.signals["watermarkQaAction"] == "review"
    assert result.signals["textLogoWatermarkRisk"] == "medium"
    assert result.models_unavailable == ("visualRisk",)
    assert "visual_risk_unavailable" in required_signal_failure_codes(
        result.model_availability
    )


def test_critical_adapter_outage_requires_review_without_fake_scores():
    result, similarity = _build(
        visual=VisualRiskAnalysis(
            provider="fake-visual",
            provider_available=False,
            status=STATUS_CRITICAL_UNAVAILABLE,
            risk="block",
            detector_availability={"ocr": STATUS_CRITICAL_UNAVAILABLE},
            error_code="private/raw/path/removed",
        )
    )

    assert result.needs_review is True
    assert result.models_unavailable == ("visualRisk",)
    assert result.signals["watermarkQaAction"] == "review"
    assert result.signals["textLogoWatermarkRisk"] == "medium"
    assert "faceSimilarityScore" not in result.signals
    assert result.skipped_heavy_reason == "critical_model_unavailable"
    assert similarity.calls == 0


def test_each_adapter_exception_is_sanitized_unavailable_and_does_not_propagate():
    cases = [
        ("faceDetector", {"face_detector": FailingFaceDetector()}),
        ("visualRisk", {"visual_adapter": FailingVisualRiskAdapter()}),
        ("localSafetyRisk", {"local_risk_adapter": FailingLocalRiskAdapter()}),
        ("faceSimilarity", {"similarity_adapter": FakeSimilarityAdapter(fail=True)}),
    ]

    for unavailable_key, kwargs in cases:
        result, _ = _build(**kwargs)
        serialized = repr(result.to_document())
        assert unavailable_key in result.models_unavailable
        assert result.needs_review is True
        assert result.signals.get("faceSimilarityScore") is None
        if unavailable_key == "faceSimilarity":
            assert result.signals["faceSimilarityReliable"] is False
        assert "private" not in serialized
        assert "Jane" not in serialized
        assert "raw prompt" not in serialized
        assert "cache path" not in serialized


def test_uncalibrated_similarity_requires_review_and_does_not_fake_pass():
    result, similarity = _build(
        similarity=FakeSimilarityResult(
            score=0.99,
            identity_decision="uncertain",
            identity_reliable=False,
            needs_review=True,
            calibration_version=None,
        )
    )

    assert similarity.calls == 1
    assert result.needs_review is True
    assert "faceSimilarityScore" not in result.signals
    assert result.signals["faceSimilarityReliable"] is False
    assert result.signals["faceSimilarityNeedsReview"] is True
    assert result.model_availability["faceSimilarity"] == "uncalibrated"



def test_clip_risk_result_emits_additional_scores_and_needs_review_metadata():
    result, _ = _build(
        local_risk=_clip_result(
            sexualized_score=0.34,
            beautification_score=0.45,
            severe_artifact_score=0.56,
            needs_review=True,
        )
    )

    assert result.needs_review is True
    assert result.signals["sexualizedScore"] == 0.34
    assert result.signals["beautificationScore"] == 0.45
    assert result.signals["severeArtifactScore"] == 0.56
    assert result.signals["brandMismatchScore"] is None
    assert result.model_availability["localSafetyRisk.calibrationVersion"] == "clip-cal-v1"
    assert result.model_availability["localSafetyRisk.needsReview"] == "true"

def test_uncalibrated_local_clip_risk_sets_models_unavailable_for_qa():
    result, similarity = _build(local_risk=_clip_result(calibrated=False))

    assert result.needs_review is True
    assert result.models_unavailable == ("localSafetyRisk",)
    assert result.model_availability["localSafetyRisk"] == "uncalibrated"
    assert result.signals["adultLike"] is None
    assert result.signals["brandFit"] is None
    assert result.skipped_heavy_reason == "critical_model_unavailable"
    assert similarity.calls == 0


def test_blurred_image_quality_sets_severe_artifact(monkeypatch):
    class FakeQuality:
        lighting_band = "balanced"
        blur_band = "blurred"
        overexposure_band = "none"
        crop_border_band = "none"

    monkeypatch.setattr(qa_signals, "analyze_image_quality", lambda image: FakeQuality())

    result, similarity = _build()

    assert result.signals["severeArtifactDetected"] is True
    assert result.signals["cropIsolationQuality"] == "fail"
    assert result.skipped_heavy_reason == "hard_lightweight_issue"
    assert similarity.calls == 0


def test_trait_schema_mismatch_reviews_without_hard_lightweight_skip():
    mismatch, _ = _build(
        source_traits=_traits(
            hair_color_range="black",
            eyewear_present=True,
            eyewear_style="round",
            eyewear_style_confidence=0.95,
        ),
        candidate_traits=_traits(
            hair_color_range="blonde",
            eyewear_present=False,
        ),
    )

    assert mismatch.trait_matches["hair_color_range"] == "mismatch"
    assert mismatch.trait_matches["eyewear_present"] == "mismatch"
    assert mismatch.signals["hardTraitContradiction"] is True
    assert mismatch.signals["traitQaApplicability"] == "available"
    assert mismatch.signals["traitQaAction"] == "review"
    assert mismatch.skipped_heavy_reason is None
    assert mismatch.needs_review is True

    missing, similarity = _build(candidate_traits={})
    assert missing.needs_review is True
    assert "hardTraitContradiction" not in missing.signals
    assert all(status == "review" for status in missing.trait_matches.values())
    assert similarity.calls == 1


def test_onboarding_gender_contract_is_not_image_inferred_and_not_signal():
    result, _ = _build(source_traits={**_traits(), "gender": "female"})

    assert result.trait_matches["onboardingGenderContract"] == "not_image_inferred"
    assert "gender" not in result.signals
    assert "gender" not in repr(result.to_document())


def test_sanitized_output_excludes_private_fields_but_keeps_coarse_text_logo_risk():
    result, _ = _build(
        source_analysis={
            "sourceRef": "gs://private/source.png",
            "rawPrompt": "draw Jane",
            "primaryFaceBbox": [1, 2, 3, 4],
            "modelAvailability": {"sourceFace": "available"},
        },
        reference_preprocess={
            "referenceRef": "signed-url",
            "ocrText": "PRIVATE SCHOOL",
            "labels": ["Acme logo"],
            "embedding": [1, 2, 3],
            "stage": "preprocessed",
        },
    )

    doc = result.to_document()
    serialized = repr(result) + repr(doc)
    assert doc["signals"]["textLogoWatermarkRisk"] == "low"
    assert "visualRegionCounts" in doc["signals"]
    assert "visualActionsRequired" in doc["signals"]
    for fragment in [
        "gs://",
        "signed-url",
        "draw Jane",
        "PRIVATE",
        "Acme",
        "bbox",
        "Bbox",
        "embedding",
        "gender",
        "pixel",
    ]:
        assert fragment not in serialized
    assert doc["stage"] == "candidate_qa_signals"


def test_metadata_flags_alone_cannot_claim_candidate_safe_without_actual_signals():
    result, _ = _build(
        local_risk=LocalSafetyRiskResult(
            provider="fake-clip-risk",
            available=False,
            calibrated=False,
            availability_reason="unavailable",
        ),
        source_analysis={"hardReject": False, "status": "pass"},
        reference_preprocess={"status": "pass"},
    )

    assert result.needs_review is True
    assert result.models_unavailable == ("localSafetyRisk",)
    assert result.signals["adultLike"] is None
    assert result.signals["brandFit"] is None
    assert "faceSimilarityScore" not in result.signals


def _text_review_visual(*, region_count=1, complexity="medium"):
    regions = tuple(
        VisualRiskRegion(
            "text",
            (20 + index * 12, 50, 60 + index * 12, 62),
            confidence=0.4,
            raw_label="redacted_text",
        )
        for index in range(region_count)
    )
    actions = [ACTION_NEUTRALIZE_TEXT_LOGO]
    if complexity == "high":
        actions.append(ACTION_REVIEW_BACKGROUND_COMPLEXITY)
    return VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        risk="review",
        status="needs_review",
        actions_required=tuple(actions),
        regions=regions,
        background_complexity=complexity,
    )


def test_text_only_visual_region_does_not_count_as_background_leakage():
    result, _ = _build(visual=_text_review_visual())

    assert result.signals["backgroundLeakageRisk"] == "low"
    assert "backgroundComplexityNeedsReview" not in result.signals
    assert result.signals["textLogoWatermarkRisk"] == "low"
    assert result.signals["watermarkDecisionClass"] == "ambiguous_text_evidence"
    assert result.signals["watermarkEvidenceClasses"] == ["ambiguous_text_evidence"]
    assert result.signals["watermarkEvidence"] == {
        "schemaVersion": "watermark_evidence_v2_token_quality_derived_v1",
        "areaBands": {"medium": 1},
        "sourceConsistency": "not_available",
        "confidenceBands": {"low": 1},
        "locationBands": {"clothing_zone": 1},
        "textQualityBands": {"plausible": 1},
        "recognizedTokenCount": 1,
        "repeatedTokenCount": 0,
        "ocrDetectionCount": 1,
        "regionEvidence": [
            {
                "kind": "text",
                "confidenceBand": "low",
                "areaBand": "medium",
                "location": "clothing_zone",
                "overlayLike": False,
                "textQuality": "plausible",
                "sourceConsistent": None,
                "repeated": False,
                "artifactHint": False,
            }
        ],
    }


def test_multiple_text_regions_keep_complexity_review_separate_from_leakage():
    result, _ = _build(visual=_text_review_visual(region_count=3, complexity="high"))

    assert result.signals["backgroundLeakageRisk"] == "low"
    assert result.signals["backgroundComplexityNeedsReview"] is True
    assert result.signals["textLogoWatermarkRisk"] == "low"
    assert result.signals["watermarkDecisionClass"] == "ambiguous_text_evidence"
    assert result.signals["watermarkEvidence"]["ocrDetectionCount"] == 3


def test_background_person_remains_high_background_leakage_and_hard_reject():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        risk="review",
        status="needs_review",
        actions_required=(ACTION_NEUTRALIZE_BACKGROUND_PERSON,),
        regions=(VisualRiskRegion("background-person", (10, 10, 30, 60)),),
        background_complexity="medium",
    )

    result, _ = _build(visual=visual)
    qa = build_avatar_qa_from_signals(result.signals)

    assert result.signals["backgroundLeakageRisk"] == "high"
    assert result.signals["secondaryPersonGenerated"] is True
    assert result.signals["secondaryFaceLeakageRisk"] == "high"
    assert set(qa.rejectReasons) == {
        "background_leakage",
        "secondary_face_leakage",
        "secondary_person_generated",
    }
    assert qa.previewAllowed is False
    assert qa.requiresHumanReview is False


def test_clean_background_remains_low_without_complexity_review():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        risk="pass",
        status="available",
        regions=(),
        actions_required=(),
        background_complexity="low",
    )

    result, _ = _build(visual=visual)

    assert result.signals["backgroundLeakageRisk"] == "low"
    assert "backgroundComplexityNeedsReview" not in result.signals
    assert result.signals["textLogoWatermarkRisk"] == "low"
    assert result.signals["watermarkDecisionClass"] == "no_text_detected"
    assert result.signals["watermarkEvidence"]["ocrDetectionCount"] == 0


@pytest.mark.parametrize("unavailable_mode", ["typed", "exception"])
def test_visual_unavailable_background_risk_remains_fail_closed(unavailable_mode):
    if unavailable_mode == "typed":
        visual = VisualRiskAnalysis(
            provider="fake-visual",
            provider_available=False,
            status=STATUS_CRITICAL_UNAVAILABLE,
            risk="block",
        )
        result, _ = _build(visual=visual)
    else:
        result, _ = _build(visual_adapter=FailingVisualRiskAdapter())

    assert result.signals["backgroundLeakageRisk"] == "medium"
    assert result.needs_review is True
    assert "visualRisk" in result.models_unavailable


def test_missing_background_signal_remains_fail_closed_at_qa_mapper():
    result = build_avatar_qa_from_signals({})

    assert result.backgroundLeakageRisk == "medium"
    assert result.previewAllowed is False
    assert result.requiresHumanReview is True


def test_high_visual_complexity_without_leakage_is_diagnostic_only():
    visual = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        risk="review",
        status="needs_review",
        actions_required=(ACTION_REVIEW_BACKGROUND_COMPLEXITY,),
        regions=(),
        background_complexity="high",
    )

    result, _ = _build(visual=visual)

    assert result.signals["backgroundLeakageRisk"] == "low"
    assert result.signals["backgroundComplexityNeedsReview"] is True
    assert result.signals["textLogoWatermarkRisk"] == "low"
    assert result.signals["watermarkDecisionClass"] == "no_text_detected"
