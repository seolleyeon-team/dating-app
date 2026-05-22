from __future__ import annotations

import os
from typing import Any, Dict

try:
    from flask import Flask, jsonify, request
except Exception:  # pragma: no cover - dependency is required in the worker image
    Flask = None  # type: ignore[assignment]
    jsonify = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]

from avatar_generation.worker import (
    AvatarGenerationError,
    is_production_environment,
    model_cache_metrics,
    process_avatar_generation_batch_payload,
    process_avatar_generation_drain,
    process_avatar_generation_payload,
    warmup_avatar_model,
)


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


def readyz_status() -> Dict[str, Any]:
    auth_mode = os.environ.get("AVATAR_WORKER_AUTH_MODE", "").strip().lower()
    if not auth_mode and _allow_insecure_local_worker():
        auth_mode = "local_insecure"
    return {
        "status": "ok",
        "authMode": auth_mode or "not_configured",
        "production": is_production_environment(),
        "batchDrainEnabled": _batch_drain_enabled(),
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
        except AvatarGenerationError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except Exception:
            return jsonify({"status": "error", "error": "internal avatar worker error"}), 500

    @flask_app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"status": "ok"})

    @flask_app.get("/readyz")
    def readyz() -> Any:
        return jsonify(readyz_status())

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
