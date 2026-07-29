import json
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.worker as worker_module
from avatar_generation.analysis.visual_risk import (
    VisualRiskAnalysis,
    VisualRiskRegion,
    unavailable_visual_risk_analysis,
)
from avatar_generation.qa import AvatarQAResult
from avatar_generation.trait_card import validate_trait_card_response
from avatar_generation.worker import process_avatar_generation_payload
from tests.test_avatar_generation_worker import (
    _fake_firestore,
    _fake_storage,
    _payload,
    _passing_qa,
)


@pytest.fixture(autouse=True)
def _isolate_worker_environment(monkeypatch):
    for name in (
        "ENVIRONMENT",
        "AVATAR_DATA_PROJECT",
        "FIRESTORE_PROJECT",
        "GCP_PROJECT",
        "SOURCE_PHOTO_BUCKET",
        "AVATAR_TEMP_BUCKET",
        "APPROVED_AVATAR_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    worker_module._TRAIT_ADAPTER_CACHE.clear()
    worker_module._FLUX_GENERATOR_CACHE.clear()


class AcceptedSourceAnalysis:
    hard_reject = False
    broad_trait_hints = {}
    primary_face = types.SimpleNamespace(bbox=(0.25, 0.20, 0.40, 0.45), confidence=0.95)
    primary_face_bbox = (0.25, 0.20, 0.40, 0.45)

    def to_document(self):
        return {
            "status": "accepted",
            "hardReject": False,
            "rejectReasons": [],
            "backgroundNeutralizationRequired": False,
        }


class FakeGenerator:
    calls = []

    def __init__(self, _model_id):
        pass

    def generate(self, *, source_image, prompt, avoid_prompt, seed):
        self.calls.append(source_image.copy())
        return Image.new("RGB", (24, 24), color=(seed % 255, 90, 130))


def _trait_response(**overrides):
    card = {
        "visible_crop": "head_and_shoulders",
        "hair_color_range": "unclear",
        "clothing_color": "unclear",
        "eyewear_present": "no",
        "eyewear_style": "none",
        "eyewear_confidence": "high",
        "eyewear_source": "florence",
        "facial_hair_present": "no",
        "facial_hair_style": "none",
        "clothing_category": "shirt",
        "avatar_presentation_gender": "male",
    }
    card.update(overrides)
    return validate_trait_card_response(
        json.dumps(
            {
                "schemaVersion": "seolleyeon_avatar_trait_card_v3",
                "privacySafe": True,
                "confidence": 0.93,
                "traitCard": card,
            }
        )
    )


def test_visual_regions_reach_preprocess_but_not_persistence(monkeypatch):
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "true")
    monkeypatch.setenv("AVATAR_SOURCE_VISUAL_RISK_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "false")
    captured = []
    original_preprocess = worker_module.preprocess_reference_image

    class VisualAdapter:
        def analyze(self, image, *, primary_face_bbox_xyxy=None):
            captured.append(primary_face_bbox_xyxy)
            return VisualRiskAnalysis(
                provider="fake",
                provider_available=True,
                regions=(VisualRiskRegion("text", (2, 3, 12, 14)),),
                risk="review",
                actions_required=("neutralize_text_logo",),
            )

    def recording_preprocess(*args, **kwargs):
        captured.append(tuple(kwargs.get("visual_risk_regions") or ()))
        return original_preprocess(*args, **kwargs)

    monkeypatch.setattr(worker_module, "analyze_avatar_source_image", lambda *_a, **_k: AcceptedSourceAnalysis())
    monkeypatch.setattr(worker_module, "preprocess_reference_image", recording_preprocess)
    monkeypatch.setattr(worker_module, "Flux2KleinImageGenerator", FakeGenerator)

    payload = _payload(job_id="avatar_quality_visual_regions")
    fs = _fake_firestore(payload)
    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="flux",
        source_visual_risk_adapter=VisualAdapter(),
    )

    assert result.status == "preview_ready"
    assert captured[0] == (8.0, 6.4, 20.8, 20.8)
    assert captured[1] and captured[1][0].bbox == (2, 3, 12, 14)
    persisted = json.dumps(fs.data["avatarJobs"][payload["jobId"]], default=str)
    assert "visualRisk" in fs.data["avatarJobs"][payload["jobId"]]["sourceAnalysis"]
    assert "primaryfacebbox" not in persisted.lower()
    assert "bbox" not in persisted
    assert "neutralize_text_logo" in persisted


