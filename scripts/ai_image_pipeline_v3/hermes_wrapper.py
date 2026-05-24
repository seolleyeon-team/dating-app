from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .config import DEFAULT_MODEL, ensure_base_dirs, now_utc, pipeline_paths, read_jsonl, replace_with_retry, to_portable_path, write_jsonl


RUN_SCHEMA_VERSION = "seolleyeon_hermes_wrapper_run_v1"
ATTEMPT_SCHEMA_VERSION = "seolleyeon_hermes_wrapper_attempt_v1"
SAFE_EXECUTION_MODES = {"dry-run", "fixture", "status", "bounded-plan-dry-run"}
REAL_IMAGEGEN_EXECUTION_MODES = {"bounded-run", "autopilot"}
EXECUTION_MODES = tuple(sorted(SAFE_EXECUTION_MODES | REAL_IMAGEGEN_EXECUTION_MODES))
DEFAULT_OUTPUT_DIR = Path("ai_image") / "runs"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class HermesWrapperError(RuntimeError):
    pass


@dataclass(frozen=True)
class HermesWrapperConfig:
    root: Path
    run_id: str
    task_brief: str = ""
    task_brief_file: Path | None = None
    reference_images: tuple[str, ...] = ()
    output_dir: Path = DEFAULT_OUTPUT_DIR
    pass_threshold: int = 90
    max_attempts: int = 3
    execution_mode: str = "dry-run"
    allow_real_imagegen: bool = False
    force: bool = False
    timeout_sec: int | None = None
    python_bin: str = sys.executable
    bash_bin: str = "bash"


@dataclass(frozen=True)
class HermesRunPaths:
    run_dir: Path
    brief: Path
    run_json: Path
    manifest_jsonl: Path
    prompts: Path
    generated_raw: Path
    generated_processed: Path
    verdicts: Path
    diffs: Path
    final: Path
    logs: Path


@dataclass(frozen=True)
class HermesWrapperResult:
    status: str
    run_id: str
    run_dir: Path
    manifest_path: Path
    run_json_path: Path
    attempt: int
    command: tuple[str, ...] = ()
    return_code: int | None = None
    error: str = ""
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    reference_images: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def as_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "runId": self.run_id,
            "runDir": to_portable_path(self.run_dir),
            "manifestPath": to_portable_path(self.manifest_path),
            "runJsonPath": to_portable_path(self.run_json_path),
            "attempt": self.attempt,
            "command": list(self.command),
            "returnCode": self.return_code,
            "error": self.error,
            "referenceImages": [dict(item) for item in self.reference_images],
        }
        if self.stdout_path is not None:
            payload["stdoutPath"] = to_portable_path(self.stdout_path)
        if self.stderr_path is not None:
            payload["stderrPath"] = to_portable_path(self.stderr_path)
        return payload


def _validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise HermesWrapperError(
            "run_id must contain only letters, numbers, dots, underscores, and hyphens, "
            "and must not start with punctuation."
        )


def default_run_id() -> str:
    return "hermes_" + now_utc().replace(":", "").replace("+", "Z")


def _resolve_root(root: Path | str | None) -> Path:
    return pipeline_paths(root).root


def _resolve_output_dir(root: Path, output_dir: Path | str | None) -> Path:
    value = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def _run_paths(root: Path, run_id: str, output_dir: Path | str | None) -> HermesRunPaths:
    run_dir = _resolve_output_dir(root, output_dir) / run_id
    return HermesRunPaths(
        run_dir=run_dir,
        brief=run_dir / "brief.md",
        run_json=run_dir / "run.json",
        manifest_jsonl=run_dir / "manifest.jsonl",
        prompts=run_dir / "prompts",
        generated_raw=run_dir / "generated" / "raw",
        generated_processed=run_dir / "generated" / "processed",
        verdicts=run_dir / "verdicts",
        diffs=run_dir / "diffs",
        final=run_dir / "final",
        logs=run_dir / "logs",
    )


