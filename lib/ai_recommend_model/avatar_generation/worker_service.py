from __future__ import annotations

import os
from typing import Any, Dict

try:
    from flask import Flask, jsonify, request
except Exception:  # pragma: no cover - dependency is required in the worker image
    Flask = None  # type: ignore[assignment]
    jsonify = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]

from avatar_generation.fidelity_corridor import CorridorMode, CorridorPolicy
from avatar_generation.avatar_prompt_contract import AVATAR_GENERAL_PROMPT_VERSION
from avatar_generation.calibration_runner import CalibrationRunnerError
from avatar_generation.calibration_recovery import execute_g004_calibration_recovery_request
from avatar_generation.calibration_service import execute_g004_calibration_request
from avatar_generation.model_adapters.azure_contracts import (
    AZURE_GPT_IMAGE_2_MODEL_ID,
    AZURE_GPT_IMAGE_2_VERSION,
    AzureGptImage2Config,
)
from avatar_generation.worker import (
    AvatarGenerationError,
    AvatarQAReadinessError,
    is_production_environment,
    model_cache_metrics,
    process_avatar_generation_batch_payload,
    process_avatar_generation_drain,
    process_avatar_generation_payload,
    resolve_firestore_project,
    validate_bridge_runtime_config,
    warmup_avatar_model,
)
from avatar_generation.qa_preflight import get_qa_runtime_readiness
from avatar_generation.qa_diagnostics import collect_qa_runtime_diagnostics


class AvatarWorkerAuthError(AvatarGenerationError):
    pass


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_local_environment() -> bool:
    return os.environ.get("ENVIRONMENT", "").strip().lower() in {"local", "dev", "development", "test"}


def _allow_insecure_local_worker() -> bool:
    return _is_local_environment() and (
        _env_bool("ALLOW_INSECURE_WORKER_LOCAL")
        or _env_bool("AVATAR_WORKER_ALLOW_INSECURE_LOCAL")
    )


def _batch_drain_enabled() -> bool:
    return (
        os.environ.get("AVATAR_BATCHING_ENABLED", "").strip().lower() in {"1", "true", "yes", "y", "on"}
        and os.environ.get("AVATAR_BATCH_MODE", "").strip().lower() == "drain"
    )


def _g004_paid_endpoint_enabled() -> bool:
    return _env_bool("AVATAR_CALIBRATION_PAID_ENDPOINT_ENABLED")


def _g004_recovery_endpoint_enabled() -> bool:
    return _env_bool("AVATAR_CALIBRATION_RECOVERY_ENDPOINT_ENABLED")


def _qa_diagnostics_enabled() -> bool:
    return _env_bool("AVATAR_QA_DIAGNOSTICS_ENABLED")



def _release_posture() -> Dict[str, Any]:
    corridor = CorridorPolicy.from_env()
    azure_config = AzureGptImage2Config.from_env(require_credentials=False)
    return {
        "provider": "azure",
        "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
        "modelFamily": AZURE_GPT_IMAGE_2_VERSION,
        "promptVersion": AVATAR_GENERAL_PROMPT_VERSION,
        "sourceInputMode": "storage_normalized_original_direct",
        "uploadNormalization": "existing_avatar_media_ingestion",
        "preGenerationTransform": "none",
        "azureConfig": azure_config.safe_dict(),
        "legacyGenerationPrerequisites": {
            "flux": False,
            "referencePreprocessing": False,
            "traitExtraction": False,
        },
        "fidelityCorridor": {
            "mode": corridor.mode.value,
            "calibrationVersion": corridor.calibration_version,
            "enforced": bool(
                corridor.mode is CorridorMode.ENFORCED and corridor.calibrated
            ),
        },
        "publicRollout": _env_bool("AVATAR_PUBLIC_ROLLOUT_ENABLED"),
        "g004Endpoints": {
            "paidCalibration": _g004_paid_endpoint_enabled(),
            "qaRecovery": _g004_recovery_endpoint_enabled(),
        },
    }