def test_visual_outage_in_production_bridge_needs_review_without_generation(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production_bridge")
    monkeypatch.setenv("AVATAR_DATA_PROJECT", "seolleyeon-festival")
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "false")
    FakeGenerator.calls = []

    class OutageAdapter:
        def analyze(self, image, *, primary_face_bbox_xyxy=None):
            return unavailable_visual_risk_analysis("fake", error_code="fake_unavailable")

    monkeypatch.setattr(worker_module, "analyze_avatar_source_image", lambda *_a, **_k: AcceptedSourceAnalysis())
    monkeypatch.setattr(worker_module, "Flux2KleinImageGenerator", FakeGenerator)
    payload = _payload(job_id="avatar_quality_visual_outage")
    fs = _fake_firestore(payload)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="flux",
        firestore_project="seolleyeon-festival",
        source_visual_risk_adapter=OutageAdapter(),
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert result.status == "needs_review"
    assert result.candidate_ids == []
    assert not FakeGenerator.calls
    assert job["errorCode"] == "avatar_source_visual_risk_model_unavailable"
    assert fs.data["avatarCandidates"] == {}



def test_visual_adapter_exception_in_production_bridge_needs_review_without_generation(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production_bridge")
    monkeypatch.setenv("AVATAR_DATA_PROJECT", "seolleyeon-festival")
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "false")
    FakeGenerator.calls = []

    class RaisingAdapter:
        provider = "raising_visual"

        def analyze(self, image, *, primary_face_bbox_xyxy=None):
            raise RuntimeError("visual model unavailable: /sensitive/path")

    monkeypatch.setattr(worker_module, "analyze_avatar_source_image", lambda *_a, **_k: AcceptedSourceAnalysis())
    monkeypatch.setattr(worker_module, "Flux2KleinImageGenerator", FakeGenerator)
    payload = _payload(job_id="avatar_quality_visual_exception")
    fs = _fake_firestore(payload)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="flux",
        firestore_project="seolleyeon-festival",
        source_visual_risk_adapter=RaisingAdapter(),
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    visual_risk = job["sourceAnalysis"]["visualRisk"]
    assert result.status == "needs_review"
    assert result.candidate_ids == []
    assert not FakeGenerator.calls
    assert fs.data["avatarCandidates"] == {}
    assert job["errorCode"] == "avatar_source_visual_risk_model_unavailable"
    assert visual_risk["provider"] == "raising_visual"
    assert visual_risk["errorCode"] == "source_visual_risk_adapter_unavailable"
    assert "/sensitive/path" not in json.dumps(job, default=str)


def test_generation_reference_for_flux_analysis_reference_for_trait_and_qa(monkeypatch):
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_USE_PRIVACY_REFERENCE", "false")
    worker_module._TRAIT_ADAPTER_CACHE.clear()
    FakeGenerator.calls = []
    trait_pixels = []
    qa_metadata = []

    class TraitAdapter:
        def __init__(self, **_kwargs):
            pass

        def extract_traits(self, *, image, avatar_presentation_gender):
            trait_pixels.append(image.getpixel((0, 0)))
            return _trait_response(avatar_presentation_gender=avatar_presentation_gender)

    def qa_runner(source_ref, candidate_ref, metadata):
        qa_metadata.append(metadata)
        return _passing_qa(source_ref, candidate_ref, metadata)

    monkeypatch.setattr(worker_module, "analyze_avatar_source_image", lambda *_a, **_k: AcceptedSourceAnalysis())
    monkeypatch.setattr(worker_module, "Florence2TraitExtractionAdapter", TraitAdapter)
    monkeypatch.setattr(worker_module, "Flux2KleinImageGenerator", FakeGenerator)
    payload = _payload(job_id="avatar_quality_reference_split")
    fs = _fake_firestore(payload)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=qa_runner,
        mode="flux",
    )

    assert result.status == "preview_ready"
    expected = (247, 242, 236)
    assert all(abs(a - b) <= 5 for a, b in zip(FakeGenerator.calls[0].getpixel((0, 0)), expected))
    assert all(abs(a - b) <= 5 for a, b in zip(trait_pixels[0], expected))
    assert all(abs(a - b) <= 5 for a, b in zip(qa_metadata[0]["_source_image"].getpixel((0, 0)), expected))
    assert all(abs(a - b) <= 5 for a, b in zip(qa_metadata[0]["_analysis_reference_image"].getpixel((0, 0)), expected))
    persisted = json.dumps(fs.data["avatarJobs"][payload["jobId"]], default=str)
    persisted += json.dumps(fs.data["avatarCandidates"], default=str)
    assert "_analysis_reference_image" not in persisted



