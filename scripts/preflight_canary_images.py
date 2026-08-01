from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
AVATAR_LIB = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AVATAR_LIB) not in sys.path:
    sys.path.insert(0, str(AVATAR_LIB))

try:
    from avatar_generation.analysis.config import SourceSafetyConfig
    from avatar_generation.analysis.detectors import (
        MediaPipeFaceDetector,
        OpenCvHaarFaceDetector,
    )
    from avatar_generation.analysis.source_analyzer import analyze_avatar_source_image
except Exception as exc:  # pragma: no cover - import failure is reported at runtime
    SourceSafetyConfig = None  # type: ignore[assignment]
    MediaPipeFaceDetector = None  # type: ignore[assignment]
    OpenCvHaarFaceDetector = None  # type: ignore[assignment]
    analyze_avatar_source_image = None  # type: ignore[assignment]
    IMPORT_ERROR = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
else:
    IMPORT_ERROR = ""


def _provider_status() -> dict[str, Any]:
    mediapipe_available = False
    opencv_available = False
    if MediaPipeFaceDetector is not None:
        mediapipe_available = bool(MediaPipeFaceDetector.is_available())
    if OpenCvHaarFaceDetector is not None:
        opencv_available = bool(OpenCvHaarFaceDetector.is_available())
    return {
        "mediapipeAvailable": mediapipe_available,
        "opencvFallbackAvailable": opencv_available,
        "importError": IMPORT_ERROR,
        "installHint": _mediapipe_install_hint() if not mediapipe_available else "",
    }


def _mediapipe_install_hint() -> str:
    if sys.version_info >= (3, 13):
        return (
            "Local Python is 3.13; MediaPipe wheels may be unavailable. "
            "Use a worker-matching Python 3.11/3.12 venv, then install the pinned "
            "worker MediaPipe dependency."
        )
    return ".venv\\Scripts\\python.exe -m pip install mediapipe"


def _analysis_config(provider: str) -> SourceSafetyConfig:
    if SourceSafetyConfig is None:
        raise RuntimeError("avatar source analyzer import failed")
    status = _provider_status()
    use_mediapipe = provider == "mediapipe" or (
        provider == "mediapipe_or_fallback" and status["mediapipeAvailable"]
    )
    return SourceSafetyConfig(
        mediapipe_enabled=use_mediapipe,
        mediapipe_fail_closed_in_production=False,
    )


def _recommendation(status: str, reject_reasons: list[str], *, jpeg_ok: bool) -> str:
    if not jpeg_ok:
        return "BLOCK_LOW_QUALITY"
    if status == "accepted":
        return "PASS"
    reasons = set(reject_reasons)
    if "no_face" in reasons:
        return "BLOCK_NO_FACE"
    if "multiple_faces" in reasons:
        return "BLOCK_MULTI_FACE"
    if "face_too_small" in reasons:
        return "BLOCK_FACE_TOO_SMALL"
    if "corrupt_image" in reasons:
        return "BLOCK_LOW_QUALITY"
    return "NEEDS_MANUAL_REVIEW"


def _face_summary(analysis: Mapping[str, Any]) -> dict[str, Any]:
    face = analysis.get("face") if isinstance(analysis.get("face"), Mapping) else {}
    return {
        "faceCount": face.get("count"),
        "faceRelativeSize": face.get("areaRatio"),
        "faceBboxConfidence": face.get("confidence"),
        "occlusionScore": face.get("occlusionScore"),
    }


def analyze_file(image_record: Mapping[str, Any], provider: str) -> dict[str, Any]:
    path = Path(str(image_record.get("outputPath") or ""))
    result: dict[str, Any] = {
        "inputFile": image_record.get("inputFile"),
        "normalizedFile": image_record.get("outputFile"),
        "path": str(path.resolve()) if path else "",
        "exists": path.is_file(),
        "readable": False,
        "plainJpeg": False,
        "bytes": None,
        "width": None,
        "height": None,
        "provider": "",
        "providerConfidence": "lower" if not _provider_status()["mediapipeAvailable"] else "normal",
        "recommendation": "BLOCK_LOW_QUALITY",
        "rejectReasons": [],
        "face": {},
        "textLogoRisk": "not_run",
        "error": "",
    }
    if not path.is_file():
        result["error"] = "normalized file missing"
        return result
    try:
        result["bytes"] = path.stat().st_size
        with Image.open(path) as image:
            result["readable"] = True
            result["plainJpeg"] = str(image.format or "").upper() == "JPEG"
            result["width"], result["height"] = image.size
        if analyze_avatar_source_image is None:
            raise RuntimeError(IMPORT_ERROR or "source analyzer unavailable")
        with path.open("rb") as handle:
            analysis_obj = analyze_avatar_source_image(
                handle.read(),
                source_ref=f"local://{path.name}",
                config=_analysis_config(provider),
            )
        analysis = analysis_obj.to_document()
        detector = analysis.get("detector") if isinstance(analysis.get("detector"), Mapping) else {}
        result["provider"] = detector.get("provider", "")
        result["rejectReasons"] = list(analysis.get("rejectReasons") or [])
        result["face"] = _face_summary(analysis)
        result["recommendation"] = _recommendation(
            str(analysis.get("status") or ""),
            result["rejectReasons"],
            jpeg_ok=bool(result["plainJpeg"] and result["readable"] and result["bytes"]),
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
    return result


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(manifest_path: Path, provider: str) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    provider_info = _provider_status()
    images = [
        analyze_file(item, provider)
        for item in manifest.get("images", [])
        if item.get("status") == "normalized"
    ]
    counts: dict[str, int] = {}
    for item in images:
        rec = str(item.get("recommendation") or "UNKNOWN")
        counts[rec] = counts.get(rec, 0) + 1
    active_provider = "mediapipe" if provider_info["mediapipeAvailable"] else "opencv_fallback"
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "manifestPath": str(manifest_path.resolve()),
        "requestedProvider": provider,
        "activeProvider": active_provider,
        "providerInfo": provider_info,
        "count": len(images),
        "recommendationCounts": counts,
        "images": images,
        "notes": [
            "OpenCV fallback confidence is lower than Cloud Run MediaPipe Face Landmarker."
            if active_provider == "opencv_fallback"
            else "MediaPipe is available locally.",
            "Text/logo and occlusion checks are best-effort only in local preflight.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight normalized canary images.")
    parser.add_argument("--manifest_json", required=True)
    parser.add_argument("--output_json", required=True)
    parser.add_argument(
        "--provider",
        default="mediapipe_or_fallback",
        choices=("mediapipe_or_fallback", "mediapipe", "opencv_fallback"),
    )
    args = parser.parse_args(argv)

    report_path = Path(args.output_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(Path(args.manifest_json), args.provider)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(report_path.resolve()),
                "activeProvider": report["activeProvider"],
                "recommendationCounts": report["recommendationCounts"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
