from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping

from .config import ensure_base_dirs, now_utc, pipeline_paths, write_csv
from .manifest import load_generation_manifest


DUPLICATE_SIMILARITY_FIELDS = (
    "pairId",
    "assetIdA",
    "assetIdB",
    "profileIdA",
    "profileIdB",
    "genderA",
    "genderB",
    "shotTypeA",
    "shotTypeB",
    "sha256A",
    "sha256B",
    "pHashA",
    "pHashB",
    "pHashDistance",
    "clipSimilarity",
    "decision",
    "updatedAt",
)

DUPLICATE_AUDIT_FIELDS = (
    "duplicateGroup",
    "sha256",
    "assetId",
    "profileId",
    "gender",
    "shotType",
    "localPath",
    "fileBytes",
    "updatedAt",
)

DISTRIBUTION_FIELDS = ("group", "gender", "shotType", "identityScope", "reserveStatus", "status", "count", "updatedAt")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_image_path(row: Mapping[str, Any]) -> Path:
    for key in ("localPath", "rawPath", "finalPath"):
        value = str(row.get(key) or "")
        if not value:
            continue
        path = Path(value)
        if path.exists() and path.is_file():
            return path
    return Path("")


def phash(path: Path) -> str:
    try:
        from PIL import Image
    except ImportError:
        return ""
    try:
        with Image.open(path) as image:
            gray = image.convert("L").resize((32, 32))
            pixel_data = gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
            pixels = list(pixel_data)
        mean = sum(pixels) / len(pixels)
        bits = ["1" if pixel >= mean else "0" for pixel in pixels]
        return "".join(f"{int(''.join(bits[i:i + 4]), 2):x}" for i in range(0, len(bits), 4))
    except Exception:  # noqa: BLE001 - optional audit signal only.
        return ""


def hamming_hex(a: str, b: str) -> int | str:
    if not a or not b or len(a) != len(b):
        return ""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _clip_similarity_placeholder(_a: Path, _b: Path) -> str:
    # CLIP image embeddings are intentionally optional. If a project-local CLIP stack is installed,
    # this function is the narrow integration point; otherwise pHash still provides local duplicate QA.
    return ""


def audit_duplicates(
    *,
    root: Path | str | None = None,
    min_file_bytes: int = 1,
    phash_threshold: int = 12,
) -> dict[str, int]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    rows = load_generation_manifest(paths)
    image_rows: list[dict[str, Any]] = []
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        image_path = row_image_path(row)
        if str(image_path) in {"", "."} or not image_path.exists() or not image_path.is_file() or image_path.stat().st_size < min_file_bytes:
            continue
        enriched = dict(row)
        enriched["_path"] = image_path
        enriched["_sha256"] = file_sha256(image_path)
        enriched["_pHash"] = phash(image_path)
        enriched["_fileBytes"] = image_path.stat().st_size
        image_rows.append(enriched)
        by_hash[enriched["_sha256"]].append(enriched)

    exact_report: list[dict[str, Any]] = []
    duplicate_groups = [group for group in by_hash.values() if len(group) > 1]
    for index, group in enumerate(sorted(duplicate_groups, key=lambda values: values[0]["_sha256"])):
        duplicate_group = f"sha256:{index}"
        for row in sorted(group, key=lambda value: str(value.get("assetId", ""))):
            exact_report.append(
                {
                    "duplicateGroup": duplicate_group,
                    "sha256": row["_sha256"],
                    "assetId": row.get("assetId", ""),
                    "profileId": row.get("profileId", ""),
                    "gender": row.get("gender", ""),
                    "shotType": row.get("shotType", ""),
                    "localPath": str(row["_path"]),
                    "fileBytes": row["_fileBytes"],
                    "updatedAt": now_utc(),
                }
            )

    similarity_report: list[dict[str, Any]] = []
    for pair_index, (left, right) in enumerate(combinations(image_rows, 2), start=1):
        distance = hamming_hex(str(left.get("_pHash", "")), str(right.get("_pHash", "")))
        exact = left["_sha256"] == right["_sha256"]
        near = isinstance(distance, int) and distance <= phash_threshold
        if not exact and not near:
            continue
        similarity_report.append(
            {
                "pairId": f"pair_{pair_index:06d}",
                "assetIdA": left.get("assetId", ""),
                "assetIdB": right.get("assetId", ""),
                "profileIdA": left.get("profileId", ""),
                "profileIdB": right.get("profileId", ""),
                "genderA": left.get("gender", ""),
                "genderB": right.get("gender", ""),
                "shotTypeA": left.get("shotType", ""),
                "shotTypeB": right.get("shotType", ""),
                "sha256A": left["_sha256"],
                "sha256B": right["_sha256"],
                "pHashA": left.get("_pHash", ""),
                "pHashB": right.get("_pHash", ""),
                "pHashDistance": distance,
                "clipSimilarity": _clip_similarity_placeholder(left["_path"], right["_path"]),
                "decision": "exact_duplicate" if exact else "near_duplicate_review",
                "updatedAt": now_utc(),
            }
        )

    write_csv(paths.reports / "duplicate_audit_report.csv", exact_report, DUPLICATE_AUDIT_FIELDS)
    write_csv(paths.reports / "duplicate_similarity_report.csv", similarity_report, DUPLICATE_SIMILARITY_FIELDS)
    write_distribution_report(root=root)
    return {
        "checked": len(image_rows),
        "duplicateGroups": len(duplicate_groups),
        "duplicateAssets": len(exact_report),
        "similarPairs": len(similarity_report),
    }


def write_distribution_report(*, root: Path | str | None = None) -> dict[str, int]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    rows = load_generation_manifest(paths)
    counters: Counter[tuple[str, str, str, str, str, str]] = Counter()
    for row in rows:
        counters[
            (
                "asset_distribution",
                str(row.get("gender", "")),
                str(row.get("shotType", "")),
                str(row.get("identityScope", "production")),
                str(row.get("reserveStatus", "")),
                str(row.get("status", "")),
            )
        ] += 1
    report = [
        {
            "group": group,
            "gender": gender,
            "shotType": shot_type,
            "identityScope": scope,
            "reserveStatus": reserve_status,
            "status": status,
            "count": count,
            "updatedAt": now_utc(),
        }
        for (group, gender, shot_type, scope, reserve_status, status), count in sorted(counters.items())
    ]
    write_csv(paths.reports / "distribution_report.csv", report, DISTRIBUTION_FIELDS)
    return {"rows": len(report), "assets": len(rows)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit duplicate/diversity signals for Seolleyeon AI image files.")
    parser.add_argument("--root", default=None, help="Workspace root. Defaults to the repository root.")
    parser.add_argument("--min_file_bytes", type=int, default=1)
    parser.add_argument("--phash_threshold", type=int, default=12)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    counts = audit_duplicates(root=args.root, min_file_bytes=args.min_file_bytes, phash_threshold=args.phash_threshold)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
