from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import now_utc, pipeline_paths, to_portable_path
from .pending_state import pending_is_resolved
from .qa import inspect_image_detail


RECEIPT_SCHEMA_VERSION = "seolleyeon_one_asset_transaction_v3"

PARENT_OWNED_CONTROLLER_RELATIVE_PATHS = (
    "ai_image/manifests/current_chunk_plan.json",
    "ai_image/manifests/current_chunk_state.json",
)

FORBIDDEN_CHILD_RELATIVE_PATHS = (
    "ai_image/manifests/asset_qa_manifest.jsonl",
    "ai_image/manifests/identity_qa_manifest.jsonl",
    "ai_image/manifests/approved_identity_manifest.jsonl",
    "ai_image/manifests/rejected_identity_manifest.jsonl",
    "ai_image/manifests/needs_review_identity_manifest.jsonl",
    "ai_image/manifests/manual_review_required.flag",
    "ai_image/reports/latest_distribution_audit.json",
    "ai_image/reports/distribution_audit.json",
    "ai_image/reports/distribution_report.csv",
    "ai_image/reports/visual_verdict/asset_qa_latest.json",
    "ai_image/reports/visual_verdict/identity_qa_latest.json",
    "ai_image/reports/visual_verdict/distribution_audit_latest.json",
    "lib/ai_recommend_model/seolleyeon_run_all.py",
    "lib/ai_recommend_model/seolleyeon_svd_train_export.py",
    "lib/ai_recommend_model/seolleyeon_knn_train_export.py",
    "lib/ai_recommend_model/seolleyeon_clip_train_export.py",
    "lib/ai_recommend_model/seolleyeon_clip_embedder.py",
    "lib/ai_recommend_model/seolleyeon_rrf_export.py",
    "lib/ai_recommend_model/seolleyeon_rec_common_v3.py",
)

FORBIDDEN_RECEIPT_CLAIMS = {
    "visualQaApproved",
    "visualQAApproved",
    "identityApproved",
    "distributionApproved",
    "countsTowardDistribution",
    "finalDatasetApproved",
    "completionPassed",
}


class OneAssetTransactionError(RuntimeError):
    pass


def _root(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).root


def _as_path(root: Path | str | None, value: Any) -> Path:
    text = str(value or "")
    if not text:
        return Path("")
    path = Path(text)
    if path.is_absolute():
        return path
    return _root(root) / path


def _same_path(root: Path | str | None, actual: Any, expected: Any) -> bool:
    try:
        return _as_path(root, actual).resolve() == _as_path(root, expected).resolve()
    except OSError:
        return False


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_snapshot_name(path_text: str) -> str:
    return path_text.replace(":", "").replace("\\", "__").replace("/", "__")


def transaction_receipt_path(root: Path | str | None, chunk_id: str, asset_id: str, attempt: int) -> Path:
    return pipeline_paths(root).reports / "chunks" / chunk_id / "transactions" / f"{asset_id}_attempt{attempt}.json"


def build_one_asset_worker_prompt(
    expected: Mapping[str, Any],
    *,
    generation_prompt: str = "",
    reference_path: str | None = None,
) -> str:
    receipt_path = str(expected.get("expectedReceiptPath") or transaction_receipt_path(None, str(expected.get("chunkId") or ""), str(expected.get("assetId") or ""), int(expected.get("attempt") or 0)))
    reference_block = ""
    if reference_path:
        reference_block = (
            "\nReference requirement:\n"
            f"- referencePath: {reference_path}\n"
            "- Use the reference face_card as the same-person identity anchor.\n"
            "- If the reference is unavailable, write a failed receipt with error=reference_missing and stop.\n"
            "- The receipt must include referenceAttached=true and referencePathSha256 for this attached image.\n"
        )
    return (
        "Run exactly one Seolleyeon one-asset Image Gen transaction.\n\n"
        "You are the one-asset worker, not the controller.\n"
        "Process only this asset:\n"
        f"- chunkId: {expected.get('chunkId')}\n"
        f"- assetId: {expected.get('assetId')}\n"
        f"- profileId: {expected.get('profileId')}\n"
        f"- gender: {expected.get('gender')}\n"
        f"- numericId: {expected.get('numericId')}\n"
        f"- shotType: {expected.get('shotType')}\n"
        f"- attempt: {expected.get('attempt')}\n"
        f"- expectedRawPath: {expected.get('expectedRawPath')}\n"
        f"- expectedFinalPath: {expected.get('expectedFinalPath')}\n"
        f"- expectedReceiptPath: {receipt_path}\n"
        f"{reference_block}\n"
        "Allowed actions:\n"
        "1. Generate exactly one image for this asset using Codex internal Image Gen.\n"
        "2. Recover that generated image to the expected raw and final paths.\n"
        "3. Resolve the matching pending-imagegen.json for this asset only.\n"
        "4. Run single-asset file QA only as local receipt evidence; do not run the global file-qa command.\n"
        "5. Write the transaction receipt JSON at the expected receipt path.\n"
        "6. Stop.\n\n"
        "Allowed write paths:\n"
        "- The expected raw image path for this asset only.\n"
        "- The expected final image path for this asset only.\n"
        "- The expected receipt path for this asset only.\n"
        "- The matching pending-imagegen.json for this asset only.\n"
        "- Optional per-asset temp/file-QA report paths under the current chunk report directory.\n\n"
        "Forbidden actions:\n"
        "- Do not process any other asset.\n"
        "- Do not process any other identity.\n"
        "- Do not run scripts/run_ai_image_pipeline_v3.py file-qa.\n"
        "- Do not run scripts/run_ai_image_pipeline_v3.py apply-visual-asset-qa.\n"
        "- Do not run scripts/run_ai_image_pipeline_v3.py apply-visual-identity-qa.\n"
        "- Do not run scripts/run_ai_image_pipeline_v3.py apply-visual-distribution-audit.\n"
        "- Do not run distribution audit.\n"
        "- Do not run completion check.\n"
        "- Do not run visual QA.\n"
        "- Do not apply visual-verdict JSON.\n"
        "- Do not update approved_identity_manifest.jsonl.\n"
        "- Do not update asset_qa_manifest.jsonl.\n"
        "- Do not update identity_qa_manifest.jsonl.\n"
        "- Do not update latest_distribution_audit.json.\n"
        "- Do not run supervisor.\n"
        "- Do not run bounded-chunk-run recursively.\n"
        "- Do not clear manual_review_required.flag.\n"
        "- Do not modify recommender files.\n"
        "- Do not continue after the receipt is written.\n\n"
        "Receipt rules:\n"
        f"- schemaVersion must be {RECEIPT_SCHEMA_VERSION}.\n"
        "- The receipt must not claim visual approval, identity approval, distribution approval, or completion.\n"
        "- Return no prose except a short confirmation that the receipt was written.\n\n"
        "Generation prompt:\n"
        f"{generation_prompt}\n"
    )


def snapshot_forbidden_files(root: Path | str | None = None, *, extra_paths: Sequence[Path | str] | None = None) -> dict[str, dict[str, Any]]:
    base = _root(root)
    # current_chunk_plan/state are parent-owned controller bookkeeping files.
    # They intentionally move while the bounded executor updates the board-visible
    # state machine around a child Image Gen call. Guarding them as child-forbidden
    # caused false-positive child_forbidden_mutation blocks after successful image
    # recovery. Validate plan/state consistency separately via bounded plan/status
    # checks and keep this guard focused on artifacts the child must never touch.
    paths = [base / relative for relative in FORBIDDEN_CHILD_RELATIVE_PATHS]
    for extra in extra_paths or ():
        path = Path(extra)
        paths.append(path if path.is_absolute() else base / path)
    snapshot: dict[str, dict[str, Any]] = {}
    for path in paths:
        key = to_portable_path(path)
        snapshot[key] = {
            "exists": path.exists(),
            "sha256": _sha256(path),
            "size": path.stat().st_size if path.exists() else None,
        }
    return snapshot


def backup_forbidden_files(
    root: Path | str | None,
    snapshot: Mapping[str, Mapping[str, Any]],
    *,
    chunk_id: str,
    asset_id: str,
    attempt: int,
) -> dict[str, Any]:
    backup_root = pipeline_paths(root).reports / "chunks" / chunk_id / "forbidden_file_backups" / f"{asset_id}_attempt{attempt}"
    backups = backup_root / "before"
    quarantine = backup_root / "quarantine"
    backups.mkdir(parents=True, exist_ok=True)
    quarantine.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schemaVersion": "seolleyeon_forbidden_file_backup_v3",
        "chunkId": chunk_id,
        "assetId": asset_id,
        "attempt": attempt,
        "createdAt": now_utc(),
        "backupRoot": to_portable_path(backup_root),
        "quarantineRoot": to_portable_path(quarantine),
        "entries": {},
    }
    entries = payload["entries"]
    for path_text, before in snapshot.items():
        path = Path(path_text)
        entry = {
            "path": path_text,
            "beforeExists": bool(before.get("exists")),
            "beforeSha256": before.get("sha256"),
            "beforeSize": before.get("size"),
            "backupPath": None,
        }
        if path.exists() and path.is_file():
            backup_path = backups / _safe_snapshot_name(path_text)
            shutil.copy2(path, backup_path)
            entry["backupPath"] = to_portable_path(backup_path)
        entries[path_text] = entry
    metadata_path = backup_root / "backup_metadata.json"
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["metadataPath"] = to_portable_path(metadata_path)
    return payload


def restore_forbidden_files(
    root: Path | str | None,
    backup: Mapping[str, Any],
    violations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    del root
    quarantine_root = Path(str(backup.get("quarantineRoot") or ""))
    quarantine_root.mkdir(parents=True, exist_ok=True)
    entries = backup.get("entries") if isinstance(backup.get("entries"), Mapping) else {}
    report: dict[str, Any] = {
        "schemaVersion": "seolleyeon_forbidden_file_restore_v3",
        "restoredAt": now_utc(),
        "backupRoot": backup.get("backupRoot"),
        "quarantineRoot": to_portable_path(quarantine_root),
        "items": [],
    }
    for violation in violations:
        path_text = str(violation.get("path") or "")
        if not path_text:
            continue
        path = Path(path_text)
        entry = entries.get(path_text) if isinstance(entries, Mapping) else None
        item = {"path": path_text, "quarantinePath": None, "action": "no_backup_available"}
        if path.exists() and path.is_file():
            quarantine_path = quarantine_root / _safe_snapshot_name(path_text)
            shutil.copy2(path, quarantine_path)
            item["quarantinePath"] = to_portable_path(quarantine_path)
        if isinstance(entry, Mapping) and entry.get("beforeExists") and entry.get("backupPath"):
            backup_path = Path(str(entry["backupPath"]))
            if backup_path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, path)
                item["action"] = "restored_from_backup"
        elif isinstance(entry, Mapping) and not entry.get("beforeExists") and path.exists():
            path.unlink()
            item["action"] = "removed_child_created_file"
        report["items"].append(item)
    restore_report_path = quarantine_root.parent / "restore_report.json"
    restore_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["reportPath"] = to_portable_path(restore_report_path)
    return report