def _qa_readiness_for_readyz() -> Dict[str, Any]:
    if _is_local_environment():
        return {
            "schemaVersion": "avatar_qa_preflight_v1",
            "ready": True,
            "failureCode": "",
            "blockingComponents": [],
            "components": {
                "runtime": {
                    "status": "not_required",
                    "critical": False,
                    "reason": "local_environment",
                }
            },
            "signalCoverage": {},
        }
    return get_qa_runtime_readiness().to_document()

def readyz_status() -> Dict[str, Any]:
    validate_bridge_runtime_config()
    auth_mode = os.environ.get("AVATAR_WORKER_AUTH_MODE", "").strip().lower()
    if not auth_mode and _allow_insecure_local_worker():
        auth_mode = "local_insecure"
    qa_readiness = _qa_readiness_for_readyz()
    return {
        "status": "ok" if qa_readiness.get("ready") is True else "degraded",
        "authMode": auth_mode or "not_configured",
        "production": is_production_environment(),
        "dataProject": resolve_firestore_project() or "ambient",
        "batchDrainEnabled": _batch_drain_enabled(),
        "releasePosture": _release_posture(),
        "qaReadiness": qa_readiness,
        "metrics": model_cache_metrics(),
    }


def _require_shared_secret() -> None:
    expected = os.environ.get("AVATAR_WORKER_SHARED_SECRET", "")
    headers = getattr(request, "headers", {}) if request is not None else {}
    provided = headers.get("X-Avatar-Worker-Token", "")
    if not expected or provided != expected:
        raise AvatarWorkerAuthError("Avatar worker request is not authorized.")


def _require_cloud_run_iam_config() -> None:
    if not _env_bool("AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED"):
        raise AvatarWorkerAuthError(
            "Avatar worker request is not authorized; Cloud Run IAM enforcement is not configured."
        )
    if not os.environ.get("K_SERVICE"):
        raise AvatarWorkerAuthError(
            "Avatar worker request is not authorized; Cloud Run service context is missing."
        )


def _require_worker_auth() -> None:
    """Require explicit auth posture in production.

    Production should use Cloud Run IAM with run.invoker/OIDC before traffic
    reaches Flask, or the app-level shared-secret fallback for non-IAM staging.
    """
    auth_mode = os.environ.get("AVATAR_WORKER_AUTH_MODE", "").strip().lower()
    if auth_mode == "cloud_run_iam":
        _require_cloud_run_iam_config()
        return

    if is_production_environment():
        if auth_mode == "shared_secret" or _env_bool("AVATAR_WORKER_REQUIRE_SHARED_SECRET"):
            _require_shared_secret()
            return
        raise AvatarWorkerAuthError(
            "Avatar worker request is not authorized; production auth mode is not configured."
        )

    if _env_bool("AVATAR_WORKER_REQUIRE_SHARED_SECRET"):
        _require_shared_secret()
        return

    if _allow_insecure_local_worker():
        return

    raise AvatarWorkerAuthError(
        "ALLOW_INSECURE_WORKER_LOCAL=true is required for unauthenticated local avatar worker requests."
    )


