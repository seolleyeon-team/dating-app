import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.qa_preflight as qa_preflight  # noqa: E402
import avatar_generation.qa_runtime as qa_runtime  # noqa: E402
from test_avatar_calibration_artifact import _valid_mapping  # noqa: E402


def _write_artifact(tmp_path: Path) -> Path:
    value = _valid_mapping()
    path = tmp_path / "avatar_qa_calibration_v1.json"
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    return path


def test_configured_artifact_preflight_is_available(monkeypatch, tmp_path):
    path = _write_artifact(tmp_path)
    monkeypatch.setenv("AVATAR_QA_CALIBRATION_ARTIFACT_PATH", str(path))
    monkeypatch.setenv("AVATAR_QA_CALIBRATION_ARTIFACT_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())

    readiness = qa_preflight.build_calibration_artifact_readiness()

    assert readiness.name == "calibrationArtifact"
    assert readiness.status == "available"
    assert readiness.critical is True


def test_required_staging_artifact_missing_is_uncalibrated(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("AVATAR_QA_CALIBRATION_ARTIFACT_PATH", raising=False)
    monkeypatch.delenv("AVATAR_QA_CALIBRATION_ARTIFACT_SHA256", raising=False)

    readiness = qa_preflight.build_calibration_artifact_readiness()

    assert readiness.status == "uncalibrated"
    assert readiness.reason == "calibration_artifact_missing"
    assert readiness.critical is True


def test_artifact_policy_overrides_legacy_similarity_env(monkeypatch, tmp_path):
    path = _write_artifact(tmp_path)
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("AVATAR_QA_CALIBRATION_ARTIFACT_PATH", str(path))
    monkeypatch.setenv("AVATAR_QA_SIMILARITY_CALIBRATION_VERSION", "legacy")
    monkeypatch.setenv("AVATAR_QA_SIMILARITY_THRESHOLD", "0.01")
    monkeypatch.setenv("AVATAR_QA_SIMILARITY_REVIEW_MARGIN", "0.0")
    monkeypatch.setattr(qa_runtime, "_DEFAULT_QA_RUNTIME", None)

    policy = qa_runtime._similarity_policy_from_env()

    assert policy is not None
    assert policy.calibration_version == "g004-test-v1"
    assert policy.threshold == 0.86
    assert policy.review_margin == 0.04


def test_staging_readiness_contains_calibration_artifact_gate(monkeypatch, tmp_path):
    path = _write_artifact(tmp_path)
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("AVATAR_QA_CALIBRATION_ARTIFACT_PATH", str(path))

    available = lambda name: qa_preflight.QAComponentReadiness(
        name=name, status="available", critical=True, reason="ok"
    )
    monkeypatch.setattr(qa_preflight, "_probe_image_decode", lambda: available("imageDecode"))
    monkeypatch.setattr(qa_preflight, "_probe_face_detector", lambda: available("faceDetector"))
    monkeypatch.setattr(qa_preflight, "_probe_visual_risk", lambda: available("visualRisk"))
    monkeypatch.setattr(qa_preflight, "_probe_local_safety", lambda: available("localSafetyRisk"))
    monkeypatch.setattr(qa_preflight, "_probe_face_similarity", lambda: available("faceSimilarity"))
    monkeypatch.setattr(qa_preflight, "_probe_device", lambda: available("device"))

    readiness = qa_preflight.build_qa_runtime_readiness()

    assert readiness.ready is True
    assert readiness.to_document()["components"]["calibrationArtifact"]["status"] == "available"
