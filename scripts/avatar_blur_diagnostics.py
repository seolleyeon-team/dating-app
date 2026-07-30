from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
for import_root in (REPO_ROOT, AI_MODEL_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from avatar_generation.analysis.config import SourceSafetyConfig
from avatar_generation.analysis.small_face.blur_assessment import (
    BlurAssessment,
    BlurAssessmentConfig,
    BlurAssessor,
)
from avatar_generation.analysis.small_face.config import SmallFacePipelineConfig
from avatar_generation.analysis.small_face.crop_landmarker import CropFaceLandmarker
from avatar_generation.analysis.small_face.cropper import HeadShouldersCropper
from avatar_generation.analysis.small_face.diagnostic_metrics import (
    compression_bucket,
    contrast_bucket,
    exposure_bucket,
    measure_safe_metrics,
)
from avatar_generation.analysis.small_face.diagnostic_roi import (
    DiagnosticRoi,
    canonical_downscale,
    extract_with_valid_mask,
    face_quality_roi,
    full_image_roi,
    head_shoulders_native_roi,
    resize_roi,
)
from avatar_generation.analysis.small_face.full_range_detector import FullRangeFaceDetector
from avatar_generation.analysis.small_face.neutralize import SecondaryFaceNeutralizer
from avatar_generation.analysis.small_face.nms import merge_detections_nms
from avatar_generation.analysis.small_face.orientation import ImageOrientationNormalizer
from avatar_generation.analysis.small_face.primary_selector import PrimaryFaceSelector
from avatar_generation.analysis.small_face.tile_detector import OverlappingTileDetector
from avatar_generation.preprocessing.reference import (
    ReferencePreprocessConfig,
    preprocess_reference_image,
)
from scripts.avatar_exact_consent import evaluate_exact_uid_photo_consent

ANALYZER_VERSION = "worker-00047-current-v1"
WORKER_REVISION = "seolleyeon-avatar-worker-00047-9qx"
EXPECTED_COUNT = 10


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_mapping(path: Path) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for raw in path.read_text(encoding="utf-8-sig", errors="strict").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        uid, photo = line.split("=", 1)
        uid = uid.strip().strip("<>")
        photo_path = Path(photo.strip())
        if uid and photo_path.name:
            rows.append((uid, photo_path))
    return rows


def _configure_environment(model_path: Path, landmarker_path: Path) -> None:
    os.environ.update(
        {
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
    )


def _bucket(value: float, boundaries: Iterable[tuple[float, str]], fallback: str) -> str:
    for maximum, label in boundaries:
        if value < maximum:
            return label
    return fallback


def _image_size_bucket(size: tuple[int, int]) -> str:
    edge = max(size)
    return _bucket(edge, ((720, "lt720"), (1080, "720_1079"), (1920, "1080_1919")), "ge1920")


def _face_size_bucket(short_side: int) -> str:
    return _bucket(
        short_side,
        ((32, "lt32"), (48, "32_47"), (64, "48_63"), (80, "64_79"), (120, "80_119"), (192, "120_191")),
        "ge192",
    )


def _area_bucket(value: float) -> str:
    return _bucket(value, ((0.01, "lt001"), (0.03, "001_0029"), (0.08, "003_0079"), (0.18, "008_0179")), "ge018")


def _score_bucket(value: float | None) -> str:
    if value is None:
        return "unavailable"
    return _bucket(value, ((0.4, "low"), (0.7, "moderate"), (0.9, "high")), "very_high")


def _scale_bucket(value: float) -> str:
    if value > 1.001:
        return "upscale"
    if value < 0.999:
        return "downscale"
    return "native"


def _padding_bucket(valid_ratio: float) -> str:
    padding = max(0.0, 1.0 - valid_ratio)
    return _bucket(padding, ((0.001, "none"), (0.05, "low"), (0.20, "moderate")), "high")


def _detector_pass(value: str) -> str:
    if value == "full_image":
        return "full"
    if value.startswith("tile_2"):
        return "tile_2x2"
    if value.startswith("tile_3"):
        return "tile_3x3"
    return "other"


def _old_decision(face_short_side: int, sharpness_score: float | None) -> tuple[str, str | None]:
    if face_short_side < 64:
        return "rejected", "avatar_source_face_too_small"
    if sharpness_score is not None and sharpness_score < 0.12:
        return "rejected", "avatar_source_face_too_blurry"
    return "accepted", None


def _sanitized_root_cause(assessment: BlurAssessment) -> str:
    """Map process-local evidence to the approved diagnostic taxonomy."""

    if assessment.decision == "pass":
        return "NOT_APPLICABLE"
    if assessment.root_cause in {
        "LOW_FACE_RESOLUTION",
        "LOW_LIGHT_OR_EXPOSURE",
    }:
        return assessment.root_cause
    # The current CPU signals do not identify optical-blur subtype reliably.
    return "UNKNOWN_NEEDS_MORE_EVIDENCE"


def _stage_document(roi: DiagnosticRoi) -> dict[str, object]:
    return measure_safe_metrics(roi).to_safe_document()


def _validate_inputs(
    *,
    input_dir: Path,
    mapping_file: Path,
    consent_file: Path,
    model_path: Path,
    landmarker_path: Path,
) -> list[tuple[str, Path]]:
    for required in (mapping_file, consent_file, model_path, landmarker_path):
        if not required.is_file():
            raise FileNotFoundError("Required local input is missing")
    mapping = _load_mapping(mapping_file)
    if len(mapping) != EXPECTED_COUNT:
        raise ValueError("Unexpected mapping row count")
    photos = sorted(input_dir.glob("participant_*.jpeg"))
    if len(photos) != EXPECTED_COUNT:
        raise ValueError("Unexpected local image count")
    by_name = {path.name: path for path in photos}
    normalized: list[tuple[str, Path]] = []
    for uid, mapped_path in mapping:
        local_photo = by_name.get(mapped_path.name)
        if local_photo is None:
            raise ValueError("Mapping and local image set do not match")
        normalized.append((uid, local_photo))
    normalized.sort(key=lambda item: item[1].name)
    consent = evaluate_exact_uid_photo_consent(
        consent_file=consent_file,
        expected_rows=normalized,
    )
    if not consent.get("satisfiedByThisFile") or consent.get("matchedRowCount") != EXPECTED_COUNT:
        raise ValueError("Exact-consent validation failed closed")
    return normalized


def _detect_primary(
    *,
    image,
    config: SmallFacePipelineConfig,
    detector: FullRangeFaceDetector,
    tiles: OverlappingTileDetector,
    selector: PrimaryFaceSelector,
):
    full = detector.detect(
        image,
        min_confidence=config.fallback_min_confidence,
        detector_pass="full_image",
    )
    tile_detections = []
    used_tile = False
    if tiles.should_run_tiles(full, image_width=image.size[0], image_height=image.size[1]):
        tile_detections, _ = tiles.detect(image)
        used_tile = True
    merged = merge_detections_nms(
        [*full, *tile_detections],
        iou_threshold=config.cross_pass_nms_iou,
    )
    selection = selector.select(merged)
    if selection.primary is None or selection.reason_code:
        raise ValueError("No unambiguous primary face")
    return selection, used_tile


def _diagnose_row(
    *,
    row_index: int,
    uid: str,
    photo_path: Path,
    config: SmallFacePipelineConfig,
    detector: FullRangeFaceDetector,
    tiles: OverlappingTileDetector,
    selector: PrimaryFaceSelector,
    cropper: HeadShouldersCropper,
    landmarker: CropFaceLandmarker,
    neutralizer: SecondaryFaceNeutralizer,
    blur_assessor: BlurAssessor,
) -> dict[str, object]:
    image_bytes = photo_path.read_bytes()
    normalized = ImageOrientationNormalizer().normalize(image_bytes)
    if normalized is None:
        raise ValueError(f"Row {row_index} could not be normalized")
    image = normalized.image
    selection, used_tile = _detect_primary(
        image=image,
        config=config,
        detector=detector,
        tiles=tiles,
        selector=selector,
    )
    primary = selection.primary
    assert primary is not None
    crop_result = cropper.crop(image, primary)
    landmarker_ok, _points, _reason = landmarker.run(crop_result.image)

    s0 = full_image_roi(image)
    s1 = extract_with_valid_mask(image, primary.bbox_pixels)
    s2 = face_quality_roi(image, primary.bbox_pixels, margin_ratio=0.12)
    s3 = head_shoulders_native_roi(
        image,
        primary.bbox_pixels,
        expand_horizontal=config.crop_expand_horizontal,
        expand_top=config.crop_expand_top,
        expand_bottom=config.crop_expand_bottom,
    )
    s4, canonical_scale = canonical_downscale(
        s2,
        canonical_short_side=blur_assessor.config.canonical_short_side_px,
    )
    s5, resize_scale = resize_roi(s3, crop_result.image.size)
    neutralized = neutralizer.apply(
        crop_result.image,
        secondary_faces=selection.secondary_faces,
        crop_transform=crop_result.transform,
        original_width=image.size[0],
        original_height=image.size[1],
        primary=primary,
    )
    s6 = DiagnosticRoi(
        image=neutralized.image,
        valid_mask=s5.valid_mask,
        source_box=s5.source_box,
    )
    source_analysis = {
        "faces": [
            {
                "bbox": primary.bbox_normalized.as_xywh(),
                "confidence": primary.confidence,
            }
        ]
    }
    privacy_reference = preprocess_reference_image(
        image,
        source_analysis=source_analysis,
        config=ReferencePreprocessConfig(),
        sam_enabled=False,
    )
    s7 = full_image_roi(privacy_reference.image)

    old_result, old_reason = _old_decision(
        primary.face_short_side_px,
        primary.sharpness_score,
    )
    assessment = blur_assessor.assess(image, primary)
    root_cause = _sanitized_root_cause(assessment)
    s2_metrics = measure_safe_metrics(s2)
    stage_metrics = {
        "S0": _stage_document(s0),
        "S1": _stage_document(s1),
        "S2": s2_metrics.to_safe_document(),
        "S3": _stage_document(s3),
        "S4": _stage_document(s4),
        "S5": _stage_document(s5),
        "S6": _stage_document(s6),
        "S7": _stage_document(s7),
    }
    return {
        "rowIndex": row_index,
        "uidHash": "uid:" + hashlib.sha256(uid.encode("utf-8")).hexdigest()[:12],
        "photoHashPrefix": _sha256_bytes(image_bytes)[:12],
        "analyzerVersion": ANALYZER_VERSION,
        "blurMetricVersion": assessment.metric_version,
        "blurPolicyVersion": assessment.policy_version,
        "blurCalibrationStatus": assessment.calibration_status,
        "resultBefore": old_result,
        "safeReasonBefore": old_reason,
        "originalImageSizeBucket": _image_size_bucket(image.size),
        "primaryFaceSizeBucket": _face_size_bucket(primary.face_short_side_px),
        "faceShortSidePx": primary.face_short_side_px,
        "faceAreaRatioBucket": _area_bucket(primary.face_area_ratio),
        "detectorPass": _detector_pass(primary.detector_pass),
        "usedTileFallback": used_tile,
        "detectorConfidenceBucket": _score_bucket(primary.confidence),
        "primarySelectionScoreBucket": _score_bucket(selection.primary_score),
        "cropScaleBucket": _scale_bucket(crop_result.transform.scale_x),
        "resizeScaleBucket": _scale_bucket(resize_scale),
        "canonicalScaleBucket": _scale_bucket(canonical_scale),
        "paddingRatioBucket": _padding_bucket(s3.valid_pixel_ratio),
        "landmarkerPresenceBucket": "present" if landmarker_ok else "unstable",
        "exposureBucket": exposure_bucket(s2_metrics),
        "contrastBucket": contrast_bucket(s2_metrics),
        "compressionRiskBucket": compression_bucket(s2_metrics),
        "stageMetrics": stage_metrics,
        "rootCauseCategory": root_cause,
        "proposedDecision": assessment.decision,
    }


def _markdown(report: dict[str, Any]) -> str:
    blocked = [row for row in report["rows"] if row["resultBefore"] == "rejected"]
    lines = [
        "# PR8.5 blur diagnostics",
        "",
        "Date: 2026-07-28",
        "",
        "## Result",
        "",
        f"- Status: `{report['status']}`",
        f"- Participants: {report['participantCount']}",
        f"- Previous accepted: {report['oldAcceptedCount']}",
        f"- Previous blur blocked: {report['oldBlurBlockedCount']}",
        "- Live upload: 0",
        "- Cloud mutation: none",
        "- Production ready: false",
        "",
        "S1, S2, and S4 are decision-relevant native/canonical face-quality stages. "
        "S0, S3, S5, S6, and S7 are diagnostic-only comparison stages.",
        "",
        "## Anonymous blocked rows",
        "",
        "| rowIndex | face size | exposure | contrast | compression | root cause | proposed decision |",
        "| ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for row in blocked:
        lines.append(
            f"| {row['rowIndex']} | {row['primaryFaceSizeBucket']} | "
            f"{row['exposureBucket']} | {row['contrastBucket']} | "
            f"{row['compressionRiskBucket']} | {row['rootCauseCategory']} | "
            f"{row['proposedDecision']} |"
        )
    lines.extend(
        [
            "",
            f"Shadow decisions: {report['shadowDecisionCounts']}. The current "
            "ten-row cohort is diagnostic evidence only; borderline and review "
            "outcomes remain unresolved and thresholds are not production-calibrated.",
            "",
            "The report contains only hashed participant labels and safe aggregate metrics. "
            "No live or deployment action was performed.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> dict[str, Any]:
    mapping = _validate_inputs(
        input_dir=args.input_dir,
        mapping_file=args.mapping_file,
        consent_file=args.consent_file,
        model_path=args.model_path,
        landmarker_path=args.landmarker_path,
    )
    _configure_environment(args.model_path, args.landmarker_path)
    config = SmallFacePipelineConfig.from_env()
    SourceSafetyConfig.from_env()
    detector = FullRangeFaceDetector(config)
    tiles = OverlappingTileDetector(config, detector)
    selector = PrimaryFaceSelector(config)
    cropper = HeadShouldersCropper(config)
    landmarker = CropFaceLandmarker(
        model_path=str(args.landmarker_path),
        min_detection_confidence=0.45,
        min_presence_confidence=0.50,
    )
    neutralizer = SecondaryFaceNeutralizer(config)
    blur_assessor = BlurAssessor(
        BlurAssessmentConfig(min_native_short_side_px=config.min_short_side_trait_px)
    )
    started = time.perf_counter()
    rows = [
        _diagnose_row(
            row_index=index,
            uid=uid,
            photo_path=photo,
            config=config,
            detector=detector,
            tiles=tiles,
            selector=selector,
            cropper=cropper,
            landmarker=landmarker,
            neutralizer=neutralizer,
            blur_assessor=blur_assessor,
        )
        for index, (uid, photo) in enumerate(mapping, start=1)
    ]
    old_accepted = sum(row["resultBefore"] == "accepted" for row in rows)
    old_blur = sum(
        row["safeReasonBefore"] == "avatar_source_face_too_blurry" for row in rows
    )
    shadow_decision_counts = {
        decision: sum(row["proposedDecision"] == decision for row in rows)
        for decision in sorted({str(row["proposedDecision"]) for row in rows})
    }
    report: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_LOCAL_DIAGNOSTIC",
        "workerRevision": WORKER_REVISION,
        "analyzerVersion": ANALYZER_VERSION,
        "blurMetricVersion": blur_assessor.config.metric_version,
        "blurPolicyVersion": blur_assessor.config.policy_version,
        "blurCalibrationStatus": blur_assessor.config.calibration_status,
        "participantCount": len(rows),
        "consentMatchedCount": len(mapping),
        "oldAcceptedCount": old_accepted,
        "oldBlurBlockedCount": old_blur,
        "shadowDecisionCounts": shadow_decision_counts,
        "detectorModelSha256": _sha256_file(args.model_path),
        "canonicalShortSidePx": blur_assessor.config.canonical_short_side_px,
        "elapsedMs": int((time.perf_counter() - started) * 1000),
        "rows": rows,
        "redacted": True,
        "privatePathsIncluded": False,
        "rawGeometryIncluded": False,
        "rawLandmarksIncluded": False,
        "liveUploadExecuted": False,
        "cloudMutationExecuted": False,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.write_text(_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run privacy-safe local PR8.5 blur diagnostics"
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--mapping-file", type=Path, required=True)
    parser.add_argument("--consent-file", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--landmarker-path", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    print(
        json.dumps(
            {
                "status": report["status"],
                "participantCount": report["participantCount"],
                "oldAcceptedCount": report["oldAcceptedCount"],
                "oldBlurBlockedCount": report["oldBlurBlockedCount"],
                "shadowDecisionCounts": report["shadowDecisionCounts"],
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
