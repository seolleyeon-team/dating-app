"""Worker QA gates that do not depend on any generation backend.

Moved out of the retired FLUX-driven quality-integration suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))
TESTS_DIR = REPO_ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import avatar_generation.worker as worker_module  # noqa: E402
from avatar_generation.qa import AvatarQAResult  # noqa: E402
from avatar_generation.worker import process_avatar_generation_payload  # noqa: E402

from test_avatar_generation_worker import (  # noqa: E402
    _fake_firestore,
    _fake_storage,
    _passing_qa,
    _payload,
)


@pytest.fixture(autouse=True)
def _isolate_worker_environment(monkeypatch):
    for name in ("ENVIRONMENT", "AVATAR_DATA_PROJECT", "FIRESTORE_PROJECT", "GCP_PROJECT", "APPROVED_AVATAR_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", "seolleyeon-final-private-source-photos")
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", "seolleyeon-avatar-temp")
    worker_module._TRAIT_ADAPTER_CACHE.clear()
    worker_module.reset_model_cache_for_tests()


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
