from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.config import SourceSafetyConfig
from avatar_generation.analysis.small_face import (
    SmallFacePipelineConfig,
    SmallFaceSourcePipeline,
)
from avatar_generation.analysis.source_analyzer import analyze_avatar_source_image


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sharpness_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    return "ge012" if value >= 0.12 else "lt012"


def _recommendation(
    *, analyzer_status: str, reject_reasons: list[str], pipeline_reason: str | None
) -> str:
    if analyzer_status == "accepted":
        return "PASS"
    if "no_face" in reject_reasons:
        return "BLOCK_NO_FACE"
    if any(
        reason in reject_reasons
        for reason in ("multi_face_primary", "multiple_faces", "ambiguous_primary_face")
    ):
        return "BLOCK_MULTI_FACE"
    if pipeline_reason == "avatar_source_face_too_blurry":
        return "BLOCK_LOW_QUALITY"
    if "face_too_small" in reject_reasons:
        return "BLOCK_FACE_TOO_SMALL"
    return "BLOCK_LOW_QUALITY"


def _configure_environment(model_path: Path, landmarker_path: Path) -> None:
    values = {
        "ENVIRONMENT": "staging",
        "AVATAR_SMALL_FACE_PIPELINE_ENABLED": "true",
        "AVATAR_FACE_FULL_RANGE_ENABLED": "true",
        "AVATAR_FACE_TILE_FALLBACK_ENABLED": "true",
        "AVATAR_FACE_DETECT_MODEL_PATH": str(model_path),
        "AVATAR_MEDIAPIPE_FACE_LANDMARKER_MODEL_PATH": str(landmarker_path),
        "AVATAR_FACE_TILE_GRIDS": "2,3",
        "AVATAR_FACE_TILE_OVERLAP": "0.25",
        "AVATAR_FACE_CROSS_PASS_NMS_IOU": "0.35",
        "AVATAR_FACE_MIN_SHORT_SIDE_DETECT_PX": "48",
        "AVATAR_FACE_MIN_SHORT_SIDE_TRAIT_PX": "64",
        "AVATAR_PRIMARY_CROP_TARGET_SIZE": "512",
        "AVATAR_PRIMARY_CROP_MAX_SIZE": "768",
        "AVATAR_ALLOW_SMALL_BACKGROUND_FACES_IF_REMOVED": "true",
        "AVATAR_REJECT_LARGE_SECONDARY_FACE": "true",
    }
    os.environ.update(values)


