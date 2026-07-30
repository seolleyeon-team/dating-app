from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PRIVATE_OUTPUT_PATTERNS = (
    re.compile(r"gs://", re.IGNORECASE),
    re.compile(r"gcs://", re.IGNORECASE),
    re.compile(r"sourcePhotoRefs?", re.IGNORECASE),
    re.compile(r"sourcePhotoGcsUri", re.IGNORECASE),
    re.compile(r"\bgcsUri\b", re.IGNORECASE),
    re.compile(r"userPrivateMedia", re.IGNORECASE),
    re.compile(r"clipEmbeddings", re.IGNORECASE),
    re.compile(r"X-Goog-Signature", re.IGNORECASE),
    re.compile(r"X-Goog-Credential", re.IGNORECASE),
    re.compile(r"GoogleAccessId", re.IGNORECASE),
    re.compile(r"Signature=", re.IGNORECASE),
    re.compile(r"signedUrl", re.IGNORECASE),
    re.compile(r"seolleyeon(?:-final)?-private-source-photos", re.IGNORECASE),
    re.compile(r"seolleyeon(?:-final)?-avatar-temp", re.IGNORECASE),
)

RAW_KEYS = {
    "rawLandmarks",
    "raw_landmarks",
    "faceLandmarks",
    "face_landmarks",
    "landmarks",
    "blendshapes",
    "rawBlendshapes",
    "rawEmbeddings",
    "embeddings",
}

EXPANDED_FIELDS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("hair_bangs", ("hair", "bangs"), ("hair_bangs",)),
    ("facial_hair_present", ("facialHair", "present"), ("facial_hair_present",)),
    ("facial_hair_style", ("facialHair", "broadStyle"), ("facial_hair_style",)),
    (
        "facial_feature_balance",
        ("faceImpression", "facialFeatureBalance"),
        ("facial_feature_balance",),
    ),
    ("eye_shape_mood", ("faceImpression", "eyeShapeMood"), ("eye_shape_mood",)),
    ("brow_shape", ("faceImpression", "browShape"), ("brow_shape",)),
    (
        "nose_bridge_impression",
        ("faceImpression", "noseBridgeImpression"),
        ("nose_bridge_impression",),
    ),
    (
        "mouth_fullness_category",
        ("faceImpression", "mouthFullnessCategory"),
        ("mouth_fullness_category",),
    ),
)


