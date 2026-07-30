#!/usr/bin/env python3
"""Sanitized Firestore migration from source project to staging.

Default mode is dry-run. The script refuses to copy private media collections,
image URLs, signed URLs, source photo references, raw vectors, and private GCS
paths. It preserves document IDs and writes only when --apply is passed.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from google.cloud import firestore


DEFAULT_DENY_COLLECTIONS = {
    "userPrivateMedia",
    "clipEmbeddings",
    "avatarJobs",
    "avatarCandidates",
    "privateMedia",
    "sourcePhotoMetadata",
    "faceEmbeddings",
}

DENY_COLLECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"private",
        r"embedding",
        r"sourcePhoto",
        r"avatarCandidate",
        r"avatarJob",
        r"temp",
        r"signedUrl",
        r"face",
    )
]

DROP_KEY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^photoUrls$",
        r"^avatarUrls$",
        r"approvedAvatarUrl",
        r"approvedAvatarStoragePath",
        r"realProfilePhotoUrl",
        r"chatRealPhotoUrl",
        r"realPhotoUrl",
        r"sourcePhoto",
        r"gcsUri",
        r"imageRef",
        r"imageUrl",
        r"imageUrls",
        r"previewUrl",
        r"downloadUrl",
        r"signedUrl",
        r"signedURL",
        r"faceEmbedding",
        r"clipEmbedding",
        r"embedding",
        r"vector",
        r"rawVector",
        r"tempAvatarUrl",
        r"candidateImageRef",
    )
]

SUSPICIOUS_VALUE_MARKERS = [
    "gs://",
    "gcs://",
    "seolleyeon-private-source-photos",
    "seolleyeon-final-private-source-photos",
    "seolleyeon-chat-profile-photos",
    "seolleyeon-final-chat-profile-photos",
    "seolleyeon-avatar-temp",
    "seolleyeon-final-avatar-temp",
    "seolleyeon-approved-avatars",
    "x-goog-signature",
    "x-goog-credential",
    "x-goog-expires",
    "googleaccessid",
    "signature=",
    "expires=",
]

SAFE_USER_FIELDS = {
    "uid",
    "kakaoUserId",
    "nickname",
    "university",
    "department",
    "major",
    "gender",
    "age",
    "birthYear",
    "year",
    "interests",
    "selfIntroduction",
    "status",
    "isStudentVerified",
    "studentEmail",
    "studentVerifiedAt",
    "verifiedAt",
    "createdAt",
    "updatedAt",
    "lastLoginAt",
    "lastActiveAt",
    "onboarding",
    "idealType",
    "profileImageMode",
    "initialSetupComplete",
    "onboardingCompletedAt",
}


@dataclass
class Stats:
    collections_scanned: int = 0
    collections_denied: int = 0
    docs_scanned: int = 0
    docs_would_write: int = 0
    docs_written: int = 0
    docs_dropped_empty: int = 0
    fields_dropped: int = 0
    suspicious_values_dropped: int = 0
    denied_collections: list[str] = field(default_factory=list)
    migrated_collections: dict[str, int] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)


def firestore_value_to_jsonish(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def is_denied_collection(name: str) -> bool:
    return name in DEFAULT_DENY_COLLECTIONS or any(pattern.search(name) for pattern in DENY_COLLECTION_PATTERNS)


def should_drop_key(key: str) -> bool:
    return any(pattern.search(key) for pattern in DROP_KEY_PATTERNS)


def is_suspicious_string(value: str) -> bool:
    lower = value.lower()
    if "firebasestorage.googleapis.com" in lower and ("alt=media" in lower or "/source/" in lower or "%2fsource%2f" in lower):
        return True
    return any(marker in lower for marker in SUSPICIOUS_VALUE_MARKERS)


def sanitize(value: Any, *, path: str, stats: Stats, users_mode: bool = False) -> tuple[bool, Any]:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if should_drop_key(str(key)):
                stats.fields_dropped += 1
                continue
            keep, sanitized = sanitize(child, path=child_path, stats=stats, users_mode=users_mode)
            if keep:
                out[str(key)] = sanitized
        return True, out
    if isinstance(value, list):
        out_list: list[Any] = []
        for index, child in enumerate(value):
            keep, sanitized = sanitize(child, path=f"{path}[{index}]", stats=stats, users_mode=users_mode)
            if keep:
                out_list.append(sanitized)
        return True, out_list
    if isinstance(value, str):
        if is_suspicious_string(value):
            stats.suspicious_values_dropped += 1
            return False, None
        return True, value
    return True, value


def sanitize_user_doc(data: Mapping[str, Any], stats: Stats) -> dict[str, Any]:
    filtered = {key: value for key, value in data.items() if key in SAFE_USER_FIELDS}
    keep, sanitized = sanitize(filtered, path="users", stats=stats, users_mode=True)
    assert keep and isinstance(sanitized, dict)
    onboarding = sanitized.get("onboarding")
    if isinstance(onboarding, dict):
        onboarding.pop("photoUrls", None)
        onboarding.pop("avatarUrls", None)
        sanitized["onboarding"] = onboarding
    sanitized["profileImageMode"] = "avatar"
    return sanitized


def sanitize_doc(collection: str, data: Mapping[str, Any], stats: Stats) -> dict[str, Any]:
    if collection == "users":
        return sanitize_user_doc(data, stats)
    keep, sanitized = sanitize(data, path=collection, stats=stats)
    assert keep and isinstance(sanitized, dict)
    return sanitized


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def iter_collections(client: firestore.Client, allowlist: list[str]) -> Iterable[firestore.CollectionReference]:
    if allowlist:
        for name in allowlist:
            yield client.collection(name)
    else:
        yield from client.collections()


def flush_batch(batch: firestore.WriteBatch | None, count: int) -> None:
    if batch is not None and count > 0:
        batch.commit()


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.source_project == args.target_project:
        raise SystemExit("source_project and target_project must differ")
    if args.target_project != "seolleyeon-final":
        raise SystemExit("target_project must be seolleyeon-final")
    if args.apply and not args.sanitize_ack:
        raise SystemExit("--apply requires --sanitize_ack")
    if args.delete_target_before_apply:
        raise SystemExit("--delete_target_before_apply is intentionally unsupported in this safe migration script")

    source = firestore.Client(project=args.source_project, database=args.database)
    target = firestore.Client(project=args.target_project, database=args.database)
    allowlist = parse_csv(args.collection_allowlist)
    extra_deny = set(parse_csv(args.collection_denylist))
    stats = Stats()

    for collection_ref in iter_collections(source, allowlist):
        name = collection_ref.id
        stats.collections_scanned += 1
        if is_denied_collection(name) or name in extra_deny:
            stats.collections_denied += 1
            stats.denied_collections.append(name)
            stats.decisions.append({"collection": name, "classification": "DENY_PRIVATE"})
            continue
        if name == "users" and args.skip_users:
            stats.collections_denied += 1
            stats.denied_collections.append(name)
            stats.decisions.append({"collection": name, "classification": "SKIP_USERS"})
            continue

        stats.decisions.append({"collection": name, "classification": "SANITIZE_REQUIRED"})
        batch = target.batch() if args.apply else None
        batch_count = 0
        collection_written = 0

        query = collection_ref.limit(args.max_docs_per_collection) if args.max_docs_per_collection else collection_ref
        for doc in query.stream():
            stats.docs_scanned += 1
            data = doc.to_dict() or {}
            sanitized = sanitize_doc(name, data, stats)
            if not sanitized:
                stats.docs_dropped_empty += 1
                continue
            stats.docs_would_write += 1
            collection_written += 1
            if args.apply:
                assert batch is not None
                batch.set(target.collection(name).document(doc.id), sanitized)
                batch_count += 1
                if batch_count >= args.batch_size:
                    flush_batch(batch, batch_count)
                    stats.docs_written += batch_count
                    batch = target.batch()
                    batch_count = 0
        if args.apply and batch_count:
            flush_batch(batch, batch_count)
            stats.docs_written += batch_count
        if collection_written:
            stats.migrated_collections[name] = collection_written

    result = {
        "mode": "apply" if args.apply else "dry_run",
        "source_project": args.source_project,
        "target_project": args.target_project,
        "database": args.database,
        "stats": stats.__dict__,
        "status": "pass",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source_project", default="seolleyeon")
    parser.add_argument("--target_project", default="seolleyeon-final")
    parser.add_argument("--database", default="(default)")
    parser.add_argument("--collection_allowlist", default="")
    parser.add_argument("--collection_denylist", default="")
    parser.add_argument("--max_docs_per_collection", type=int, default=25)
    parser.add_argument("--skip_users", action="store_true")
    parser.add_argument("--include_users_sanitized", action="store_true")
    parser.add_argument("--resume_from", default="")
    parser.add_argument("--batch_size", type=int, default=250)
    parser.add_argument("--delete_target_before_apply", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--sanitize_ack", action="store_true")
    parser.add_argument("--report_json", default="out/staging_migration_dry_run.json")
    parser.add_argument("--dry_run", action="store_true", help="Explicit dry-run marker for readability.")
    args = parser.parse_args()

    result = run(args)
    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, default=firestore_value_to_jsonish, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, default=firestore_value_to_jsonish, ensure_ascii=False))


if __name__ == "__main__":
    main()
