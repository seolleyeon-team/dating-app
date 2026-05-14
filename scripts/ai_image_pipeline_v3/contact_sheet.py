from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import SHOT_ORDER, ensure_base_dirs, pipeline_paths
from .manifest import load_generation_manifest


@dataclass(frozen=True)
class ContactSheetResult:
    output_path: Path
    image_count: int
    columns: int
    rows: int


def existing_image_rows(
    rows: list[Mapping[str, Any]],
    *,
    limit: int | None,
    gender: str | None = None,
    shot_type: str | None = None,
    approved_only: bool = False,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        if gender and str(row.get("gender")) != gender:
            continue
        if shot_type and str(row.get("shotType")) != shot_type:
            continue
        candidate_paths = [Path(str(value)) for value in (row.get("finalPath"), row.get("localPath")) if str(value or "").strip()]
        image_path = next((path for path in candidate_paths if path.is_file()), None)
        if not image_path:
            continue
        if approved_only and str(row.get("status")) not in {"qa_approved", "vision_approved"}:
            continue
        enriched = dict(row)
        enriched["_contactSheetPath"] = str(image_path)
        selected.append(enriched)
        if limit and len(selected) >= limit:
            break
    return selected


def _draw_sheet(rows: list[Mapping[str, Any]], output_path: Path, *, columns: int, thumb_size: tuple[int, int]) -> ContactSheetResult:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required to generate contact sheets: pip install Pillow") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_columns = max(1, int(columns))
    caption_height = 58
    if not rows:
        blank = Image.new("RGB", (thumb_size[0], 90), "white")
        draw = ImageDraw.Draw(blank)
        draw.text((8, 8), "No images", fill=(20, 20, 20))
        blank.save(output_path)
        return ContactSheetResult(output_path=output_path, image_count=0, columns=1, rows=1)

    row_count = (len(rows) + safe_columns - 1) // safe_columns
    cell_width, cell_height = thumb_size[0], thumb_size[1] + caption_height
    sheet = Image.new("RGB", (safe_columns * cell_width, row_count * cell_height), "white")
    draw = ImageDraw.Draw(sheet)

    for index, row in enumerate(rows):
        source = Path(str(row.get("_contactSheetPath") or row.get("localPath") or ""))
        with Image.open(source) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail(thumb_size)
            x = (index % safe_columns) * cell_width + (thumb_size[0] - thumb.width) // 2
            y = (index // safe_columns) * cell_height + (thumb_size[1] - thumb.height) // 2
            sheet.paste(thumb, (x, y))
        caption_y = (index // safe_columns) * cell_height + thumb_size[1] + 4
        caption = f"{row.get('assetId', '')}"
        if len(caption) > 34:
            caption = caption[:31] + "..."
        draw.text(((index % safe_columns) * cell_width + 6, caption_y), caption, fill=(20, 20, 20))
        draw.text(
            ((index % safe_columns) * cell_width + 6, caption_y + 18),
            f"{row.get('profileId', '')} {row.get('shotType', '')}",
            fill=(70, 70, 70),
        )

    sheet.save(output_path)
    return ContactSheetResult(output_path=output_path, image_count=len(rows), columns=safe_columns, rows=row_count)


def generate_contact_sheet(
    *,
    root: Path | str | None = None,
    output_name: str = "contact_sheet.png",
    limit: int | None = None,
    columns: int = 3,
    thumb_size: tuple[int, int] = (220, 220),
    gender: str | None = None,
    shot_type: str | None = None,
    approved_only: bool = False,
) -> ContactSheetResult:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    rows = existing_image_rows(
        load_generation_manifest(paths),
        limit=limit,
        gender=gender,
        shot_type=shot_type,
        approved_only=approved_only,
    )
    output_path = paths.reports / output_name
    return _draw_sheet(rows, output_path, columns=columns, thumb_size=thumb_size)


def generate_grouped_contact_sheets(
    *,
    root: Path | str | None = None,
    stage: str = "pilot",
    limit: int | None = None,
    columns: int = 4,
    approved_only: bool = False,
) -> list[ContactSheetResult]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    all_rows = load_generation_manifest(paths)
    results: list[ContactSheetResult] = []
    for gender in ("female", "male"):
        for shot_type in SHOT_ORDER:
            rows = existing_image_rows(
                all_rows,
                limit=limit,
                gender=gender,
                shot_type=shot_type,
                approved_only=approved_only,
            )
            output = paths.reports / "contact_sheets" / f"{stage}_contact_sheet_{gender}_{shot_type}.png"
            results.append(_draw_sheet(rows, output, columns=columns, thumb_size=(220, 300)))
    return results


def generate_identity_contact_sheets(
    *,
    root: Path | str | None = None,
    limit_identities: int | None = None,
    columns: int = 3,
    approved_only: bool = False,
) -> list[ContactSheetResult]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    all_rows = load_generation_manifest(paths)
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for row in all_rows:
        by_profile.setdefault(str(row.get("profileId") or ""), []).append(dict(row))
    results: list[ContactSheetResult] = []
    for index, (profile_id, profile_rows) in enumerate(sorted(by_profile.items())):
        if limit_identities is not None and index >= limit_identities:
            break
        rows = existing_image_rows(sorted(profile_rows, key=lambda row: SHOT_ORDER.index(str(row.get("shotType"))) if str(row.get("shotType")) in SHOT_ORDER else 99), limit=None, approved_only=approved_only)
        output = paths.reports / "contact_sheets" / "identities" / f"{profile_id}.png"
        results.append(_draw_sheet(rows, output, columns=columns, thumb_size=(220, 300)))
    return results


def generate_chunk_contact_sheets(
    *,
    root: Path | str | None = None,
    chunk_size: int = 24,
    columns: int = 4,
    approved_only: bool = False,
) -> list[ContactSheetResult]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    all_rows = load_generation_manifest(paths)
    profile_ids = sorted({str(row.get("profileId") or "") for row in all_rows if bool(row.get("activeForTarget", True))})
    results: list[ContactSheetResult] = []
    for chunk_index in range(0, len(profile_ids), max(1, int(chunk_size))):
        chunk_profiles = set(profile_ids[chunk_index : chunk_index + max(1, int(chunk_size))])
        rows = existing_image_rows([row for row in all_rows if str(row.get("profileId") or "") in chunk_profiles], limit=None, approved_only=approved_only)
        output = paths.reports / "contact_sheets" / "chunks" / f"chunk_{chunk_index // max(1, int(chunk_size)) + 1:03d}.png"
        results.append(_draw_sheet(rows, output, columns=columns, thumb_size=(220, 300)))
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate contact sheets for Seolleyeon AI image review.")
    parser.add_argument("--root", default=None, help="Workspace root. Defaults to the repository root.")
    parser.add_argument("--manifest", default=None, help="Compatibility option; generation_manifest.jsonl remains the source of truth.")
    parser.add_argument("--out_dir", default=None, help="Compatibility option for Makefile targets.")
    parser.add_argument("--output_name", default=None)
    parser.add_argument("--stage", choices=["pilot", "full", "smoke", "custom"], default="pilot")
    parser.add_argument("--grouped", action="store_true", help="Generate gender/shotType grouped contact sheets under reports/contact_sheets.")
    parser.add_argument("--identity_sheets", action="store_true", help="Generate one 3-shot contact sheet per identity.")
    parser.add_argument("--chunked", action="store_true", help="Generate review contact sheets split by identity chunks.")
    parser.add_argument("--chunk_size", type=int, default=24)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--gender", choices=["female", "male"], default=None)
    parser.add_argument("--shot_type", choices=list(SHOT_ORDER), default=None)
    parser.add_argument("--approved_only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.out_dir and not args.grouped and not args.output_name:
        args.grouped = True
    if args.grouped:
        results = generate_grouped_contact_sheets(
            root=args.root,
            stage=args.stage,
            limit=args.limit,
            columns=args.columns,
            approved_only=args.approved_only,
        )
        print(
            {
                "outputs": [str(result.output_path) for result in results],
                "imageCount": sum(result.image_count for result in results),
            }
        )
        if not args.identity_sheets and not args.chunked:
            return 0
    combined_results: list[ContactSheetResult] = []
    if args.identity_sheets:
        combined_results.extend(
            generate_identity_contact_sheets(
                root=args.root,
                limit_identities=args.limit,
                columns=3,
                approved_only=args.approved_only,
            )
        )
    if args.chunked:
        combined_results.extend(
            generate_chunk_contact_sheets(
                root=args.root,
                chunk_size=args.chunk_size,
                columns=args.columns,
                approved_only=args.approved_only,
            )
        )
    if combined_results:
        print(
            {
                "outputs": [str(result.output_path) for result in combined_results],
                "imageCount": sum(result.image_count for result in combined_results),
            }
        )
        return 0
    result = generate_contact_sheet(
        root=args.root,
        output_name=args.output_name or "contact_sheet.png",
        limit=args.limit,
        columns=args.columns,
        gender=args.gender,
        shot_type=args.shot_type,
        approved_only=args.approved_only,
    )
    print(
        {
            "outputPath": str(result.output_path),
            "imageCount": result.image_count,
            "columns": result.columns,
            "rows": result.rows,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
