#!/usr/bin/env python3
"""Refuse a Functions deploy that would drop environment variables.

`firebase deploy` replaces a function's environment with whatever the env file
contains. A key that is live but missing from the file is silently deleted. On
2026-09-08 that removed `JOB_QUEUE_MODE`, `TASK_INVOKER_SERVICE_ACCOUNT` and 17
other variables from five production functions in a single command.

The check that missed it compared the candidate deploy against the same
incomplete local file it came from - a circular comparison that can only ever
agree with itself. The authority here is the environment of the revision that
is actually serving traffic, plus the variables the source code reads.

Usage:
    python scripts/functions_env_regression_guard.py \\
        --project seolleyeon-final --region asia-northeast3 \\
        --env-file functions/.env.seolleyeon-final \\
        --function getCurrentAvatarGenerationStatus [--function ...] \\
        [--allow-remove-key KEY] [--allow-add-key KEY] [--allow-change-key KEY] \\
        [--source-dir functions/src]

An intentional change is declared one key and one operation at a time. A
declaration authorises exactly the key it names, exactly the operation it
names, and nothing else the diff happens to contain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

# Injected by Cloud Run / the Functions framework. Never carried in an env file.
PLATFORM_MANAGED_KEYS = frozenset({
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
})

# Values that must never be printed, even when they differ. A UID allowlist is
# in here with the credentials: AVATAR_UPLOAD_ALLOWED_UIDS carries real account
# identifiers, and a diff of it would put them in a deploy log.
SECRET_KEY_PATTERN = re.compile(
    r"(SECRET|TOKEN|PASSWORD|PRIVATE_KEY|API_KEY|CREDENTIAL|SIGNING"
    r"|(?:^|_)UIDS?(?:_|$))",
    re.IGNORECASE,
)

# What a shell may export and an env file may carry. Anything else - a glob,
# a prefix, a regex - is a declaration nobody can have meant literally.
ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

ENV_READ_PATTERN = re.compile(r"process\.env(?:\.([A-Z][A-Z0-9_]*)|\[\"([A-Z][A-Z0-9_]*)\"\])")


class GuardError(RuntimeError):
    """The live environment could not be established. Never fail open on this."""


@dataclass
class EnvFinding:
    function: str
    key: str
    kind: str  # removed | changed | added | missing_required | unused_authorization
    detail: str = ""

    def render(self) -> str:
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.function}: {self.kind} {self.key}{suffix}"


@dataclass
class EnvCheckResult:
    findings: list[EnvFinding] = field(default_factory=list)
    checked_functions: list[str] = field(default_factory=list)
    authorized: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


def is_secret_key(key: str) -> bool:
    return bool(SECRET_KEY_PATTERN.search(key))


def redact(key: str, value: str) -> str:
    if is_secret_key(key):
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        return f"<secret sha256:{digest}>"
    return repr(value)


def parse_env_file(text: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key] = value
    return env


def required_env_keys_from_source(source_dir: Path) -> set[str]:
    """Environment variables the deployed code actually reads."""
    keys: set[str] = set()
    for path in sorted(source_dir.rglob("*.ts")):
        if path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for direct, bracketed in ENV_READ_PATTERN.findall(text):
            keys.add(direct or bracketed)
    return keys - set(PLATFORM_MANAGED_KEYS)


def validate_authorizations(flag: str, keys: Iterable[str]) -> set[str]:
    """Exact, case-sensitive variable names. No globs, prefixes or patterns."""
    seen: set[str] = set()
    for key in keys:
        if not ENV_KEY_PATTERN.match(key):
            raise GuardError(
                f"{flag} {key!r} does not name an environment variable. "
                "Declarations are exact names; a pattern would authorise keys "
                "nobody looked at."
            )
        if key in PLATFORM_MANAGED_KEYS:
            raise GuardError(
                f"{flag} {key} is injected by Cloud Run and never carried in "
                "an env file. A deploy cannot add, drop or change it."
            )
        if key in seen:
            raise GuardError(f"{flag} {key} is declared more than once")
        seen.add(key)
    return seen


def plan_functions_env_check(
    *,
    deployed: Mapping[str, Mapping[str, str]],
    candidate: Mapping[str, str],
    required_from_source: Iterable[str] = (),
    allowed_removals: Iterable[str] = (),
    allowed_additions: Iterable[str] = (),
    allowed_changes: Iterable[str] = (),
) -> EnvCheckResult:
    """Compare each function's live environment against the candidate deploy.

    Pure: no gcloud, no filesystem. The caller supplies the live environments.
    """
    removals = validate_authorizations("--allow-remove-key", allowed_removals)
    additions = validate_authorizations("--allow-add-key", allowed_additions)
    changes = validate_authorizations("--allow-change-key", allowed_changes)
    for left, right, declared_left, declared_right in (
        ("--allow-remove-key", "--allow-add-key", removals, additions),
        ("--allow-remove-key", "--allow-change-key", removals, changes),
        ("--allow-add-key", "--allow-change-key", additions, changes),
    ):
        both = sorted(declared_left & declared_right)
        if both:
            raise GuardError(
                f"{left} and {right} both declare {', '.join(both)}. "
                "One key, one operation - a deploy cannot do both."
            )

    required = set(required_from_source)
    result = EnvCheckResult()
    # What the diff actually contains, so a declaration matching nothing can be
    # reported instead of quietly ignored.
    observed: dict[str, set[str]] = {"removed": set(), "added": set(), "changed": set()}

    for function in sorted(deployed):
        result.checked_functions.append(function)
        live = {
            key: value
            for key, value in deployed[function].items()
            if key not in PLATFORM_MANAGED_KEYS
        }
        for key in sorted(live):
            if key not in candidate:
                observed["removed"].add(key)
                if key not in removals:
                    result.findings.append(EnvFinding(
                        function, key, "removed",
                        "live on the serving revision but absent from the candidate env",
                    ))
            elif candidate[key] != live[key]:
                # Exact string identity, never normalised. NFC and NFD look
                # alike and are not; folding either into the other changes what
                # a token, signature or encoded payload means.
                observed["changed"].add(key)
                if key not in changes:
                    result.findings.append(EnvFinding(
                        function, key, "changed",
                        f"{redact(key, live[key])} -> {redact(key, candidate[key])}",
                    ))
        # An added variable is a behaviour change too. One of these re-enabled
        # a closed-beta upload allowlist on the onboarding entry point while
        # the app sat in store review: every non-listed user, the reviewer
        # included, would have been refused.
        for key in sorted(set(candidate) - set(live)):
            observed["added"].add(key)
            if key not in additions:
                result.findings.append(EnvFinding(
                    function, key, "added",
                    "absent from the serving revision but present in the candidate env",
                ))
        # A variable the code reads and the platform does not inject must be
        # present somewhere; losing it is how a guard turns into a silent
        # fallback.
        for key in sorted(required & set(live) - set(candidate) - removals):
            result.findings.append(EnvFinding(
                function, key, "missing_required",
                "read by functions/src but absent from the candidate env",
            ))

    # A declaration nothing matched is an operator error - a typo, a stale
    # intent, the wrong function named - and it is cheaper to catch here than
    # after the deploy.
    for flag, declared, operation in (
        ("--allow-remove-key", removals, "removed"),
        ("--allow-add-key", additions, "added"),
        ("--allow-change-key", changes, "changed"),
    ):
        for key in sorted(declared):
            if key in observed[operation]:
                result.authorized.append(f"{operation} {key} ({flag})")
            else:
                result.findings.append(EnvFinding(
                    "(declared)", key, "unused_authorization",
                    f"{flag} {key} was declared, but no checked function has "
                    f"that key {operation}",
                ))
    return result


def print_report(
    result: EnvCheckResult, deployed: Mapping[str, Mapping[str, str]]
) -> None:
    for function in result.checked_functions:
        print(f"checked {function}: {len(deployed[function])} live variables")
    for line in result.authorized:
        print(f"authorized {line}")
    if result.ok:
        print("ENV REGRESSION GUARD: PASS (nothing undeclared is dropped or altered)")
        return
    print("ENV REGRESSION GUARD: FAIL")
    for finding in result.findings:
        print(f"  {finding.render()}")
    print(
        "\nDeploying now would change these variables. Restore them in the env "
        "file, or declare each intended change on its own: --allow-remove-key "
        "KEY, --allow-add-key KEY, --allow-change-key KEY."
    )


# gcloud is itself a Python program. When its stdout is a pipe it encodes with
# the console code page, and on Windows every character that code page cannot
# represent silently becomes "?" - a Hangul sender name arrived as
# "??? <noreply@...>" and the guard reported a change that had not happened.
# The parent decoding as UTF-8 cannot see this: "???" is valid ASCII. So pin
# the child's output encoding here instead of inheriting the operator's shell,
# which is what made `PYTHONIOENCODING=utf-8 python ...` look like a fix.
GCLOUD_CHILD_ENCODING = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def gcloud_child_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env.update(GCLOUD_CHILD_ENCODING)
    return env


def run_gcloud_json(args: Sequence[str], *, what: str) -> object:
    """Run gcloud and parse its JSON. Every failure mode raises, none returns."""
    executable = shutil.which("gcloud")
    if executable is None:
        raise GuardError(f"cannot describe {what}: gcloud is not on PATH")
    # No shell: cmd.exe between the guard and gcloud adds nothing but another
    # locale-dependent layer. shutil.which resolves gcloud.cmd on Windows,
    # which is the only reason shell=True was needed.
    described = subprocess.run(
        [executable, *args],
        capture_output=True,
        shell=False,
        env=gcloud_child_env(),
    )
    if described.returncode != 0:
        # stderr is diagnostic only - it never feeds a comparison, so an
        # escaped rendering is enough and cannot hide a decode problem.
        detail = described.stderr.decode("utf-8", errors="backslashreplace").strip()
        raise GuardError(
            f"cannot describe {what}: gcloud exited {described.returncode}: {detail[:300]}"
        )
    try:
        text = described.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        # Strict on purpose. errors="replace" here is exactly the corruption
        # this function exists to prevent, one layer further down.
        raise GuardError(
            f"cannot describe {what}: gcloud stdout is not valid utf-8 ({error})"
        ) from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise GuardError(
            f"cannot describe {what}: gcloud did not return JSON ({error})"
        ) from error


def deployed_env_for(function: str, project: str, region: str) -> dict[str, str]:
    service = function.lower()
    described = run_gcloud_json(
        [
            "run", "services", "describe", service,
            f"--project={project}", f"--region={region}", "--format=json",
        ],
        what=service,
    )
    try:
        containers = described["spec"]["template"]["spec"]["containers"]
        entries = containers[0].get("env", [])
    except (AttributeError, IndexError, KeyError, TypeError) as error:
        raise GuardError(
            f"cannot describe {service}: unexpected gcloud JSON shape ({error})"
        ) from error
    # An entry with valueFrom (a secret reference) carries no value. Reading it
    # as "" would report every secret-backed variable as changed.
    return {item["name"]: item["value"] for item in entries if "value" in item}


class _RetiredBroadFlag(argparse.Action):
    """`--allow-removal KEY` waived every check for that key, a value change
    included, so declaring a removal quietly signed off a substitution nobody
    had asked for. It is refused by name rather than removed, so an operator
    reaching for it is told what replaced it."""

    def __call__(self, parser, namespace, values, option_string=None):
        parser.error(
            f"{option_string} waived every check for that key, including a "
            "value change it never declared. Use --allow-remove-key KEY, "
            "--allow-add-key KEY or --allow-change-key KEY - one key, one "
            "operation."
        )


def main(argv: Sequence[str] | None = None) -> int:
    # A finding carries whatever the live environment holds, and the console
    # cannot always represent it - a Windows code page killed the report
    # half-printed, leaving a traceback where the findings should have been.
    # Escape on the way out. This is display only: every comparison is already
    # decided by the time anything is printed, so nothing here can soften a
    # verdict the way a lenient *input* decode would.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="backslashreplace")
    try:
        return _run(argv)
    except GuardError as error:
        print("ENV REGRESSION GUARD: FAIL")
        print(f"  {error}")
        return 1


def _run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--function", action="append", required=True, dest="functions")
    parser.add_argument(
        "--allow-remove-key", action="append", default=[], dest="allowed_removals",
        metavar="KEY", help="authorise dropping exactly this variable",
    )
    parser.add_argument(
        "--allow-add-key", action="append", default=[], dest="allowed_additions",
        metavar="KEY", help="authorise introducing exactly this variable",
    )
    parser.add_argument(
        "--allow-change-key", action="append", default=[], dest="allowed_changes",
        metavar="KEY", help="authorise changing exactly this variable's value",
    )
    for retired in ("--allow-removal", "--allow-addition"):
        parser.add_argument(
            retired, action=_RetiredBroadFlag, nargs="?", help=argparse.SUPPRESS
        )
    parser.add_argument("--source-dir", default="functions/src")
    args = parser.parse_args(argv)

    candidate = parse_env_file(Path(args.env_file).read_text(encoding="utf-8"))
    source_dir = Path(args.source_dir)
    required = required_env_keys_from_source(source_dir) if source_dir.is_dir() else set()
    deployed = {
        function: deployed_env_for(function, args.project, args.region)
        for function in args.functions
    }

    result = plan_functions_env_check(
        deployed=deployed,
        candidate=candidate,
        required_from_source=required,
        allowed_removals=args.allowed_removals,
        allowed_additions=args.allowed_additions,
        allowed_changes=args.allowed_changes,
    )
    print_report(result, deployed)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
