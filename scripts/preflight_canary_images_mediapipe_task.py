from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image


DEFAULT_MIN_FACE_AREA_RATIO = 0.08


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _recommendation(face_count: int, area_ratio: float, min_face_area_ratio: float) -> str:
    if face_count <= 0:
        return "BLOCK_NO_FACE"
    if face_count > 1:
        return "BLOCK_MULTI_FACE"
    if area_ratio < min_face_area_ratio:
        return "BLOCK_FACE_TOO_SMALL"
    return "PASS"


def _detect_faces(path: Path, landmarker: Any, mp: Any) -> tuple[int, list[dict[str, float]]]:
    import numpy as np

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(rgb))
        result = landmarker.detect(mp_image)

    faces: list[dict[str, float]] = []
    for landmarks in getattr(result, "face_landmarks", []) or []:
        if not landmarks:
            continue
        xs = [max(0.0, min(1.0, float(point.x))) for point in landmarks]
        ys = [max(0.0, min(1.0, float(point.y))) for point in landmarks]
        area = 0.0
        if xs and ys:
            area = max(0.0, max(xs) - min(xs)) * max(0.0, max(ys) - min(ys))
        faces.append({"areaRatio": round(area, 6)})
    return len(faces), faces


def build_report(
    *,
    manifest_json: Path,
    model_path: Path,
    min_face_area_ratio: float,
) -> Dict[str, Any]:
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision
    except Exception as exc:
        raise RuntimeError(
            "MediaPipe Tasks import failed. Run this with a Python environment that "
            "has mediapipe installed, for example .venv_mediapipe_preflight."
        ) from exc

    if not model_path.is_file():
        raise FileNotFoundError(
            f"Face Landmarker model not found: {model_path}. "
            "Use the worker-baked face_landmarker.task or the local cached copy."
        )

    manifest = _load_json(manifest_json)
    options = vision.FaceLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path.resolve())),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=2,
        min_face_detection_confidence=0.6,
        min_face_presence_confidence=0.6,
        output_face_blendshapes=True,
    )

    images: List[Dict[str, Any]] = []
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        for item in manifest.get("images", []):
            if item.get("status") != "normalized":
                continue
            path = Path(str(item.get("outputPath") or ""))
            row: Dict[str, Any] = {
                "inputFile": item.get("inputFile"),
                "normalizedFile": item.get("outputFile"),
                "exists": path.is_file(),
                "plainJpeg": False,
                "width": None,
                "height": None,
                "faceCount": 0,
                "faces": [],
                "recommendation": "BLOCK_LOW_QUALITY",
                "error": "",
            }
            try:
                with Image.open(path) as image:
                    row["plainJpeg"] = str(image.format or "").upper() == "JPEG"
                    row["width"], row["height"] = image.size
                face_count, faces = _detect_faces(path, landmarker, mp)
                max_area = max((float(face["areaRatio"]) for face in faces), default=0.0)
                row["faceCount"] = face_count
                row["faces"] = faces
                row["recommendation"] = _recommendation(
                    face_count,
                    max_area,
                    min_face_area_ratio,
                )
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
            images.append(row)

    counts: Dict[str, int] = {}
    for item in images:
        rec = str(item.get("recommendation") or "UNKNOWN")
        counts[rec] = counts.get(rec, 0) + 1
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "mediapipe_face_landmarker_tasks",
        "modelPath": str(model_path),
        "minFaceAreaRatio": min_face_area_ratio,
        "mediapipeVersion": getattr(mp, "__version__", ""),
        "recommendationCounts": counts,
        "images": images,
        "notes": [
            "This local report uses MediaPipe Tasks Face Landmarker, matching the Cloud Run worker detector family more closely than OpenCV Haar fallback.",
            "The report contains file names and redacted analysis only; it does not include image bytes, source refs, or signed URLs.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MediaPipe Tasks preflight for normalized canary images."
    )
    parser.add_argument("--manifest_json", required=True)
    parser.add_argument("--output_json", required=True)
    parser.add_argument("--model_path", required=True)
    parser.add_argument(
        "--min_face_area_ratio",
        type=float,
        default=DEFAULT_MIN_FACE_AREA_RATIO,
    )
    args = parser.parse_args(argv)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(
        manifest_json=Path(args.manifest_json),
        model_path=Path(args.model_path),
        min_face_area_ratio=args.min_face_area_ratio,
    )
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "recommendationCounts": report["recommendationCounts"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
