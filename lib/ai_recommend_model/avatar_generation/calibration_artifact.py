from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class CalibrationArtifactError(ValueError):
    """Raised when a calibration artifact cannot be trusted or used."""


ENV_CALIBRATION_ARTIFACT_PATH = "AVATAR_QA_CALIBRATION_ARTIFACT_PATH"
ENV_CALIBRATION_ARTIFACT_SHA256 = "AVATAR_QA_CALIBRATION_ARTIFACT_SHA256"
ENV_CALIBRATION_EXPECTED_MODELS = "AVATAR_QA_CALIBRATION_EXPECTED_MODELS_JSON"
ENV_CALIBRATION_EXPECTED_PREPROCESSING = "AVATAR_QA_CALIBRATION_EXPECTED_PREPROCESSING_JSON"


_SCHEMA_VERSION = "avatar_qa_calibration_v1"
_SIMILARITY_THRESHOLD_KEYS = {"childlike", "sexualized", "beautification", "brand_mismatch", "severe_artifact"}
_SIMILARITY_MINIMUM_KEYS = {"adult_like", "brand_fit"}
_HEX_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_FORBIDDEN_KEY_FRAGMENTS = (
    "embedding",
    "landmark",
    "bbox",
    "sourceimage",
    "candidateimage",
    "signedurl",
    "privatepath",
    "rawuid",
    "sourceuid",
    "hashprefix",
    "sourcehash",
    "candidatehash",
)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _without_integrity(value: Mapping[str, Any]) -> dict[str, Any]:
    copied = json.loads(json.dumps(value, ensure_ascii=False))
    integrity = copied.get("integrity")
    if isinstance(integrity, dict):
        integrity.pop("sha256", None)
        if not integrity:
            copied.pop("integrity", None)
    else:
        copied.pop("integrity", None)
    return copied


def canonical_artifact_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(_without_integrity(value))).hexdigest()


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationArtifactError(f"{name} must be a non-empty string.")
    return value.strip()


def _require_probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationArtifactError(f"{name} must be numeric.")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise CalibrationArtifactError(f"{name} is outside the allowed range.")
    return result


