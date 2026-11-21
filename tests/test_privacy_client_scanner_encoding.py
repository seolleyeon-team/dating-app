"""Privacy scanner encoding coverage.

The scanner used to read every client source with ``errors="ignore"``. A file
stored as UTF-16 then decoded into text whose characters were separated by NUL
bytes, so no marker ever matched and the file passed silently. A scanner that
cannot read a file must say so instead of reporting a clean result.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from privacy_client_scanner import (  # noqa: E402
    decode_client_source,
    scan_client_files,
)
from repo_source_files import repository_files  # noqa: E402

LEAKY_SOURCE = (
    "class Leak {\n"
    "  static const bucket = 'seolleyeon-final-private-source-photos';\n"
    "}\n"
)
CLEAN_SOURCE = "class Clean {\n  static const value = 'ok';\n}\n"


def _client_file(root: Path, name: str, data: bytes) -> Path:
    target = root / "lib" / "features" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def test_utf8_client_source_is_scanned_normally(tmp_path):
    _client_file(tmp_path, "clean.dart", CLEAN_SOURCE.encode("utf-8"))
    _client_file(tmp_path, "leaky.dart", LEAKY_SOURCE.encode("utf-8"))

    scan = scan_client_files(tmp_path)

    assert scan.scanned_file_count == 2
    assert scan.leakage_count == 1
    assert scan.unscannable_files == ()


def test_utf16_client_source_is_reported_instead_of_silently_passing(tmp_path):
    path = _client_file(tmp_path, "wide.dart", LEAKY_SOURCE.encode("utf-16"))

    scan = scan_client_files(tmp_path)

    assert scan.scanned_file_count == 1
    # 조용한 통과가 아니라 명시적 보고여야 한다.
    assert scan.unscannable_count == 1
    assert scan.unscannable_files == (str(path),)


def test_decode_client_source_rejects_wide_encodings():
    assert decode_client_source(CLEAN_SOURCE.encode("utf-8")) == CLEAN_SOURCE

    for data in (
        CLEAN_SOURCE.encode("utf-16"),
        CLEAN_SOURCE.encode("utf-16-be"),
        CLEAN_SOURCE.encode("utf-16-le"),
    ):
        with pytest.raises(UnicodeDecodeError):
            decode_client_source(data)


def test_repository_client_sources_are_all_decodable():
    """실제 레포에 검사 불가능한 클라이언트 소스가 남아 있지 않아야 한다."""
    scan = scan_client_files(REPO_ROOT)

    assert scan.unscannable_files == ()
    assert scan.scanned_file_count > 0


TRACKED_SOURCE_SUFFIXES = {
    ".dart",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
    ".json",
    ".rules",
    ".sh",
    ".yaml",
    ".yml",
}
SKIPPED_DIRECTORY_NAMES = {
    ".git",
    ".dart_tool",
    "build",
    "node_modules",
    "__pycache__",
    ".venv",
}


def test_no_tracked_source_file_uses_a_wide_encoding():
    """UTF-16 소스는 grep 기반 도구 전체를 조용히 무력화한다."""
    offenders = []
    # git 이 아는 파일만 본다. 작업 트리를 그대로 걸으면 무시된 로컬 산출물
    # (.tmp/ 의 복원 스냅샷 등)까지 읽어서 clean checkout 과 결과가 갈린다.
    candidates = repository_files(REPO_ROOT)
    if candidates is None:
        candidates = [path for path in REPO_ROOT.rglob("*") if path.is_file()]
    for path in candidates:
        if any(part in SKIPPED_DIRECTORY_NAMES for part in path.parts):
            continue
        if path.suffix.lower() not in TRACKED_SOURCE_SUFFIXES:
            continue
        if path.read_bytes()[:2] in (b"\xff\xfe", b"\xfe\xff"):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []
