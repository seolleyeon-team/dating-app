"""Shared utilities for the Seolleyeon recommendation pipeline."""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Structured JSON logging (Cloud Run / Cloud Logging friendly)
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """Single-line JSON per log record."""

    _SEV = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "severity": self._SEV.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for key in ("step", "run_id", "date_key", "count", "duration_s", "detail"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(step: str, run_id: str) -> logging.LoggerAdapter:
    """Return a logger that emits structured JSON to stdout."""
    logger = logging.getLogger(f"recsys.{step}")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logging.LoggerAdapter(logger, {"step": step, "run_id": run_id})


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def get_default_date_key() -> str:
    """Today's YYYYMMDD in KST."""
    return datetime.now(KST).strftime("%Y%m%d")


def generate_run_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# GCS helpers
# ---------------------------------------------------------------------------

def gcs_upload_string(
    bucket_name: str,
    blob_path: str,
    data: str,
    project: Optional[str] = None,
    content_type: str = "text/csv",
) -> str:
    """Upload string data to GCS. Returns gs:// URI."""
    from google.cloud import storage
    client = storage.Client(project=project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{bucket_name}/{blob_path}"


def gcs_download_to_file(
    bucket_name: str,
    blob_path: str,
    local_path: str,
    project: Optional[str] = None,
) -> None:
    """Download a GCS blob to a local file."""
    from google.cloud import storage
    client = storage.Client(project=project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)