def test_extra_round_qa_receives_analysis_reference(monkeypatch):
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "false")
    monkeypatch.setenv("AVATAR_INITIAL_CANDIDATE_COUNT", "4")
    monkeypatch.setenv("AVATAR_EXTRA_CANDIDATE_COUNT", "4")
    monkeypatch.setenv("AVATAR_MAX_TOTAL_CANDIDATES", "8")
    FakeGenerator.calls = []
    qa_metadata = []

    def rejecting_qa(_source_ref, _candidate_ref, metadata):
        qa_metadata.append(metadata)
        return AvatarQAResult(
            adultQa="pass",
            privacyQa="fail",
            brandQa="pass",
            cropConsistency="pass",
            previewAllowed=False,
            qaVersion="test_reject",
            rejectReasons=["too_identifiable"],
        )

    monkeypatch.setattr(worker_module, "analyze_avatar_source_image", lambda *_a, **_k: AcceptedSourceAnalysis())
    monkeypatch.setattr(worker_module, "Flux2KleinImageGenerator", FakeGenerator)
    payload = _payload(job_id="avatar_quality_extra_analysis_reference")
    fs = _fake_firestore(payload)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=rejecting_qa,
        mode="flux",
    )

    assert result.rejected_count == 8
    assert len(qa_metadata) == 8
    assert fs.data["avatarJobs"][payload["jobId"]]["generationPlan"]["extraCount"] == 4
    for metadata in qa_metadata[4:]:
        assert "_analysis_reference_image" in metadata
        assert metadata["_source_image"] is metadata["_analysis_reference_image"]
    persisted = json.dumps(fs.data["avatarJobs"][payload["jobId"]], default=str)
    persisted += json.dumps(fs.data["avatarCandidates"], default=str)
    assert "_analysis_reference_image" not in persisted


def test_region_hair_clothing_merge_keeps_onboarding_gender(monkeypatch):
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("AVATAR_CANDIDATE_TRAIT_QA_ENABLED", "false")
    worker_module._TRAIT_ADAPTER_CACHE.clear()

    class TraitAdapter:
        def __init__(self, **_kwargs):
            pass

        def extract_traits(self, *, image, avatar_presentation_gender):
            return _trait_response(
                hair_color_range="unclear",
                clothing_color="unclear",
                avatar_presentation_gender="male",
            )

    monkeypatch.setattr(worker_module, "analyze_avatar_source_image", lambda *_a, **_k: AcceptedSourceAnalysis())
    monkeypatch.setattr(worker_module, "Florence2TraitExtractionAdapter", TraitAdapter)
    monkeypatch.setattr(worker_module, "Flux2KleinImageGenerator", FakeGenerator)
    monkeypatch.setattr(
        worker_module,
        "extract_region_color_traits",
        lambda *_a, **_k: types.SimpleNamespace(
            hair_color_range=types.SimpleNamespace(value="black", confidence="high"),
            clothing_color=types.SimpleNamespace(value="blue", confidence="medium"),
            to_trait_card_update=lambda: {"hair_color_range": "black", "clothing_color": "blue"},
        ),
    )
    payload = _payload(job_id="avatar_quality_region_traits")
    fs = _fake_firestore(payload)
    fs.data["avatarJobs"][payload["jobId"]]["avatarPresentationGender"] = "female"

    process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="flux",
    )

    card = fs.data["avatarJobs"][payload["jobId"]]["traitCard"]["traitCard"]
    assert card["hair_color_range"] == "black"
    assert card["clothing_color"] == "blue"
    assert card["avatar_presentation_gender"] == "female"


def test_budget_caps_and_model_outage_skip_extra(monkeypatch):
    monkeypatch.setenv("AVATAR_INITIAL_CANDIDATE_COUNT", "4")
    monkeypatch.setenv("AVATAR_EXTRA_CANDIDATE_COUNT", "4")
    monkeypatch.setenv("AVATAR_MAX_TOTAL_CANDIDATES", "5")
    payload = _payload(job_id="avatar_quality_budget")
    fs = _fake_firestore(payload)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=lambda *_a, **_k: AvatarQAResult(
            adultQa="needs_review",
            privacyQa="needs_review",
            brandQa="needs_review",
            cropConsistency="needs_review",
            previewAllowed=False,
            requiresHumanReview=True,
            qaVersion="avatar_qa_v1_model_unavailable",
            reviewReasons=["model_unavailable"],
        ),
        mode="dry_run",
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert result.status == "no_previewable_candidates"
    assert job["generationPlan"]["initialCount"] == 4
    assert job["generationPlan"]["extraCount"] == 0
    assert job["generationPlan"]["rounds"][-1]["plan"]["blockedReasons"] == [
        "qa_critical_model_unavailable"
    ]


def test_heuristic_qa_version_denied_before_rerank(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    qa_doc = _passing_qa("source", "candidate", {}).to_document()
    qa_doc["qaVersion"] = "avatar_qa_v1_staging_heuristic_preview"
    qa_doc["previewAllowed"] = True

    assert worker_module._candidate_status_from_qa(qa_doc) == "needs_review"
