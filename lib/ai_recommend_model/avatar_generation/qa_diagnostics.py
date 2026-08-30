"""Process-local, redacted diagnostics for the deployed QA runtime."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from .calibration_artifact import CalibrationArtifactError, load_configured_calibration_artifact
from .qa_contract import OPTIONAL_SIGNAL_NAMES, REQUIRED_SIGNAL_ALIASES
from .qa_preflight import get_qa_runtime_readiness
from .qa_runtime import get_default_clip_risk_scorer, get_default_similarity_adapter


DIAGNOSTIC_SCHEMA_VERSION = "avatar_qa_runtime_diagnostic_v1"
_DIAGNOSTIC_IMAGE = Image.new("RGB", (64, 64), (128, 128, 128))


def collect_qa_runtime_diagnostics() -> dict[str, Any]:
    """Probe local model stages without returning paths, images, or embeddings."""

    artifact = _load_artifact()
    result: dict[str, Any] = {
        "schemaVersion": DIAGNOSTIC_SCHEMA_VERSION,
        "offlineMode": {
            "hfHubOffline": os.environ.get("HF_HUB_OFFLINE", "") == "1",
            "transformersOffline": os.environ.get("TRANSFORMERS_OFFLINE", "") == "1",
        },
        "requiredSignals": list(REQUIRED_SIGNAL_ALIASES),
        "optionalSignals": list(OPTIONAL_SIGNAL_NAMES),
        "calibrationArtifactPresent": artifact is not None,
        "calibrationVersion": getattr(artifact, "calibration_version", None),
        "clipExpectedModel": _model_version(artifact, "clipSafety"),
        "faceSimilarityExpectedModel": _model_version(artifact, "faceSimilarity"),
        "clipArtifactPresent": _model_directory_present("AVATAR_CLIP_RISK_MODEL_ID"),
        "clipTokenizerReady": False,
        "clipModelLoaded": False,
        "clipDevice": "unknown",
        "clipPromptEmbeddingsReady": False,
        "clipInferenceReady": False,
        "clipCalibrationLoaded": _clip_calibration_loaded(artifact),
        "faceSimilarityArtifactPresent": _model_directory_present("AVATAR_QA_SIMILARITY_MODEL_ID"),
        "faceSimilarityProcessorReady": False,
        "faceSimilarityModelLoaded": False,
        "faceSimilarityDevice": "unknown",
        "faceSimilarityInferenceReady": False,
        "faceSimilarityCalibrationLoaded": _face_similarity_calibration_loaded(artifact),
        "clipFailureCode": "",
        "faceSimilarityFailureCode": "",
        "sanitizedFailureCode": "",
    }

    try:
        scorer = get_default_clip_risk_scorer()
        processor, model = scorer._load_components()
        result["clipTokenizerReady"] = _processor_ready(processor)
        result["clipModelLoaded"] = model is not None
        result["clipDevice"] = _model_device(model)
        scores = scorer.score_prompt_groups(
            _DIAGNOSTIC_IMAGE,
            {"diagnostic": {"safe": ("a safe portrait",), "unsafe": ("a corrupted image",)}},
        )
        result["clipPromptEmbeddingsReady"] = _mapping_has_values(scores)
        result["clipInferenceReady"] = _mapping_has_values(scores)
    except Exception as exc:  # pragma: no cover - exercised by deployed runtime
        result["clipFailureCode"] = _failure_code("clip", exc)

    try:
        adapter = get_default_similarity_adapter()
        encoder = getattr(adapter, "encoder", adapter)
        processor, model = encoder._load_components()
        result["faceSimilarityProcessorReady"] = _processor_ready(processor)
        result["faceSimilarityModelLoaded"] = model is not None
        result["faceSimilarityDevice"] = _model_device(model)
        embedding = encoder.encode_image(_DIAGNOSTIC_IMAGE)
        result["faceSimilarityInferenceReady"] = bool(embedding)
    except Exception as exc:  # pragma: no cover - exercised by deployed runtime
        result["faceSimilarityFailureCode"] = _failure_code("face_similarity", exc)

    result["sanitizedFailureCode"] = str(
        result["clipFailureCode"] or result["faceSimilarityFailureCode"] or ""
    )
    try:
        result["qaPreflight"] = get_qa_runtime_readiness().to_document()
    except Exception as exc:  # pragma: no cover - exercised by deployed runtime
        result["qaPreflight"] = {"ready": False, "failureCode": _failure_code("qa_preflight", exc)}
        if not result["sanitizedFailureCode"]:
            result["sanitizedFailureCode"] = result["qaPreflight"]["failureCode"]
    result["gpu"] = _gpu_snapshot()
    result["dependencyVersions"] = _dependency_versions()
    return result


def _load_artifact() -> Any | None:
    try:
        return load_configured_calibration_artifact(required=True)
    except CalibrationArtifactError:
        return None


def _model_directory_present(env_name: str) -> bool:
    value = os.environ.get(env_name, "").strip()
    return bool(value) and Path(value).is_dir()


def _model_version(artifact: Any, name: str) -> str | None:
    versions = getattr(artifact, "model_versions", {}) if artifact is not None else {}
    value = versions.get(name) if isinstance(versions, Mapping) else None
    return str(value) if value else None


def _clip_calibration_loaded(artifact: Any) -> bool:
    if artifact is None:
        return False
    try:
        return bool(artifact.to_clip_policy().is_valid)
    except Exception:
        return False


def _face_similarity_calibration_loaded(artifact: Any) -> bool:
    if artifact is None:
        return False
    face_similarity = getattr(artifact, "face_similarity", {})
    return isinstance(face_similarity, Mapping) and bool(face_similarity.get("threshold"))


def _processor_ready(processor: Any) -> bool:
    return processor is not None and getattr(processor, "tokenizer", processor) is not None


def _model_device(model: Any) -> str:
    try:
        parameters = getattr(model, "parameters", None)
        parameter = next(parameters()) if callable(parameters) else None
        device = str(getattr(parameter, "device", "unknown"))
        return device if device.replace(":", "").replace(".", "").replace("-", "").isalnum() else "unknown"
    except Exception:
        return "unknown"


def _mapping_has_values(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value)


def _failure_code(stage: str, exc: Exception) -> str:
    exception_type = type(exc).__name__.strip().lower()
    safe_type = "".join(char if char.isalnum() else "_" for char in exception_type).strip("_")
    return f"{stage}_failed_{safe_type or 'exception'}"


def _gpu_snapshot() -> dict[str, Any]:
    try:
        import torch

        if not bool(torch.cuda.is_available()):
            return {"available": False}
        return {
            "available": True,
            "deviceCount": int(torch.cuda.device_count()),
            "allocatedBytes": int(torch.cuda.memory_allocated()),
            "reservedBytes": int(torch.cuda.memory_reserved()),
            "peakAllocatedBytes": int(torch.cuda.max_memory_allocated()),
        }
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"available": False, "failureCode": _failure_code("gpu", exc)}


def _dependency_versions() -> dict[str, str | None]:
    names = ("torch", "transformers", "huggingface-hub", "Pillow")
    return {
        name: _package_version(name)
        for name in names
    }


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


__all__ = ["DIAGNOSTIC_SCHEMA_VERSION", "collect_qa_runtime_diagnostics"]
