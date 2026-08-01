from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
AVATAR_LIB = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AVATAR_LIB) not in sys.path:
    sys.path.insert(0, str(AVATAR_LIB))

from avatar_generation.analysis.config import SourceSafetyConfig
from avatar_generation.analysis.detectors import StaticFaceDetector
from avatar_generation.analysis.schema import FaceDetection
from avatar_generation.analysis.source_analyzer import analyze_avatar_source_image
from avatar_generation.preprocessing.reference import (
    ReferencePreprocessConfig,
    preprocess_reference_image,
)


FORBIDDEN_MARKERS = (
    "sourcePhotoRefs",
    "sourcePhotoGcsUri",
    "gcsUri",
    "userPrivateMedia",
    "clipEmbeddings",
    "gs://",
    "gcs://",
    "signedUrl",
    "X-Goog-Signature",
    "GoogleAccessId",
    "seolleyeon-final-private-source-photos",
    "seolleyeon-final-avatar-temp",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_text(value: Any, *, length: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _load_mapping(path: Path, canary_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        uid, photo = line.split("=", 1)
        photo_path = Path(photo.strip())
        resolved = photo_path if photo_path.is_file() else canary_root / photo_path.name
        rows.append(
            {
                "uidHash": f"uid:{_hash_text(uid)}",
                "photoFile": photo_path.name,
                "path": resolved,
                "exists": resolved.is_file(),
            }
        )
    return rows


def _analysis_config() -> SourceSafetyConfig:
    return SourceSafetyConfig(
        mediapipe_enabled=False,
        mediapipe_fail_closed_in_production=False,
        primary_face_min_score_margin=0.20,
        primary_face_min_relative_area=0.04,
        allow_small_background_faces_if_removed=True,
        reject_large_secondary_face=True,
    )


def _analyze(image: Image.Image, faces: Sequence[FaceDetection]) -> Mapping[str, Any]:
    result = analyze_avatar_source_image(
        image,
        source_ref="local://canary-smoke-redacted.jpg",
        detector=StaticFaceDetector(faces, provider_name="smoke_static"),
        config=_analysis_config(),
    )
    return result.to_document()


def _reference_preprocess(image: Image.Image, analysis: Mapping[str, Any]) -> Mapping[str, Any]:
    result = preprocess_reference_image(
        image,
        source_analysis=analysis,
        config=ReferencePreprocessConfig(
            primary_crop_enabled=True,
            background_neutralization_enabled=True,
            background_neutral_color="#F7F2EC",
            background_text_logo_blur=True,
        ),
    )
    return result.metadata


def _safe_json(value: Mapping[str, Any]) -> bool:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    return not any(marker in encoded for marker in FORBIDDEN_MARKERS)


def _load_staging_preview_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "previewReadyCount": 0, "safeResponse": False}
    report = json.loads(path.read_text(encoding="utf-8"))
    jobs = report.get("jobs") if isinstance(report.get("jobs"), list) else []
    preview_ready = 0
    safe_response = report.get("responseSafetyViolationCount") == 0
    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        job_doc = job.get("job") if isinstance(job.get("job"), Mapping) else {}
        preview_api = (
            job.get("previewApi") if isinstance(job.get("previewApi"), Mapping) else {}
        )
        if job_doc.get("status") == "preview_ready":
            preview_ready += 1
        if preview_api.get("safeResponse") is False:
            safe_response = False
    return {
        "present": True,
        "status": report.get("status"),
        "jobCount": len(jobs),
        "previewReadyCount": preview_ready,
        "safeResponse": safe_response,
        "source": path.name,
    }


def build_report(
    *,
    mapping_file: Path,
    canary_root: Path,
    staging_runner_report: Path,
) -> dict[str, Any]:
    rows = _load_mapping(mapping_file, canary_root)
    selected = [row for row in rows if row["exists"]][:3]
    report: dict[str, Any] = {
        "generatedAt": _now(),
        "status": "BLOCKED_MISSING_CANARY_FIXTURES",
        "mappingFile": mapping_file.name,
        "canaryRoot": str(canary_root),
        "rows": [
            {
                "uidHash": row["uidHash"],
                "photoFile": row["photoFile"],
                "exists": row["exists"],
            }
            for row in rows
        ],
        "checks": {},
        "stagingPreviewEvidence": _load_staging_preview_evidence(staging_runner_report),
        "redacted": True,
    }
    if len(selected) < 3:
        report["safeReport"] = _safe_json(report)
        return report

    simple = Image.open(selected[0]["path"]).convert("RGB")
    complex_image = Image.open(selected[1]["path"]).convert("RGB")
    group = Image.open(selected[2]["path"]).convert("RGB")

    simple_analysis = _analyze(
        simple,
        [FaceDetection(bbox=(0.35, 0.18, 0.30, 0.27), confidence=0.98)],
    )
    complex_analysis = _analyze(
        complex_image,
        [
            FaceDetection(bbox=(0.31, 0.18, 0.30, 0.27), confidence=0.98),
            FaceDetection(bbox=(0.82, 0.16, 0.07, 0.07), confidence=0.78),
        ],
    )
    group_analysis = _analyze(
        group,
        [
            FaceDetection(bbox=(0.18, 0.18, 0.30, 0.27), confidence=0.96),
            FaceDetection(bbox=(0.53, 0.18, 0.30, 0.27), confidence=0.95),
        ],
    )
    complex_preprocess = _reference_preprocess(complex_image, complex_analysis)
    staging_preview = report["stagingPreviewEvidence"]

    report["checks"] = {
        "simpleBackgroundAccepted": simple_analysis.get("status") == "accepted",
        "complexBackgroundAccepted": complex_analysis.get("status") == "accepted",
        "complexBackgroundNeutralized": complex_preprocess.get("backgroundNeutralized")
        is True,
        "complexPrimaryCropApplied": complex_preprocess.get("primaryCropApplied") is True,
        "complexBackgroundFaceRisk": complex_analysis.get("backgroundFaceRisk"),
        "groupPhotoRejected": group_analysis.get("hardReject") is True
        and "multi_face_primary" in (group_analysis.get("rejectReasons") or []),
        "stagingPreviewReadyIfPossible": (
            staging_preview.get("present") is True
            and int(staging_preview.get("previewReadyCount") or 0) > 0
        ),
        "noPrivateLeak": True,
    }
    report["metadata"] = {
        "simpleSourceAnalysis": simple_analysis,
        "complexSourceAnalysis": complex_analysis,
        "complexReferencePreprocess": complex_preprocess,
        "groupSourceAnalysis": group_analysis,
    }
    report["safeReport"] = _safe_json(report)
    report["checks"]["noPrivateLeak"] = bool(report["safeReport"]) and bool(
        staging_preview.get("safeResponse")
    )
    report["status"] = (
        "PASS"
        if all(bool(value) for value in report["checks"].values())
        else "FAIL"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local complex-background avatar canary smoke."
    )
    parser.add_argument("--mapping_file", required=True)
    parser.add_argument("--canary_root", default="canary_inputs/normalized")
    parser.add_argument("--staging_runner_report", default="out/pr84_canary_runner_apply.json")
    parser.add_argument("--output_json", required=True)
    args = parser.parse_args(argv)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(
        mapping_file=Path(args.mapping_file),
        canary_root=Path(args.canary_root),
        staging_runner_report=Path(args.staging_runner_report),
    )
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "status": report["status"],
                "checks": report.get("checks", {}),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
