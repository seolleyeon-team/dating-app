from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.florence2 import Florence2TraitExtractionAdapter


def _fixture_image() -> Image.Image:
    image = Image.new("RGB", (512, 512), (238, 235, 226))
    draw = ImageDraw.Draw(image)
    draw.ellipse((170, 120, 342, 300), fill=(224, 182, 148))
    draw.rectangle((160, 95, 352, 170), fill=(42, 32, 28))
    draw.rectangle((190, 300, 322, 420), fill=(72, 92, 130))
    return image


def _write_report(report: dict, path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test Florence-2 trait extraction plumbing.")
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--image_path", default="")
    parser.add_argument("--report_json", default="")
    args = parser.parse_args(argv)

    if args.image_path:
        image = Image.open(args.image_path).convert("RGB")
    else:
        image = _fixture_image()

    adapter = Florence2TraitExtractionAdapter(dry_run=args.dry_run)
    result = adapter.extract_traits(image=image)
    report = {
        "status": "ok",
        "mode": "dry_run" if args.dry_run else "real_model",
        "schemaVersion": result.schema_version,
        "privacySafe": result.privacy_safe,
        "confidence": result.confidence,
        "errors": result.errors,
        "traitCardKeys": sorted(result.trait_card.to_dict(include_unclear=False).keys()),
    }
    _write_report(report, args.report_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
