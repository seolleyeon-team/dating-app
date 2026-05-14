from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROMPT_FILES = {
    "visual-asset-qa-instructions": "VISUAL_VERDICT_ASSET_QA_PROMPT.md",
    "visual-identity-qa-instructions": "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md",
    "visual-distribution-audit-instructions": "VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md",
}
DEFAULT_VISUAL_JSON = {
    "apply-visual-asset-qa": "ai_image/reports/visual_verdict/asset_qa_latest.json",
    "apply-visual-identity-qa": "ai_image/reports/visual_verdict/identity_qa_latest.json",
    "apply-visual-distribution-audit": "ai_image/reports/visual_verdict/distribution_audit_latest.json",
}


def _prompt_path(root: Path | str | None, filename: str) -> Path:
    base = Path(root).resolve() if root is not None else Path.cwd()
    return base / "ai_image" / "prompts" / filename


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _default_visual_json(root: Path | str | None, command: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    relative = DEFAULT_VISUAL_JSON.get(command)
    if not relative:
        return None
    base = Path(root).resolve() if root is not None else Path.cwd()
    return str(base / relative)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cross-platform Seolleyeon AI image pipeline dispatcher.")
    parser.add_argument("command", choices=[
        "prepare-720",
        "normalize-manifest-paths",
        "recover",
        "file-qa",
        "contact-sheets",
        "visual-asset-qa-instructions",
        "visual-identity-qa-instructions",
        "visual-distribution-audit-instructions",
        "apply-visual-asset-qa",
        "apply-visual-identity-qa",
        "apply-visual-distribution-audit",
        "distribution-audit",
        "completion-check",
        "pending-status",
        "resolve-pending",
        "clear-cancelled-pending",
        "active-visual-probe",
        "active-visual-asset-qa",
        "active-visual-identity-qa",
        "active-visual-distribution-qa",
        "active-visual-qa-all",
        "bounded-chunk-plan",
        "bounded-chunk-run",
        "bounded-chunk-resume",
        "bounded-chunk-status",
        "bounded-chunk-validate-plan",
        "bounded-chunk-reconcile",
        "bounded-chunk-qa",
        "bounded-chunk-finalize",
        "bounded-chunk-e2e-smoke",
        "bounded-identity-worker",
        "bounded-identity-parallel-run",
        "hermes-wrapper",
        "supervisor-720",
        "supervisor-chunk-only",
        "supervisor-identity-only",
        "supervisor-asset-only",
    ])
    parser.add_argument("--root", default=None)
    parser.add_argument("--visual_json", default=None)
    parser.add_argument("--pending", default=None)
    parser.add_argument("--run-id", "--run_id", dest="run_id", default="")
    parser.add_argument("--task-brief", "--task_brief", dest="task_brief", default="")
    parser.add_argument("--task-brief-file", "--task_brief_file", dest="task_brief_file", default=None)
    parser.add_argument("--reference-image", "--reference_image", dest="reference_images", action="append", default=[])
    parser.add_argument("--output-dir", "--output_dir", dest="output_dir", default="ai_image/runs")
    parser.add_argument("--pass-threshold", "--pass_threshold", dest="pass_threshold", type=int, default=90)
    parser.add_argument("--max-attempts", "--max_attempts", dest="max_attempts", type=int, default=3)
    parser.add_argument("--execution-mode", "--execution_mode", dest="execution_mode", default="dry-run")
    parser.add_argument("--allow-real-imagegen", "--allow_real_imagegen", dest="allow_real_imagegen", action="store_true", default=False)
    parser.add_argument("--timeout-sec", "--timeout_sec", dest="timeout_sec", type=int, default=0)
    parser.add_argument("--python-bin", "--python_bin", dest="python_bin", default=sys.executable)
    parser.add_argument("--bash-bin", "--bash_bin", dest="bash_bin", default="bash")
    parser.add_argument("--chunk_id", default=None)
    parser.add_argument("--max_identities", type=int, default=24)
    parser.add_argument("--max_assets", type=int, default=72)
    parser.add_argument("--reason", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", "--dry_run", dest="dry_run", action="store_true", default=False)
    parser.add_argument("--production", "--no-dry-run", "--execute", dest="production", action="store_true", default=False)
    parser.add_argument("--force-replan", "--force_replan", dest="force_replan", action="store_true", default=False)
    parser.add_argument("--abandon-current", "--abandon_current", dest="abandon_current", action="store_true", default=False)
    parser.add_argument("--agent-cmd", "--agent_cmd", dest="agent_cmd", default=None)
    parser.add_argument("--identity-id", "--identity_id", dest="identity_id", default="e2e_identity_001")
    parser.add_argument("--worker-id", "--worker_id", dest="worker_id", default="")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--fixture", action="store_true", default=False)
    parser.add_argument("--fixture-fail-shot", "--fixture_fail_shot", dest="fixture_fail_shot", default="")
    parser.add_argument("--asset-id", "--asset_id", dest="asset_id", default="")
    parser.add_argument("--keep-artifacts", "--keep_artifacts", dest="keep_artifacts", action="store_true", default=False)
    parser.add_argument("--no-restore", "--no_restore", dest="no_restore", action="store_true", default=False)
    parser.add_argument("--preflight-only", "--preflight_only", dest="preflight_only", action="store_true", default=False)
    parser.add_argument("--apply", dest="apply", action="store_true", default=False)
    parser.add_argument("--clear-manual-flag-if-safe", "--clear_manual_flag_if_safe", dest="clear_manual_flag_if_safe", action="store_true", default=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command

    if command == "hermes-wrapper":
        from .hermes_wrapper import HermesWrapperError, config_from_args, run_hermes_wrapper

        try:
            result = run_hermes_wrapper(config_from_args(args))
        except HermesWrapperError as exc:
            _print_json({"status": "failed", "error": str(exc)})
            return 2
        _print_json(result.as_json())
        return 0 if result.status != "failed" else 2

    if command == "prepare-720":
        from .prepare import prepare_assets

        result = prepare_assets(root=args.root, female_count=120, male_count=120, reserve_female_count=20, reserve_male_count=20, force=args.force)
        _print_json(
            {
                "specs": result.specs_count,
                "assets": result.asset_count,
                "manifest": str(result.manifest_jsonl),
                "imagegenQueue": str(result.imagegen_queue_jsonl),
            }
        )
        return 0

    if command == "normalize-manifest-paths":
        from .manifest_repair import normalize_generation_paths

        _print_json(normalize_generation_paths(root=args.root, dry_run=args.dry_run, backup=not args.force))
        return 0

    if command == "recover":
        from .codex_imagegen import recover_pending_imagegen
        from .identity_parallel import per_asset_pending_path

        pending = per_asset_pending_path(args.root, args.asset_id) if args.asset_id else args.pending
        result = recover_pending_imagegen(root=args.root, pending=pending, force=args.force)
        _print_json({key: str(value) if isinstance(value, Path) else value for key, value in result.__dict__.items()})
        return 0

    if command == "file-qa":
        from .qa import qa_images

        _print_json(qa_images(root=args.root, force=args.force))
        return 0

    if command == "contact-sheets":
        from .contact_sheet import generate_grouped_contact_sheets

        results = generate_grouped_contact_sheets(root=args.root, stage="pilot")
        _print_json({"outputs": [str(result.output_path) for result in results], "imageCount": sum(result.image_count for result in results)})
        return 0

    if command in PROMPT_FILES:
        print(_prompt_path(args.root, PROMPT_FILES[command]).read_text(encoding="utf-8"))
        return 0

    if command == "apply-visual-asset-qa":
        from .visual_verdict import apply_asset_qa

        _print_json(apply_asset_qa(root=args.root, input_path=_default_visual_json(args.root, command, args.visual_json), force=args.force))
        return 0

    if command == "apply-visual-identity-qa":
        from .visual_verdict import apply_identity_qa

        _print_json(apply_identity_qa(root=args.root, input_path=_default_visual_json(args.root, command, args.visual_json)))
        return 0

    if command == "apply-visual-distribution-audit":
        from .visual_verdict import apply_distribution_audit

        result = apply_distribution_audit(root=args.root, input_path=_default_visual_json(args.root, command, args.visual_json))
        _print_json(result)
        return 2 if result.get("needsManualReview") else 0

    if command == "distribution-audit":
        from .distribution_audit import audit_distribution

        audit = audit_distribution(root=args.root)
        _print_json(
            {
                "passed": audit["passed"],
                "finalDecision": audit["finalDecision"],
                "approvedCompleteIdentityCount": audit["approvedCompleteIdentityCount"],
                "failConditions": audit["failConditions"],
            }
        )
        return 0

    if command == "completion-check":
        from .completion import completion_check

        result = completion_check(root=args.root)
        _print_json(result)
        return 0 if result["passed"] else 1

    if command == "pending-status":
        if args.asset_id:
            from .identity_parallel import identity_parallel_status

            _print_json(identity_parallel_status(root=args.root, asset_id=args.asset_id))
            return 0
        from .pending_admin import pending_status_report

        _print_json(pending_status_report(root=args.root, pending=args.pending))
        return 0

    if command == "resolve-pending":
        from .pending_admin import resolve_pending

        _print_json(resolve_pending(root=args.root, pending=args.pending, reason=args.reason or "manual_resolution"))
        return 0

    if command == "clear-cancelled-pending":
        from .pending_admin import clear_cancelled_pending

        _print_json(clear_cancelled_pending(root=args.root, pending=args.pending, reason=args.reason or "cancelled_pending_clear"))
        return 0

    if command == "active-visual-probe":
        from .active_visual_verdict_runner import probe_codex_image_input

        result = probe_codex_image_input(root=args.root)
        _print_json(result)
        return 0 if result["available"] else 2

    if command == "active-visual-asset-qa":
        from .active_visual_verdict_runner import run_active_visual_asset_qa

        _print_json(run_active_visual_asset_qa(root=args.root, chunk_id=args.chunk_id))
        return 0

    if command == "active-visual-identity-qa":
        from .active_visual_verdict_runner import run_active_visual_identity_qa

        _print_json(run_active_visual_identity_qa(root=args.root, chunk_id=args.chunk_id))
        return 0

    if command == "active-visual-distribution-qa":
        from .active_visual_verdict_runner import run_active_visual_distribution_qa

        _print_json(run_active_visual_distribution_qa(root=args.root, chunk_id=args.chunk_id))
        return 0

    if command == "active-visual-qa-all":
        from .active_visual_verdict_runner import run_active_visual_qa_all

        _print_json(run_active_visual_qa_all(root=args.root, chunk_id=args.chunk_id))
        return 0

    if command == "bounded-chunk-e2e-smoke":
        from .e2e_bounded_imagegen_smoke_v3 import E2EConfig, run_e2e_smoke

        root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
        config = E2EConfig(
            root=root,
            chunk_id=args.chunk_id or "",
            agent_cmd=args.agent_cmd,
            identity_id=args.identity_id,
            keep_artifacts=args.keep_artifacts,
            no_restore=args.no_restore,
            preflight_only=args.preflight_only,
        )
        if not config.chunk_id:
            from .e2e_bounded_imagegen_smoke_v3 import default_e2e_chunk_id

            config.chunk_id = default_e2e_chunk_id()
        result = run_e2e_smoke(config)
        _print_json(result)
        return 0 if result["status"] in {"passed", "preflight_passed"} else 2

    if command in {"bounded-identity-worker", "bounded-identity-parallel-run"}:
        from .identity_parallel import IdentityParallelConfig, IdentityWorkerConfig, run_identity_parallel, run_identity_worker

        root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
        run_id = args.run_id or "identity_parallel_cli"
        if not args.fixture:
            _print_json({"status": "failed", "error": "--fixture is required; identity parallel execution is currently fixture/mock only."})
            return 2
        if command == "bounded-identity-worker":
            result = run_identity_worker(
                IdentityWorkerConfig(
                    root=root,
                    identity_id=args.identity_id,
                    run_id=run_id,
                    worker_id=args.worker_id or f"{run_id}-{args.identity_id}",
                    fixture=True,
                    fixture_fail_shot=args.fixture_fail_shot,
                )
            )
            _print_json(result)
            return 0 if result.get("status") not in {"failed"} else 2
        result = run_identity_parallel(
            IdentityParallelConfig(
                root=root,
                run_id=run_id,
                workers=max(1, int(args.workers)),
                fixture=True,
                fixture_fail_shot=args.fixture_fail_shot,
                max_identities=max(0, int(args.max_identities)),
            )
        )
        _print_json(result)
        return 0 if result.get("status") not in {"failed"} else 2

    if command.startswith("bounded-chunk-"):
        from .bounded_batch_executor import (
            BoundedBatchExecutorError,
            PlanValidationError,
            bounded_chunk_status,
            create_chunk_plan,
            finalize_bounded_chunk,
            reconcile_bounded_chunk,
            resume_bounded_chunk,
            run_bounded_chunk,
            run_bounded_chunk_qa,
            validate_current_chunk_plan,
        )

        try:
            if command == "bounded-chunk-plan":
                _print_json(
                    create_chunk_plan(
                        root=args.root,
                        max_identities=args.max_identities,
                        max_assets=args.max_assets,
                        dry_run=args.dry_run,
                        production=args.production,
                        force_replan=args.force_replan,
                        abandon_current=args.abandon_current,
                        abandon_reason=args.reason or "fresh_production_replan_after_distribution_audit",
                    )
                )
                return 0
        except PlanValidationError as exc:
            _print_json({"status": "failed", "reasonCode": exc.reason_code, "error": str(exc), **dict(exc.details)})
            return 2
        except BoundedBatchExecutorError as exc:
            _print_json({"status": "failed", "reasonCode": "bounded_executor_error", "error": str(exc)})
            return 2
        if command == "bounded-chunk-run":
            result = run_bounded_chunk(root=args.root)
            _print_json(result)
            return 0 if result.get("status") not in {"failed", "needs_manual_review"} else 2
        if command == "bounded-chunk-resume":
            result = resume_bounded_chunk(root=args.root)
            _print_json(result)
            return 0 if result.get("status") not in {"failed", "needs_manual_review"} else 2
        if command == "bounded-chunk-status":
            _print_json(bounded_chunk_status(root=args.root))
            return 0
        if command == "bounded-chunk-validate-plan":
            result = validate_current_chunk_plan(root=args.root, strict=False)
            _print_json(result)
            return 0 if result.get("valid") else 2
        if command == "bounded-chunk-reconcile":
            _print_json(reconcile_bounded_chunk(root=args.root, dry_run=args.dry_run or not args.apply, apply=args.apply, clear_manual_flag_if_safe=args.clear_manual_flag_if_safe))
            return 0
        if command == "bounded-chunk-qa":
            _print_json(run_bounded_chunk_qa(root=args.root))
            return 0
        if command == "bounded-chunk-finalize":
            _print_json(finalize_bounded_chunk(root=args.root))
            return 0

    if command.startswith("supervisor-"):
        from .supervisor import supervisor_status

        mode = {
            "supervisor-720": "auto",
            "supervisor-chunk-only": "chunk",
            "supervisor-identity-only": "identity",
            "supervisor-asset-only": "asset",
        }[command]
        _print_json(supervisor_status(root=args.root, mode=mode))
        return 0

    raise AssertionError(f"Unhandled command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
