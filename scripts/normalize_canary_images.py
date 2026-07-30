from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageSequence


ACCEPTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mpo"}


def _sha256_prefix(path: Path, *, length: int = 12) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:length]


def _output_path(output_dir: Path, stem: str) -> Path:
    # The source files are never overwritten. Normalized outputs are deterministic
    # so UID/photo mapping files do not drift across repeated PR8.4 preflight runs.
    return output_dir / f"{stem}_plain.jpg"


def _frame_count(image: Image.Image) -> int:
    try:
        return sum(1 for _ in ImageSequence.Iterator(image))
    except Exception:
        return 1


def normalize_image(source: Path, output_dir: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "inputFile": source.name,
        "inputPath": str(source.resolve()),
        "status": "failed",
        "error": "",
    }
    try:
        input_bytes = source.stat().st_size
        with Image.open(source) as image:
            input_format = str(image.format or "").upper()
            frames = _frame_count(image)
            first_frame = next(ImageSequence.Iterator(image)).copy()
            normalized = ImageOps.exif_transpose(first_frame).convert("RGB")

        output_path = _output_path(output_dir, source.stem)
        normalized.save(
            output_path,
            format="JPEG",
            quality=92,
            optimize=True,
            progressive=False,
        )
        record.update(
            {
                "status": "normalized",
                "inputFormat": input_format,
                "inputBytes": input_bytes,
                "inputSha256Prefix": _sha256_prefix(source),
                "outputPath": str(output_path.resolve()),
                "outputFile": output_path.name,
                "outputBytes": output_path.stat().st_size,
                "outputSha256Prefix": _sha256_prefix(output_path),
                "width": normalized.width,
                "height": normalized.height,
                "frameCount": frames,
                "usedFirstFrame": frames > 1 or input_format == "MPO",
            }
        )
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
    return record


def build_manifest(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for source in sorted(input_dir.iterdir()):
        if not source.is_file() or source.suffix.lower() not in ACCEPTED_EXTENSIONS:
            continue
        images.append(normalize_image(source, output_dir))
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputDir": str(input_dir.resolve()),
        "outputDir": str(output_dir.resolve()),
        "acceptedExtensions": sorted(ACCEPTED_EXTENSIONS),
        "count": len(images),
        "normalizedCount": sum(1 for item in images if item.get("status") == "normalized"),
        "images": images,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize canary images to plain JPEG.")
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--manifest_json", required=True)
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest_json)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(Path(args.input_dir), Path(args.output_dir))
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest": str(manifest_path.resolve()),
                "normalizedCount": manifest["normalizedCount"],
                "count": manifest["count"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if manifest["normalizedCount"] == manifest["count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
