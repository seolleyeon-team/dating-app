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
from avatar_generation.worker import AvatarGenerationError, process_avatar_generation_payload
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
        "APPROVED_AVATAR_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", "seolleyeon-final-private-source-photos")
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", "seolleyeon-avatar-temp")
    worker_module._TRAIT_ADAPTER_CACHE.clear()


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
