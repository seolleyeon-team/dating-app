"""Cross-region avatar build guard.

The avatar worker runs on Cloud Run in ``asia-southeast1`` because that is the
only region where this project holds L4 GPU quota. When a build config pushes
the (multi-GB) worker image to the Seoul Artifact Registry instead, every
Cloud Run cold start pulls it back across regions and the transfer is billed.

``tests/test_avatar_retired_generation_paths.py`` already pins the canonical
root config. This module widens that to *every* tracked Cloud Build config, so
a stale copy cannot reintroduce a Seoul destination for the avatar worker.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path

from repo_source_files import repository_files

REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_REGISTRY_REGION = "asia-southeast1"
CANONICAL_REPOSITORY = "seolleyeon-avatar-repo"
CANONICAL_IMAGE_PREFIX = (
    f"{CANONICAL_REGISTRY_REGION}-docker.pkg.dev/seolleyeon-final/"
    f"{CANONICAL_REPOSITORY}/seolleyeon-avatar-worker"
)

# Only avatar worker destinations are in scope. recs-pipeline and other
# non-avatar artifacts legitimately live in the Seoul repository.
AVATAR_WORKER_IMAGE = re.compile(
    r"(?P<region>[a-z0-9-]+)-docker\.pkg\.dev/"
    r"(?P<project>[a-z0-9-]+)/"
    r"(?P<repository>[a-z0-9-]+)/"
    r"seolleyeon-avatar-worker"
)


def _tracked_cloudbuild_configs() -> list[Path]:
    files = repository_files(REPO_ROOT)
    if files is None:
        return sorted(REPO_ROOT.glob("**/cloudbuild*.yaml"))
    return [path for path in files if fnmatch(path.name, "cloudbuild*.yaml")]


def _avatar_worker_destinations() -> list[tuple[Path, re.Match[str]]]:
    found: list[tuple[Path, re.Match[str]]] = []
    for config in _tracked_cloudbuild_configs():
        text = config.read_text(encoding="utf-8")
        for match in AVATAR_WORKER_IMAGE.finditer(text):
            found.append((config, match))
    return found


def test_at_least_one_avatar_worker_build_config_is_discovered():
    """Guard the guard: a rename must not silently make this test vacuous."""
    destinations = _avatar_worker_destinations()
    assert destinations, "no avatar worker Cloud Build destination found"
    configs = {config.name for config, _ in destinations}
    assert "cloudbuild.avatar-worker.yaml" in configs


def test_no_cloud_build_config_pushes_the_avatar_worker_outside_singapore():
    violations = []
    for config, match in _avatar_worker_destinations():
        if match.group("region") != CANONICAL_REGISTRY_REGION:
            violations.append(
                f"{config.relative_to(REPO_ROOT).as_posix()}: region "
                f"{match.group('region')!r} != {CANONICAL_REGISTRY_REGION!r}"
            )
        if match.group("repository") != CANONICAL_REPOSITORY:
            violations.append(
                f"{config.relative_to(REPO_ROOT).as_posix()}: repository "
                f"{match.group('repository')!r} != {CANONICAL_REPOSITORY!r}"
            )
    assert not violations, (
        "avatar worker image would be pushed outside the Cloud Run region, "
        "which bills a cross-region pull on every cold start:\n  "
        + "\n  ".join(violations)
    )


def test_canonical_root_config_uses_the_canonical_destination():
    text = (REPO_ROOT / "cloudbuild.avatar-worker.yaml").read_text(encoding="utf-8")
    assert CANONICAL_IMAGE_PREFIX in text


def test_operator_setup_script_defaults_to_the_canonical_registry():
    """The PowerShell entrypoint must not rely on the operator passing -Repository."""
    text = (REPO_ROOT / "scripts" / "staging_avatar_live_setup.ps1").read_text(
        encoding="utf-8"
    )
    assert f'$ArtifactRegistryRegion = "{CANONICAL_REGISTRY_REGION}"' in text
    assert f'$Repository = "{CANONICAL_REPOSITORY}"' in text
    assert f'$WorkerRegion = "{CANONICAL_REGISTRY_REGION}"' in text


def test_operator_setup_script_pins_the_build_to_the_canonical_region():
    """A global Cloud Build runs in the US and ships ~5GB across continents.

    Build execution, source staging, registry and runtime must all sit in
    ``asia-southeast1``; relying on the operator to remember ``--region`` is
    exactly how the cross-region bill came back last time.

    Updated 2026-09-11. This assertion used to read the inline gcloud command in
    the setup script. It passed on 2026-09-10 while a production build still
    staged source in the US multi-region bucket, because the operator did not
    run the script -- the command was reconstructed by hand. Guarding the file
    could never catch that, so the recipe moved into
    ``scripts/avatar_build_contract.py`` and the invariant is asserted there,
    where every sanctioned invocation has to go through it.
    """
    setup = (REPO_ROOT / "scripts" / "staging_avatar_live_setup.ps1").read_text(
        encoding="utf-8"
    )
    assert f'$BuildRegion = "{CANONICAL_REGISTRY_REGION}"' in setup
    # The setup script must delegate rather than carry a second copy of the
    # recipe; two copies is how they drifted apart.
    assert "build_avatar_worker.ps1" in setup
    assert "gcloud builds submit" not in setup

    contract = (REPO_ROOT / "scripts" / "avatar_build_contract.py").read_text(
        encoding="utf-8"
    )
    assert f'BUILD_REGION = "{CANONICAL_REGISTRY_REGION}"' in contract
    # Regional execution alone still stages source in the US multi-region
    # bucket; this is the supported flag that moves staging into the region.
    assert 'BUCKET_BEHAVIOR_FLAG = "--default-buckets-behavior"' in contract
    assert 'BUCKET_BEHAVIOR = "REGIONAL_USER_OWNED_BUCKET"' in contract
