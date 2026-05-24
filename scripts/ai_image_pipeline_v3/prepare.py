from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping
from pathlib import Path

from .config import (
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_SIZE,
    PRIMARY_FEMALE_COUNT,
    PRIMARY_MALE_COUNT,
    RESERVE_FEMALE_COUNT,
    RESERVE_MALE_COUNT,
    ensure_base_dirs,
    pipeline_paths,
    prompt_hash,
    write_csv,
    write_jsonl,
)
from .codex_imagegen import write_identity_manifest, write_imagegen_queue
from .distribution_prepare import build_distribution_controlled_asset_records, distribution_counts
from .distribution_targets import load_distribution_targets, write_default_distribution_targets
from .identity import build_counted_reserved_specs, build_reserved_specs
from .manifest import enrich_asset, load_generation_manifest, merge_manifest_rows, write_generation_outputs
from .prompt_source import build_asset_records_from_specs, generate_asset_records


@dataclass(frozen=True)
class PrepareResult:
    specs_count: int
    asset_count: int
    assets_jsonl: Path
    identity_manifest_jsonl: Path
    imagegen_queue_jsonl: Path
    manifest_jsonl: Path
    status_csv: Path


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# prepare-720 dry-run report",
        "",
        f"- specs: {report.get('specs')}",
        f"- assets: {report.get('assets')}",
        f"- identities: {report.get('identityCount')}",
        f"- primary identities: {report.get('primaryIdentities')}",
        f"- reserve identities: {report.get('reserveIdentities')}",
        f"- primary assets: {report.get('primaryAssets')}",
        f"- reserve assets: {report.get('reserveAssets')}",
        f"- promptTargetingVersion counts: {report.get('promptTargetingVersionCounts')}",
        f"- promptHash missing: {report.get('promptHashMissing')}",
        f"- promptHash mismatches: {report.get('promptHashMismatches')}",
        f"- positive forbidden term count: {report.get('positivePromptForbiddenTermCount')}",
        f"- no active writes: {report.get('noActiveWrites')}",
        "",
        "## distribution",
        "```json",
        json.dumps(report.get("distributionCounts", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _positive_prompt_forbidden_summary(assets: list[Mapping[str, Any]]) -> dict[str, Any]:
    # Keep this scanner intentionally narrow: it looks for explicit forbidden styling/setting tokens
    # in the positive prompt text emitted for generation. Prompt-builder tests cover negated safety text.
    forbidden = (
        "school uniform",
        "idol trainee",
        "celebrity lookalike",
        "nightclub",
        "swimsuit",
        "lingerie",
        "luxury hotel",
        "neon party",
        "watermark",
    )
    hits: list[dict[str, str]] = []
    for asset in assets:
        prompt = str(asset.get("prompt") or "")
        positive_prompt = prompt.split("\n\nAvoid:", 1)[0].lower()
        for term in forbidden:
            index = positive_prompt.find(term)
            if index == -1:
                continue
            prefix = positive_prompt[max(0, index - 24):index]
            if any(negation in prefix for negation in ("no ", "without ", "not ")):
                continue
            hits.append({"assetId": str(asset.get("assetId") or ""), "term": term})
    return {"forbiddenTerms": list(forbidden), "count": len(hits), "hits": hits[:50]}


def _build_prepare_dry_run_report(
    *,
    root: Path | str | None,
    selected_specs: list[Mapping[str, Any]],
    selected_assets: list[Mapping[str, Any]],
    enriched: list[Mapping[str, Any]],
) -> tuple[Path, Path, dict[str, Any]]:
    paths = pipeline_paths(root)
    audit_dir = paths.reports / "pipeline_audit"
    json_path = audit_dir / "prepare_720_dry_run_latest.json"
    md_path = audit_dir / "prepare_720_dry_run_latest.md"
    primary_specs = [spec for spec in selected_specs if not bool(spec.get("isReserve"))]
    reserve_specs = [spec for spec in selected_specs if bool(spec.get("isReserve"))]
    primary_assets = [asset for asset in selected_assets if not bool(asset.get("isReserve"))]
    reserve_assets = [asset for asset in selected_assets if bool(asset.get("isReserve"))]
    version_counts = Counter(str(asset.get("promptTargetingVersion") or "") for asset in selected_assets)
    current_prompt_targeting_version = str(
        (enriched[0].get("promptTargetingVersion") if enriched else "")
        or (selected_assets[0].get("promptTargetingVersion") if selected_assets else "")
        or ""
    )
    missing_version_count = sum(1 for asset in selected_assets if not asset.get("promptTargetingVersion"))
    hash_missing = sum(1 for asset in enriched if not asset.get("promptHash"))
    hash_mismatches = sum(1 for asset in enriched if str(asset.get("promptHash") or "") != prompt_hash(str(asset.get("prompt") or "")))
    positive_scan = _positive_prompt_forbidden_summary(selected_assets)
    report: dict[str, Any] = {
        "dryRun": True,
        "noActiveWrites": True,
        "specs": len(selected_specs),
        "assets": len(selected_assets),
        "identityCount": len({str(spec.get("profileId")) for spec in selected_specs}),
        "primaryIdentities": len(primary_specs),
        "reserveIdentities": len(reserve_specs),
        "primaryAssets": len(primary_assets),
        "reserveAssets": len(reserve_assets),
        "promptTargetingVersionCounts": dict(version_counts),
        "currentPromptTargetingVersion": current_prompt_targeting_version,
        "missingPromptTargetingVersion": missing_version_count,
        "oldVersionCount": sum(
            count
            for version, count in version_counts.items()
            if version and current_prompt_targeting_version and version != current_prompt_targeting_version
        ),
        "promptHashMissing": hash_missing,
        "promptHashMismatches": hash_mismatches,
        "distributionCounts": distribution_counts(list(selected_specs)),
        "positivePromptForbiddenTermCount": positive_scan["count"],
        "positivePromptForbiddenScan": positive_scan,
        "v4PromptMetadataValidation": {
            "passed": missing_version_count == 0 and hash_missing == 0 and hash_mismatches == 0,
            "silhouetteIdentityReadableLanguagePresent": any("identity-readable" in str(asset.get("prompt") or "").lower() or "recognizable same adult" in str(asset.get("prompt") or "").lower() for asset in selected_assets if asset.get("shotType") == "silhouette_card"),
            "foxLikeMidBandGuardPresent": any(str(asset.get("targetFaceType") or "") == "fox_like" and str(asset.get("targetLooksLevelBand") or "") == "2.5-3.2" for asset in selected_assets),
        },
        "reportPath": str(json_path),
        "markdownReportPath": str(md_path),
    }
    _write_json(json_path, report)
    _write_markdown(md_path, report)
    return json_path, md_path, report


def prepare_assets(
    *,
    root: Path | str | None = None,
    female_count: int = PRIMARY_FEMALE_COUNT,
    male_count: int = PRIMARY_MALE_COUNT,
    reserve_female_count: int = RESERVE_FEMALE_COUNT,
    reserve_male_count: int = RESERVE_MALE_COUNT,
    start_female: int = 1,
    start_male: int = 1,
    start_reserve_female: int | None = None,
    start_reserve_male: int | None = None,
    seed: int = 20260504,
    id_width: int = 3,
    limit: int | None = None,
    limit_identities: int | None = None,
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    quality: str = DEFAULT_QUALITY,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    dry_run: bool = False,
    force: bool = False,
    replace_manifest: bool = False,
    reserve_identities: list[str] | tuple[str, ...] | None = None,
    out_dir: Path | str | None = None,
    distribution_targets: bool = True,
) -> PrepareResult:
    paths = pipeline_paths(root)
    if not dry_run:
        ensure_base_dirs(paths)
        write_default_distribution_targets(root)
    targets = load_distribution_targets(root)
    use_distribution_control = (
        distribution_targets
        and not reserve_identities
        and int(female_count) == int(targets["finalTarget"]["femaleApprovedIdentities"])
        and int(male_count) == int(targets["finalTarget"]["maleApprovedIdentities"])
        and limit is None
        and limit_identities is None
    )
    if use_distribution_control:
        specs, assets = build_distribution_controlled_asset_records(
            root=root,
            female_count=female_count,
            male_count=male_count,
            reserve_female_count=reserve_female_count,
            reserve_male_count=reserve_male_count,
            start_female=start_female,
            start_male=start_male,
            start_reserve_female=start_reserve_female if start_reserve_female is not None else start_female + female_count,
            start_reserve_male=start_reserve_male if start_reserve_male is not None else start_male + male_count,
            seed=seed,
            id_width=id_width,
        )
    else:
        specs, assets = generate_asset_records(
            female_count=female_count,
            male_count=male_count,
            start_female=start_female,
            start_male=start_male,
            seed=seed,
            id_width=id_width,
        )
        counted_reserved_specs = build_counted_reserved_specs(
            female_count=reserve_female_count,
            male_count=reserve_male_count,
            start_female=start_reserve_female if start_reserve_female is not None else start_female + female_count,
            start_male=start_reserve_male if start_reserve_male is not None else start_male + male_count,
            seed=seed,
            id_width=id_width,
        )
        explicit_reserved_specs = build_reserved_specs(reserve_identities or [], seed=seed, id_width=id_width)
        reserved_specs = [*counted_reserved_specs, *explicit_reserved_specs]
        if reserved_specs:
            existing_profile_ids = {str(spec["profileId"]) for spec in specs}
            seen_reserved: set[str] = set()
            unique_reserved_specs = []
            for spec in reserved_specs:
                profile_id = str(spec["profileId"])
                if profile_id in existing_profile_ids or profile_id in seen_reserved:
                    continue
                seen_reserved.add(profile_id)
                unique_reserved_specs.append(spec)
            if unique_reserved_specs:
                reserve_assets = [
                    {
                        **dict(asset),
                        "identityScope": "reserve",
                        "isReserve": True,
                        "reserveStatus": "standby",
                        "activeForTarget": False,
                        "identityDecision": "",
                    }
                    for asset in build_asset_records_from_specs(unique_reserved_specs)
                ]
                specs = [*specs, *unique_reserved_specs]
                assets = [*assets, *reserve_assets]
    if limit_identities:
        selected_profile_ids_ordered: list[str] = []
        for spec in specs:
            profile_id = str(spec["profileId"])
            if profile_id not in selected_profile_ids_ordered:
                selected_profile_ids_ordered.append(profile_id)
            if len(selected_profile_ids_ordered) >= int(limit_identities):
                break
        keep_profiles = set(selected_profile_ids_ordered)
        specs = [spec for spec in specs if str(spec["profileId"]) in keep_profiles]
        assets = [asset for asset in assets if str(asset["profileId"]) in keep_profiles]

    selected_assets = list(assets[:limit] if limit else assets)
    selected_profile_ids = {str(row["profileId"]) for row in selected_assets}
    selected_specs = [spec for spec in specs if str(spec["profileId"]) in selected_profile_ids]

    enriched = [
        enrich_asset(
            row,
            paths,
            model=model,
            size=size,
            quality=quality,
            output_format=output_format,
            status="prepared",
            dry_run=dry_run,
        )
        for row in selected_assets
    ]
    if dry_run:
        existing = []
        merged = list(enriched)
    else:
        existing = [] if replace_manifest else load_generation_manifest(paths)
        merged = enriched if replace_manifest else merge_manifest_rows(existing, enriched, force=force)
    selected_asset_ids = {str(row["assetId"]) for row in enriched}
    if replace_manifest:
        merged = [row for row in merged if str(row.get("assetId")) in selected_asset_ids]

    specs_jsonl = paths.manifests / "ai_profile_specs_v3.jsonl"
    assets_jsonl = paths.manifests / "ai_profile_assets_v3.jsonl"
    assets_csv = paths.manifests / "ai_profile_assets_v3.csv"
    if dry_run:
        dry_json, _dry_md, _dry_report = _build_prepare_dry_run_report(
            root=root,
            selected_specs=list(selected_specs),
            selected_assets=list(selected_assets),
            enriched=list(enriched),
        )
        return PrepareResult(
            specs_count=len(selected_specs),
            asset_count=len(selected_assets),
            assets_jsonl=dry_json,
            identity_manifest_jsonl=dry_json,
            imagegen_queue_jsonl=dry_json,
            manifest_jsonl=dry_json,
            status_csv=dry_json.with_suffix(".md"),
        )

    reserve_profile_ids = {str(asset.get("profileId")) for asset in selected_assets if bool(asset.get("isReserve"))}
    identity_jsonl = write_identity_manifest(
        root,
        (
            {
                **dict(spec),
                "identityScope": "reserve" if str(spec.get("profileId")) in reserve_profile_ids else "primary",
                "isReserve": str(spec.get("profileId")) in reserve_profile_ids,
            }
            for spec in selected_specs
        ),
    )
    queue_jsonl = write_imagegen_queue(root, merged)
    write_jsonl(specs_jsonl, selected_specs)
    write_jsonl(assets_jsonl, selected_assets)
    write_csv(
        assets_csv,
        selected_assets,
        (
            "profileId",
            "assetId",
            "gender",
            "identityScope",
            "isReserve",
            "shotType",
            "legacyStoragePath",
            "storagePath",
            "prompt",
        ),
    )
    write_generation_outputs(paths, merged)
    return PrepareResult(
        specs_count=len(selected_specs),
        asset_count=len(selected_assets),
        assets_jsonl=assets_jsonl,
        identity_manifest_jsonl=identity_jsonl,
        imagegen_queue_jsonl=queue_jsonl,
        manifest_jsonl=paths.manifests / "generation_manifest.jsonl",
        status_csv=paths.reports / "generation_status.csv",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare Seolleyeon AI image v3 asset manifests.")
    parser.add_argument("--root", default=None, help="Workspace root. Defaults to the repository root.")
    parser.add_argument("--female_count", type=int, default=PRIMARY_FEMALE_COUNT)
    parser.add_argument("--male_count", type=int, default=PRIMARY_MALE_COUNT)
    parser.add_argument("--reserve_female_count", type=int, default=RESERVE_FEMALE_COUNT)
    parser.add_argument("--reserve_male_count", type=int, default=RESERVE_MALE_COUNT)
    parser.add_argument("--start_female", type=int, default=1)
    parser.add_argument("--start_male", type=int, default=1)
    parser.add_argument("--start_reserve_female", type=int, default=None)
    parser.add_argument("--start_reserve_male", type=int, default=None)
    parser.add_argument("--seed", type=int, default=20260504)
    parser.add_argument("--id_width", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--limit_identities", type=int, default=None)
    parser.add_argument(
        "--out_dir",
        default=None,
        help="Compatibility option. Manifests are always written under <root>/ai_image/manifests.",
    )
    parser.add_argument(
        "--targets_json",
        default=None,
        help="Compatibility option. Distribution targets are loaded from <root>/ai_image/config.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument("--quality", default=DEFAULT_QUALITY)
    parser.add_argument("--output_format", default=DEFAULT_OUTPUT_FORMAT)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--replace_manifest",
        action="store_true",
        help="Replace generation manifest with this prepared selection. Intended for dry-run/smoke checks.",
    )
    parser.add_argument(
        "--reserve_identity",
        action="append",
        default=[],
        help="Reserve an explicit profileId (for example female_901). Repeat for multiple identities.",
    )
    parser.add_argument("--no_distribution_targets", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = prepare_assets(
        root=args.root,
        female_count=args.female_count,
        male_count=args.male_count,
        reserve_female_count=args.reserve_female_count,
        reserve_male_count=args.reserve_male_count,
        start_female=args.start_female,
        start_male=args.start_male,
        start_reserve_female=args.start_reserve_female,
        start_reserve_male=args.start_reserve_male,
        seed=args.seed,
        id_width=args.id_width,
        limit=args.limit,
        limit_identities=args.limit_identities,
        model=args.model,
        size=args.size,
        quality=args.quality,
        output_format=args.output_format,
        dry_run=args.dry_run,
        force=args.force,
        replace_manifest=args.replace_manifest,
        reserve_identities=args.reserve_identity,
        out_dir=args.out_dir,
        distribution_targets=not args.no_distribution_targets,
    )
    print(
        f"prepared specs={result.specs_count} assets={result.asset_count} "
        f"identity_manifest={result.identity_manifest_jsonl} "
        f"imagegen_queue={result.imagegen_queue_jsonl} "
        f"assets_jsonl={result.assets_jsonl} status_csv={result.status_csv}"
    )
    return 0