def create_app() -> Any:
    if Flask is None or jsonify is None or request is None:
        raise AvatarGenerationError("Flask is required for avatar worker HTTP service.")

    flask_app = Flask(__name__)

    @flask_app.post("/tasks/avatar-generation")
    def avatar_generation_task() -> Any:
        try:
            _require_worker_auth()
            payload: Dict[str, Any] = request.get_json(force=True, silent=False)
            schema_version = str(payload.get("schemaVersion") or "")
            if schema_version == "avatar_batch_job_v1":
                result = process_avatar_generation_batch_payload(payload)
            else:
                result = process_avatar_generation_payload(payload)
            return jsonify(result.to_dict())
        except AvatarWorkerAuthError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 401
        except AvatarQAReadinessError as exc:
            return jsonify(
                {
                    "status": "error",
                    "error": str(exc),
                    "errorCode": exc.error_code,
                    "retryable": True,
                    "qaPreflight": exc.readiness.to_document(),
                }
            ), 503
        except AvatarGenerationError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except Exception:
            return jsonify({"status": "error", "error": "internal avatar worker error"}), 500

    @flask_app.post("/tasks/avatar-generation/drain")
    def avatar_generation_drain_task() -> Any:
        try:
            _require_worker_auth()
            if not _batch_drain_enabled():
                raise AvatarGenerationError("Avatar drain mode requires AVATAR_BATCHING_ENABLED=true and AVATAR_BATCH_MODE=drain.")
            result = process_avatar_generation_drain()
            return jsonify(result.to_dict())
        except AvatarWorkerAuthError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 401
        except AvatarQAReadinessError as exc:
            return jsonify(
                {
                    "status": "error",
                    "error": str(exc),
                    "errorCode": exc.error_code,
                    "retryable": True,
                    "qaPreflight": exc.readiness.to_document(),
                }
            ), 503
        except AvatarGenerationError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except Exception:
            return jsonify({"status": "error", "error": "internal avatar worker error"}), 500

    @flask_app.post("/internal/g004-calibration")
    def g004_calibration() -> Any:
        try:
            _require_worker_auth()
            if not _g004_paid_endpoint_enabled():
                raise CalibrationRunnerError(
                    "calibration_paid_endpoint_disabled",
                    "Paid calibration endpoint is disabled on this revision.",
                )
            payload: Dict[str, Any] = request.get_json(force=True, silent=False)
            return jsonify(execute_g004_calibration_request(payload))
        except AvatarWorkerAuthError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 401
        except CalibrationRunnerError as exc:
            status_code = (
                503
                if exc.code == "calibration_qa_not_ready"
                else 403
                if exc.code == "calibration_paid_endpoint_disabled"
                else 400
            )
            return jsonify(
                {
                    "status": "error",
                    "error": str(exc),
                    "errorCode": exc.code,
                }
            ), status_code
        except Exception:
            return jsonify({"status": "error", "error": "internal avatar worker error"}), 500

    @flask_app.post("/internal/g004-calibration-recovery")
    def g004_calibration_recovery() -> Any:
        try:
            _require_worker_auth()
            if not _g004_recovery_endpoint_enabled():
                raise CalibrationRunnerError(
                    "calibration_recovery_endpoint_disabled",
                    "Calibration recovery endpoint is disabled on this revision.",
                )
            payload: Dict[str, Any] = request.get_json(force=True, silent=False)
            return jsonify(execute_g004_calibration_recovery_request(payload))
        except AvatarWorkerAuthError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 401
        except CalibrationRunnerError as exc:
            status_code = (
                503
                if exc.code == "calibration_qa_not_ready"
                else 403
                if exc.code == "calibration_recovery_endpoint_disabled"
                else 400
            )
            return jsonify(
                {
                    "status": "error",
                    "error": str(exc),
                    "errorCode": exc.code,
                }
            ), status_code
        except Exception:
            return jsonify({"status": "error", "error": "internal avatar worker error"}), 500

    @flask_app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"status": "ok"})

    @flask_app.get("/readyz")
    def readyz() -> Any:
        body = readyz_status()
        return jsonify(body), (200 if body.get("status") == "ok" else 503)

    @flask_app.get("/internal/g004-qa-diagnostics")
    def g004_qa_diagnostics() -> Any:
        try:
            _require_worker_auth()
            if not _qa_diagnostics_enabled():
                return jsonify({"status": "error", "errorCode": "qa_diagnostics_disabled"}), 403
            return jsonify(collect_qa_runtime_diagnostics())
        except AvatarWorkerAuthError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 401
        except Exception:
            return jsonify({"status": "error", "error": "internal qa diagnostics error"}), 500

    @flask_app.post("/warmup")
    def warmup() -> Any:
        try:
            _require_worker_auth()
            return jsonify(warmup_avatar_model())
        except AvatarWorkerAuthError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 401
        except AvatarGenerationError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except Exception:
            return jsonify({"status": "error", "error": "internal avatar worker error"}), 500

    return flask_app


app = create_app() if Flask is not None else None


def main() -> None:
    if app is None:
        raise AvatarGenerationError("Flask is required for avatar worker HTTP service.")
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":  # pragma: no cover
    main()