def _hash_text(value: Any, *, length: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _safe_id(value: Any, prefix: str, *, redact: bool) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"{prefix}:{_hash_text(text)}" if redact else text


def _as_map(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "to_datetime"):
        try:
            dt = value.to_datetime()
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = _timestamp(value)
    if parsed is None:
        raise ValueError(f"Invalid --since ISO timestamp: {value}")
    return parsed


def _get_path(data: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _camelize_snake(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _trait_card_payload(job: Mapping[str, Any]) -> dict[str, Any]:
    wrapper = _as_map(job.get("traitCard"))
    nested = wrapper.get("traitCard") if isinstance(wrapper.get("traitCard"), Mapping) else None
    trait = _as_map(nested) if nested is not None else wrapper

    if any(key in trait for key in ("hair_bangs", "facial_hair_present", "eye_shape_mood")):
        return trait

    flattened: dict[str, Any] = {}
    for _, nested_path, flat_path in EXPANDED_FIELDS:
        value = _get_path(trait, nested_path)
        if value is not None:
            flattened[flat_path[0]] = value
    return flattened or trait


def _broad_trait_hints(job: Mapping[str, Any]) -> dict[str, Any]:
    source = _as_map(job.get("sourceAnalysis"))
    return _as_map(source.get("broadTraitHints"))


def _value_for_field(trait_card: Mapping[str, Any], field: str) -> Any:
    if field in trait_card:
        return trait_card.get(field)
    camel = _camelize_snake(field)
    if camel in trait_card:
        return trait_card.get(camel)
    return None


def _field_source(field: str, value: Any, hints: Mapping[str, Any], wrapper: Mapping[str, Any]) -> str:
    field_sources = _as_map(wrapper.get("fieldSources") or wrapper.get("field_sources"))
    if field_sources.get(field):
        return str(field_sources[field])
    hint_value = hints.get(field)
    if hint_value is None:
        hint_value = hints.get(_camelize_snake(field))
    if hint_value not in (None, "", "unclear") and str(hint_value) == str(value):
        return "mediapipe_hint"
    if value in (None, "", "unclear"):
        return "validator_default_or_missing"
    return "vlm_or_merge"


def _raw_key_hits(value: Any, prefix: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key) in RAW_KEYS:
                hits.append(path)
            hits.extend(_raw_key_hits(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_raw_key_hits(child, f"{prefix}[{index}]"))
    return hits


def summarize_job(job_id: str, job: Mapping[str, Any], *, redact: bool) -> dict[str, Any]:
    source = _as_map(job.get("sourceAnalysis"))
    model_availability = _as_map(source.get("modelAvailability"))
    wrapper = _as_map(job.get("traitCard"))
    trait_card = _trait_card_payload(job)
    hints = _broad_trait_hints(job)

    fields: dict[str, dict[str, Any]] = {}
    non_unclear = 0
    for field, _, _ in EXPANDED_FIELDS:
        value = _value_for_field(trait_card, field)
        unclear = value in (None, "", "unclear")
        if not unclear:
            non_unclear += 1
        fields[field] = {
            "value": "unclear" if unclear else value,
            "unclear": bool(unclear),
            "source": _field_source(field, value, hints, wrapper),
        }

    total = len(EXPANDED_FIELDS)
    diagnosis = "ok"
    if non_unclear == 0:
        if not wrapper:
            diagnosis = "trait_card_missing"
        elif hints:
            diagnosis = "broad_hints_present_but_trait_card_unclear"
        elif model_availability.get("mediapipe") != "available":
            diagnosis = "mediapipe_unavailable_or_not_recorded"
        else:
            diagnosis = "vlm_or_validator_returned_unclear"

    return {
        "jobId": _safe_id(job_id, "job", redact=redact),
        "uidHash": _safe_id(job.get("uid"), "uid", redact=True),
        "status": str(job.get("status") or ""),
        "createdAt": str(_timestamp(job.get("createdAt")) or ""),
        "sourceAnalysis": {
            "modelAvailability": {
                "mediapipe": str(model_availability.get("mediapipe") or ""),
                "faceDetector": str(model_availability.get("faceDetector") or ""),
            },
            "faceCount": source.get("faceCount"),
            "singlePerson": source.get("singlePerson"),
            "broadTraitHintsPresent": bool(hints),
            "broadTraitHintFields": sorted(str(key) for key in hints.keys()),
        },
        "traitCardPresent": bool(wrapper),
        "expandedFields": fields,
        "coverage": {
            "totalExpandedFields": total,
            "nonUnclearCount": non_unclear,
            "unclearCount": total - non_unclear,
            "coveragePercentage": round((non_unclear / total) * 100.0, 2),
        },
        "diagnosis": diagnosis,
        "rawAnalysisKeyHits": _raw_key_hits({"sourceAnalysis": source, "traitCard": wrapper}),
    }


def _candidate_docs_from_fixture(data: Mapping[str, Any], job_id: str) -> list[Mapping[str, Any]]:
    return [
        dict(value)
        for value in _as_map(data.get("avatarCandidates")).values()
        if isinstance(value, Mapping) and str(value.get("jobId") or "") == job_id
    ]


def _jobs_from_fixture(data: Mapping[str, Any], uids: set[str], since: datetime | None) -> list[tuple[str, Mapping[str, Any]]]:
    rows = []
    for job_id, job in _as_map(data.get("avatarJobs")).items():
        if not isinstance(job, Mapping):
            continue
        if uids and str(job.get("uid") or "") not in uids:
            continue
        created = _timestamp(job.get("createdAt") or job.get("updatedAt"))
        if since and created and created < since:
            continue
        rows.append((str(job_id), job))
    return rows


def _load_live_jobs(project: str, uids: set[str], since: datetime | None) -> list[tuple[str, Mapping[str, Any]]]:
    try:
        from google.cloud import firestore  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError(f"google-cloud-firestore unavailable: {exc}") from exc

    client = firestore.Client(project=project)
    rows: list[tuple[str, Mapping[str, Any]]] = []
    for uid in sorted(uids):
        query = client.collection("avatarJobs").where("uid", "==", uid)
        for snapshot in query.stream():
            data = snapshot.to_dict() or {}
            created = _timestamp(data.get("createdAt") or data.get("updatedAt"))
            if since and created and created < since:
                continue
            rows.append((snapshot.id, data))
    rows.sort(key=lambda item: str(_timestamp(item[1].get("createdAt")) or ""), reverse=True)
    return rows


def _assert_safe_output(report: Mapping[str, Any]) -> None:
    text = json.dumps(report, ensure_ascii=False, default=str)
    for pattern in PRIVATE_OUTPUT_PATTERNS:
        if pattern.search(text):
            raise RuntimeError(f"Unsafe private value in trait coverage report: {pattern.pattern}")
    if "rawLandmarks" in text or "face_landmarks" in text:
        raise RuntimeError("Raw landmark key leaked into trait coverage report")


def write_csv(path: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "jobId",
        "uidHash",
        "status",
        "mediapipe",
        "faceDetector",
        "broadTraitHintsPresent",
        "nonUnclearCount",
        "unclearCount",
        "coveragePercentage",
        "diagnosis",
    ] + [field for field, _, _ in EXPANDED_FIELDS]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for job in jobs:
            row = {
                "jobId": job.get("jobId"),
                "uidHash": job.get("uidHash"),
                "status": job.get("status"),
                "mediapipe": _as_map(_as_map(job.get("sourceAnalysis")).get("modelAvailability")).get("mediapipe"),
                "faceDetector": _as_map(_as_map(job.get("sourceAnalysis")).get("modelAvailability")).get("faceDetector"),
                "broadTraitHintsPresent": _as_map(job.get("sourceAnalysis")).get("broadTraitHintsPresent"),
                "nonUnclearCount": _as_map(job.get("coverage")).get("nonUnclearCount"),
                "unclearCount": _as_map(job.get("coverage")).get("unclearCount"),
                "coveragePercentage": _as_map(job.get("coverage")).get("coveragePercentage"),
                "diagnosis": job.get("diagnosis"),
            }
            fields = _as_map(job.get("expandedFields"))
            for field, _, _ in EXPANDED_FIELDS:
                row[field] = _as_map(fields.get(field)).get("value")
            writer.writerow(row)


def build_report(
    *,
    project: str,
    uids: set[str],
    since: datetime | None,
    fixture_json: Path | None,
    redact: bool,
) -> dict[str, Any]:
    if fixture_json:
        fixture = json.loads(fixture_json.read_text(encoding="utf-8"))
        job_rows = _jobs_from_fixture(fixture, uids, since)
    else:
        job_rows = _load_live_jobs(project, uids, since)

    jobs = [summarize_job(job_id, job, redact=redact) for job_id, job in job_rows]
    coverage_values = [
        float(_as_map(job.get("coverage")).get("coveragePercentage") or 0.0)
        for job in jobs
    ]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "since": since.isoformat() if since else "",
        "uidCount": len(uids),
        "jobCount": len(jobs),
        "summary": {
            "averageCoveragePercentage": round(sum(coverage_values) / len(coverage_values), 2)
            if coverage_values
            else 0.0,
            "allExpandedFieldsUnclearCount": sum(
                1
                for job in jobs
                if _as_map(job.get("coverage")).get("nonUnclearCount") == 0
            ),
            "diagnosisCounts": {},
        },
        "jobs": jobs,
    }
    diagnosis_counts: dict[str, int] = {}
    for job in jobs:
        diagnosis = str(job.get("diagnosis") or "unknown")
        diagnosis_counts[diagnosis] = diagnosis_counts.get(diagnosis, 0) + 1
    report["summary"]["diagnosisCounts"] = diagnosis_counts
    _assert_safe_output(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report avatar trait coverage for canary jobs.")
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--uids", required=True)
    parser.add_argument("--since")
    parser.add_argument("--output_json", required=True)
    parser.add_argument("--output_csv")
    parser.add_argument("--redact", action="store_true")
    parser.add_argument("--fixture_json")
    args = parser.parse_args(argv)

    uids = {uid.strip() for uid in args.uids.split(",") if uid.strip()}
    report = build_report(
        project=args.project,
        uids=uids,
        since=_parse_since(args.since),
        fixture_json=Path(args.fixture_json) if args.fixture_json else None,
        redact=args.redact,
    )
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_csv:
        write_csv(Path(args.output_csv), report["jobs"])
    print(
        json.dumps(
            {
                "output": str(output_json.resolve()),
                "jobCount": report["jobCount"],
                "averageCoveragePercentage": report["summary"]["averageCoveragePercentage"],
                "diagnosisCounts": report["summary"]["diagnosisCounts"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
