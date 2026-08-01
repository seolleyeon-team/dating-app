#!/usr/bin/env python3
"""Audit staging avatar jobs created before the current source/job contract.

The report intentionally avoids full sourcePhotoRefs and private GCS paths.
Apply mode only marks old, non-approved jobs as superseded; it never deletes
source photos or approved avatars.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


TERMINAL_KEEP_STATUSES = {"approved"}
MUTABLE_OLD_STATUSES = {
    "",
    "queued",
    "enqueued",
    "running",
    "generating",
    "qa_pending",
    "preview_ready",
    "needs_review",
    "no_previewable_candidates",
    "failed",
}


def _hash_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _is_production_project(project: str) -> bool:
    normalized = project.strip().lower()
    return normalized == "seolleyeon" or normalized.endswith("-prod")


def _as_dict(snapshot: Any) -> dict[str, Any]:
    data = snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
    return dict(data or {})


def _source_count(job: Mapping[str, Any]) -> int:
    refs = job.get("sourcePhotoRefs")
    return len(refs) if isinstance(refs, list) else 0


def _safe_job_row(job_id: str, job: Mapping[str, Any], private_doc: Mapping[str, Any]) -> dict[str, Any]:
    uid = str(job.get("uid") or "")
    current_job = str(private_doc.get("currentAvatarJobId") or "")
    current_source = str(private_doc.get("currentAvatarSourcePhotoId") or "")
    source_ids = job.get("sourcePhotoIds") if isinstance(job.get("sourcePhotoIds"), list) else []
    job_source = str(source_ids[0]) if source_ids else ""
    return {
        "jobIdHash": _hash_id(job_id),
        "uidHash": _hash_id(uid),
        "status": str(job.get("status") or ""),
        "avatarSourceSelectionVersion": job.get("avatarSourceSelectionVersion"),
        "hasCurrentAvatarJobId": bool(current_job),
        "hasCurrentAvatarSourcePhotoId": bool(current_source),
        "currentJobMatch": bool(current_job and current_job == job_id),
        "currentSourceMatch": bool(current_source and current_source == job_source),
        "sourcePhotoRefsCount": _source_count(job),
        "sourcePhotoIdHash": _hash_id(job_source) if job_source else "",
    }


def _load_private_doc(db: Any, uid: str) -> dict[str, Any]:
    if not uid:
        return {}
    snap = db.collection("userPrivateMedia").document(uid).get()
    return _as_dict(snap) if getattr(snap, "exists", False) else {}


def audit(project: str, *, limit: int, apply: bool) -> dict[str, Any]:
    if _is_production_project(project):
        raise SystemExit(f"Refusing to audit/apply against production-like project: {project}")

    from google.cloud import firestore

    db = firestore.Client(project=project)
    query = db.collection("avatarJobs").limit(limit)

    old_contract: list[dict[str, Any]] = []
    preview_not_current: list[dict[str, Any]] = []
    mutations: list[dict[str, Any]] = []

    for snap in query.stream():
        job_id = snap.id
        job = _as_dict(snap)
        uid = str(job.get("uid") or "")
        private_doc = _load_private_doc(db, uid)
        row = _safe_job_row(job_id, job, private_doc)
        is_old_contract = job.get("avatarSourceSelectionVersion") in {None, ""}
        if is_old_contract or not row["hasCurrentAvatarJobId"] or not row["hasCurrentAvatarSourcePhotoId"]:
            old_contract.append(row)

        if row["status"] == "preview_ready" and not row["currentJobMatch"]:
            preview_not_current.append(row)

        status = row["status"]
        if (
            apply
            and is_old_contract
            and status not in TERMINAL_KEEP_STATUSES
            and status in MUTABLE_OLD_STATUSES
        ):
            snap.reference.set(
                {
                    "status": "superseded",
                    "errorCode": "avatar_job_superseded_old_contract",
                    "errorMessage": "Staging cleanup: job predates current avatar source/job contract.",
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            mutations.append({"jobIdHash": row["jobIdHash"], "newStatus": "superseded"})

    return {
        "project": project,
        "mode": "apply" if apply else "dry_run",
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
        "scannedLimit": limit,
        "oldContractCount": len(old_contract),
        "previewReadyNotCurrentCount": len(preview_not_current),
        "mutationCount": len(mutations),
        "oldContractSamples": old_contract[:50],
        "previewReadyNotCurrentSamples": preview_not_current[:50],
        "mutations": mutations[:100],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report_json", default="")
    args = parser.parse_args()

    report = audit(args.project, limit=max(1, args.limit), apply=bool(args.apply))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report_json:
        path = Path(args.report_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