def ensure_run_dirs(paths: HermesRunPaths) -> None:
    for folder in (
        paths.run_dir,
        paths.prompts,
        paths.generated_raw,
        paths.generated_processed,
        paths.verdicts,
        paths.diffs,
        paths.final,
        paths.logs,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replace_with_retry(tmp, path)


def _brief_text(config: HermesWrapperConfig) -> str:
    if config.task_brief_file is not None:
        brief_path = config.task_brief_file if config.task_brief_file.is_absolute() else config.root / config.task_brief_file
        if not brief_path.exists():
            raise HermesWrapperError(f"task brief file does not exist: {brief_path}")
        return brief_path.read_text(encoding="utf-8")
    return config.task_brief


def write_or_preserve_brief(paths: HermesRunPaths, text: str, *, force: bool) -> None:
    if paths.brief.exists():
        existing = paths.brief.read_text(encoding="utf-8")
        if existing == text:
            return
        if not force:
            raise HermesWrapperError(
                f"brief.md already exists for this run with different content: {paths.brief}. "
                "Use --force to replace it."
            )
    paths.brief.write_text(text, encoding="utf-8")


def _resolve_reference_images(root: Path, references: Sequence[str]) -> tuple[dict[str, Any], ...]:
    reports: list[dict[str, Any]] = []
    for value in references:
        candidate = Path(value)
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        reports.append(
            {
                "input": value,
                "path": to_portable_path(path),
                "exists": path.exists(),
                "size": path.stat().st_size if path.exists() else 0,
            }
        )
    return tuple(reports)


def _missing_references(reference_reports: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(item.get("path") or item.get("input") or "") for item in reference_reports if not item.get("exists")]


def _next_attempt(paths: HermesRunPaths) -> int:
    rows = read_jsonl(paths.manifest_jsonl)
    attempts = [int(row.get("attempt") or 0) for row in rows if isinstance(row, Mapping)]
    return max(attempts, default=0) + 1


def _resolve_bash_binary(
    requested: str,
    *,
    which_func: Callable[[str], str | None] = shutil.which,
    bash_candidates: Sequence[Path] | None = None,
) -> str:
    requested_path = Path(requested)
    if requested_path.is_absolute() and requested_path.exists():
        return str(requested_path)
    resolved = which_func(requested)
    if resolved:
        return resolved
    if requested != "bash":
        return requested
    candidates = bash_candidates or (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Git" / "bin" / "bash.exe",
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return requested


def _command_for_mode(
    config: HermesWrapperConfig,
    *,
    which_func: Callable[[str], str | None] = shutil.which,
    bash_candidates: Sequence[Path] | None = None,
) -> tuple[str, ...]:
    script = config.root / "scripts" / "run_ai_image_pipeline_v3.py"
    if config.execution_mode == "dry-run":
        return ("dry-run",)
    if config.execution_mode == "fixture":
        return ("fixture",)
    if config.execution_mode == "status":
        return (config.python_bin, str(script), "bounded-chunk-status", "--root", str(config.root))
    if config.execution_mode == "bounded-plan-dry-run":
        return (config.python_bin, str(script), "bounded-chunk-plan", "--root", str(config.root), "--dry-run")
    if config.execution_mode == "bounded-run":
        return (config.python_bin, str(script), "bounded-chunk-run", "--root", str(config.root))
    if config.execution_mode == "autopilot":
        raise HermesWrapperError(
            "execution mode 'autopilot' is deprecated and disabled; production image generation must use bounded-run."
        )
    raise HermesWrapperError(f"unsupported execution mode: {config.execution_mode}")


def _append_attempt(paths: HermesRunPaths, row: Mapping[str, Any]) -> None:
    rows = read_jsonl(paths.manifest_jsonl)
    rows.append(dict(row))
    write_jsonl(paths.manifest_jsonl, rows)


def _base_attempt_row(
    *,
    config: HermesWrapperConfig,
    paths: HermesRunPaths,
    attempt: int,
    reference_reports: Sequence[Mapping[str, Any]],
    command: Sequence[str],
) -> dict[str, Any]:
    created_at = now_utc()
    return {
        "schemaVersion": ATTEMPT_SCHEMA_VERSION,
        "run_id": config.run_id,
        "runId": config.run_id,
        "attempt": int(attempt),
        "prompt": "",
        "prompt_path": to_portable_path(paths.brief),
        "promptPath": to_portable_path(paths.brief),
        "model": DEFAULT_MODEL,
        "provider": DEFAULT_MODEL,
        "raw_image": "",
        "rawImage": "",
        "processed_image": "",
        "processedImage": "",
        "reference_images": [dict(item) for item in reference_reports],
        "referenceImages": [dict(item) for item in reference_reports],
        "verdict_path": "",
        "verdictPath": "",
        "score": None,
        "verdict": "",
        "category_match": None,
        "categoryMatch": None,
        "created_at": created_at,
        "createdAt": created_at,
        "command_used": list(command),
        "commandUsed": list(command),
        "execution_mode": config.execution_mode,
        "pass_threshold": int(config.pass_threshold),
        "max_attempts": int(config.max_attempts),
        "error": "",
    }


def _write_run_json(
    *,
    config: HermesWrapperConfig,
    paths: HermesRunPaths,
    status: str,
    attempt: int,
    command: Sequence[str],
    return_code: int | None,
    reference_reports: Sequence[Mapping[str, Any]],
    error: str = "",
) -> None:
    payload = {
        "schemaVersion": RUN_SCHEMA_VERSION,
        "runId": config.run_id,
        "status": status,
        "root": to_portable_path(config.root),
        "runDir": to_portable_path(paths.run_dir),
        "briefPath": to_portable_path(paths.brief),
        "manifestPath": to_portable_path(paths.manifest_jsonl),
        "executionMode": config.execution_mode,
        "passThreshold": int(config.pass_threshold),
        "maxAttempts": int(config.max_attempts),
        "referenceImages": [dict(item) for item in reference_reports],
        "lastAttempt": int(attempt),
        "lastCommand": list(command),
        "lastReturnCode": return_code,
        "error": error,
        "updatedAt": now_utc(),
    }
    _write_json(paths.run_json, payload)


def _write_fixture_artifacts(paths: HermesRunPaths, config: HermesWrapperConfig, attempt: int) -> tuple[Path, Path]:
    prompt_path = paths.prompts / f"attempt{attempt:02d}_fixture_prompt.md"
    verdict_path = paths.verdicts / f"attempt{attempt:02d}_fixture_verdict.json"
    prompt_path.write_text(
        "\n".join(
            [
                "# Hermes wrapper fixture prompt",
                "",
                config.task_brief or "Fixture run without real image generation.",
                "",
                "No real image generation was invoked.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        verdict_path,
        {
            "score": 100,
            "verdict": "pass",
            "category_match": True,
            "differences": [],
            "suggestions": [],
            "reasoning": "Fixture verdict for wrapper contract tests; no real visual QA was run.",
        },
    )
    return prompt_path, verdict_path


def _run_subprocess(
    command: Sequence[str],
    *,
    config: HermesWrapperConfig,
    stdout_path: Path,
    stderr_path: Path,
    run_func: Callable[..., subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "cwd": str(config.root),
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "shell": False,
    }
    if config.timeout_sec is not None and config.timeout_sec > 0:
        kwargs["timeout"] = config.timeout_sec
    try:
        result = run_func(list(command), **kwargs)
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text((exc.stderr or "") + f"\nwrapper timeout after {config.timeout_sec} seconds\n", encoding="utf-8")
        raise HermesWrapperError(f"wrapper command timed out after {config.timeout_sec} seconds") from exc
    except OSError as exc:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc), encoding="utf-8")
        raise HermesWrapperError(f"wrapper command failed to start: {exc}") from exc
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    return result


def run_hermes_wrapper(
    config: HermesWrapperConfig,
    *,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> HermesWrapperResult:
    _validate_run_id(config.run_id)
    if config.execution_mode not in EXECUTION_MODES:
        raise HermesWrapperError(f"unsupported execution mode: {config.execution_mode}")
    if config.execution_mode in REAL_IMAGEGEN_EXECUTION_MODES and not config.allow_real_imagegen:
        raise HermesWrapperError(
            f"execution mode {config.execution_mode!r} may invoke real Codex Image Gen; pass --allow-real-imagegen explicitly."
        )

    ensure_base_dirs(pipeline_paths(config.root))
    paths = _run_paths(config.root, config.run_id, config.output_dir)
    ensure_run_dirs(paths)
    brief = _brief_text(config)
    write_or_preserve_brief(paths, brief, force=config.force)

    reference_reports = _resolve_reference_images(config.root, config.reference_images)
    missing_references = _missing_references(reference_reports)
    command = _command_for_mode(config)
    attempt = _next_attempt(paths)
    command_path = paths.logs / f"attempt{attempt:02d}.command.json"
    stdout_path = paths.logs / f"attempt{attempt:02d}.stdout.txt"
    stderr_path = paths.logs / f"attempt{attempt:02d}.stderr.txt"
    _write_json(command_path, {"command": list(command), "executionMode": config.execution_mode, "createdAt": now_utc()})

    if missing_references:
        error = "missing reference images: " + ", ".join(missing_references)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(error + "\n", encoding="utf-8")
        row = _base_attempt_row(config=config, paths=paths, attempt=attempt, reference_reports=reference_reports, command=command)
        row.update(
            {
                "status": "failed",
                "stdout_path": to_portable_path(stdout_path),
                "stdoutPath": to_portable_path(stdout_path),
                "stderr_path": to_portable_path(stderr_path),
                "stderrPath": to_portable_path(stderr_path),
                "error": error,
            }
        )
        _append_attempt(paths, row)
        _write_run_json(config=config, paths=paths, status="failed", attempt=attempt, command=command, return_code=2, reference_reports=reference_reports, error=error)
        return HermesWrapperResult(
            status="failed",
            run_id=config.run_id,
            run_dir=paths.run_dir,
            manifest_path=paths.manifest_jsonl,
            run_json_path=paths.run_json,
            attempt=attempt,
            command=tuple(command),
            return_code=2,
            error=error,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            reference_images=reference_reports,
        )

    row = _base_attempt_row(config=config, paths=paths, attempt=attempt, reference_reports=reference_reports, command=command)
    if config.execution_mode == "dry-run":
        row.update({"status": "dry_run", "verdict": "not_run", "error": ""})
        _append_attempt(paths, row)
        _write_run_json(config=config, paths=paths, status="dry_run", attempt=attempt, command=command, return_code=0, reference_reports=reference_reports)
        stdout_path.write_text("dry-run: no existing OMX pipeline command was invoked\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return HermesWrapperResult(
            status="dry_run",
            run_id=config.run_id,
            run_dir=paths.run_dir,
            manifest_path=paths.manifest_jsonl,
            run_json_path=paths.run_json,
            attempt=attempt,
            command=tuple(command),
            return_code=0,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            reference_images=reference_reports,
        )

    if config.execution_mode == "fixture":
        prompt_path, verdict_path = _write_fixture_artifacts(paths, config, attempt)
        row.update(
            {
                "status": "fixture_complete",
                "prompt_path": to_portable_path(prompt_path),
                "promptPath": to_portable_path(prompt_path),
                "verdict_path": to_portable_path(verdict_path),
                "verdictPath": to_portable_path(verdict_path),
                "score": 100,
                "verdict": "pass",
                "category_match": True,
                "categoryMatch": True,
            }
        )
        _append_attempt(paths, row)
        _write_run_json(config=config, paths=paths, status="fixture_complete", attempt=attempt, command=command, return_code=0, reference_reports=reference_reports)
        stdout_path.write_text("fixture: wrote prompt and verdict artifacts without image generation\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return HermesWrapperResult(
            status="fixture_complete",
            run_id=config.run_id,
            run_dir=paths.run_dir,
            manifest_path=paths.manifest_jsonl,
            run_json_path=paths.run_json,
            attempt=attempt,
            command=tuple(command),
            return_code=0,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            reference_images=reference_reports,
        )

    try:
        result = _run_subprocess(command, config=config, stdout_path=stdout_path, stderr_path=stderr_path, run_func=run_func)
    except HermesWrapperError as exc:
        row.update({"status": "failed", "error": str(exc), "stdout_path": to_portable_path(stdout_path), "stderr_path": to_portable_path(stderr_path)})
        _append_attempt(paths, row)
        _write_run_json(config=config, paths=paths, status="failed", attempt=attempt, command=command, return_code=2, reference_reports=reference_reports, error=str(exc))
        return HermesWrapperResult(
            status="failed",
            run_id=config.run_id,
            run_dir=paths.run_dir,
            manifest_path=paths.manifest_jsonl,
            run_json_path=paths.run_json,
            attempt=attempt,
            command=tuple(command),
            return_code=2,
            error=str(exc),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            reference_images=reference_reports,
        )

    status = "succeeded" if result.returncode == 0 else "failed"
    error = "" if result.returncode == 0 else f"wrapper command exited with {result.returncode}"
    row.update(
        {
            "status": status,
            "return_code": int(result.returncode),
            "returnCode": int(result.returncode),
            "stdout_path": to_portable_path(stdout_path),
            "stdoutPath": to_portable_path(stdout_path),
            "stderr_path": to_portable_path(stderr_path),
            "stderrPath": to_portable_path(stderr_path),
            "error": error,
        }
    )
    _append_attempt(paths, row)
    _write_run_json(
        config=config,
        paths=paths,
        status=status,
        attempt=attempt,
        command=command,
        return_code=int(result.returncode),
        reference_reports=reference_reports,
        error=error,
    )
    return HermesWrapperResult(
        status=status,
        run_id=config.run_id,
        run_dir=paths.run_dir,
        manifest_path=paths.manifest_jsonl,
        run_json_path=paths.run_json,
        attempt=attempt,
        command=tuple(command),
        return_code=int(result.returncode),
        error=error,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        reference_images=reference_reports,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes-friendly wrapper around the existing Seolleyeon OMX image pipeline.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--run-id", "--run_id", dest="run_id", default="")
    parser.add_argument("--task-brief", "--task_brief", dest="task_brief", default="")
    parser.add_argument("--task-brief-file", "--task_brief_file", dest="task_brief_file", default=None)
    parser.add_argument("--reference-image", "--reference_image", dest="reference_images", action="append", default=[])
    parser.add_argument("--output-dir", "--output_dir", dest="output_dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--pass-threshold", "--pass_threshold", dest="pass_threshold", type=int, default=90)
    parser.add_argument("--max-attempts", "--max_attempts", dest="max_attempts", type=int, default=3)
    parser.add_argument("--execution-mode", "--execution_mode", dest="execution_mode", choices=EXECUTION_MODES, default="dry-run")
    parser.add_argument("--allow-real-imagegen", "--allow_real_imagegen", dest="allow_real_imagegen", action="store_true", default=False)
    parser.add_argument("--force", action="store_true", default=False)
    parser.add_argument("--timeout-sec", "--timeout_sec", dest="timeout_sec", type=int, default=0)
    parser.add_argument("--python-bin", "--python_bin", dest="python_bin", default=sys.executable)
    parser.add_argument("--bash-bin", "--bash_bin", dest="bash_bin", default=os.environ.get("BASH_BIN", "bash"))
    return parser


def config_from_args(args: argparse.Namespace) -> HermesWrapperConfig:
    root = _resolve_root(args.root)
    run_id = args.run_id or default_run_id()
    task_brief_file = Path(args.task_brief_file) if args.task_brief_file else None
    return HermesWrapperConfig(
        root=root,
        run_id=run_id,
        task_brief=str(args.task_brief or ""),
        task_brief_file=task_brief_file,
        reference_images=tuple(args.reference_images or ()),
        output_dir=Path(args.output_dir),
        pass_threshold=int(args.pass_threshold),
        max_attempts=int(args.max_attempts),
        execution_mode=str(args.execution_mode),
        allow_real_imagegen=bool(args.allow_real_imagegen),
        force=bool(args.force),
        timeout_sec=int(args.timeout_sec) if int(args.timeout_sec or 0) > 0 else None,
        python_bin=str(args.python_bin),
        bash_bin=str(args.bash_bin),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_hermes_wrapper(config_from_args(args))
    except HermesWrapperError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result.as_json(), ensure_ascii=False, indent=2))
    return 0 if result.status not in {"failed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
