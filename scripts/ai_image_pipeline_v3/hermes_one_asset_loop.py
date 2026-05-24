from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .bounded_batch_executor import bounded_chunk_status, reconcile_bounded_chunk, run_bounded_chunk
from .codex_imagegen import PENDING_JSON_ALL_ZERO, PENDING_JSON_EMPTY, PENDING_JSON_INVALID, pending_path, read_pending, recover_pending_imagegen, write_pending
from .completion import completion_check
from .config import DEFAULT_CODEX_GENERATED_IMAGES_DIR, now_utc, pipeline_paths, read_jsonl, replace_with_retry, to_portable_path, write_jsonl
from .manifest import load_generation_manifest
from .one_asset_transaction import build_receipt_from_existing_file, transaction_receipt_path, write_receipt
from .pending_admin import finalize_pending_failed
from .pending_state import pending_is_resolved
from .qa import inspect_image_detail

LOOP_SCHEMA_VERSION = "seolleyeon_hermes_one_asset_loop_v3"
LOCK_STALE_SECONDS = 10 * 60
TERMINAL_ASSET_STATES = {"file_qa_passed", "file_qa_failed", "failed", "retry_needed", "missing_finalized"}
INVALID_PENDING_REASONS = {PENDING_JSON_EMPTY, PENDING_JSON_ALL_ZERO, PENDING_JSON_INVALID, "pending_json_empty", "pending_json_all_zero", "pending_json_invalid"}


