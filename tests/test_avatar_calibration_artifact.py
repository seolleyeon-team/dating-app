import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.calibration_artifact import (  # noqa: E402
    CalibrationArtifact,
    CalibrationArtifactError,
    canonical_artifact_sha256,
    load_configured_calibration_artifact,
)


def _without_integrity() -> dict:
    return {
        "schemaVersion": "avatar_qa_calibration_v1",
        "calibrationVersion": "g004-test-v1",
        "createdAt": "2026-08-23T00:00:00Z",
        "gitRevision": "test-revision",
        "qaContractVersion": "avatar-qa-v1",
        "cohortPolicyVersion": "g004-5plus-v1",
        "modelVersions": {
            "faceSimilarity": "openai/clip-vit-base-patch32",
            "clipSafety": "openai/clip-vit-large-patch14",
        },
        "preprocessingVersions": {
            "reference": "avatar-reference-v1",
            "qa": "avatar-qa-preprocess-v1",
        },
        "faceSimilarity": {
            "model": "openai/clip-vit-base-patch32",
            "metric": "cosine",
            "semanticRole": "identity_privacy_upper_bound",
            "threshold": 0.86,
            "thresholdDirection": "gte_review",
            "reviewMargin": 0.04,
            "evidenceSummary": "deterministic non-user evidence",
        },
        "clipSafety": {
            "model": "openai/clip-vit-large-patch14",
            "thresholds": {
                "childlike": 0.35,
                "sexualized": 0.35,
                "beautification": 0.55,
                "brand_mismatch": 0.45,
                "severe_artifact": 0.35,
            },
            "minimumScores": {
                "adult_like": 0.55,
                "brand_fit": 0.55,
            },
            "evidenceSummary": "deterministic non-user evidence",
        },
        "humanReviewPolicy": {"rubricVersion": "g004-v1"},
    }


def _valid_mapping() -> dict:
    value = _without_integrity()
    value["integrity"] = {"sha256": canonical_artifact_sha256(value)}
    return value


def test_valid_artifact_maps_to_runtime_policies():
    artifact = CalibrationArtifact.from_mapping(_valid_mapping())

    assert artifact.calibration_version == "g004-test-v1"
    assert artifact.to_similarity_policy().threshold == 0.86
    assert artifact.to_similarity_policy().review_margin == 0.04
    assert artifact.to_clip_policy().thresholds["childlike"] == 0.35
    assert artifact.to_clip_policy().minimums["adult_like"] == 0.55


@pytest.mark.parametrize("missing", ["schemaVersion", "faceSimilarity", "clipSafety", "integrity"])
def test_artifact_rejects_missing_required_sections(missing):
    value = _valid_mapping()
    value.pop(missing)

    with pytest.raises(CalibrationArtifactError):
        CalibrationArtifact.from_mapping(value)


def test_artifact_rejects_forbidden_raw_data_fields():
    value = _valid_mapping()
    value["debug"] = {"rawEmbedding": [0.1, 0.2]}
    value["integrity"] = {"sha256": canonical_artifact_sha256({key: item for key, item in value.items() if key != "integrity"})}

    with pytest.raises(CalibrationArtifactError, match="forbidden"):
        CalibrationArtifact.from_mapping(value)


def test_artifact_rejects_integrity_mismatch():
    value = _valid_mapping()
    value["integrity"]["sha256"] = "0" * 64

    with pytest.raises(CalibrationArtifactError, match="checksum"):
        CalibrationArtifact.from_mapping(value)


@pytest.mark.parametrize("field", ["threshold", "reviewMargin"])
def test_artifact_rejects_out_of_range_similarity_values(field):
    value = _valid_mapping()
    value["faceSimilarity"][field] = 1.5
    value["integrity"] = {"sha256": canonical_artifact_sha256({key: item for key, item in value.items() if key != "integrity"})}

    with pytest.raises(CalibrationArtifactError, match="range"):
        CalibrationArtifact.from_mapping(value)


def test_load_verifies_file_checksum_and_expected_versions(tmp_path):
    value = _valid_mapping()
    path = tmp_path / "avatar_qa_calibration_v1.json"
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    file_sha = hashlib.sha256(raw).hexdigest()

    artifact = CalibrationArtifact.load(
        path,
        expected_sha256=file_sha,
        expected_models={"faceSimilarity": "openai/clip-vit-base-patch32"},
        expected_preprocessing={"reference": "avatar-reference-v1"},
    )
    assert artifact.calibration_version == "g004-test-v1"

    with pytest.raises(CalibrationArtifactError, match="file checksum"):
        CalibrationArtifact.load(path, expected_sha256="1" * 64)

    with pytest.raises(CalibrationArtifactError, match="model version"):
        CalibrationArtifact.load(path, expected_models={"faceSimilarity": "wrong"})

    with pytest.raises(CalibrationArtifactError, match="preprocessing version"):
        CalibrationArtifact.load(path, expected_preprocessing={"reference": "wrong"})


def test_configured_loader_enforces_pinned_model_and_preprocessing_versions(monkeypatch, tmp_path):
    value = _valid_mapping()
    path = tmp_path / "avatar_qa_calibration_v1.json"
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)

    monkeypatch.setenv("AVATAR_QA_CALIBRATION_ARTIFACT_PATH", str(path))
    monkeypatch.setenv("AVATAR_QA_CALIBRATION_ARTIFACT_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setenv(
        "AVATAR_QA_CALIBRATION_EXPECTED_MODELS_JSON",
        json.dumps({"faceSimilarity": "openai/clip-vit-base-patch32"}),
    )
    monkeypatch.setenv(
        "AVATAR_QA_CALIBRATION_EXPECTED_PREPROCESSING_JSON",
        json.dumps({"reference": "avatar-reference-v1"}),
    )

    assert load_configured_calibration_artifact(required=True) is not None

    monkeypatch.setenv(
        "AVATAR_QA_CALIBRATION_EXPECTED_MODELS_JSON",
        json.dumps({"faceSimilarity": "wrong-model"}),
    )
    with pytest.raises(CalibrationArtifactError, match="model version"):
        load_configured_calibration_artifact(required=True)


def test_repository_g004_artifact_is_pinned_to_measured_pre_live_evidence():
    """Catch a missing/stale worker artifact before a staging image is built."""

    path = (
        REPO_ROOT
        / "lib"
        / "ai_recommend_model"
        / "avatar_generation"
        / "artifacts"
        / "avatar_qa_calibration_v1.json"
    )

    artifact = CalibrationArtifact.load(
        path,
        expected_models={
            "faceSimilarity": (
                "openai/clip-vit-base-patch32"
                "@3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
            ),
            "clipSafety": (
                "openai/clip-vit-large-patch14"
                "@32bd64288804d66eefd0ccbe215aa642df71cc41"
            ),
        },
        expected_preprocessing={
            "reference": "avatar_reference_preprocess_metadata_v1:privacy_strict_v1",
            "qa": "avatar_qa_v2:transformers-4.57.6:pillow-11.3.0",
        },
    )

    assert artifact.calibration_version == "g004-staging-20260823-v1"
    assert artifact.face_similarity["threshold"] == 0.799743
    assert artifact.face_similarity["reviewMargin"] == 0.185528
    assert artifact.clip_safety["thresholds"] == {
        "childlike": 0.2126,
        "sexualized": 0.508071,
        "beautification": 0.502082,
        "brand_mismatch": 0.585567,
        "severe_artifact": 0.474342,
    }
    assert artifact.clip_safety["minimumScores"] == {
        "adult_like": 0.7874,
        "brand_fit": 0.445412,
    }
