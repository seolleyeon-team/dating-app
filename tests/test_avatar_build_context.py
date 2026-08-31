"""Static build-context regression for the canonical avatar worker image.

Guards against the historical failure class where source tests pass but a
runtime module is missing from the container image (ModuleNotFoundError after
deploy). No image is built here; this only checks the build recipe and the
presence of every canonical runtime module inside the copied context.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AG = REPO_ROOT / "lib" / "ai_recommend_model" / "avatar_generation"
DOCKERFILE = AG / "Dockerfile"

REQUIRED_RUNTIME_FILES = [
    "worker.py",
    "worker_service.py",
    "qa.py",
    "qa_signals.py",
    "qa_runtime.py",
    "qa_contract.py",
    "qa_preflight.py",
    "qa_diagnostics.py",
    "preview_policy.py",
    "trait_policy.py",
    "unique_mark_policy.py",
    "avatar_prompt_contract.py",
    "analysis/watermark.py",
    "analysis/visual_risk.py",
    "model_adapters/azure_contracts.py",
    "model_adapters/azure_gpt_image_2.py",
    "model_adapters/azure_rate_limit.py",
    "model_adapters/azure_transport.py",
    "artifacts/avatar_qa_calibration_v1.json",
]


def test_dockerfile_copies_the_whole_model_tree():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY lib/ai_recommend_model /app" in text


def test_dockerfile_defaults_to_canonical_azure_mode():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "AVATAR_WORKER_MODE=azure_gpt_image_2" in text


def test_every_canonical_runtime_module_exists_in_build_context():
    missing = [rel for rel in REQUIRED_RUNTIME_FILES if not (AG / rel).is_file()]
    assert missing == []


# ---------------------------------------------------------------------------
# .dockerignore build-context contract
#
# The repo-root .dockerignore is a recsys-first allowlist ("*" then "!...").
# The avatar worker builds from the SAME repo-root context, so every COPY
# source in the avatar Dockerfile must survive that filter. Cloud Build
# 4cd9b850 (2026-08-30) failed exactly here: requirements_avatar_worker.txt
# and the whole avatar_generation subtree were excluded from the context.
#
# The matcher below follows Docker/Moby .dockerignore semantics for the
# pattern shapes used in this file: patterns match the path or any parent
# directory of the path, later patterns win, and a leading "!" re-includes.
# ---------------------------------------------------------------------------

import fnmatch

DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def _dockerignore_patterns():
    patterns = []
    for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate:
            line = line[1:]
        patterns.append((negate, line.strip("/")))
    return patterns


def _pattern_matches(pattern: str, path: str) -> bool:
    # A pattern matches the path itself or any of its parent directories
    # (Docker treats a matched directory as matching everything below it).
    candidates = [path]
    parts = path.split("/")
    for i in range(1, len(parts)):
        candidates.append("/".join(parts[:i]))
    for candidate in candidates:
        if fnmatch.fnmatchcase(candidate, pattern):
            return True
        # "dir/**" also matches everything strictly below dir.
        if pattern.endswith("/**") and candidate.startswith(pattern[:-3] + "/"):
            return True
    return False


def docker_context_includes(path: str) -> bool:
    included = True
    for negate, pattern in _dockerignore_patterns():
        if _pattern_matches(pattern, path):
            included = negate
    return included


AVATAR_CONTEXT_REQUIRED = [
    "requirements_avatar_worker.txt",
    "lib/ai_recommend_model/avatar_generation/Dockerfile",
    "lib/ai_recommend_model/avatar_generation/worker.py",
    "lib/ai_recommend_model/avatar_generation/worker_service.py",
    "lib/ai_recommend_model/avatar_generation/qa.py",
    "lib/ai_recommend_model/avatar_generation/qa_runtime.py",
    "lib/ai_recommend_model/avatar_generation/preview_policy.py",
    "lib/ai_recommend_model/avatar_generation/trait_policy.py",
    "lib/ai_recommend_model/avatar_generation/unique_mark_policy.py",
    "lib/ai_recommend_model/avatar_generation/avatar_prompt_contract.py",
    "lib/ai_recommend_model/avatar_generation/analysis/watermark.py",
    "lib/ai_recommend_model/avatar_generation/analysis/visual_risk.py",
    "lib/ai_recommend_model/avatar_generation/model_adapters/azure_gpt_image_2.py",
    "lib/ai_recommend_model/avatar_generation/model_adapters/azure_transport.py",
    "lib/ai_recommend_model/avatar_generation/model_adapters/azure_rate_limit.py",
    "lib/ai_recommend_model/avatar_generation/model_adapters/azure_contracts.py",
    "lib/ai_recommend_model/avatar_generation/artifacts/avatar_qa_calibration_v1.json",
    "lib/ai_recommend_model/avatar_generation/calibration_recovery.py",
    "lib/ai_recommend_model/avatar_generation/calibration_service.py",
]

RECSYS_CONTEXT_REQUIRED = [
    "recsys/Dockerfile" ,
    "lib/ai_recommend_model/seolleyeon_rec_common_v3.py",
]

CONTEXT_FORBIDDEN = [
    ".git/config",
    ".env",
    "functions/src/index.ts",
    "docs/avatar-production/avatar-qa-contract.md",
    "festival_web/pubspec.yaml",
    "android/app/build.gradle",
    "test/widget_test.dart",
    "rules_tests/helpers.mjs",
]


def test_dockerignore_keeps_every_avatar_copy_source_in_context():
    missing = [p for p in AVATAR_CONTEXT_REQUIRED if not docker_context_includes(p)]
    assert missing == [], f"excluded from docker build context: {missing}"


def test_dockerignore_keeps_recsys_contract_and_excludes_unrelated_trees():
    recsys_missing = [
        p for p in RECSYS_CONTEXT_REQUIRED if not docker_context_includes(p)
    ]
    assert recsys_missing == []
    leaked = [p for p in CONTEXT_FORBIDDEN if docker_context_includes(p)]
    assert leaked == [], f"unexpectedly included in docker build context: {leaked}"
