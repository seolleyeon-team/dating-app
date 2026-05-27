from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_existing_mapping(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not path.is_file():
        return mapping
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        uid, photo_path = line.split("=", 1)
        mapping[Path(photo_path.strip()).name] = uid.strip().strip("<>")
    return mapping


def _prepared_users(report: Mapping[str, Any]) -> list[dict[str, str]]:
    users = report.get("users")
    if not isinstance(users, Mapping):
        return []
    prepared: list[dict[str, str]] = []
    for label, item in users.items():
        if not isinstance(item, Mapping):
            continue
        uid = str(item.get("uid") or "").strip()
        email = str(item.get("email") or "").strip()
        if uid:
            prepared.append({"label": str(label), "uid": uid, "email": email})
    return prepared


def _pass_fixtures(preflight: Mapping[str, Any]) -> list[dict[str, str]]:
    fixtures: list[dict[str, str]] = []
    for item in preflight.get("images", []):
        if not isinstance(item, Mapping) or item.get("recommendation") != "PASS":
            continue
        filename = str(item.get("normalizedFile") or "").strip()
        if filename:
            fixtures.append(
                {
                    "inputFile": str(item.get("inputFile") or ""),
                    "normalizedFile": filename,
                }
            )
    return sorted(fixtures, key=lambda fixture: fixture["normalizedFile"])


def _normalized_path(output_dir: Path, filename: str) -> str:
    return str((output_dir / filename).resolve())


def build_template(
    *,
    prepared_report: Mapping[str, Any],
    preflight_report: Mapping[str, Any],
    existing_mapping: Mapping[str, str],
    normalized_dir: Path,
    allow_existing_remap: bool = False,
    activate_rows: bool = False,
) -> dict[str, Any]:
    users = _prepared_users(prepared_report)
    fixtures = _pass_fixtures(preflight_report)
    pair_count = min(len(users), len(fixtures))
    rows: list[dict[str, Any]] = []
    for index in range(pair_count):
        user = users[index]
        fixture = fixtures[index]
        existing_uid = existing_mapping.get(fixture["normalizedFile"], "")
        consent_required = bool(existing_uid and existing_uid != user["uid"] and not allow_existing_remap)
        inactive_reason = ""
        if consent_required:
            inactive_reason = "existing_photo_mapped_to_different_uid"
        elif not activate_rows:
            inactive_reason = "explicit_activation_required"
        rows.append(
            {
                "label": user["label"],
                "uid": user["uid"],
                "photoFile": fixture["normalizedFile"],
                "photoPath": _normalized_path(normalized_dir, fixture["normalizedFile"]),
                "active": activate_rows and not consent_required,
                "consentRequired": consent_required,
                "reason": inactive_reason,
            }
        )
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "preparedUserCount": len(users),
        "passFixtureCount": len(fixtures),
        "candidatePairCount": pair_count,
        "activeRowCount": sum(1 for row in rows if row["active"]),
        "consentRequiredCount": sum(1 for row in rows if row["consentRequired"]),
        "activateRowsRequested": activate_rows,
        "rows": rows,
        "notes": [
            "This is a local mapping template only. Review consent before copying active rows to canary_uid_photo_map.txt.",
            "Rows are inactive by default. Use --activate_rows only after confirming UID-specific photo consent.",
            "Rows that reuse a photo previously mapped to a different UID are commented out unless --allow_existing_remap is provided.",
        ],
    }


def _render_template(report: Mapping[str, Any]) -> str:
    lines = [
        "# PR8.4 canary UID/photo mapping template",
        "# Review consent before copying active rows to canary_uid_photo_map.txt.",
        "# Commented rows are not upload-ready.",
        "",
    ]
    for row in report.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        prefix = "" if row.get("active") else "# "
        suffix = ""
        if row.get("consentRequired"):
            suffix = "  # CONSENT_REQUIRED: existing photo was mapped to a different UID"
        elif not row.get("active"):
            suffix = "  # INACTIVE: explicit activation required after UID-specific consent review"
        lines.append(f"{prefix}{row.get('uid')}={row.get('photoPath')}{suffix}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a consent-safe PR8.4 canary mapping template.")
    parser.add_argument("--prepared_users_report_json", default="out/pr84_prepare_canary_auth_users_apply.json")
    parser.add_argument("--preflight_json", default="out/canary_preflight_report_mediapipe.json")
    parser.add_argument("--existing_mapping_file", default="canary_uid_photo_map.txt")
    parser.add_argument("--normalized_dir", default="canary_inputs/normalized")
    parser.add_argument("--output_txt", default="out/pr84_canary_uid_photo_map_template.txt")
    parser.add_argument("--output_json", default="out/pr84_canary_uid_photo_map_template.json")
    parser.add_argument("--allow_existing_remap", action="store_true")
    parser.add_argument("--activate_rows", action="store_true")
    args = parser.parse_args(argv)

    report = build_template(
        prepared_report=_load_json(Path(args.prepared_users_report_json)),
        preflight_report=_load_json(Path(args.preflight_json)),
        existing_mapping=_load_existing_mapping(Path(args.existing_mapping_file)),
        normalized_dir=Path(args.normalized_dir),
        allow_existing_remap=args.allow_existing_remap,
        activate_rows=args.activate_rows,
    )
    output_txt = Path(args.output_txt)
    output_json = Path(args.output_json)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text(_render_template(report), encoding="utf-8")
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "outputTxt": str(output_txt.resolve()),
                "outputJson": str(output_json.resolve()),
                "candidatePairCount": report["candidatePairCount"],
                "activeRowCount": report["activeRowCount"],
                "consentRequiredCount": report["consentRequiredCount"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