def detect_forbidden_mutations(root: Path | str | None, snapshot: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    del root
    violations: list[dict[str, Any]] = []
    for path_text, before in snapshot.items():
        path = Path(path_text)
        exists = path.exists()
        digest = _sha256(path)
        if bool(before.get("exists")) != exists or before.get("sha256") != digest:
            violations.append(
                {
                    "path": path_text,
                    "beforeExists": bool(before.get("exists")),
                    "afterExists": exists,
                    "beforeSha256": before.get("sha256"),
                    "afterSha256": digest,
                }
            )
    return violations


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        raise OneAssetTransactionError(f"invalid_receipt_json:{exc}") from exc
    if not isinstance(payload, dict):
        raise OneAssetTransactionError("receipt_not_object")
    return payload


def _verify_match(receipt: Mapping[str, Any], expected: Mapping[str, Any], field: str) -> None:
    if str(receipt.get(field) or "") != str(expected.get(field) or ""):
        raise OneAssetTransactionError(f"receipt_{field}_mismatch")


def verify_one_asset_transaction(
    *,
    root: Path | str | None = None,
    receipt_path: Path | str,
    expected: Mapping[str, Any],
    pending_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(receipt_path)
    if not path.exists():
        raise OneAssetTransactionError("receipt_missing")
    receipt = _load_receipt(path)
    if receipt.get("schemaVersion") != RECEIPT_SCHEMA_VERSION:
        raise OneAssetTransactionError("receipt_schema_mismatch")
    for field in ("chunkId", "assetId", "profileId", "gender", "numericId", "shotType"):
        _verify_match(receipt, expected, field)
    if int(receipt.get("attempt") or 0) != int(expected.get("attempt") or 0):
        raise OneAssetTransactionError("receipt_attempt_mismatch")
    if str(receipt.get("status") or "") != "succeeded":
        raise OneAssetTransactionError("receipt_status_not_succeeded")
    for key in FORBIDDEN_RECEIPT_CLAIMS:
        if key in receipt:
            raise OneAssetTransactionError(f"receipt_forbidden_claim:{key}")
    if not _same_path(root, receipt.get("rawPath"), expected.get("expectedRawPath")):
        raise OneAssetTransactionError("receipt_raw_path_mismatch")
    if not _same_path(root, receipt.get("finalPath"), expected.get("expectedFinalPath")):
        raise OneAssetTransactionError("receipt_final_path_mismatch")

    if pending_payload is not None:
        for field in ("chunkId", "assetId", "profileId", "shotType"):
            if str(pending_payload.get(field) or "") != str(expected.get(field) or ""):
                raise OneAssetTransactionError(f"pending_{field}_mismatch")
        if int(pending_payload.get("attempt") or 0) != int(expected.get("attempt") or 0):
            raise OneAssetTransactionError("pending_attempt_mismatch")
        if not (pending_is_resolved(pending_payload) or bool(receipt.get("pendingResolved"))):
            raise OneAssetTransactionError("pending_not_resolved")

    expected_reference = str(expected.get("referencePath") or "")
    if expected_reference:
        if not bool(receipt.get("referenceAttached")):
            raise OneAssetTransactionError("receipt_reference_not_attached")
        if not _same_path(root, receipt.get("referencePath"), expected_reference):
            raise OneAssetTransactionError("receipt_reference_path_mismatch")
        reference_path = _as_path(root, expected_reference)
        reference_digest = _sha256(reference_path)
        expected_digest = str(expected.get("referencePathSha256") or reference_digest or "")
        if not reference_digest or str(receipt.get("referencePathSha256") or "") != expected_digest:
            raise OneAssetTransactionError("receipt_reference_hash_mismatch")

    raw_path = _as_path(root, receipt.get("rawPath"))
    final_path = _as_path(root, receipt.get("finalPath"))
    raw_detail = inspect_image_detail(raw_path)
    final_detail = inspect_image_detail(final_path)
    if not raw_detail.get("ok"):
        raise OneAssetTransactionError("raw_file_invalid:" + ",".join(str(item) for item in raw_detail.get("reasons", [])))
    if not final_detail.get("ok"):
        raise OneAssetTransactionError("final_file_invalid:" + ",".join(str(item) for item in final_detail.get("reasons", [])))
    return {
        "valid": True,
        "receipt": dict(receipt),
        "assetId": str(receipt.get("assetId") or ""),
        "rawPath": to_portable_path(raw_path),
        "finalPath": to_portable_path(final_path),
        "fileQa": final_detail,
    }


def build_receipt_from_existing_file(
    *,
    root: Path | str | None,
    expected: Mapping[str, Any],
    source: str = "parent_reconcile_existing_file",
    status: str = "succeeded",
) -> dict[str, Any]:
    raw_path = _as_path(root, expected.get("expectedRawPath"))
    final_path = _as_path(root, expected.get("expectedFinalPath"))
    reference_path = _as_path(root, expected.get("referencePath")) if expected.get("referencePath") else None
    final_detail = inspect_image_detail(final_path)
    raw_detail = inspect_image_detail(raw_path) if raw_path.exists() else final_detail
    ok = bool(final_detail.get("ok"))
    return {
        "schemaVersion": RECEIPT_SCHEMA_VERSION,
        "transactionId": f"{expected.get('chunkId')}_{expected.get('assetId')}_attempt{expected.get('attempt')}",
        "chunkId": str(expected.get("chunkId") or ""),
        "assetId": str(expected.get("assetId") or ""),
        "profileId": str(expected.get("profileId") or ""),
        "gender": str(expected.get("gender") or ""),
        "numericId": str(expected.get("numericId") or ""),
        "shotType": str(expected.get("shotType") or ""),
        "attempt": int(expected.get("attempt") or 0),
        "startedAt": now_utc(),
        "finishedAt": now_utc(),
        "generated": "unknown",
        "recovered": final_path.exists(),
        "pendingResolved": True,
        "fileQaRan": True,
        "fileQaPassed": ok,
        "rawPath": to_portable_path(raw_path if raw_path.exists() else final_path),
        "finalPath": to_portable_path(final_path),
        "sourceGeneratedImagePath": "",
        "referencePath": to_portable_path(reference_path) if reference_path else None,
        "referenceAttached": bool(reference_path),
        "referencePathSha256": _sha256(reference_path) if reference_path else None,
        "fileQa": {
            "decision": "file_passed" if ok else "file_rejected",
            "width": int(final_detail.get("width") or 0),
            "height": int(final_detail.get("height") or 0),
            "format": final_detail.get("format") or "",
            "aspectRatio": (float(final_detail.get("width") or 0) / float(final_detail.get("height") or 1)),
            "sizeBytes": int(final_detail.get("fileBytes") or 0),
            "reasons": list(final_detail.get("reasons", [])),
        },
        "workerActions": [source, "file_qa_ran"],
        "stdoutLog": "",
        "stderrLog": "",
        "error": None if ok else ";".join(str(item) for item in final_detail.get("reasons", [])),
        "status": status if ok else "failed",
        "source": source,
    }


def write_receipt(path: Path | str, payload: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Seolleyeon one-asset transaction receipts.")
    parser.add_argument("command", choices=["verify"])
    parser.add_argument("--root", default=None)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected", required=True, help="JSON object with expected asset fields.")
    parser.add_argument("--pending", default="")
    args = parser.parse_args(argv)
    expected = json.loads(args.expected)
    pending = json.loads(Path(args.pending).read_text(encoding="utf-8")) if args.pending else None
    result = verify_one_asset_transaction(root=args.root, receipt_path=args.receipt, expected=expected, pending_payload=pending)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
