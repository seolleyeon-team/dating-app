from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


CLIENT_EXTENSIONS = {".dart", ".js", ".jsx", ".ts", ".tsx"}
ROOT_CLIENT_PATHS = (
    Path("lib/features"),
    Path("lib/services"),
    Path("lib/shared"),
    Path("lib/data"),
    Path("build/web"),
)
FESTIVAL_CLIENT_PATHS = (Path("src"), Path("lib"), Path("build/web"))
POLICY_ALLOWLIST_FILES = {
    "avatar_generation_models.dart",
    "avatar_lock_policy.dart",
    "profile_display_image_resolver.dart",
}
PRIVATE_MEDIA_MARKERS = (
    "private-source-photos",
    "avatar-temp",
    "chat-profile-photos",
)
SENSITIVE_MARKERS = PRIVATE_MEDIA_MARKERS + (
    "userprivatemedia",
    "clipembeddings",
    "sourcephotorefs",
    "sourcephotogcsuri",
    "gcsuri",
    "raw_landmarks",
    "face_landmarks",
    "facelandmarks",
    "blendshapes",
    "x-goog-signature",
    "x-goog-credential",
    "googleaccessid",
    "signedurl",
    "getsignedurl",
)
SIGNED_POLICY_MARKERS = {
    "x-goog-signature",
    "x-goog-credential",
    "googleaccessid",
    "signedurl",
    "getsignedurl",
}
SAFE_LOG_WRAPPERS = (
    "privacylogutils.",
    "firebasediagnostics.safeerrorforlog(",
)
SAFE_METADATA_FRAGMENTS = (
    ".scheme",
    ".host",
    ".queryparameters.keys",
    ".method",
    ".statuscode",
    ".code",
    ".runtimetype",
)
SENSITIVE_LOG_IDENTIFIERS = re.compile(
    r"\b(uid|email|token|url|uri|path|sourcephotourl|error|stack|stacktrace|request|response|userinfo|nickname|user)\b",
    re.IGNORECASE,
)
SENSITIVE_IDENTITY_ALIAS = re.compile(
    r"\b(?:[A-Za-z_]\w*(?:Id|UID|Uid)\w*|uid[A-Z_]\w*)\b"
)
LOG_CALL_RE = re.compile(r"\b(?:debugPrint|print)\s*\((.*?)\)\s*;", re.DOTALL)
INTERPOLATION_RE = re.compile(r"\$([A-Za-z_]\w*)|\$\{(.*?)\}", re.DOTALL)
BUILT_PRIVATE_BUCKET_RE = re.compile(
    r"(?:(?:gs|gcs)://|https?://(?:storage\.googleapis\.com/|firebasestorage\.googleapis\.com/v0/b/)?)"
    r"[a-z0-9][a-z0-9._-]{0,222}(?:private-source-photos|avatar-temp|chat-profile-photos)"
    r"|\b[a-z0-9](?:[a-z0-9.-]{0,220}[a-z0-9])?-(?:private-source-photos|avatar-temp|chat-profile-photos)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClientSurfaceScan:
    scanned_file_count: int
    leakage_count: int


def scan_client_files(
    repo_root: Path,
    *,
    festival_roots: Sequence[Path] = (),
) -> ClientSurfaceScan:
    files = list(_iter_surface_files(repo_root, festival_roots=festival_roots))
    leakage_count = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _file_has_leak(path, text):
            leakage_count += 1
    return ClientSurfaceScan(
        scanned_file_count=len(files),
        leakage_count=leakage_count,
    )


def _iter_surface_files(
    repo_root: Path,
    *,
    festival_roots: Sequence[Path],
) -> Iterable[Path]:
    seen: set[Path] = set()
    roots: list[Path] = [repo_root / relative for relative in ROOT_CLIENT_PATHS]
    for festival_root in festival_roots:
        roots.extend(Path(festival_root) / relative for relative in FESTIVAL_CLIENT_PATHS)
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in CLIENT_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def _file_has_leak(path: Path, text: str) -> bool:
    code = _strip_comments(text)
    lowered = code.lower()
    marker_candidates = SENSITIVE_MARKERS
    if path.name.lower() in POLICY_ALLOWLIST_FILES:
        marker_candidates = ()
    elif "build" in {part.lower() for part in path.parts}:
        if BUILT_PRIVATE_BUCKET_RE.search(code):
            return True
        marker_candidates = tuple(
            marker
            for marker in SENSITIVE_MARKERS
            if marker not in SIGNED_POLICY_MARKERS
            and marker not in PRIVATE_MEDIA_MARKERS
        )
    if any(marker in lowered for marker in marker_candidates):
        return True
    return _has_unsafe_log_call(code)


def _strip_comments(text: str) -> str:
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", without_blocks)


def _has_unsafe_log_call(text: str) -> bool:
    for match in LOG_CALL_RE.finditer(text):
        expression = match.group(1).strip()
        if _unsafe_log_expression(expression):
            return True
    return False


def _contains_sensitive_log_identifier(value: str) -> bool:
    return bool(
        SENSITIVE_LOG_IDENTIFIERS.search(value)
        or SENSITIVE_IDENTITY_ALIAS.search(value)
    )


def _unsafe_log_expression(expression: str) -> bool:
    interpolations = list(INTERPOLATION_RE.finditer(expression))
    if not interpolations:
        if expression.startswith(("'", '"')):
            return False
        return _contains_sensitive_log_identifier(expression)
    for match in interpolations:
        value = (match.group(1) or match.group(2) or "").strip()
        lowered = value.lower()
        if any(wrapper in lowered for wrapper in SAFE_LOG_WRAPPERS):
            continue
        if "isnotempty" in lowered or "!= null" in lowered:
            continue
        if any(fragment in lowered for fragment in SAFE_METADATA_FRAGMENTS):
            continue
        if _contains_sensitive_log_identifier(value):
            return True
    return False


def value_contains_privacy_leak(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if any(marker in str(key).lower() for marker in SENSITIVE_MARKERS):
                return True
            if value_contains_privacy_leak(child):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(value_contains_privacy_leak(child) for child in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in SENSITIVE_MARKERS)
    return False


def count_leaky_records(value: object) -> int:
    if not isinstance(value, dict):
        return int(value_contains_privacy_leak(value))
    return sum(1 for child in value.values() if value_contains_privacy_leak(child))