def _reject_forbidden_fields(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            normalized = key_text.replace("_", "").replace("-", "").lower()
            if child_path == "integrity.sha256":
                continue
            if any(fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise CalibrationArtifactError(f"forbidden calibration artifact field: {child_path}")
            _reject_forbidden_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_fields(child, f"{path}.{index}")


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationArtifactError(f"{name} must be an object.")
    return value


@dataclass(frozen=True)
class CalibrationArtifact:
    payload: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CalibrationArtifact":
        if not isinstance(value, Mapping):
            raise CalibrationArtifactError("calibration artifact must be an object.")
        _reject_forbidden_fields(value)
        schema_version = _require_text(value.get("schemaVersion"), "schemaVersion")
        if schema_version != _SCHEMA_VERSION:
            raise CalibrationArtifactError("unsupported calibration artifact schema.")
        for field in (
            "calibrationVersion",
            "createdAt",
            "gitRevision",
            "qaContractVersion",
            "cohortPolicyVersion",
        ):
            _require_text(value.get(field), field)

        model_versions = _require_mapping(value.get("modelVersions"), "modelVersions")
        preprocessing_versions = _require_mapping(value.get("preprocessingVersions"), "preprocessingVersions")
        if not model_versions or not preprocessing_versions:
            raise CalibrationArtifactError("modelVersions and preprocessingVersions must not be empty.")
        for key, model in model_versions.items():
            _require_text(key, "modelVersions key")
            _require_text(model, f"modelVersions.{key}")
        for key, version in preprocessing_versions.items():
            _require_text(key, "preprocessingVersions key")
            _require_text(version, f"preprocessingVersions.{key}")

        face = _require_mapping(value.get("faceSimilarity"), "faceSimilarity")
        _require_text(face.get("model"), "faceSimilarity.model")
        if _require_text(face.get("metric"), "faceSimilarity.metric").lower() != "cosine":
            raise CalibrationArtifactError("faceSimilarity.metric must be cosine.")
        if _require_text(face.get("semanticRole"), "faceSimilarity.semanticRole") != "identity_privacy_upper_bound":
            raise CalibrationArtifactError("faceSimilarity.semanticRole is invalid.")
        _require_probability(face.get("threshold"), "faceSimilarity.threshold")
        _require_text(face.get("thresholdDirection"), "faceSimilarity.thresholdDirection")
        _require_probability(face.get("reviewMargin"), "faceSimilarity.reviewMargin")
        _require_text(face.get("evidenceSummary"), "faceSimilarity.evidenceSummary")

        clip = _require_mapping(value.get("clipSafety"), "clipSafety")
        _require_text(clip.get("model"), "clipSafety.model")
        thresholds = _require_mapping(clip.get("thresholds"), "clipSafety.thresholds")
        minimums = _require_mapping(clip.get("minimumScores"), "clipSafety.minimumScores")
        if set(thresholds) != _SIMILARITY_THRESHOLD_KEYS:
            raise CalibrationArtifactError("clipSafety.thresholds keys are incomplete or unexpected.")
        if set(minimums) != _SIMILARITY_MINIMUM_KEYS:
            raise CalibrationArtifactError("clipSafety.minimumScores keys are incomplete or unexpected.")
        for key, threshold in thresholds.items():
            _require_probability(threshold, f"clipSafety.thresholds.{key}")
        for key, minimum in minimums.items():
            _require_probability(minimum, f"clipSafety.minimumScores.{key}")
        _require_text(clip.get("evidenceSummary"), "clipSafety.evidenceSummary")

        human = _require_mapping(value.get("humanReviewPolicy"), "humanReviewPolicy")
        _require_text(human.get("rubricVersion"), "humanReviewPolicy.rubricVersion")

        integrity = _require_mapping(value.get("integrity"), "integrity")
        checksum = _require_text(integrity.get("sha256"), "integrity.sha256")
        if not _HEX_SHA256.fullmatch(checksum):
            raise CalibrationArtifactError("integrity.sha256 must be a SHA-256 hex digest.")
        if checksum.lower() != canonical_artifact_sha256(value):
            raise CalibrationArtifactError("calibration artifact checksum mismatch.")

        copied = json.loads(json.dumps(value, ensure_ascii=False))
        return cls(payload=copied)

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        expected_sha256: str | None = None,
        expected_models: Mapping[str, str] | None = None,
        expected_preprocessing: Mapping[str, str] | None = None,
    ) -> "CalibrationArtifact":
        try:
            raw = path.read_bytes()
        except Exception as exc:
            raise CalibrationArtifactError("calibration artifact file unavailable.") from exc
        if expected_sha256 is not None:
            actual_file_sha = hashlib.sha256(raw).hexdigest()
            if actual_file_sha.lower() != str(expected_sha256).strip().lower():
                raise CalibrationArtifactError("calibration artifact file checksum mismatch.")
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise CalibrationArtifactError("calibration artifact JSON is invalid.") from exc
        artifact = cls.from_mapping(value)
        if expected_models:
            for key, expected in expected_models.items():
                if artifact.model_versions.get(key) != expected:
                    raise CalibrationArtifactError(f"calibration artifact model version mismatch: {key}")
        if expected_preprocessing:
            for key, expected in expected_preprocessing.items():
                if artifact.preprocessing_versions.get(key) != expected:
                    raise CalibrationArtifactError(f"calibration artifact preprocessing version mismatch: {key}")
        return artifact

    @property
    def schema_version(self) -> str:
        return str(self.payload["schemaVersion"])

    @property
    def calibration_version(self) -> str:
        return str(self.payload["calibrationVersion"])

    @property
    def model_versions(self) -> Mapping[str, str]:
        return self.payload["modelVersions"]

    @property
    def preprocessing_versions(self) -> Mapping[str, str]:
        return self.payload["preprocessingVersions"]

    @property
    def face_similarity(self) -> Mapping[str, Any]:
        return self.payload["faceSimilarity"]

    @property
    def clip_safety(self) -> Mapping[str, Any]:
        return self.payload["clipSafety"]

    def to_similarity_policy(self) -> Any:
        from .model_adapters.image_similarity import CalibrationPolicy

        return CalibrationPolicy(
            calibration_version=self.calibration_version,
            threshold=float(self.face_similarity["threshold"]),
            review_margin=float(self.face_similarity["reviewMargin"]),
        )

    def to_clip_policy(self) -> Any:
        from .model_adapters.clip_risk import ClipRiskCalibrationPolicy

        return ClipRiskCalibrationPolicy(
            calibration_version=self.calibration_version,
            risk_thresholds=dict(self.clip_safety["thresholds"]),
            minimum_scores=dict(self.clip_safety["minimumScores"]),
        )


def load_configured_calibration_artifact(*, required: bool = False) -> CalibrationArtifact | None:
    path_text = os.environ.get(ENV_CALIBRATION_ARTIFACT_PATH, "").strip()
    if not path_text:
        if required:
            raise CalibrationArtifactError("calibration artifact is missing.")
        return None
    expected_sha256 = os.environ.get(ENV_CALIBRATION_ARTIFACT_SHA256, "").strip() or None
    expected_models = _mapping_from_env(ENV_CALIBRATION_EXPECTED_MODELS)
    expected_preprocessing = _mapping_from_env(ENV_CALIBRATION_EXPECTED_PREPROCESSING)
    return CalibrationArtifact.load(
        Path(path_text),
        expected_sha256=expected_sha256,
        expected_models=expected_models,
        expected_preprocessing=expected_preprocessing,
    )


def _mapping_from_env(name: str) -> Mapping[str, str] | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise CalibrationArtifactError(f"{name} is invalid.") from exc
    if not isinstance(value, Mapping) or not value:
        raise CalibrationArtifactError(f"{name} is invalid.")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, str) or not item.strip():
            raise CalibrationArtifactError(f"{name} is invalid.")
        result[key.strip()] = item.strip()
    return result


__all__ = [
    "CalibrationArtifact",
    "CalibrationArtifactError",
    "canonical_artifact_sha256",
    "ENV_CALIBRATION_ARTIFACT_PATH",
    "ENV_CALIBRATION_ARTIFACT_SHA256",
    "ENV_CALIBRATION_EXPECTED_MODELS",
    "ENV_CALIBRATION_EXPECTED_PREPROCESSING",
    "load_configured_calibration_artifact",
]
