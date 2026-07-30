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


def _load_uid_photo_consent(path: Path) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if not path.is_file():
        return pairs
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        uid, photo = line.split("=", 1)
        pairs.add((uid.strip().strip("<>"), Path(photo.strip()).name))
    return pairs


def build_activation(
    *,
    template: Mapping[str, Any],
    consent_pairs: set[tuple[str, str]],
    confirm_uid_photo_consent: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    candidate_pairs: set[tuple[str, str]] = set()
    candidate_consent_rows: list[str] = []
    for item in template.get("rows", []):
        if not isinstance(item, Mapping):
            continue
        uid = str(item.get("uid") or "").strip()
        photo_file = str(item.get("photoFile") or "").strip()
        if uid and photo_file:
            candidate_pairs.add((uid, photo_file))
            candidate_consent_rows.append(f"{uid}={photo_file}")
        pair_consented = (uid, photo_file) in consent_pairs
        active = bool(confirm_uid_photo_consent and pair_consented)
        blockers: list[str] = []
        if not confirm_uid_photo_consent:
            blockers.append("confirm_uid_photo_consent_required")
        if not pair_consented:
            blockers.append("uid_photo_pair_consent_missing")
        rows.append(
            {
                "label": item.get("label"),
                "uid": uid,
                "photoFile": photo_file,
                "photoPath": item.get("photoPath"),
                "active": active,
                "blockers": blockers,
            }
        )
    blocker_counts: dict[str, int] = {}
    for row in rows:
        if row["active"]:
            continue
        for blocker in row["blockers"]:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    required_consent_rows = [
        f"{row['uid']}={row['photoFile']}"
        for row in rows
        if row["uid"] and row["photoFile"] and not row["active"]
    ]
    matched_consent_pairs = consent_pairs & candidate_pairs
    unexpected_consent_pairs = consent_pairs - candidate_pairs
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "confirmUidPhotoConsent": confirm_uid_photo_consent,
        "candidatePairCount": len(rows),
        "consentPairCount": len(consent_pairs),
        "matchedConsentPairCount": len(matched_consent_pairs),
        "unexpectedConsentPairCount": len(unexpected_consent_pairs),
        "activeRowCount": sum(1 for row in rows if row["active"]),
        "blockedRowCount": sum(1 for row in rows if not row["active"]),
        "blockerCounts": dict(sorted(blocker_counts.items())),
        "candidateConsentMapRows": candidate_consent_rows,
        "requiredConsentMapRows": required_consent_rows,
        "rows": rows,
        "notes": [
            "This activation requires an exact UID=photoFile consent map.",
            "candidateConsentMapRows are the canonical exact UID/photo rows for PR8.4.",
            "requiredConsentMapRows are still-blocked rows to copy only after consent is confirmed.",
            "No upload is performed by this script.",
        ],
    }


def _render_mapping(report: Mapping[str, Any]) -> str:
    lines = [
        "# PR8.4 activated canary mapping",
        "# Generated only from rows with exact UID/photo consent.",
        "",
    ]
    for row in report.get("rows", []):
        if isinstance(row, Mapping) and row.get("active"):
            lines.append(f"{row.get('uid')}={row.get('photoPath')}")
    lines.append("")
    return "\n".join(lines)


def _render_required_consent_template(report: Mapping[str, Any]) -> str:
    lines = [
        "# PR8.4 UID/photo consent map template",
        "# Copy these rows to pr84_uid_photo_consent_map.txt only after exact UID-photo consent is confirmed.",
        "# This file is advisory and is not used for upload.",
        "",
    ]
    rows = report.get("candidateConsentMapRows") or report.get("requiredConsentMapRows", [])
    for row in rows:
        lines.append(f"# {row}")
    lines.append("")
    return "\n".join(lines)


def _activation_status(report: Mapping[str, Any], *, min_users: int) -> str:
    if int(report.get("unexpectedConsentPairCount") or 0) > 0:
        return "BLOCKED_CONSENT_MISMATCH"
    if int(report.get("activeRowCount") or 0) >= min_users:
        return "READY"
    return "BLOCKED_CONSENT"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Activate PR8.4 canary UID/photo mapping after exact consent.")
    parser.add_argument("--template_json", default="out/pr84_canary_uid_photo_map_template.json")
    parser.add_argument("--uid_photo_consent_map", default="pr84_uid_photo_consent_map.txt")
    parser.add_argument("--output_mapping", default="out/pr84_canary_uid_photo_map_activated.txt")
    parser.add_argument("--output_json", default="out/pr84_canary_uid_photo_map_activation.json")
    parser.add_argument("--required_consent_template", default="out/pr84_uid_photo_consent_map_required.txt")
    parser.add_argument("--confirm_uid_photo_consent", action="store_true")
    parser.add_argument(
        "--require_ready",
        action="store_true",
        help="Exit non-zero unless at least --min_users rows are active.",
    )
    parser.add_argument("--min_users", type=int, default=3)
    args = parser.parse_args(argv)

    uid_photo_consent_map = Path(args.uid_photo_consent_map)
    consent_pairs = _load_uid_photo_consent(uid_photo_consent_map)
    report = build_activation(
        template=_load_json(Path(args.template_json)),
        consent_pairs=consent_pairs,
        confirm_uid_photo_consent=args.confirm_uid_photo_consent,
    )
    report["uidPhotoConsentMap"] = {
        "path": str(uid_photo_consent_map.resolve()),
        "present": uid_photo_consent_map.is_file(),
        "pairCount": len(consent_pairs),
        "matchedPairCount": report["matchedConsentPairCount"],
        "unexpectedPairCount": report["unexpectedConsentPairCount"],
    }
    status = _activation_status(report, min_users=args.min_users)
    report["status"] = status
    report["minUsers"] = args.min_users
    output_json = Path(args.output_json)
    output_mapping = Path(args.output_mapping)
    required_consent_template = Path(args.required_consent_template)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_mapping.parent.mkdir(parents=True, exist_ok=True)
    required_consent_template.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_mapping.write_text(_render_mapping(report), encoding="utf-8")
    required_consent_template.write_text(_render_required_consent_template(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "outputJson": str(output_json.resolve()),
                "outputMapping": str(output_mapping.resolve()),
                "requiredConsentTemplate": str(required_consent_template.resolve()),
                "status": status,
                "activeRowCount": report["activeRowCount"],
                "blockedRowCount": report["blockedRowCount"],
                "matchedConsentPairCount": report["matchedConsentPairCount"],
                "unexpectedConsentPairCount": report["unexpectedConsentPairCount"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if status == "READY" or not args.require_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
