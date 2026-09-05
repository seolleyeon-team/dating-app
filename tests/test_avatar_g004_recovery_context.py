"""G004 recovery-route v6 provenance context contract (PIPELINE_PROVENANCE_DRIFT fix).

Runtime recovery attempt #3 (2026-08-31) proved that the recovery/calibration
QA metadata — and, latently, the worker's own azure candidate metadata — do
not satisfy `trait_policy._is_canonical_azure_contract`, because the
authority keys (`provider`, `pipelineMode`, `traitQaMode`,
`traitQaAuthority`, `uniqueMarkQaMode`, `uniqueMarkQaAuthority`) were
duplicated by hand and drifted. Result: trait applicability resolved to
unavailable/review on all 20 SAME-20 candidates and unique-mark
applicability never engaged.

These tests lock one shared canonical contract source for every QA path.
No thresholds or policy semantics are touched.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
sys.path.insert(0, str(AI_MODEL_DIR))

from PIL import Image  # noqa: E402

from avatar_generation.calibration_service import _qa_metadata  # noqa: E402
from avatar_generation.qa_pipeline_contract import (  # noqa: E402
    canonical_azure_qa_pipeline_contract,
)
from avatar_generation.trait_policy import (  # noqa: E402
    TRAIT_QA_ACTION_ALLOW,
    TRAIT_QA_APPLICABILITY_NOT_APPLICABLE,
    TRAIT_QA_MODE_CANONICAL_DISABLED,
    classify_trait_qa_pipeline,
    resolve_trait_qa_state,
)
from avatar_generation.unique_mark_policy import (  # noqa: E402
    UNIQUE_MARK_QA_ACTION_ALLOW,
    UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE,
    resolve_unique_mark_qa_state,
)
from avatar_generation import worker  # noqa: E402


def _image() -> Image.Image:
    return Image.new("RGB", (32, 32), (128, 128, 128))


def _recovery_metadata() -> dict:
    return _qa_metadata(_image(), _image())


def _worker_azure_metadata() -> dict:
    payload = worker.parse_avatar_generation_payload(
        {
            "schemaVersion": "avatar_job_v1",
            "jobType": "avatar_generation",
            "jobId": "avatar_job_ctx_contract_001",
            "uid": "u_ctx",
            "sourcePhotoIds": ["src_1"],
            "sourcePhotoRefs": [
                "gs://seolleyeon-final-private-source-photos/users/u_ctx/source/src_1.jpg"
            ],
            "sourcePhotoObjectGenerations": ["101"],
            "sourceSelectionMode": "quality_selector_v1",
            "candidateCount": 1,
            "modelId": "azure_gpt_image_2",
        }
    )
    artifact = worker.CandidateArtifact(
        candidate_id="cand_ctx_001",
        image_ref="gs://seolleyeon-final-avatar-temp/users/u_ctx/jobs/j/candidates/c.png",
        image_bytes=b"",
        seed=1,
        generation_params={},
    )
    return worker._candidate_qa_metadata(
        payload,
        artifact,
        run_mode=worker.CANONICAL_AZURE_WORKER_MODE,
        source_analysis_doc={},
        reference_preprocess_doc={},
        source_image=_image(),
        candidate_image=_image(),
    )


def test_canonical_contract_helper_satisfies_trait_authority():
    contract = canonical_azure_qa_pipeline_contract()
    assert classify_trait_qa_pipeline(contract) == TRAIT_QA_MODE_CANONICAL_DISABLED


def test_recovery_metadata_is_canonical_for_trait_applicability():
    metadata = _recovery_metadata()
    assert classify_trait_qa_pipeline(metadata) == TRAIT_QA_MODE_CANONICAL_DISABLED
    state = resolve_trait_qa_state(metadata, None, None, None)
    assert state.applicability == TRAIT_QA_APPLICABILITY_NOT_APPLICABLE
    assert state.action == TRAIT_QA_ACTION_ALLOW
    assert state.needs_review is False


def test_worker_azure_metadata_is_canonical_for_trait_applicability():
    metadata = _worker_azure_metadata()
    assert classify_trait_qa_pipeline(metadata) == TRAIT_QA_MODE_CANONICAL_DISABLED
    state = resolve_trait_qa_state(metadata, None, None, None)
    assert state.applicability == TRAIT_QA_APPLICABILITY_NOT_APPLICABLE
    assert state.action == TRAIT_QA_ACTION_ALLOW


def test_recovery_metadata_engages_unique_mark_applicability():
    metadata = _recovery_metadata()
    state = resolve_unique_mark_qa_state(metadata, {})
    assert state is not None
    assert state.applicability == UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE
    assert state.action == UNIQUE_MARK_QA_ACTION_ALLOW


def test_all_paths_share_the_same_authority_values():
    contract = canonical_azure_qa_pipeline_contract()
    recovery = _recovery_metadata()
    worker_meta = _worker_azure_metadata()
    for key, value in contract.items():
        assert recovery.get(key) == value, f"recovery drifted on {key}"
        assert worker_meta.get(key) == value, f"worker drifted on {key}"
    # jobs.py persisted-doc provenance keeps its own schema, but the values it
    # shares with the QA contract must agree with the canonical authority.
    from avatar_generation.jobs import AvatarJobSpec, build_avatar_job_doc

    doc = build_avatar_job_doc(
        AvatarJobSpec(
            job_id="avatar_job_ctx_contract_002",
            uid="u_ctx",
            source_photo_ids=["src_1"],
            source_photo_refs=["gs://b/users/u_ctx/source/src_1.jpg"],
        )
    )
    assert doc["model"]["provider"] == contract["provider"]
    assert doc["generationBackend"] == contract["generationBackend"]
    for key in (
        "sourceInputMode",
        "uploadNormalization",
        "preGenerationTransform",
        "legacyTraitExtraction",
        "legacyReferencePreprocessing",
        "legacyFlux",
        "uniqueMarkQaMode",
        "uniqueMarkQaAuthority",
    ):
        assert doc["provenance"][key] == contract[key], key


def test_not_applicable_is_distinct_from_provider_outage():
    # N/A comes from the canonical pipeline contract; unavailable stays the
    # outcome for an expected-but-missing producer. The fix must not blur them.
    enabled_contract = {
        **canonical_azure_qa_pipeline_contract(),
        "pipelineMode": "flux",
        "traitQaMode": "enabled",
    }
    state = resolve_trait_qa_state(enabled_contract, None, None, None)
    assert state.applicability != TRAIT_QA_APPLICABILITY_NOT_APPLICABLE