def run_parity(
    *,
    input_dir: Path,
    model_path: Path,
    landmarker_path: Path,
    worker_revision: str,
    output_path: Path,
    expected_count: int,
) -> dict[str, Any]:
    if not model_path.is_file():
        raise FileNotFoundError(f"Detector model is missing: {model_path.name}")
    if not landmarker_path.is_file():
        raise FileNotFoundError(f"Landmarker model is missing: {landmarker_path.name}")

    photos = sorted(input_dir.glob("participant_*.jpeg"))
    if len(photos) != expected_count:
        raise ValueError(
            f"Expected {expected_count} participant JPEGs, found {len(photos)}"
        )

    _configure_environment(model_path, landmarker_path)
    pipeline_config = SmallFacePipelineConfig.from_env()
    source_config = SourceSafetyConfig.from_env()
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()

    for photo in photos:
        image_bytes = photo.read_bytes()
        pipeline = SmallFaceSourcePipeline(
            config=pipeline_config,
            source_config=source_config,
            landmarker_model_path=str(landmarker_path),
        )
        pipeline_result = pipeline.run(image_bytes)
        analyzer_result = analyze_avatar_source_image(
            image_bytes,
            source_ref=f"redacted:{photo.name}",
            config=source_config,
            small_face_config=pipeline_config,
        )
        primary = pipeline_result.analysis.primary_detection
        metrics = pipeline_result.analysis.metrics
        usable = bool(pipeline_result.analysis.avatar_usable)
        accepted = analyzer_result.status == "accepted"
        recommendation = _recommendation(
            analyzer_status=analyzer_result.status,
            reject_reasons=list(analyzer_result.reject_reasons),
            pipeline_reason=pipeline_result.analysis.reason_code,
        )
        rows.append(
            {
                "case": photo.name,
                "faceDetected": bool(pipeline_result.analysis.face_detected),
                "faceCount": int(analyzer_result.face_count),
                "recommendation": recommendation,
                "pipelineUsable": usable,
                "pipelineReason": pipeline_result.analysis.reason_code,
                "primaryFaceSizeBucket": metrics.get("primaryFaceSizeBucket"),
                "sharpnessScoreBucket": _sharpness_bucket(
                    primary.sharpness_score if primary is not None else None
                ),
                "analyzerStatus": analyzer_result.status,
                "analyzerReasons": list(analyzer_result.reject_reasons),
                "pipelineAnalyzerConflict": usable != accepted,
                "usedTileFallback": bool(
                    pipeline_result.analysis.used_tile_fallback
                ),
            }
        )

    face_detected_count = sum(bool(row["faceDetected"]) for row in rows)
    pipeline_usable_count = sum(bool(row["pipelineUsable"]) for row in rows)
    analyzer_accepted_count = sum(
        row["analyzerStatus"] == "accepted" for row in rows
    )
    conflict_count = sum(bool(row["pipelineAnalyzerConflict"]) for row in rows)
    blur_blocked_count = sum(
        row["pipelineReason"] == "avatar_source_face_too_blurry" for row in rows
    )
    recommendation_counts: dict[str, int] = {}
    for row in rows:
        recommendation = str(row["recommendation"])
        recommendation_counts[recommendation] = (
            recommendation_counts.get(recommendation, 0) + 1
        )
    preflight_images = [
        {
            "inputFile": row["case"],
            "normalizedFile": row["case"],
            "exists": True,
            "plainJpeg": True,
            "faceCount": row["faceCount"],
            "recommendation": row["recommendation"],
            "error": "",
        }
        for row in rows
    ]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_DEPLOYED_ANALYZER_PARITY"
            if conflict_count == 0
            else "FAILED_ANALYZER_PARITY"
        ),
        "project": "seolleyeon-final",
        "provider": "small_face_pipeline_full_range_tiles_crop_landmarker",
        "workerRevision": worker_revision,
        "modelSha256": _sha256(model_path),
        "participantCount": len(rows),
        "faceDetectedCount": face_detected_count,
        "pipelineUsableCount": pipeline_usable_count,
        "analyzerAcceptedCount": analyzer_accepted_count,
        "pipelineAnalyzerConflictCount": conflict_count,
        "blurQualityBlockedCount": blur_blocked_count,
        "tileFallbackCount": sum(bool(row["usedTileFallback"]) for row in rows),
        "totalElapsedMs": int((time.perf_counter() - started) * 1000),
        "liveUploadExecuted": False,
        "recommendationCounts": recommendation_counts,
        "images": preflight_images,
        "rows": rows,
        "redacted": True,
        "privatePathsIncluded": False,
        "rawGeometryIncluded": False,
        "rawLandmarksIncluded": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run redacted small-face pipeline/analyzer parity on local JPEG fixtures."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--landmarker-path", type=Path, required=True)
    parser.add_argument("--worker-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=10)
    args = parser.parse_args()

    report = run_parity(
        input_dir=args.input_dir,
        model_path=args.model_path,
        landmarker_path=args.landmarker_path,
        worker_revision=args.worker_revision,
        output_path=args.output,
        expected_count=args.expected_count,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "participantCount": report["participantCount"],
                "faceDetectedCount": report["faceDetectedCount"],
                "pipelineUsableCount": report["pipelineUsableCount"],
                "analyzerAcceptedCount": report["analyzerAcceptedCount"],
                "pipelineAnalyzerConflictCount": report[
                    "pipelineAnalyzerConflictCount"
                ],
                "blurQualityBlockedCount": report["blurQualityBlockedCount"],
            },
            separators=(",", ":"),
        )
    )
    return 0 if report["status"] == "PASS_DEPLOYED_ANALYZER_PARITY" else 1


if __name__ == "__main__":
    raise SystemExit(main())