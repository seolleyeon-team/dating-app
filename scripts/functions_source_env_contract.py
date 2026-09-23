#!/usr/bin/env python3
"""Static, function-scoped source and environment contract analysis.

The normal Functions environment guard compares a candidate dotenv with a
serving Cloud Run revision.  A function with no serving revision has no such
authority, so bootstrap recovery needs a second, source-based contract.  This
module resolves the local TypeScript import closure for one exported function
and inventories environment reads across the complete module-load closure.

This is intentionally conservative: a dynamic ``process.env[...]`` access or
an unresolved local import is an error rather than an invitation to guess.
Values are never read from dotenv files here; only source key names are
reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PLATFORM_MANAGED_KEYS = frozenset(
    {
        "EVENTARC_CLOUD_EVENT_SOURCE",
        "FIREBASE_CONFIG",
        "FUNCTION_REGION",
        "FUNCTION_SIGNATURE_TYPE",
        "FUNCTION_TARGET",
        "GCLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
        "K_CONFIGURATION",
        "K_REVISION",
        "K_SERVICE",
        "LOG_EXECUTION_ID",
        "PORT",
    }
)

ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LITERAL_ENV_PATTERN = re.compile(
    r"process\.env(?:\.([A-Z][A-Z0-9_]*)|\s*\[\s*[\"']([A-Z][A-Z0-9_]*)[\"']\s*\])"
)
ENV_BASE_PATTERN = re.compile(r"process\.env\b")
LOCAL_IMPORT_PATTERN = re.compile(
    r"(?:\bfrom\s*|\bimport\s*\(\s*)[\"'](\.{1,2}/[^\"']+)[\"']"
)
SECRET_BINDING_PATTERN = re.compile(
    r"\b(?:defineSecret|defineJsonSecret)\s*\(\s*[\"']([^\"']+)[\"']"
)


class SourceContractError(RuntimeError):
    """The source closure cannot be proven complete and deterministic."""


@dataclass(frozen=True)
class EnvRead:
    module: Path
    line: int
    key: str | None
    classification: str
    expression: str


@dataclass(frozen=True)
class SourceEnvContract:
    entry_module: Path
    modules: tuple[Path, ...]
    env_reads: tuple[EnvRead, ...]
    secret_bindings: tuple[str, ...]

    @property
    def unknown_reads(self) -> tuple[EnvRead, ...]:
        return tuple(read for read in self.env_reads if read.classification == "UNKNOWN")

    @property
    def platform_managed_keys(self) -> frozenset[str]:
        return frozenset(
            read.key
            for read in self.env_reads
            if read.key is not None and read.classification == "PLATFORM_MANAGED"
        )

    @property
    def required_plain_env_keys(self) -> frozenset[str]:
        return frozenset(
            read.key
            for read in self.env_reads
            if read.key is not None and read.classification == "REQUIRED_NO_DEFAULT"
        )

    @property
    def optional_plain_env_keys(self) -> frozenset[str]:
        return frozenset(
            read.key
            for read in self.env_reads
            if read.key is not None and read.classification == "OPTIONAL_SAFE_DEFAULT"
        )

    @property
    def custom_plain_env_keys(self) -> frozenset[str]:
        return self.required_plain_env_keys | self.optional_plain_env_keys


def _resolve_local_module(importer: Path, specifier: str) -> Path:
    base = (importer.parent / specifier).resolve()
    candidates = [base]
    if base.suffix == "":
        candidates.extend(
            [
                base.with_suffix(".ts"),
                base.with_suffix(".tsx"),
                base / "index.ts",
                base / "index.tsx",
            ]
        )
    elif base.suffix == ".js":
        candidates.append(base.with_suffix(".ts"))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    rendered = ", ".join(str(candidate) for candidate in candidates)
    raise SourceContractError(
        f"unresolved local import {specifier!r} from {importer}: tried [{rendered}]"
    )


def _local_imports(module: Path) -> tuple[str, ...]:
    text = module.read_text(encoding="utf-8", errors="strict")
    return tuple(sorted(set(LOCAL_IMPORT_PATTERN.findall(text))))


def resolve_import_closure(entry_module: Path) -> tuple[Path, ...]:
    """Resolve all local imports loaded when the entry module is evaluated."""

    entry = entry_module.resolve()
    if not entry.is_file():
        raise SourceContractError(f"source entry does not exist: {entry}")

    visited: set[Path] = set()
    pending = [entry]
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        for specifier in _local_imports(module):
            pending.append(_resolve_local_module(module, specifier))
    return tuple(sorted(visited))


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _is_optional_safe_default(line: str, end: int) -> bool:
    tail = line[end:]
    # ``?.`` and a fallback are both safe undefined-value paths.  The source
    # still records the key, but it is not required in a minimal dotenv.
    return "?." in tail or "??" in tail or "||" in tail


def _env_reads(module: Path) -> tuple[EnvRead, ...]:
    text = module.read_text(encoding="utf-8", errors="strict")
    reads: list[EnvRead] = []
    literal_spans: list[tuple[int, int]] = []

    for match in LITERAL_ENV_PATTERN.finditer(text):
        key = match.group(1) or match.group(2)
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        relative_end = match.end() - line_start
        classification = (
            "PLATFORM_MANAGED"
            if key in PLATFORM_MANAGED_KEYS
            else (
                "OPTIONAL_SAFE_DEFAULT"
                if _is_optional_safe_default(line, relative_end)
                else "REQUIRED_NO_DEFAULT"
            )
        )
        reads.append(
            EnvRead(
                module=module,
                line=_line_number(text, match.start()),
                key=key,
                classification=classification,
                expression=line.strip(),
            )
        )
        literal_spans.append(match.span())

    for match in ENV_BASE_PATTERN.finditer(text):
        if any(start <= match.start() < end for start, end in literal_spans):
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = len(text)
        reads.append(
            EnvRead(
                module=module,
                line=_line_number(text, match.start()),
                key=None,
                classification="UNKNOWN",
                expression=text[line_start:line_end].strip(),
            )
        )

    return tuple(reads)


def _secret_bindings(modules: Iterable[Path]) -> tuple[str, ...]:
    names: set[str] = set()
    for module in modules:
        text = module.read_text(encoding="utf-8", errors="strict")
        names.update(SECRET_BINDING_PATTERN.findall(text))
    return tuple(sorted(names))


def analyze_source_env_contract(
    *,
    source_dir: Path,
    entry_relative_path: str,
    export_name: str,
) -> SourceEnvContract:
    """Analyze one exported function's complete local module-load closure."""

    source_root = source_dir.resolve()
    entry = (source_root / entry_relative_path).resolve()
    try:
        entry.relative_to(source_root)
    except ValueError as error:
        raise SourceContractError("source entry must remain under functions/src") from error

    entry_text = entry.read_text(encoding="utf-8", errors="strict")
    export_pattern = re.compile(
        rf"\bexport\s+(?:const|function|async\s+function)\s+{re.escape(export_name)}\b"
    )
    if not export_pattern.search(entry_text):
        raise SourceContractError(
            f"export {export_name!r} was not found in {entry_relative_path}"
        )

    modules = resolve_import_closure(entry)
    reads = tuple(read for module in modules for read in _env_reads(module))
    secrets = _secret_bindings(modules)
    return SourceEnvContract(
        entry_module=entry,
        modules=modules,
        env_reads=reads,
        secret_bindings=secrets,
    )


def all_source_env_keys(source_dir: Path) -> frozenset[str]:
    """Return literal environment names anywhere in production TypeScript."""

    keys: set[str] = set()
    for path in sorted(source_dir.rglob("*.ts")):
        if path.name.endswith(".test.ts") or "__tests__" in path.parts:
            continue
        for read in _env_reads(path):
            if read.key is not None:
                keys.add(read.key)
    return frozenset(keys)
