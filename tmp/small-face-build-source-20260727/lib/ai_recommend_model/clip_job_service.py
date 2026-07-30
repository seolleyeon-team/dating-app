#!/usr/bin/env python3
"""HTTP service wrapper for Seolleyeon CLIP embedding jobs.

Cloud Tasks/Pub/Sub should call ``POST /tasks/clip-embedding`` with the same
``clip_job_v1`` payload accepted by ``seolleyeon_clip_job_handler.py``. This
module is intentionally thin so the CLI, tests, and service share one handler.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

try:
    from flask import Flask, jsonify, request
except Exception:  # pragma: no cover - dependency is installed in the worker image
    Flask = None  # type: ignore[assignment]
    jsonify = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]

from seolleyeon_clip_job_handler import process_clip_job_payload
from seolleyeon_rec_common_v3 import redact_private_image_ref


class ClipWorkerAuthError(PermissionError):
    pass


def _project_id() -> str:
    project = (
        os.getenv("FIRESTORE_PROJECT")
        or os.getenv("GCP_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or ""
    ).strip()
    if not project:
        raise ValueError("FIRESTORE_PROJECT or GCP_PROJECT is required")
    return project


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_production_environment() -> bool:
    return os.environ.get("ENVIRONMENT", "").strip().lower() == "production"


def _is_local_environment() -> bool:
    return os.environ.get("ENVIRONMENT", "").strip().lower() in {
        "local",
        "dev",
        "development",
        "test",
    }


def _allow_insecure_local_worker() -> bool:
    return _is_local_environment() and (
        _env_bool("ALLOW_INSECURE_WORKER_LOCAL")
        or _env_bool("CLIP_WORKER_ALLOW_INSECURE_LOCAL")
    )


def _require_shared_secret() -> None:
    if request is None:
        raise RuntimeError("flask>=3.0.0 is required")
    expected = os.getenv("CLIP_TASK_SHARED_SECRET", "").strip()
    if not expected:
        raise ClipWorkerAuthError("CLIP worker request is not authorized.")
    received = request.headers.get("X-Seolleyeon-Task-Secret", "").strip()
    if received != expected:
        raise ClipWorkerAuthError("CLIP worker request is not authorized.")


def _verify_local_shared_secret() -> None:
    """Backward-compatible wrapper for explicit shared-secret auth."""
    _require_shared_secret()


def _require_cloud_run_iam_config() -> None:
    if not _env_bool("CLIP_WORKER_CLOUD_RUN_IAM_ENFORCED"):
        raise ClipWorkerAuthError(
            "CLIP worker request is not authorized; Cloud Run IAM enforcement is not configured."
        )
    if not os.environ.get("K_SERVICE"):
        raise ClipWorkerAuthError(
            "CLIP worker request is not authorized; Cloud Run service context is missing."
        )


def _require_worker_auth() -> None:
    """Require an explicit CLIP worker auth posture before processing private media."""
    auth_mode = os.environ.get("CLIP_WORKER_AUTH_MODE", "").strip().lower()
    if _is_production_environment():
        if auth_mode == "cloud_run_iam":
            _require_cloud_run_iam_config()
            return
        if auth_mode == "shared_secret" or _env_bool("CLIP_WORKER_REQUIRE_SHARED_SECRET"):
            _require_shared_secret()
            return
        raise ClipWorkerAuthError(
            "CLIP worker request is not authorized; production auth mode is not configured."
        )

    if auth_mode == "cloud_run_iam":
        _require_cloud_run_iam_config()
        return

    if auth_mode == "shared_secret" or _env_bool("CLIP_WORKER_REQUIRE_SHARED_SECRET"):
        _require_shared_secret()
        return

    if _allow_insecure_local_worker():
        return

    raise ClipWorkerAuthError(
        "ALLOW_INSECURE_WORKER_LOCAL=true is required for unauthenticated local CLIP worker requests."
    )


def _request_payload() -> Mapping[str, Any]:
    if request is None:
        raise RuntimeError("flask>=3.0.0 is required")
    payload = request.get_json(silent=True)
    if not isinstance(payload, Mapping):
        raise ValueError("JSON request body is required")
    return payload


def create_app() -> Flask:
    if Flask is None or jsonify is None:
        raise RuntimeError("flask>=3.0.0 is required")
    app = Flask(__name__)

    @app.post("/tasks/clip-embedding")
    def tasks_clip_embedding():
        try:
            _require_worker_auth()
            result = process_clip_job_payload(
                _request_payload(),
                firestore_project=_project_id(),
                firestore_database=os.getenv("FIRESTORE_DATABASE") or None,
                private_media_collection=os.getenv(
                    "PRIVATE_MEDIA_COLLECTION", "userPrivateMedia"
                ),
                clip_embeddings_collection=os.getenv(
                    "CLIP_EMBEDDINGS_COLLECTION", "clipEmbeddings"
                ),
                device=os.getenv("CLIP_DEVICE", "auto"),
                dry_run=os.getenv("CLIP_JOB_DRY_RUN", "").lower() in {"1", "true", "yes"},
            )
        except PermissionError as exc:
            return jsonify({"status": "unauthorized", "error": str(exc)}), 401
        except Exception as exc:
            return (
                jsonify(
                    {
                        "status": "failed",
                        "error": redact_private_image_ref(str(exc)),
                    }
                ),
                500,
            )
        return jsonify(result)

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app


app = create_app() if Flask is not None else None


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
