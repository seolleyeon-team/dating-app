"""Persist explicit model source status for verification and diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None


def write_source_status(
    *,
    project: str,
    date_key: str,
    source: str,
    status: str,
    reason: str,
    user_ids: Iterable[str] | None = None,
    database: str | None = None,
    policy_provenance: Mapping[str, Any] | None = None,
) -> int:
    """Write a current-date status document for every real actor.

    ``policy_provenance`` 는 이 문서가 어떤 생활권 정책 상태에서 만들어졌는지를
    담는다. 학습 데이터가 없어 모델을 만들지 못한 경우에도 정책 세대는 기록해야
    한다 — 모델 가용성과 정책 epoch 는 서로 다른 정보이고, 활성화 이후의 검증은
    provenance 가 없는 문서를 신뢰하지 않는다.
    """
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed")
    db = firestore.Client(project=project, database=database)
    if user_ids is None:
        user_ids = [doc.id for doc in db.collection("users").list_documents()]
    batch = db.batch()
    count = 0
    for uid in sorted({str(value) for value in user_ids if str(value).strip()}):
        ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/{source}")
        payload: dict[str, Any] = {
            "status": status,
            "reason": reason,
            "algorithmVersion": f"{source}_status_{date_key}",
            "generatedAt": firestore.SERVER_TIMESTAMP,
            "topN": 0,
            "items": [],
            "modelStatus": {
                "source": source,
                "status": status,
                "reason": reason,
                "recordedAt": datetime.now(tz=timezone.utc).isoformat(),
            },
        }
        if policy_provenance is not None:
            payload["policy"] = dict(policy_provenance)
        batch.set(ref, payload, merge=True)
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
    if count % 400:
        batch.commit()
    return count


__all__ = ["write_source_status"]
