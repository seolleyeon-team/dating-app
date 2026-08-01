from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONSENT_FILE = "canary_uid_photo_consent.txt"
FALLBACK_CONSENT_FILES = ("canary_consent.txt",)
DEFAULT_REQUIRED_UID_PHOTO_ROWS_FILE = "out/pr84_uid_photo_consent_map_required.txt"

TERM_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("project", ("seolleyeon-final",)),
    ("staging", ("staging",)),
    ("avatar_canary", ("avatar canary", "avatar qa", "아바타")),
    ("explicit_consent", ("explicit consent", "consented", "동의")),
    ("privacy_monitoring", ("privacy monitoring", "privacy qa", "privacy")),
    ("not_production", ("not production", "production rollout이 아닙니다", "production rollout")),
)


def _read_text(path: Path) -> tuple[str, str]:
    if not path.is_file():
        return "", "missing"
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace"), "utf-8-replace"


def _has_mojibake_markers(text: str) -> bool:
    if "\ufffd" in text:
        return True
    if text.count("?") >= 4:
        return True
    return any(marker in text for marker in ("李", "寃", "湲", "瑜", "먮"))


def _parse_uid_photo_rows(text: str) -> list[str]:
    rows: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            line = line[1:].strip()
        if "=" not in line:
            continue
        uid, photo = line.split("=", 1)
        uid = uid.strip().strip("<>")
        photo_file = Path(photo.strip()).name
        if uid and photo_file:
            rows.append(f"{uid}={photo_file}")
    return rows


def load_required_uid_photo_rows(path: Path) -> list[str]:
    text, _encoding = _read_text(path)
    return _parse_uid_photo_rows(text)


def _exact_uid_photo_summary(parsed_rows: list[str], required_rows: list[str]) -> dict[str, Any]:
    parsed_set = set(parsed_rows)
    required_set = set(required_rows)
    matched_rows = [row for row in required_rows if row in parsed_set]
    missing_rows = [row for row in required_rows if row not in parsed_set]
    unexpected_rows = [row for row in parsed_rows if row not in required_set]
    satisfied = bool(required_rows) and not missing_rows and not unexpected_rows
    return {
        "requiredForPr84Activation": True,
        "satisfiedByThisFile": satisfied,
        "requiredMapFile": "pr84_uid_photo_consent_map.txt",
        "parsedRowCount": len(parsed_rows),
        "requiredRowCount": len(required_rows),
        "matchedRowCount": len(matched_rows),
        "missingRowCount": len(missing_rows),
        "unexpectedRowCount": len(unexpected_rows),
        "matchedRows": matched_rows,
        "missingRows": missing_rows,
        "unexpectedRows": unexpected_rows,
    }


def evaluate_consent_text(
    text: str,
    *,
    present: bool = True,
    encoding: str = "",
    required_uid_photo_rows: list[str] | None = None,
) -> dict[str, Any]:
    normalized = " ".join(text.lower().split())
    missing_terms: list[str] = []
    matched_terms: list[str] = []
    for key, alternatives in TERM_GROUPS:
        if any(term.lower() in normalized for term in alternatives):
            matched_terms.append(key)
        else:
            missing_terms.append(key)
    blockers: list[str] = []
    if not present:
        blockers.append("consent_file_missing")
    if _has_mojibake_markers(text):
        blockers.append("consent_file_mojibake_or_unreadable")
    for term in missing_terms:
        blockers.append(f"consent_missing_{term}")
    parsed_uid_photo_rows = _parse_uid_photo_rows(text)
    return {
        "present": present,
        "valid": present and not blockers,
        "scope": "general_canary_consent_evidence",
        "exactUidPhotoConsent": _exact_uid_photo_summary(
            parsed_uid_photo_rows,
            required_uid_photo_rows or [],
        ),
        "encoding": encoding,
        "matchedTerms": matched_terms,
        "missingTerms": missing_terms,
        "blockers": blockers,
        "redacted": True,
    }


def evaluate_consent_file(path: Path) -> dict[str, Any]:
    text, encoding = _read_text(path)
    return evaluate_consent_text(text, present=path.is_file(), encoding=encoding)


def evaluate_consent_file_with_required_rows(
    path: Path,
    *,
    required_rows_path: Path,
) -> dict[str, Any]:
    text, encoding = _read_text(path)
    return evaluate_consent_text(
        text,
        present=path.is_file(),
        encoding=encoding,
        required_uid_photo_rows=load_required_uid_photo_rows(required_rows_path),
    )


def resolve_consent_path(requested: str | None, *, cwd: Path = Path(".")) -> tuple[Path, str]:
    if requested:
        return Path(requested), "explicit"
    default_path = cwd / DEFAULT_CONSENT_FILE
    if default_path.is_file():
        return default_path, "default"
    for name in FALLBACK_CONSENT_FILES:
        fallback_path = cwd / name
        if fallback_path.is_file():
            return fallback_path, "fallback"
    return default_path, "default_missing"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate PR8.4 canary consent evidence.")
    parser.add_argument(
        "--consent_file",
        default=None,
        help=(
            "General canary consent evidence file. Defaults to "
            f"{DEFAULT_CONSENT_FILE}, with {', '.join(FALLBACK_CONSENT_FILES)} fallback."
        ),
    )
    parser.add_argument("--output_json", default="out/pr84_consent_evidence.json")
    parser.add_argument("--required_uid_photo_rows_file", default=DEFAULT_REQUIRED_UID_PHOTO_ROWS_FILE)
    args = parser.parse_args(argv)

    consent_path, consent_file_selection = resolve_consent_path(args.consent_file)
    required_rows_path = Path(args.required_uid_photo_rows_file)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "consentFile": consent_path.name,
        "requestedConsentFile": Path(args.consent_file).name if args.consent_file else None,
        "consentFileSelection": consent_file_selection,
        "fallbackConsentFiles": list(FALLBACK_CONSENT_FILES),
        "requiredUidPhotoRowsFile": str(required_rows_path),
        **evaluate_consent_file_with_required_rows(
            consent_path,
            required_rows_path=required_rows_path,
        ),
    }
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "valid": report["valid"],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