@dataclass
class LoopConfig:
    root: Path
    mode: str = "once"
    max_assets: int = 1
    max_identities: int = 0
    target_approved_identities: int = 240
    target_approved_images: int = 720
    allow_imagegen: bool = False
    dry_run: bool = False
    once: bool = False
    max_cycles: int | None = None
    max_runtime_minutes: float = 10.0
    stop_on_manual_flag: bool = True
    stop_on_hard_blocker: bool = True
    write_report: bool = True
    resume: bool = False
    auto_clear_stale_manual_flag: bool = False
    codex_bin: str | None = None
    auto_resolve_pending: bool = True
    auto_reconcile: bool = True
    max_pending_attempts: int = 3
    retry_delay_seconds: float = 2.0
    fail_asset_after_max_retries: bool = True


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(dict(payload), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    replace_with_retry(tmp, path)


def _decode_bytes(data: bytes | None) -> str:
    if data is None:
        return ""
    for enc in ("utf-8", "utf-8-sig", "cp949", "mbcs", "latin-1"):
        try:
            return data.decode(enc, errors="replace")
        except LookupError:
            continue
    return data.decode("latin-1", errors="replace")


def safe_run(args: Sequence[str], *, cwd: Path, timeout: float = 300.0, input_bytes: bytes = b"") -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            list(args),
            cwd=str(cwd),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
            text=False,
        )
        stdout = _decode_bytes(proc.stdout)
        stderr = _decode_bytes(proc.stderr)
        return {
            "command": list(args),
            "returncode": int(proc.returncode),
            "stdout": stdout,
            "stderr": stderr,
            "stdoutExcerpt": stdout[-4000:],
            "stderrExcerpt": stderr[-4000:],
            "timedOut": False,
            "durationSeconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": list(args),
            "returncode": -1,
            "stdout": _decode_bytes(exc.stdout),
            "stderr": _decode_bytes(exc.stderr),
            "stdoutExcerpt": _decode_bytes(exc.stdout)[-4000:],
            "stderrExcerpt": _decode_bytes(exc.stderr)[-4000:],
            "timedOut": True,
            "durationSeconds": round(time.monotonic() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001 - fail closed with diagnostics.
        return {
            "command": list(args),
            "returncode": -2,
            "stdout": "",
            "stderr": str(exc),
            "stdoutExcerpt": "",
            "stderrExcerpt": str(exc)[-4000:],
            "timedOut": False,
            "durationSeconds": round(time.monotonic() - started, 3),
        }


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        # Windows os.kill(pid, 0) may fail for live foreign processes; use tasklist if available.
        if os.name == "nt":
            result = safe_run(["tasklist", "/FI", f"PID eq {pid}"], cwd=Path.cwd(), timeout=10)
            return str(pid) in result.get("stdout", "")
        return False


class LoopLock:
    def __init__(self, config: LoopConfig) -> None:
        self.config = config
        self.path = pipeline_paths(config.root).manifests / "hermes_one_asset_loop.lock"
        self.acquired = False

    def acquire(self, state: str = "ACQUIRE_LOCK") -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except Exception:  # noqa: BLE001
                payload = {}
            pid = int(payload.get("pid") or 0)
            heartbeat = str(payload.get("heartbeatAt") or payload.get("startedAt") or "")
            alive = _pid_alive(pid)
            stale = True
            try:
                # ISO offset parse without importing dateutil.
                from datetime import datetime
                hb = datetime.fromisoformat(heartbeat)
                stale = (time.time() - hb.timestamp()) > LOCK_STALE_SECONDS
            except Exception:  # noqa: BLE001
                stale = True
            if alive and not stale:
                return {"acquired": False, "result": "LOOP_ALREADY_RUNNING", "lock": payload}
            archive = self.path.with_name(f"hermes_one_asset_loop.stale.{int(time.time())}.lock")
            try:
                self.path.replace(archive)
            except OSError:
                shutil.copy2(self.path, archive)
                self.path.unlink(missing_ok=True)
        self.heartbeat(state)
        self.acquired = True
        return {"acquired": True, "result": "LOCK_ACQUIRED", "lockPath": to_portable_path(self.path)}

    def heartbeat(self, state: str, *, chunk_id: str = "", asset_id: str = "") -> None:
        payload = {
            "schemaVersion": LOOP_SCHEMA_VERSION,
            "pid": os.getpid(),
            "startedAt": now_utc(),
            "heartbeatAt": now_utc(),
            "mode": self.config.mode,
            "chunkId": chunk_id,
            "assetId": asset_id,
            "currentState": state,
        }
        if self.path.exists():
            try:
                old = json.loads(self.path.read_text(encoding="utf-8-sig"))
                payload["startedAt"] = old.get("startedAt") or payload["startedAt"]
            except Exception:  # noqa: BLE001
                pass
        atomic_write_json(self.path, payload)

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False


def _manual_flag(root: Path) -> Path:
    return pipeline_paths(root).manifests / "manual_review_required.flag"


def _reports(root: Path) -> tuple[Path, Path, Path]:
    report_dir = pipeline_paths(root).reports / "pipeline_audit"
    report_dir.mkdir(parents=True, exist_ok=True)
    return (
        report_dir / "hermes_one_asset_loop_latest.json",
        report_dir / "hermes_one_asset_loop_latest.md",
        report_dir / "hermes_one_asset_loop_events.jsonl",
    )


def append_event(root: Path, event: Mapping[str, Any]) -> None:
    _, _, events_path = _reports(root)
    rows = read_jsonl(events_path)
    rows.append(dict(event))
    write_jsonl(events_path, rows)


def _approved_counts(root: Path) -> tuple[int, int]:
    completion = completion_check(root=root)
    return int(completion.get("approvedCompleteIdentities") or 0), int(completion.get("approvedImages") or 0)


def _current_chunk_id(status: Mapping[str, Any]) -> str:
    return str(status.get("chunkId") or status.get("validation", {}).get("chunkId") or "")


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _protected_file_hashes(root: Path) -> dict[str, str | None]:
    rels = [
        "lib/ai_recommend_model/seolleyeon_run_all.py",
        "lib/ai_recommend_model/seolleyeon_svd_train_export.py",
        "lib/ai_recommend_model/seolleyeon_knn_train_export.py",
        "lib/ai_recommend_model/seolleyeon_clip_train_export.py",
        "lib/ai_recommend_model/seolleyeon_clip_embedder.py",
        "lib/ai_recommend_model/seolleyeon_rrf_export.py",
        "lib/ai_recommend_model/seolleyeon_rec_common_v3.py",
    ]
    paths = [root / rel for rel in rels]
    paths.extend(sorted((root / "lib" / "ai_recommend_model").glob("seolleyeon_meeting_*.py")))
    paths.extend(sorted(root.glob("requirements*.txt")))
    return {to_portable_path(path): _sha256_file(path) for path in paths}


def _protected_hash_changes(before: Mapping[str, str | None], after: Mapping[str, str | None]) -> list[str]:
    keys = sorted(set(before) | set(after))
    return [key for key in keys if before.get(key) != after.get(key)]


def _expected_from_pending(root: Path, pending: Mapping[str, Any]) -> dict[str, Any]:
    asset_id = str(pending.get("assetId") or "")
    row = next((dict(r) for r in load_generation_manifest(pipeline_paths(root)) if str(r.get("assetId") or "") == asset_id), {})
    expected = dict(row)
    expected.update({
        "chunkId": str(pending.get("chunkId") or row.get("chunkId") or ""),
        "assetId": asset_id,
        "profileId": str(pending.get("profileId") or row.get("profileId") or ""),
        "gender": str(pending.get("gender") or row.get("gender") or ""),
        "numericId": str(pending.get("numericId") or row.get("numericId") or ""),
        "shotType": str(pending.get("shotType") or row.get("shotType") or ""),
        "attempt": int(pending.get("attempt") or row.get("attempt") or row.get("attemptCount") or 1),
        "expectedRawPath": str(pending.get("expectedRawPath") or row.get("expectedRawPath") or row.get("rawPath") or ""),
        "expectedFinalPath": str(pending.get("expectedFinalPath") or row.get("expectedFinalPath") or row.get("finalPath") or ""),
    })
    reference = str(pending.get("resolvedReferencePath") or pending.get("referenceLocalPath") or row.get("resolvedReferencePath") or row.get("referenceLocalPath") or "")
    if reference:
        expected["referencePath"] = reference
    return expected


def _pending_expected_file_valid(root: Path, pending: Mapping[str, Any]) -> Path | None:
    expected = _expected_from_pending(root, pending)
    for key in ("expectedFinalPath", "expectedRawPath"):
        value = str(expected.get(key) or "")
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        if path.exists() and inspect_image_detail(path).get("ok"):
            return path
    return None


def recover_existing_pending_file(root: Path, pending: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve an active pending checkpoint when the expected raw/final file already exists.

    This covers interrupted parent-managed handoffs where image generation/recovery
    wrote the image but the pending checkpoint was not marked resolved. It writes the
    same one-asset receipt shape used by the normal worker and never approves assets.
    """
    existing = _pending_expected_file_valid(root, pending)
    if existing is None:
        return {"status": "not_recoverable", "reasonCode": "expected_file_missing_or_invalid", "assetId": pending.get("assetId")}
    expected = _expected_from_pending(root, pending)
    receipt_path = transaction_receipt_path(root, str(expected["chunkId"]), str(expected["assetId"]), int(expected["attempt"]))
    receipt = build_receipt_from_existing_file(root=root, expected=expected, source="hermes_existing_pending_file")
    receipt["generated"] = "preexisting"
    receipt["pendingResolved"] = True
    write_receipt(receipt_path, receipt)
    resolved = dict(pending)
    resolved.update({
        "status": "resolved",
        "resolved": True,
        "recoveryStatus": "recovered_existing_file",
        "resolvedAt": now_utc(),
        "sourcePath": to_portable_path(existing),
        "receiptPath": to_portable_path(receipt_path),
    })
    write_pending(pending_path(root), resolved)
    return {
        "state": "PENDING_RECOVERABLE",
        "status": "succeeded",
        "assetId": expected.get("assetId"),
        "sourcePath": to_portable_path(existing),
        "receiptPath": to_portable_path(receipt_path),
        "fileQaPassed": bool(receipt.get("fileQaPassed")),
        "recoveredExistingFile": True,
    }


def _reconcile_is_safe(dry_run: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if dry_run.get("manualFlagPresent") or dry_run.get("manualReviewRequired"):
        reasons.append("manual_flag_present")
    if dry_run.get("unknownFiles"):
        reasons.append("unknown_files")
    if int(dry_run.get("extraGenerationAssetCount") or 0) != 0:
        reasons.append("extra_generation_assets")
    if dry_run.get("approvalCountWouldChange") or dry_run.get("distributionCountWouldChange"):
        reasons.append("approval_or_distribution_count_would_change")
    if dry_run.get("approvalsChanged") or dry_run.get("distributionChanged"):
        reasons.append("approval_or_distribution_changed")
    if dry_run.get("reasonsIfCannotClear") and "pending_unresolved" in list(dry_run.get("reasonsIfCannotClear") or []):
        reasons.append("pending_unresolved")
    return not reasons, reasons


def auto_reconcile_pending(root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    probe = reconcile_bounded_chunk(root=root, apply=False, dry_run=True)
    safe, reasons = _reconcile_is_safe(probe)
    if not safe:
        return {"status": "blocked", "reasonCode": "RECONCILE_UNSAFE", "unsafeReasons": reasons, "dryRun": probe}
    if dry_run:
        return {"status": "dry_run", "reasonCode": "reconcile_would_apply", "dryRun": probe}
    applied = reconcile_bounded_chunk(root=root, apply=True, dry_run=False)
    return {"status": "applied", "dryRun": probe, "apply": applied, "stateChanged": bool(applied.get("stateChanged"))}


def archive_and_reconstruct_invalid_pending(root: Path, pending: Mapping[str, Any]) -> dict[str, Any]:
    paths = pipeline_paths(root)
    path = pending_path(root)
    reason = str(pending.get("pendingInvalidReason") or pending.get("reason") or "pending_json_invalid")
    archive_dir = paths.manifests / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    archive_path = archive_dir / f"invalid_pending_{stamp}.bin"
    sidecar = archive_dir / f"invalid_pending_{stamp}.reason.json"
    if path.exists():
        shutil.copy2(path, archive_path)
    atomic_write_json(sidecar, {"reason": reason, "originalPath": to_portable_path(path), "archivePath": to_portable_path(archive_path), "updatedAt": now_utc()})

    state_path = paths.manifests / "current_chunk_state.json"
    plan_path = paths.manifests / "current_chunk_plan.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reasonCode": "PENDING_RECONSTRUCTION_FAILED", "error": str(exc), "archivePath": to_portable_path(archive_path)}
    pending_assets = [asset for asset, status in dict(state.get("assetStates") or {}).items() if status == "pending_imagegen"]
    if len(pending_assets) != 1:
        return {"status": "failed", "reasonCode": "PENDING_RECONSTRUCTION_FAILED", "pendingAssetCount": len(pending_assets), "archivePath": to_portable_path(archive_path)}
    asset_id = pending_assets[0]
    rows = load_generation_manifest(paths)
    row = next((dict(r) for r in rows if str(r.get("assetId") or "") == asset_id), None)
    if not row:
        return {"status": "failed", "reasonCode": "PENDING_RECONSTRUCTION_FAILED", "reason": "asset_not_in_generation_manifest", "assetId": asset_id, "archivePath": to_portable_path(archive_path)}
    chunk_id = str(state.get("chunkId") or plan.get("chunkId") or "")
    attempt = int(row.get("attempt") or row.get("attemptCount") or 1)
    handoff_prompt = paths.reports / "chunks" / chunk_id / "parent_imagegen_handoffs" / f"{asset_id}_attempt{attempt}.prompt.txt"
    if not handoff_prompt.exists():
        return {"status": "failed", "reasonCode": "PENDING_RECONSTRUCTION_FAILED", "reason": "handoff_prompt_missing", "assetId": asset_id, "archivePath": to_portable_path(archive_path)}
    reconstructed = dict(row)
    reconstructed.update({
        "schemaVersion": "seolleyeon_pending_imagegen_v3",
        "chunkId": chunk_id,
        "assetId": asset_id,
        "profileId": row.get("profileId"),
        "shotType": row.get("shotType"),
        "attempt": attempt,
        "status": "pending_imagegen",
        "resolved": False,
        "recoveryStatus": "pending",
        "expectedRawPath": row.get("expectedRawPath") or row.get("rawPath"),
        "expectedFinalPath": row.get("expectedFinalPath") or row.get("finalPath"),
        "handoffPromptPath": to_portable_path(handoff_prompt),
        "promptHash": row.get("promptHash"),
        "promptTargetingVersion": row.get("promptTargetingVersion"),
        "reconstructedAt": now_utc(),
        "reconstructedFromInvalidReason": reason,
    })
    write_pending(path, reconstructed)
    return {"status": "reconstructed", "assetId": asset_id, "archivePath": to_portable_path(archive_path), "sidecarPath": to_portable_path(sidecar)}


def _generated_images_snapshot() -> set[Path]:
    base = Path(os.environ.get("CODEX_GENERATED_IMAGES_DIR") or DEFAULT_CODEX_GENERATED_IMAGES_DIR)
    if not base.exists():
        return set()
    return {p.resolve() for p in base.rglob("*.png") if p.is_file()}


def _find_codex_bin(config: LoopConfig) -> str | None:
    if config.codex_bin:
        return config.codex_bin
    candidate = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    if candidate.exists():
        return str(candidate)
    resolved = shutil.which("codex") or shutil.which("codex.cmd")
    return resolved


def _run_internal_imagegen(root: Path, pending: Mapping[str, Any], config: LoopConfig) -> dict[str, Any]:
    codex = _find_codex_bin(config)
    if not codex:
        return {"status": "failed", "reasonCode": "PENDING_IMAGEGEN_WORKER_UNAVAILABLE", "generated": False, "generatedCount": 0}
    handoff_value = str(pending.get("handoffPromptPath") or "").strip()
    handoff = Path(handoff_value) if handoff_value else Path()
    if handoff_value and not handoff.is_absolute():
        handoff = root / handoff
    if not handoff_value or not handoff.exists() or not handoff.is_file():
        chunk_id = str(pending.get("chunkId") or "")
        asset_id = str(pending.get("assetId") or "")
        attempt = int(pending.get("attempt") or 1)
        handoff = root / "ai_image" / "reports" / "chunks" / chunk_id / "parent_imagegen_handoffs" / f"{asset_id}_attempt{attempt}.prompt.txt"
    if not handoff.exists() or not handoff.is_file():
        return {"status": "failed", "reasonCode": "handoff_prompt_missing", "generated": False, "generatedCount": 0}
    before = _generated_images_snapshot()
    prompt = handoff.read_text(encoding="utf-8-sig")
    asset_id = str(pending.get("assetId") or "")
    prompt += f"\n\nSTRICT LOOP OVERRIDE:\n- Generate exactly ONE image only for assetId {asset_id}.\n- Do not process any other asset.\n- Print IMAGEGEN_DONE after the single image is generated.\n"
    result = safe_run([codex, "exec", "--sandbox", "workspace-write", prompt], cwd=root, timeout=min(900, max(60, config.max_runtime_minutes * 60)), input_bytes=b"")
    after = _generated_images_snapshot()
    new_images = sorted(after - before, key=lambda p: p.stat().st_mtime if p.exists() else 0)
    out = dict(result)
    out.update({"generatedCount": len(new_images), "generatedImages": [to_portable_path(p) for p in new_images], "generated": len(new_images) == 1 and result.get("returncode") == 0})
    if len(new_images) > 1:
        out.update({"status": "failed", "reasonCode": "IMAGEGEN_MULTIPLE_OUTPUTS"})
    elif len(new_images) == 0 or result.get("returncode") != 0:
        out.update({"status": "failed", "reasonCode": "PENDING_IMAGEGEN_FAILED"})
    else:
        out.update({"status": "succeeded", "sourcePath": to_portable_path(new_images[0])})
    return out


def process_pending_imagegen_once(root: Path | str, *, allow_imagegen: bool, dry_run: bool = False, codex_bin: str | None = None) -> dict[str, Any]:
    root_path = Path(root).resolve()
    pending_file = pending_path(root_path)
    pending = read_pending(pending_file)
    if not pending:
        return {"state": "PENDING_IMAGEGEN", "status": "skipped", "reasonCode": "pending_absent"}
    if pending.get("invalid") or str(pending.get("pendingInvalidReason") or pending.get("reason") or "") in INVALID_PENDING_REASONS:
        recon = archive_and_reconstruct_invalid_pending(root_path, pending)
        return {"state": "PENDING_IMAGEGEN", "status": "blocked" if recon.get("status") != "reconstructed" else "reconstructed", **recon}
    if pending_is_resolved(pending):
        return {"state": "PENDING_RESOLVED_NEEDS_RECONCILE", "status": "skipped", "reasonCode": "pending_already_resolved", "assetId": pending.get("assetId")}
    existing = recover_existing_pending_file(root_path, pending)
    if existing.get("status") == "succeeded":
        return existing
    if dry_run:
        return {"state": "PENDING_IMAGEGEN", "status": "dry_run", "assetId": pending.get("assetId"), "generated": False}
    if not allow_imagegen:
        return {"state": "PENDING_IMAGEGEN", "status": "blocked", "reasonCode": "imagegen_not_allowed", "assetId": pending.get("assetId")}
    imagegen = _run_internal_imagegen(root_path, pending, LoopConfig(root=root_path, allow_imagegen=allow_imagegen, codex_bin=codex_bin))
    if imagegen.get("status") != "succeeded":
        return {"state": "PENDING_IMAGEGEN", "status": "failed", "assetId": pending.get("assetId"), "imagegen": imagegen, "reasonCode": imagegen.get("reasonCode")}
    recovered = recover_pending_imagegen(root=root_path, source=imagegen.get("sourcePath"), run_qa=False)
    resolved = read_pending(pending_file) or {}
    expected = _expected_from_pending(root_path, resolved or pending)
    receipt_path = transaction_receipt_path(root_path, str(expected["chunkId"]), str(expected["assetId"]), int(expected["attempt"]))
    receipt = build_receipt_from_existing_file(root=root_path, expected=expected, source="hermes_one_asset_loop")
    receipt["generated"] = True
    receipt["sourceGeneratedImagePath"] = imagegen.get("sourcePath")
    receipt["pendingResolved"] = True
    write_receipt(receipt_path, receipt)
    return {
        "state": "PENDING_IMAGEGEN",
        "status": "succeeded",
        "assetId": recovered.asset_id,
        "sourcePath": to_portable_path(Path(str(imagegen.get("sourcePath")))),
        "rawPath": to_portable_path(recovered.raw_path),
        "finalPath": to_portable_path(recovered.final_path),
        "receiptPath": to_portable_path(receipt_path),
        "fileQaPassed": bool(receipt.get("fileQaPassed")),
    }


def _chunk_assets_terminal(status: Mapping[str, Any]) -> bool:
    states = dict(status.get("assetStates") or {})
    return bool(states) and all(str(value) in TERMINAL_ASSET_STATES for value in states.values())


def effective_max_cycles(config: LoopConfig) -> int:
    """Return the runtime cycle budget for the loop.

    ``--once`` is intentionally conservative and always allows only one state
    transition. Long-running modes must not inherit argparse's historical ``1``
    default: controller handoff creation is a transition, not a generated asset,
    so smoke/chunk/target need enough budget to continue into pending imagegen,
    recovery, reconcile, retries, and the next controller step.
    """
    if config.once or config.mode == "once":
        return 1
    if config.max_cycles is not None:
        return max(1, int(config.max_cycles))
    max_assets = max(1, int(config.max_assets or 1))
    if config.mode in {"smoke", "chunk"}:
        return max_assets * 4 + 20
    if config.mode == "target":
        return max(max_assets * 4 + 20, 1024)
    return max_assets * 4 + 20


def _reached_asset_cap(config: LoopConfig, assets_generated: int) -> bool:
    return config.mode in {"smoke", "chunk"} and assets_generated >= max(1, int(config.max_assets or 1))


def _resolved_pending_is_already_reconciled(pending: Mapping[str, Any], status: Mapping[str, Any]) -> bool:
    """A resolved checkpoint may remain as audit evidence after chunk state is reconciled.

    Treat it as non-blocking only when the bounded controller says it can run and
    the pending asset is no longer the active pending_imagegen asset in chunk state.
    """
    if not pending or not pending_is_resolved(pending):
        return False
    asset_id = str(pending.get("assetId") or "")
    asset_state = str(dict(status.get("assetStates") or {}).get(asset_id) or "")
    return bool(status.get("canRun")) and str(status.get("currentAssetId") or "") == "" and asset_state != "pending_imagegen"


def run_loop(config: LoopConfig) -> dict[str, Any]:
    paths = pipeline_paths(config.root)
    root = paths.root
    protected_hashes_before = _protected_file_hashes(root)
    json_report, md_report, _ = _reports(root)
    lock = LoopLock(config)
    lock_result = lock.acquire()
    if not lock_result.get("acquired"):
        result = {"result": "LOOP_STOPPED_HARD_BLOCKER", "reasonCode": lock_result.get("result"), "mode": config.mode, "cycles": 0, "hardBlockers": [lock_result.get("result")], "nextSafeCommand": None}
        if config.write_report:
            write_loop_reports(root, result)
        return result

    cycles = 0
    assets_generated = 0
    assets_recovered = 0
    file_qa_passed = 0
    file_qa_failed = 0
    hard_blockers: list[str] = []
    start = time.monotonic()
    result_name = "LOOP_STOPPED_MAX_CYCLES"
    next_safe: str | None = None
    current_chunk = ""
    pending_present = False
    pending_failures: dict[str, int] = {}
    try:
        max_cycles = effective_max_cycles(config)
        while cycles < max_cycles:
            cycles += 1
            if (time.monotonic() - start) > config.max_runtime_minutes * 60:
                result_name = "LOOP_STOPPED_MAX_CYCLES"
                hard_blockers.append("max_runtime_minutes_exceeded")
                break
            status = bounded_chunk_status(root=root)
            pending = read_pending(pending_path(root))
            current_chunk = _current_chunk_id(status)
            if pending and _resolved_pending_is_already_reconciled(pending, status):
                pending = None
            approved_ids, approved_images = _approved_counts(root)
            manual_present = _manual_flag(root).exists()
            pending_present = bool(pending)
            asset_id = str((pending or {}).get("assetId") or status.get("currentAssetId") or "")
            lock.heartbeat("PREFLIGHT", chunk_id=current_chunk, asset_id=asset_id)
            append_event(root, {"ts": now_utc(), "cycle": cycles, "state": "PREFLIGHT", "chunkId": current_chunk, "assetId": asset_id, "action": "read_status", "result": "ok", "pendingStatus": (pending or {}).get("status", "absent") if pending else "absent", "manualFlag": manual_present, "canRun": bool(status.get("canRun")), "approvedIdentities": approved_ids, "approvedImages": approved_images})

            if manual_present and config.stop_on_manual_flag:
                result_name = "LOOP_STOPPED_HARD_BLOCKER"
                hard_blockers.append("MANUAL_REVIEW_REQUIRED")
                next_safe = "inspect ai_image/manifests/manual_review_required.flag"
                break
            if pending and (pending.get("invalid") or str(pending.get("pendingInvalidReason") or pending.get("reason") or "") in INVALID_PENDING_REASONS):
                recon = archive_and_reconstruct_invalid_pending(root, pending)
                append_event(root, {"ts": now_utc(), "cycle": cycles, "state": "PENDING_IMAGEGEN", "chunkId": current_chunk, "assetId": recon.get("assetId", asset_id), "action": "archive_reconstruct_invalid_pending", "result": recon.get("status"), "pendingStatus": "invalid", "manualFlag": manual_present, "canRun": False, "approvedIdentities": approved_ids, "approvedImages": approved_images})
                if recon.get("status") != "reconstructed":
                    result_name = "LOOP_STOPPED_HARD_BLOCKER"
                    hard_blockers.append(str(recon.get("reasonCode") or "PENDING_RECONSTRUCTION_FAILED"))
                    next_safe = "inspect ai_image/manifests/archive/ and current chunk state"
                    break
                result_name = "LOOP_STOPPED_MAX_CYCLES" if config.once else result_name
                continue
            if pending and not pending_is_resolved(pending):
                lock.heartbeat("PENDING_IMAGEGEN", chunk_id=current_chunk, asset_id=asset_id)
                if not config.auto_resolve_pending:
                    result_name = "LOOP_STOPPED_HARD_BLOCKER"
                    hard_blockers.append("auto_resolve_pending_disabled")
                    next_safe = "python scripts/run_ai_image_pipeline_v3.py hermes-one-asset-loop --root . --once --allow-imagegen --auto-resolve-pending"
                    break
                worker = process_pending_imagegen_once(root, allow_imagegen=config.allow_imagegen, dry_run=config.dry_run, codex_bin=config.codex_bin)
                append_event(root, {"ts": now_utc(), "cycle": cycles, "state": worker.get("state", "PENDING_IMAGEGEN"), "chunkId": current_chunk, "assetId": worker.get("assetId", asset_id), "action": "process_pending_imagegen_once", "result": worker.get("status"), "attempt": int((pending or {}).get("attempt") or 1), "pendingStatus": "pending_imagegen", "manualFlag": manual_present, "canRun": False, "approvedIdentities": approved_ids, "approvedImages": approved_images})
                if worker.get("status") == "succeeded":
                    assets_generated += 0 if worker.get("recoveredExistingFile") else 1
                    assets_recovered += 1
                    if worker.get("fileQaPassed"):
                        file_qa_passed += 1
                    else:
                        file_qa_failed += 1
                    pending_failures.pop(str(worker.get("assetId") or asset_id), None)
                    result_name = "LOOP_STOPPED_MAX_CYCLES" if config.once else result_name
                    continue
                if worker.get("status") == "dry_run":
                    result_name = "LOOP_DRY_RUN_OK"
                    next_safe = "python scripts/run_ai_image_pipeline_v3.py hermes-one-asset-loop --root . --once --allow-imagegen"
                    break
                attempt = int((pending or {}).get("attempt") or 1)
                failure_key = str(asset_id or worker.get("assetId") or "")
                if worker.get("status") == "failed":
                    pending_failures[failure_key] = pending_failures.get(failure_key, 0) + 1
                    try:
                        failed_pending = dict(pending or {})
                        failed_pending.update({
                            "lastWorkerFailureReason": str(worker.get("reasonCode") or "pending_worker_failed"),
                            "lastWorkerFailureAt": now_utc(),
                            "loopFailureCount": pending_failures[failure_key],
                        })
                        write_pending(pending_path(root), failed_pending)
                    except Exception:
                        pass
                effective_attempt = max(attempt, pending_failures.get(failure_key, 0))
                max_attempts = max(1, int(config.max_pending_attempts or 1))
                if worker.get("status") == "failed" and effective_attempt < max_attempts:
                    if config.retry_delay_seconds > 0:
                        time.sleep(float(config.retry_delay_seconds))
                    append_event(root, {"ts": now_utc(), "cycle": cycles, "state": "PENDING_FAILED_RETRYABLE", "chunkId": current_chunk, "assetId": asset_id, "action": "retry_same_pending", "result": "scheduled", "attempt": effective_attempt, "pendingStatus": "pending_imagegen", "manualFlag": manual_present, "canRun": False, "approvedIdentities": approved_ids, "approvedImages": approved_images})
                    result_name = "LOOP_STOPPED_MAX_CYCLES" if config.once else result_name
                    continue
                if worker.get("status") == "failed" and effective_attempt >= max_attempts and config.fail_asset_after_max_retries:
                    try:
                        finalized = finalize_pending_failed(root=root, asset_id=asset_id, reason=str(worker.get("reasonCode") or "max_attempts_exhausted"))
                        append_event(root, {"ts": now_utc(), "cycle": cycles, "state": "PENDING_FAILED_MAX_ATTEMPTS", "chunkId": current_chunk, "assetId": asset_id, "action": "finalize_pending_failed", "result": finalized.get("action"), "attempt": effective_attempt, "pendingStatus": "failed", "manualFlag": manual_present, "canRun": False, "approvedIdentities": approved_ids, "approvedImages": approved_images})
                        result_name = "LOOP_STOPPED_MAX_CYCLES" if config.once else result_name
                        continue
                    except Exception as exc:  # noqa: BLE001
                        hard_blockers.append("max_attempts_finalization_failed:" + str(exc))
                result_name = "LOOP_STOPPED_HARD_BLOCKER"
                hard_blockers.append(str(worker.get("reasonCode") or worker.get("status") or "pending_worker_failed"))
                next_safe = "inspect ai_image/manifests/pending-imagegen.json and parent handoff report"
                break
            if pending and pending_is_resolved(pending):
                lock.heartbeat("RECONCILE_APPLY", chunk_id=current_chunk, asset_id=asset_id)
                if not config.auto_reconcile:
                    result_name = "LOOP_STOPPED_HARD_BLOCKER"
                    hard_blockers.append("auto_reconcile_disabled")
                    next_safe = "python scripts/run_ai_image_pipeline_v3.py bounded-chunk-reconcile --root . --dry-run"
                    break
                recon = auto_reconcile_pending(root, dry_run=config.dry_run)
                if recon.get("status") == "blocked":
                    result_name = "LOOP_STOPPED_HARD_BLOCKER"
                    hard_blockers.append(str(recon.get("reasonCode") or "RECONCILE_UNSAFE"))
                    next_safe = "inspect bounded-chunk-reconcile --dry-run output"
                    append_event(root, {"ts": now_utc(), "cycle": cycles, "state": "RECONCILE_DRY_RUN", "chunkId": current_chunk, "assetId": asset_id, "action": "bounded_chunk_reconcile", "result": "blocked", "pendingStatus": "resolved", "manualFlag": manual_present, "canRun": bool(status.get("canRun")), "approvedIdentities": approved_ids, "approvedImages": approved_images})
                    break
                if recon.get("status") == "dry_run":
                    result_name = "LOOP_DRY_RUN_OK"
                    next_safe = "python scripts/run_ai_image_pipeline_v3.py bounded-chunk-reconcile --root . --apply"
                else:
                    next_safe = "python scripts/run_ai_image_pipeline_v3.py hermes-one-asset-loop --root . --mode smoke --max-assets 3 --allow-imagegen --max-runtime-minutes 30"
                    result_name = "LOOP_STOPPED_MAX_CYCLES" if config.once else result_name
                append_event(root, {"ts": now_utc(), "cycle": cycles, "state": "RECONCILE_APPLY", "chunkId": current_chunk, "assetId": asset_id, "action": "bounded_chunk_reconcile", "result": recon.get("status"), "reconciled": recon.get("status") == "applied", "pendingStatus": "resolved", "manualFlag": manual_present, "canRun": bool(status.get("canRun")), "approvedIdentities": approved_ids, "approvedImages": approved_images})
                continue
            if status.get("canRun"):
                if _reached_asset_cap(config, assets_generated):
                    result_name = "LOOP_STOPPED_MAX_CYCLES"
                    next_safe = "python scripts/run_ai_image_pipeline_v3.py hermes-one-asset-loop --root . --mode %s --max-assets %d --allow-imagegen --max-runtime-minutes %s" % (config.mode, max(1, int(config.max_assets or 1)), config.max_runtime_minutes)
                    break
                lock.heartbeat("CAN_RUN_NO_PENDING", chunk_id=current_chunk, asset_id="")
                if config.dry_run:
                    result_name = "LOOP_DRY_RUN_OK"
                    next_safe = "python scripts/run_ai_image_pipeline_v3.py hermes-one-asset-loop --root . --once --allow-imagegen"
                    append_event(root, {"ts": now_utc(), "cycle": cycles, "state": "CAN_RUN_NO_PENDING", "chunkId": current_chunk, "assetId": "", "action": "bounded_chunk_run", "result": "dry_run_skipped", "pendingStatus": "absent", "manualFlag": manual_present, "canRun": True, "approvedIdentities": approved_ids, "approvedImages": approved_images})
                    break
                run = run_bounded_chunk(root=root)
                append_event(root, {"ts": now_utc(), "cycle": cycles, "state": "CAN_RUN_NO_PENDING", "chunkId": current_chunk, "assetId": str(run.get("assetId") or run.get("currentAssetId") or ""), "action": "bounded_chunk_run_once", "result": run.get("status"), "pendingStatus": "created" if run.get("status") == "pending_imagegen" else "", "manualFlag": manual_present, "canRun": True, "approvedIdentities": approved_ids, "approvedImages": approved_images})
                next_safe = "process the newly created pending handoff with hermes-one-asset-loop --once --allow-imagegen"
                result_name = "LOOP_STOPPED_MAX_CYCLES" if config.once else result_name
                continue
            if _chunk_assets_terminal(status):
                result_name = "LOOP_CHUNK_COMPLETE"
                next_safe = "python scripts/run_ai_image_pipeline_v3.py contact-sheets --root . --chunk_id %s --strict_chunk_scope --only-file-complete-identities" % current_chunk
                break
            result_name = "LOOP_STOPPED_HARD_BLOCKER"
            hard_blockers.append(str(status.get("reasonCode") or "no_runnable_state"))
            next_safe = "python scripts/run_ai_image_pipeline_v3.py bounded-chunk-status --root ."
            break
        final_completion = completion_check(root=root)
        if final_completion.get("passed"):
            approved_final = int(final_completion.get("approvedCompleteIdentities") or 0)
            images_final = int(final_completion.get("approvedImages") or 0)
            if approved_final < config.target_approved_identities or images_final < config.target_approved_images:
                result_name = "LOOP_STOPPED_HARD_BLOCKER"
                hard_blockers.append("completion_unexpectedly_passed_before_target")
                next_safe = "inspect completion-check evidence and approved manifests"
            else:
                result_name = "LOOP_COMPLETED_TARGET"
        protected_hash_changes = _protected_hash_changes(protected_hashes_before, _protected_file_hashes(root))
        if protected_hash_changes:
            result_name = "LOOP_STOPPED_HARD_BLOCKER"
            hard_blockers.append("protected_file_hash_changed")
            next_safe = "inspect protected file hash changes before continuing"
        result = {
            "schemaVersion": LOOP_SCHEMA_VERSION,
            "result": result_name,
            "mode": config.mode,
            "cycles": cycles,
            "assetsGenerated": assets_generated,
            "assetsRecovered": assets_recovered,
            "fileQaPassed": file_qa_passed,
            "fileQaFailed": file_qa_failed,
            "identitiesApproved": int(final_completion.get("approvedCompleteIdentities") or 0),
            "imagesApproved": int(final_completion.get("approvedImages") or 0),
            "currentChunkId": current_chunk,
            "manualFlagPresent": _manual_flag(root).exists(),
            "pendingPresent": bool(read_pending(pending_path(root))),
            "hardBlockers": hard_blockers,
            "protectedHashChanges": protected_hash_changes,
            "nextSafeCommand": next_safe,
            "reportPath": to_portable_path(json_report),
            "updatedAt": now_utc(),
        }
        if config.write_report:
            write_loop_reports(root, result)
        return result
    finally:
        lock.release()


def write_loop_reports(root: Path, result: Mapping[str, Any]) -> None:
    json_path, md_path, _ = _reports(root)
    atomic_write_json(json_path, dict(result))
    md = [
        "# Hermes one-asset loop latest",
        "",
        f"Result: {result.get('result')}",
        f"Mode: {result.get('mode')}",
        f"Cycles: {result.get('cycles')}",
        f"Assets generated: {result.get('assetsGenerated')}",
        f"Assets recovered: {result.get('assetsRecovered')}",
        f"File QA passed: {result.get('fileQaPassed')}",
        f"Identities approved: {result.get('identitiesApproved')}",
        f"Images approved: {result.get('imagesApproved')}",
        f"Current chunk: {result.get('currentChunkId')}",
        f"Manual flag present: {result.get('manualFlagPresent')}",
        f"Pending present: {result.get('pendingPresent')}",
        f"Hard blockers: {result.get('hardBlockers')}",
        "",
        "## Next safe command",
        str(result.get("nextSafeCommand") or ""),
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")


def config_from_args(args: Any) -> LoopConfig:
    mode = str(getattr(args, "mode", "") or ("once" if getattr(args, "once", False) else "chunk"))
    return LoopConfig(
        root=Path(getattr(args, "root", None) or Path.cwd()).resolve(),
        mode=mode,
        max_assets=int(getattr(args, "max_assets", 1) or 1),
        max_identities=int(getattr(args, "max_identities", 0) or 0),
        target_approved_identities=int(getattr(args, "target_approved_identities", 240) or 240),
        target_approved_images=int(getattr(args, "target_approved_images", 720) or 720),
        allow_imagegen=bool(getattr(args, "allow_imagegen", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
        once=bool(getattr(args, "once", False)),
        max_cycles=getattr(args, "max_cycles", None),
        max_runtime_minutes=float(getattr(args, "max_runtime_minutes", 10) or 10),
        stop_on_manual_flag=bool(getattr(args, "stop_on_manual_flag", True)),
        stop_on_hard_blocker=bool(getattr(args, "stop_on_hard_blocker", True)),
        write_report=bool(getattr(args, "write_report", True)),
        resume=bool(getattr(args, "resume", False)),
        auto_resolve_pending=bool(getattr(args, "auto_resolve_pending", True)),
        auto_reconcile=bool(getattr(args, "auto_reconcile", True)),
        max_pending_attempts=int(getattr(args, "max_pending_attempts", 3) or 3),
        retry_delay_seconds=float(getattr(args, "retry_delay_seconds", 2.0) or 0.0),
        fail_asset_after_max_retries=bool(getattr(args, "fail_asset_after_max_retries", True)),
    )


__all__ = [
    "LoopConfig",
    "LoopLock",
    "archive_and_reconstruct_invalid_pending",
    "config_from_args",
    "effective_max_cycles",
    "process_pending_imagegen_once",
    "run_loop",
    "safe_run",
]
