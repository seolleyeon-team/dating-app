from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any, Mapping


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _as_map(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _score_summary(qa: Mapping[str, Any], rerank: Mapping[str, Any]) -> dict[str, Any]:
    debug = _as_map(qa.get("debug"))
    scores = _as_map(debug.get("scores"))
    return {
        "faceSimilarityScore": qa.get("faceSimilarityScore")
        if qa.get("faceSimilarityScore") is not None
        else scores.get("faceSimilarityScore"),
        "perceptualHashDistance": scores.get("perceptualHashDistance"),
        "perceptualSimilarityScore": scores.get("perceptualSimilarityScore"),
        "clipSimilarityScore": scores.get("clipSimilarityScore"),
        "dinoStyleScore": scores.get("dinoStyleScore"),
        "traitConsistencyScore": rerank.get("traitConsistencyScore")
        or scores.get("traitConsistencyScore"),
        "brandFitScore": rerank.get("brandFitScore") or scores.get("brandFitScore"),
        "beautificationRiskScore": scores.get("beautificationRiskScore"),
        "childlikeRiskScore": scores.get("childlikeRiskScore"),
        "privacyPenalty": rerank.get("privacyPenalty") or scores.get("privacyPenalty"),
    }


def _threshold_snapshot(qa: Mapping[str, Any]) -> dict[str, Any]:
    debug = _as_map(qa.get("debug"))
    return _as_map(debug.get("thresholdSnapshot"))


def _model_availability(qa: Mapping[str, Any]) -> dict[str, Any]:
    debug = _as_map(qa.get("debug"))
    return _as_map(debug.get("modelAvailability"))


def _candidate_summary(doc_id: str, data: Mapping[str, Any], *, redact: bool) -> dict[str, Any]:
    qa = _as_map(data.get("qa"))
    rerank = _as_map(data.get("rerank"))
    candidate_id = str(data.get("candidateId") or doc_id)
    return {
        "candidateId": f"candidate:{_hash(candidate_id)}" if redact else candidate_id,
        "status": str(data.get("status") or ""),
        "selectionTier": str(rerank.get("selectionTier") or ""),
        "selectedForPreview": rerank.get("selectedForPreview") is True,
        "previewAllowed": qa.get("previewAllowed") is True,
        "softPass": qa.get("softPass") is True or qa.get("soft_pass") is True,
        "requiresHumanReview": qa.get("requiresHumanReview") is True,
        "rejectReasons": _safe_list(qa.get("rejectReasons")),
        "reviewReasons": _safe_list(qa.get("reviewReasons")),
        "softPassReasons": _safe_list(qa.get("softPassReasons")),
        "scores": _score_summary(qa, rerank),
        "thresholdSnapshot": _threshold_snapshot(qa),
        "modelAvailability": _model_availability(qa),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print redacted avatar candidate QA/rerank diagnostics."
    )
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--job_id", required=True)
    parser.add_argument("--redact", action="store_true")
    args = parser.parse_args()

    from google.cloud import firestore

    client = firestore.Client(project=args.project)
    query = (
        client.collection("avatarCandidates")
        .where("jobId", "==", args.job_id)
        .stream()
    )
    candidates = [
        _candidate_summary(snapshot.id, snapshot.to_dict() or {}, redact=args.redact)
        for snapshot in query
    ]
    candidates.sort(key=lambda item: str(item["candidateId"]))
    report = {
        "project": args.project,
        "jobId": f"job:{_hash(args.job_id)}" if args.redact else args.job_id,
        "candidateCount": len(candidates),
        "candidates": candidates,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
