from __future__ import annotations

from pathlib import Path
from typing import Iterable


def normalized_uid_photo_row(uid: str, photo_path: Path | str) -> str:
    return f"{str(uid).strip().strip('<>')}={Path(str(photo_path).strip()).name}"


def parse_uid_photo_rows(lines: Iterable[str]) -> set[str]:
    rows: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            line = line[1:].strip()
        if "=" not in line:
            continue
        uid, photo = line.split("=", 1)
        uid = uid.strip().strip("<>")
        photo_name = Path(photo.strip()).name
        if uid and photo_name:
            rows.add(f"{uid}={photo_name}")
    return rows


def evaluate_exact_uid_photo_consent(
    *,
    consent_file: Path,
    expected_rows: Iterable[tuple[str, Path]],
) -> dict[str, object]:
    expected = {
        normalized_uid_photo_row(uid, photo_path)
        for uid, photo_path in expected_rows
    }
    if consent_file.is_file():
        text = consent_file.read_text(encoding="utf-8-sig", errors="replace")
        actual = parse_uid_photo_rows(text.splitlines())
    else:
        actual = set()
    matched = expected & actual
    missing = expected - actual
    unexpected = actual - expected
    satisfied = bool(expected) and not missing and not unexpected
    return {
        "required": True,
        "satisfiedByThisFile": satisfied,
        "requiredRowCount": len(expected),
        "parsedRowCount": len(actual),
        "matchedRowCount": len(matched),
        "missingRowCount": len(missing),
        "unexpectedRowCount": len(unexpected),
        "redacted": True,
    }